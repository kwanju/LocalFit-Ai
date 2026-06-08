"""WebSocket /ws/voice — Pipecat pipeline mount (ADR-009/011).

Query param: ?mode=S2S|C2S|C2C|S2C  (default: C2C)

Phase 4: real STT (faster-whisper) + silero VAD wired in for S2S/S2C.
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

from app.config import AppConfig
from app.core.confirm_slot import ConfirmSlot
from app.core.counting import CompleteEvent
from app.core.counting_cues import set_ordinal
from app.db.engine import create_db_session
from app.db.models import SessionMode as DBSessionMode
from app.db.models import SessionStatus
from app.db.repositories import ExerciseRepository, SessionRepository, SetLogRepository
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
    COUNTING_COMPLETE_FOLLOW_UP_MESSAGE,
    PROACTIVE_OPENER_USER_MESSAGE,
)

router = APIRouter(tags=["ws"])


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
async def ws_voice(websocket: WebSocket, mode: str = "C2C") -> None:
    """Pipecat 4-mode voice pipeline endpoint."""
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
    use_stt = session_mode in (SessionMode.s2s, SessionMode.s2c)
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

    # Pipecat *Service 인스턴스는 단일 파이프라인 lifecycle에 종속이라 매 연결마다
    # 새로 만든다. 무거운 모델은 app.state.tts/stt (client) 안에서 한 번만 로드된 채
    # 재사용된다. 어댑터가 없으면 build_pipeline이 Mock으로 폴백.
    tts_client = getattr(websocket.app.state, "tts", None)
    stt_client = getattr(websocket.app.state, "stt", None) if use_stt else None
    tts_service = build_tts_service(tts_client)
    stt_service = build_stt_service(stt_client) if use_stt else None
    vad_analyzer = _build_vad_analyzer(config) if (config and use_stt) else None

    # ADR-013: shared ConfirmSlot between ConfirmRule + ActionDispatcher.
    slot = ConfirmSlot()

    # Phase-8: wire calendar-aware context builder (ADR-013/020).
    context_adapter: DBCoachContextAdapter | None = None
    if config is not None:
        weeks = getattr(config.coach, "calendar_pattern_weeks", 4)
        context_adapter = DBCoachContextAdapter(calendar_pattern_weeks=weeks)

    llm_processor = (
        StructuredOllamaProcessor(config, context_adapter) if config else None  # type: ignore[arg-type]
    )

    # ADR-014 phase-6: CountingManager + CountingInjectProcessor.
    counting_manager = CountingManager(config.counting) if config else None
    counting_inject = CountingInjectProcessor()
    if counting_manager is not None:
        counting_manager.attach_inject_processor(counting_inject)

    safety = SafetyGuardProcessor(counting_manager=counting_manager)
    dispatcher = ActionDispatcherProcessor(slot, counting_manager=counting_manager)
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

    # Mutable holder for DB session id (set in on_connected).
    _db_session_id: list[int | None] = [None]

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

    @transport.event_handler("on_client_connected")
    async def on_connected(transport: FastAPIWebsocketTransport, ws: WebSocket) -> None:
        logger.info("ws_voice client connected: mode={}", session_mode.value)

        # WorkoutSession 생성 (SetLog 기록에 필요)
        if config is not None:
            try:
                async with create_db_session() as db:
                    db_mode = DBSessionMode(session_mode.value.lower())
                    repo = SessionRepository(db)
                    ws_session = await repo.create(mode=db_mode.value)
                    _db_session_id[0] = ws_session.id
                    logger.info("WorkoutSession created: id={}", ws_session.id)
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
            logger.info("ws_voice: injecting proactive opener (ADR-013 §0)")
            # InputTextRawFrame so the LLM treats it as a user turn (drives the opener).
            await worker.queue_frame(InputTextRawFrame(text=PROACTIVE_OPENER_USER_MESSAGE))

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport: FastAPIWebsocketTransport, ws: WebSocket) -> None:
        logger.info("ws_voice client disconnected: mode={}", session_mode.value)

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
