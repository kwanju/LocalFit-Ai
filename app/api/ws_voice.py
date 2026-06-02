"""WebSocket /ws/voice — Pipecat pipeline mount (ADR-009/011).

Query param: ?mode=S2S|C2S|C2C|S2C  (default: C2C)

Phase 2: mock services only.  Real STT/TTS/LLM wired in Phases 3-5.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from pipecat.pipeline.worker import PipelineWorker
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from pipecat.workers.runner import WorkerRunner

from app.pipecat_services.pipeline_builder import SessionMode, build_pipeline

router = APIRouter(tags=["ws"])


@router.websocket("/ws/voice")
async def ws_voice(websocket: WebSocket, mode: str = "C2C") -> None:
    """Pipecat 4-mode voice pipeline endpoint.

    Args:
        websocket: FastAPI WebSocket connection.
        mode: Session mode — S2S / C2S / C2C / S2C (case-insensitive).
    """
    try:
        session_mode = SessionMode(mode.upper())
    except ValueError:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": f"알 수 없는 모드입니다: {mode}"})
        await websocket.close()
        return

    transport = FastAPIWebsocketTransport(
        websocket,
        FastAPIWebsocketParams(
            serializer=ProtobufFrameSerializer(),
            add_wav_header=False,
        ),
    )

    # Use the lifespan-loaded TTS service (Qwen3/Melo) if present; else mock falls back.
    tts_service = getattr(websocket.app.state, "tts_service", None)
    pipeline = build_pipeline(transport, session_mode, tts_service=tts_service)
    worker = PipelineWorker(pipeline, enable_rtvi=False)
    runner = WorkerRunner()

    @transport.event_handler("on_client_connected")
    async def on_connected(transport: FastAPIWebsocketTransport, ws: WebSocket) -> None:
        logger.info("ws_voice client connected: mode={}", session_mode.value)

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
