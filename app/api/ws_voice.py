"""WebSocket /ws/voice — Pipecat pipeline mount (ADR-009/011).

Query param: ?mode=S2S|C2S|C2C|S2C  (default: C2C)

Phase 4: real STT (faster-whisper) + silero VAD wired in for S2S/S2C.
Phase 5: SafetyGuard / ConfirmRule / StructuredOllama / ActionDispatcher
processors compose the active-coach pipeline (ADR-013). The proactive opener
runs once per session when ``config.coach.proactive_opener`` is true.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADAnalyzer, VADParams
from pipecat.frames.frames import TextFrame
from pipecat.pipeline.worker import PipelineWorker
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from pipecat.workers.runner import WorkerRunner

from app.config import AppConfig
from app.core.confirm_slot import ConfirmSlot
from app.pipecat_services.ollama_service import StructuredOllamaProcessor
from app.pipecat_services.pipeline_builder import SessionMode, build_pipeline
from app.pipecat_services.processors.action_dispatcher import ActionDispatcherProcessor
from app.pipecat_services.processors.confirm_rule import ConfirmRuleProcessor
from app.pipecat_services.processors.safety_guard import SafetyGuardProcessor
from app.prompts.coaching import PROACTIVE_OPENER_USER_MESSAGE

router = APIRouter(tags=["ws"])


def _build_vad_analyzer(config: AppConfig) -> VADAnalyzer:
    """Construct SileroVADAnalyzer from `config.vad` (ADR-007)."""
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
            serializer=ProtobufFrameSerializer(),
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
    safety = SafetyGuardProcessor()
    confirm = ConfirmRuleProcessor(slot)
    dispatcher = ActionDispatcherProcessor(slot)

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
    )
    worker = PipelineWorker(pipeline, enable_rtvi=False)
    runner = WorkerRunner()

    proactive_enabled = bool(
        config and config.coach.proactive_opener and llm_processor is not None
    )

    @transport.event_handler("on_client_connected")
    async def on_connected(transport: FastAPIWebsocketTransport, ws: WebSocket) -> None:
        logger.info("ws_voice client connected: mode={}", session_mode.value)
        if proactive_enabled:
            logger.info("ws_voice: injecting proactive opener (ADR-013 §0)")
            await worker.queue_frame(TextFrame(text=PROACTIVE_OPENER_USER_MESSAGE))

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport: FastAPIWebsocketTransport, ws: WebSocket) -> None:
        logger.info("ws_voice client disconnected: mode={}", session_mode.value)
        await runner.cancel()

    try:
        await runner.run(worker)
    except WebSocketDisconnect:
        logger.info("ws_voice WebSocket disconnected during run")
    except Exception as e:
        logger.error("ws_voice pipeline error: {}", e)
        raise
