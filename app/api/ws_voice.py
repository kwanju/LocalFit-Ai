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
from pipecat.frames.frames import OutputTransportMessageFrame, TextFrame
from pipecat.pipeline.worker import PipelineWorker
from pipecat.workers.runner import WorkerRunner

from app.config import AppConfig
from app.core.confirm_slot import ConfirmSlot
from app.core.counting import CompleteEvent
from app.db.engine import create_db_session
from app.db.models import SessionMode as DBSessionMode, SessionStatus
from app.db.repositories import ExerciseRepository, SessionRepository, SetLogRepository
from app.pipecat_services.counting_manager import CountingManager
from app.pipecat_services.json_frame_serializer import JsonFrameSerializer
from app.pipecat_services.ollama_service import StructuredOllamaProcessor
from app.pipecat_services.pipeline_builder import SessionMode, build_pipeline
from app.pipecat_services.processors.action_dispatcher import ActionDispatcherProcessor
from app.pipecat_services.processors.confirm_rule import ConfirmRuleProcessor
from app.pipecat_services.processors.counting_inject import CountingInjectProcessor
from app.pipecat_services.processors.safety_guard import SafetyGuardProcessor
from app.pipecat_services.processors.ui_control import UIControlProcessor
from app.prompts.coaching import (
    COUNTING_COMPLETE_FOLLOW_UP_MESSAGE,
    PROACTIVE_OPENER_USER_MESSAGE,
)
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport

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

    # Real services come from lifespan; absent ones fall back to mocks via build_pipeline.
    tts_service = getattr(websocket.app.state, "tts_service", None)
    stt_service = getattr(websocket.app.state, "stt_service", None) if use_stt else None
    vad_analyzer = _build_vad_analyzer(config) if (config and use_stt) else None

    # ADR-013: shared ConfirmSlot between ConfirmRule + ActionDispatcher.
    slot = ConfirmSlot()
    llm_processor = StructuredOllamaProcessor(config) if config else None

    # ADR-014 phase-6: CountingManager + CountingInjectProcessor.
    counting_manager = CountingManager(config.counting) if config else None
    counting_inject = CountingInjectProcessor()
    if counting_manager is not None:
        counting_manager.attach_inject_processor(counting_inject)

    safety = SafetyGuardProcessor(counting_manager=counting_manager)
    confirm = ConfirmRuleProcessor(slot)
    dispatcher = ActionDispatcherProcessor(slot, counting_manager=counting_manager)

    # Phase-7: UIControlProcessor handles control messages from the browser.
    ui_control = UIControlProcessor(counting_manager=counting_manager)

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
    )
    worker = PipelineWorker(pipeline, enable_rtvi=False)
    runner = WorkerRunner()

    proactive_enabled = bool(
        config and config.coach.proactive_opener and llm_processor is not None
    )

    # Mutable holder for DB session id (set in on_connected).
    _db_session_id: list[int | None] = [None]

    # Wire counting complete → SetLog + auto follow-up (ADR-014 §카운팅 완료 처리)
    if counting_manager is not None:
        async def on_counting_complete(event: CompleteEvent) -> None:
            # 1. SetLog 기록
            if _db_session_id[0] is not None:
                try:
                    async with create_db_session() as db:
                        ex_repo = ExerciseRepository(db)
                        ex = await ex_repo.get_by_name(event.exercise_name)
                        if ex and ex.id is not None:
                            set_repo = SetLogRepository(db)
                            reps = event.reps_completed if event.duration_sec is None else None
                            dur = (
                                int(event.duration_sec) if event.duration_sec is not None else None
                            )
                            await set_repo.create(
                                session_id=_db_session_id[0],
                                exercise_id=ex.id,
                                set_number=1,
                                reps_completed=reps,
                                duration_sec=dur,
                            )
                            logger.info(
                                "SetLog recorded: exercise={} reps={} dur={}",
                                event.exercise_name, reps, dur,
                            )
                except Exception as e:  # noqa: BLE001
                    logger.error("SetLog write failed: {}", e)

            # 2. 자동 follow-up LLM 호출 (ADR-013 §0 능동 주도 원칙)
            await worker.queue_frame(TextFrame(text=COUNTING_COMPLETE_FOLLOW_UP_MESSAGE))
            logger.info("ws_voice: injected counting follow-up message")

        counting_manager.on_session_complete = on_counting_complete

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
            await worker.queue_frame(TextFrame(text=PROACTIVE_OPENER_USER_MESSAGE))

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport: FastAPIWebsocketTransport, ws: WebSocket) -> None:
        logger.info("ws_voice client disconnected: mode={}", session_mode.value)

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

        await runner.cancel()

    try:
        await runner.run(worker)
    except WebSocketDisconnect:
        logger.info("ws_voice WebSocket disconnected during run")
    except Exception as e:
        logger.error("ws_voice pipeline error: {}", e)
        raise
