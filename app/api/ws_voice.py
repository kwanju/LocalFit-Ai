"""WebSocket /ws/voice — Pipecat pipeline mount (ADR-009/011).

Query param: ?mode=S2S|C2S|C2C  (default: C2C)

Phase 4: real STT (faster-whisper) + silero VAD wired in for S2S.
Phase 5: SafetyGuard / ConfirmRule / StructuredOllama / ActionDispatcher
processors compose the active-coach pipeline (ADR-013). The proactive opener
runs once per session when ``config.coach.proactive_opener`` is true.
Phase 6: CountingManager + CountingInjectProcessor wired; WorkoutSession
created on connect; SetLog recorded on counting complete; auto follow-up LLM
call injected via worker.queue_frame (ADR-014).
Phase 7: JsonFrameSerializer replaces ProtobufFrameSerializer so the browser
needs no protobuf library.  UIControlProcessor handles UI control messages.
Session lifecycle events (session_started / session_ended / vad) are sent via
OutputTransportMessageFrame.
"""

import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADAnalyzer, VADParams
from pipecat.frames.frames import (
    InputTextRawFrame,
    OutputTransportMessageFrame,
    TTSSpeakFrame,
)
from pipecat.pipeline.worker import PipelineWorker
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from pipecat.workers.runner import WorkerRunner

from app.adapters.model_manager import ModelLoadError
from app.config import AppConfig
from app.core.coach_context import is_first_session
from app.core.confirm_slot import ConfirmSlot
from app.core.counting import CompleteEvent
from app.core.counting_cues import set_ordinal
from app.core.plan import PlanGoalSpec
from app.db.engine import create_db_session
from app.db.models import SessionMode as DBSessionMode
from app.db.models import SessionStatus
from app.db.repositories import (
    ConditionRepository,
    ExerciseRepository,
    MemoryRepository,
    PlanRepository,
    SessionRepository,
    SetLogRepository,
)
from app.pipecat_services.coach_context_adapter import DBCoachContextAdapter
from app.pipecat_services.counting_manager import CountingManager
from app.pipecat_services.json_frame_serializer import JsonFrameSerializer
from app.pipecat_services.ollama_service import StructuredOllamaProcessor
from app.pipecat_services.pipeline_builder import SessionMode, build_pipeline
from app.pipecat_services.processors.action_dispatcher import ActionDispatcherProcessor
from app.pipecat_services.processors.confirm_rule import ConfirmRuleProcessor
from app.pipecat_services.processors.counting_inject import CountingInjectProcessor
from app.pipecat_services.processors.safety_guard import SafetyGuardProcessor
from app.pipecat_services.processors.ui_control import UIControlProcessor
from app.pipecat_services.processors.ui_text_broadcast import UITextBroadcastProcessor
from app.pipecat_services.service_factory import build_stt_service, build_tts_service
from app.prompts.coaching import (
    CALENDAR_SYNC_DONE_FOLLOW_UP_MESSAGE,
    CALENDAR_SYNC_NONE_FOLLOW_UP_MESSAGE,
    COUNTING_COMPLETE_FOLLOW_UP_MESSAGE,
    FIRST_SESSION_OPENER_USER_MESSAGE,
    PLAN_ADJUST_DONE_FOLLOW_UP_MESSAGE,
    PLAN_ADJUST_NO_PLAN_FOLLOW_UP_MESSAGE,
    PROACTIVE_OPENER_USER_MESSAGE,
)

router = APIRouter(tags=["ws"])

# 모드 전환 재연결로 인정하는 최대 공백(초). 이보다 오래된 carry 는 무시한다 — 오래
# 전 끊긴 세션을 엉뚱하게 이어받지 않도록(단일 사용자, ADR-032 §구현 연계).
_RESUME_MAX_GAP_SEC = 60.0


def _build_vad_analyzer(config: AppConfig) -> VADAnalyzer:
    vad_cfg = config.vad
    params = VADParams(
        confidence=vad_cfg.threshold,
        stop_secs=vad_cfg.min_silence_ms / 1000.0,
    )
    logger.info(
        "VAD analyzer: silero confidence={} stop_secs={:.2f} sr={} smart_turn={}",
        vad_cfg.threshold,
        params.stop_secs,
        vad_cfg.sample_rate,
        vad_cfg.use_smart_turn,
    )
    return SileroVADAnalyzer(sample_rate=vad_cfg.sample_rate, params=params)


@router.websocket("/ws/voice")
async def ws_voice(websocket: WebSocket, mode: str = "C2C", resume: int = 0) -> None:
    """Pipecat 3-mode voice pipeline endpoint (C2C/C2S/S2S — ADR-021).

    ``resume=1`` (모드 전환 시 프론트가 붙임): 직전 세션의 대화 이력·세션을 이어받아
    opener 를 생략한다(ADR-032 §구현 연계, 세션 연속성). 신규 시작은 resume=0.
    """
    try:
        session_mode = SessionMode(mode.upper())
    except ValueError:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": f"알 수 없는 모드입니다: {mode}"})
        await websocket.close()
        return

    # Pipecat 1.3.0 removed the implicit websocket.accept() from the transport;
    # the caller is now responsible for accepting before the transport starts.
    await websocket.accept()

    config: AppConfig | None = getattr(websocket.app.state, "config", None)
    use_stt = session_mode is SessionMode.s2s
    audio_in_sr = config.vad.sample_rate if (config and use_stt) else 16000

    transport = FastAPIWebsocketTransport(
        websocket,
        FastAPIWebsocketParams(
            serializer=JsonFrameSerializer(),
            add_wav_header=False,
            audio_in_enabled=use_stt,
            audio_in_sample_rate=audio_in_sr,
            audio_out_enabled=session_mode in (SessionMode.s2s, SessionMode.c2s),
        ),
    )

    # ADR-030: heavy models are loaded on demand per session. Trigger the load
    # (no-op if app-open prewarm already loaded), streaming a "코치 준비 중" notice
    # while we wait so the cold start is visible, not a frozen UI. VRAM 부족이면
    # 안내 후 닫는다 (안 행복한 경로).
    manager = getattr(websocket.app.state, "models", None)
    session_counted = False
    if manager is not None:
        if not manager.loaded:
            await websocket.send_json({"type": "coach_preparing"})
        try:
            await manager.load()
        except ModelLoadError as e:
            logger.error("ws_voice: model load failed: {}", e)
            await websocket.send_json({"type": "error", "message": str(e)})
            await websocket.close()
            return
        # 이 세션이 모델을 점유한다(refcount). 겹친 세션이 있으면 한쪽 종료가 다른 쪽
        # 모델을 unload 하지 않게 막는다.
        manager.session_begin()
        session_counted = True

    # Pipecat *Service 인스턴스는 단일 파이프라인 lifecycle에 종속이라 매 연결마다
    # 새로 만든다. 무거운 모델은 ModelManager(client) 안에서 세션 동안 로드된 채
    # 재사용된다. 어댑터가 없으면 build_pipeline이 Mock으로 폴백.
    tts_client = manager.tts if manager is not None else None
    stt_client = (manager.stt if manager is not None else None) if use_stt else None
    tts_service = build_tts_service(tts_client)
    stt_service = build_stt_service(stt_client) if use_stt else None
    vad_analyzer = _build_vad_analyzer(config) if (config and use_stt) else None

    # ADR-013: shared ConfirmSlot between ConfirmRule + ActionDispatcher.
    slot = ConfirmSlot()

    # Phase-8: wire calendar-aware context builder (ADR-013/020).
    context_adapter: DBCoachContextAdapter | None = None
    if config is not None:
        weeks = getattr(config.coach, "calendar_pattern_weeks", 4)
        context_adapter = DBCoachContextAdapter(
            calendar_pattern_weeks=weeks, gcal_config=config.google_calendar
        )

    llm_processor = (
        StructuredOllamaProcessor(config, context_adapter) if config else None  # type: ignore[arg-type]
    )

    # ADR-014 phase-6: CountingManager + CountingInjectProcessor.
    counting_manager = CountingManager(config.counting) if config else None
    counting_inject = CountingInjectProcessor()
    if counting_manager is not None:
        counting_manager.attach_inject_processor(counting_inject)

    # Mutable holder for DB session id (set in on_connected). 콜백들이 현재 세션을
    # 참조해야 하므로 dispatcher 구성보다 먼저 선언한다.
    _db_session_id: list[int | None] = [None]

    # ADR-025 영속 메모리 쓰기 경로 — 액션/안전키워드가 즉시 DB 에 저장(확답 X).
    # SetLog 와 동일하게 콜백마다 새 DB 세션을 연다.
    async def _record_constraint(action) -> None:
        async with create_db_session() as db:
            await MemoryRepository(db).add_constraint(
                action.kind, action.text, severity=action.severity
            )
        logger.info("memory: constraint saved kind={} text={}", action.kind, action.text)

    async def _remember_fact(action) -> None:
        async with create_db_session() as db:
            await MemoryRepository(db).add_fact(action.text, tags=action.tags)
        logger.info("memory: fact saved text={}", action.text)

    # ADR-023 컨디션 기록 — 대화 중 LLM 이 log_condition 을 내면 현재 세션에 저장.
    async def _log_condition(action) -> None:
        async with create_db_session() as db:
            await ConditionRepository(db).create(
                session_id=_db_session_id[0],
                fatigue_level=action.fatigue_level,
                soreness=getattr(action, "soreness", None),
                notes=action.notes,
            )
        logger.info(
            "condition logged: fatigue={} soreness={}",
            action.fatigue_level,
            getattr(action, "soreness", None),
        )

    # ADR-028 첫 체력검증 — 대화로 확인된 자가보고 기준선을 1층에 즉시 저장(확답 게이트는
    # 함께 내는 propose_set 이 운동 *시작* 에만 적용). 종목·지표별 upsert 라 재측정도 갱신.
    async def _set_baseline(action) -> None:
        async with create_db_session() as db:
            repo = MemoryRepository(db)
            for entry in action.entries:
                await repo.set_baseline(
                    entry.exercise, entry.metric, entry.value, note=action.note
                )
        logger.info(
            "baseline set: {}",
            [(e.exercise, e.metric, e.value) for e in action.entries],
        )

    # ADR-024 주간 플랜 — **확답 게이트 통과 후에만** 디스패처가 호출한다(자동 변경 X).
    async def _commit_plan(action) -> None:
        specs = [
            PlanGoalSpec(exercise=g.exercise, target_count=g.target_count, reps=g.reps)
            for g in action.goals
        ]
        async with create_db_session() as db:
            plan = await PlanRepository(db).create_plan(specs, note=action.note)
        logger.info("plan committed: id={} goals={}", plan.id, [s.exercise for s in specs])

    async def _commit_plan_adjustment(action) -> None:
        async with create_db_session() as db:
            repo = PlanRepository(db)
            plan = await repo.get_active()
            applied = False
            if plan is not None and plan.id is not None:
                goal = await repo.adjust_goal(
                    plan.id, action.exercise, action.new_target_count
                )
                applied = goal is not None
        # 무동작이면 사용자가 "조정됐다"고 오인하므로, 결과에 맞는 follow-up 을 코치가
        # 안내하게 한다(활성 플랜·해당 종목 목표가 없으면 먼저 목표 설정 권유).
        if applied:
            logger.info(
                "plan adjusted: exercise={} new_target={}",
                action.exercise, action.new_target_count,
            )
            await worker.queue_frame(
                InputTextRawFrame(text=PLAN_ADJUST_DONE_FOLLOW_UP_MESSAGE)
            )
        else:
            logger.warning(
                "plan adjustment not applied (no active plan/goal): exercise={}",
                action.exercise,
            )
            await worker.queue_frame(
                InputTextRawFrame(text=PLAN_ADJUST_NO_PLAN_FOLLOW_UP_MESSAGE)
            )

    # ADR-022 §9-2 캘린더 등록 — **확답 게이트 통과 후에만** 디스패처가 호출한다(자동
    # 등록 X). 미연동/오프라인이면 created=0 으로 degrade 하고 코칭은 계속(안 행복한 경로).
    async def _commit_calendar_sync(action) -> None:
        created = 0
        if config is not None and config.google_calendar.enabled:
            try:
                from app.pipecat_services.calendar_sync import CalendarSyncService

                result = await CalendarSyncService(config.google_calendar).register_plan_events()
                created = result.created
            except Exception as e:  # noqa: BLE001 — 등록 실패는 안내로 흡수, 코칭 영향 X
                logger.error("calendar register failed: {}", e)
        if created > 0:
            logger.info("calendar sync committed: {} events", created)
            await worker.queue_frame(
                InputTextRawFrame(
                    text=CALENDAR_SYNC_DONE_FOLLOW_UP_MESSAGE.format(count=created)
                )
            )
        else:
            logger.warning("calendar sync committed nothing (no plan or not connected)")
            await worker.queue_frame(
                InputTextRawFrame(text=CALENDAR_SYNC_NONE_FOLLOW_UP_MESSAGE)
            )

    # 말-행동 불일치 안전망(ADR-032): 디스패처가 follow-up 코치 turn 을 요청하면 user
    # 메시지로 큐잉한다(plan-adjust follow-up 과 동일 메커니즘). worker 는 아래에서 만들어
    # 지지만, 이 함수는 파이프라인 가동 후에만 호출되므로 late-binding 으로 안전하다.
    async def _request_followup(message: str) -> None:
        await worker.queue_frame(InputTextRawFrame(text=message))

    safety = SafetyGuardProcessor(
        counting_manager=counting_manager,
        record_constraint=_record_constraint,
    )
    dispatcher = ActionDispatcherProcessor(
        slot,
        counting_manager=counting_manager,
        log_condition=_log_condition,
        record_constraint=_record_constraint,
        remember_fact=_remember_fact,
        commit_plan=_commit_plan,
        commit_plan_adjustment=_commit_plan_adjustment,
        set_baseline=_set_baseline,
        commit_calendar_sync=_commit_calendar_sync,
        request_followup=_request_followup,
    )
    confirm = ConfirmRuleProcessor(slot, dispatcher=dispatcher)

    # Phase-7: UIControlProcessor handles control messages from the browser.
    ui_control = UIControlProcessor(counting_manager=counting_manager)

    # Pipecat 1.3 transports don't forward TextFrames to the wire — mirror them
    # as OutputTransportMessageFrame so the UI receives coach text.
    ui_text_broadcast = UITextBroadcastProcessor()

    pipeline = build_pipeline(
        transport,
        session_mode,
        llm_processor=llm_processor,
        tts_service=tts_service,
        stt_service=stt_service,
        vad_analyzer=vad_analyzer,
        safety_processor=safety,
        confirm_processor=confirm,
        action_dispatcher=dispatcher,
        confirm_slot=slot,
        counting_inject=counting_inject,
        ui_control=ui_control,
        ui_text_broadcast=ui_text_broadcast,
    )
    worker = PipelineWorker(pipeline, enable_rtvi=False)
    runner = WorkerRunner()

    proactive_enabled = bool(
        config and config.coach.proactive_opener and llm_processor is not None
    )

    # Wire counting complete → SetLog (매 세트) + auto follow-up (마지막 세트).
    # 2026-06-07: multi-set 지원으로 SetLog는 set 마다, follow-up LLM은 마지막에만.
    if counting_manager is not None:
        async def on_set_done(
            event: CompleteEvent, set_number: int, total_sets: int
        ) -> None:
            if _db_session_id[0] is None:
                return
            try:
                async with create_db_session() as db:
                    ex_repo = ExerciseRepository(db)
                    ex = await ex_repo.get_by_name(event.exercise_name)
                    if ex and ex.id is not None:
                        set_repo = SetLogRepository(db)
                        reps = event.reps_completed if event.duration_sec is None else None
                        dur = int(event.duration_sec) if event.duration_sec is not None else None
                        await set_repo.create(
                            session_id=_db_session_id[0],
                            exercise_id=ex.id,
                            set_number=set_number,
                            reps_completed=reps,
                            duration_sec=dur,
                        )
                        logger.info(
                            "SetLog recorded: exercise={} set={}/{} reps={} dur={}",
                            event.exercise_name, set_number, total_sets, reps, dur,
                        )
            except Exception as e:  # noqa: BLE001
                logger.error("SetLog write failed: {}", e)

        async def on_session_done(event: CompleteEvent) -> None:
            # ADR-024 진척 추적: 한 종목 운동을 끝내면 활성 플랜의 가장 이른 미완료 칸을
            # 완료 처리한다(목표가 없으면 no-op → 단발 fallback). 자동 변경이 아니라
            # 사용자가 실제로 한 운동의 *기록*이므로 확답 게이트 대상이 아니다.
            try:
                async with create_db_session() as db:
                    repo = PlanRepository(db)
                    plan = await repo.get_active()
                    if plan is not None and plan.id is not None:
                        marked = await repo.mark_day_done(plan.id, event.exercise_name)
                        if marked is not None:
                            logger.info(
                                "plan day done: exercise={} plan={}",
                                event.exercise_name, plan.id,
                            )
            except Exception as e:  # noqa: BLE001 — best-effort, never break follow-up
                logger.error("plan progress update failed: {}", e)

            # 마지막 세트 완료 후 follow-up LLM (다음 운동/휴식/종료 제안).
            # InputTextRawFrame so the LLM treats it as a user turn (drives follow-up).
            # 마지막 세트 완료 후이므로 카운팅 비활성 — GPU 경합 없음.
            await worker.queue_frame(
                InputTextRawFrame(text=COUNTING_COMPLETE_FOLLOW_UP_MESSAGE)
            )
            logger.info("ws_voice: injected counting follow-up message")

        async def on_rest(remaining_sec: int, set_done: int, total_sets: int) -> None:
            # UI 카운트다운 + 음성 안내. 0초는 "휴식 끝", 10초는 "10초 남음", 그 외 시작.
            if remaining_sec == 0:
                # 서수로 발화 — "2/3"이 "삼분의이"로 읽히던 문제 (2026-06-08).
                cue = f"{set_ordinal(set_done + 1)} 세트 시작!"
            elif remaining_sec == 10:
                cue = "10초 남았어요"
            else:
                cue = f"{remaining_sec}초 휴식할게요."
            await worker.queue_frame(OutputTransportMessageFrame(message={
                "type": "rest",
                "remaining_sec": remaining_sec,
                "set_done": set_done,
                "total_sets": total_sets,
            }))
            # TTSSpeakFrame (NOT TextFrame): 휴식 멘트를 즉시 개별 발화. TextFrame이면
            # TTSService 집계 버퍼에 쌓여 휴식 내내 침묵하다 세션 끝에 몰아서 나왔다
            # (2026-06-08 fix). 카운트 큐와 동일한 처리.
            await worker.queue_frame(TTSSpeakFrame(text=cue))

        counting_manager.on_set_complete = on_set_done
        counting_manager.on_session_complete = on_session_done
        counting_manager.on_rest_event = on_rest

    def _take_fresh_carry() -> dict | None:
        """모드 전환(resume=1) 재연결이고 carry 가 신선하면 그것을 소비해 반환. 아니면 None."""
        carry = getattr(websocket.app.state, "session_carry", None)
        if not resume or not isinstance(carry, dict):
            return None
        if time.monotonic() - carry.get("ts", 0.0) > _RESUME_MAX_GAP_SEC:
            return None
        websocket.app.state.session_carry = None  # 한 번만 소비
        return carry

    @transport.event_handler("on_client_connected")
    async def on_connected(transport: FastAPIWebsocketTransport, ws: WebSocket) -> None:
        logger.info("ws_voice client connected: mode={} resume={}", session_mode.value, resume)

        # 모드 전환 재연결(ADR-032 §구현 연계): 직전 세션·대화 이력을 이어받고 opener 생략.
        carry = _take_fresh_carry()
        if carry is not None and carry.get("session_id") is not None and config is not None:
            _db_session_id[0] = carry["session_id"]
            try:
                async with create_db_session() as db:
                    await SessionRepository(db).reactivate(carry["session_id"])
                if llm_processor is not None:
                    llm_processor.restore_history(carry.get("history") or [])
                logger.info(
                    "ws_voice: resumed session {} on mode switch — opener skipped",
                    carry["session_id"],
                )
            except Exception as e:  # noqa: BLE001 — 복원 실패 시 새 세션으로 강등
                logger.error("session resume failed, falling back to fresh session: {}", e)
                carry = None
            if carry is not None:
                await worker.queue_frame(OutputTransportMessageFrame(message={
                    "type": "session_started",
                    "session_id": _db_session_id[0] or 0,
                    "mode": session_mode.value.lower(),
                    "resumed": True,
                }))
                return  # 신규 세션 생성·opener 생략

        # WorkoutSession 생성 (SetLog 기록에 필요)
        if config is not None:
            try:
                async with create_db_session() as db:
                    db_mode = DBSessionMode(session_mode.value.lower())
                    repo = SessionRepository(db)
                    ws_session = await repo.create(mode=db_mode.value)
                    _db_session_id[0] = ws_session.id
                    logger.info("WorkoutSession created: id={}", ws_session.id)
                    # ADR-023: 세션 전 자가보고 체크인을 이 세션에 연결.
                    if ws_session.id is not None:
                        linked = await ConditionRepository(db).link_latest_unlinked(
                            ws_session.id
                        )
                        if linked is not None:
                            logger.info(
                                "condition checkin linked: id={} → session={}",
                                linked.id, ws_session.id,
                            )
            except Exception as e:  # noqa: BLE001
                logger.error("WorkoutSession create failed: {}", e)

        # Phase-7: notify the UI that the session has started.
        session_started_msg = OutputTransportMessageFrame(message={
            "type": "session_started",
            "session_id": _db_session_id[0] or 0,
            "mode": session_mode.value.lower(),
        })
        await worker.queue_frame(session_started_msg)

        if proactive_enabled:
            # ADR-028: 첫 세션이면 능동 운동 제안 대신 대화형 체력검증 인사를 연다.
            opener = PROACTIVE_OPENER_USER_MESSAGE
            if config is not None:
                try:
                    async with create_db_session() as db:
                        if await is_first_session(
                            MemoryRepository(db),
                            SessionRepository(db),
                            SetLogRepository(db),
                            recent_sessions=getattr(
                                config.coach, "context_recent_sessions", 5
                            ),
                        ):
                            opener = FIRST_SESSION_OPENER_USER_MESSAGE
                            logger.info("ws_voice: first session — assessment opener (ADR-028)")
                except Exception as e:  # noqa: BLE001 — best-effort, fall back to normal opener
                    logger.warning("first-session detection failed, normal opener: {}", e)
            logger.info("ws_voice: injecting proactive opener (ADR-013 §0)")
            # InputTextRawFrame so the LLM treats it as a user turn (drives the opener).
            await worker.queue_frame(InputTextRawFrame(text=opener))

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport: FastAPIWebsocketTransport, ws: WebSocket) -> None:
        logger.info("ws_voice client disconnected: mode={}", session_mode.value)

        # 0) 모드 전환 재연결을 위해 대화 이력·세션 id 를 carry 에 저장(history 초기화 전에!).
        #    바로 뒤 resume=1 재연결이 이걸 이어받는다. 신선도(_RESUME_MAX_GAP_SEC)로
        #    오래된 carry 의 오인 복원을 막는다(ADR-032 §구현 연계, 단일 사용자).
        try:
            if llm_processor is not None and _db_session_id[0] is not None:
                websocket.app.state.session_carry = {
                    "history": llm_processor.history,
                    "session_id": _db_session_id[0],
                    "ts": time.monotonic(),
                }
        except Exception as e:  # noqa: BLE001 — carry 저장 실패는 연속성만 잃을 뿐
            logger.warning("session carry save failed: {}", e)

        # 1) LLM/TTS 진행 중인 작업 즉시 무효화. disconnect 후 LLM 응답이 도착해
        #    start_counting 까지 발화하던 문제 차단 (2026-06-07).
        try:
            if llm_processor is not None:
                llm_processor.reset_history()
            slot.clear()
        except Exception as e:  # noqa: BLE001
            logger.error("session cleanup on disconnect failed: {}", e)

        # 카운팅 중이면 정지
        if counting_manager is not None:
            try:
                await counting_manager.stop()
            except Exception as e:  # noqa: BLE001
                logger.error("counting_manager.stop on disconnect failed: {}", e)

        # WorkoutSession 완료 처리
        if _db_session_id[0] is not None and config is not None:
            try:
                async with create_db_session() as db:
                    repo = SessionRepository(db)
                    await repo.end_session(_db_session_id[0], SessionStatus.completed)
            except Exception as e:  # noqa: BLE001
                logger.error("WorkoutSession end failed: {}", e)

        # Phase-7: notify UI so session store resets started=false.
        try:
            await worker.queue_frame(
                OutputTransportMessageFrame(message={"type": "session_ended"})
            )
        except Exception:  # noqa: BLE001 — best-effort, pipeline may already be torn down
            pass

        await runner.cancel()

    try:
        await runner.run(worker)
    except WebSocketDisconnect:
        logger.info("ws_voice WebSocket disconnected during run")
    except Exception as e:
        logger.error("ws_voice pipeline error: {}", e)
        raise
    finally:
        # ADR-030: session ended → unload models, reclaim VRAM (idle ≈ baseline).
        # Guaranteed here (not only in on_client_disconnected) so an abrupt drop
        # still frees VRAM. unload() is idempotent. ★ 겹친 세션 보호: 마지막 세션이
        # 끝날 때만 unload — 안 그러면 한 연결 종료가 다른 활성 연결의 모델을 죽인다.
        if manager is not None and session_counted:
            try:
                if manager.session_end() == 0:
                    await manager.unload()
                else:
                    logger.info("ws_voice: 다른 세션이 활성 — 모델 unload 보류")
            except Exception as e:  # noqa: BLE001 — never mask the original error
                logger.error("ModelManager unload failed: {}", e)
