"""FastAPI entrypoint. Lifespan loads config, initializes the DB, and constructs
adapters (ADR-012). Adapter construction is tolerant: a missing GPU/model leaves
that adapter unavailable (reported by /health) instead of crashing startup.
"""

import logging
import logging.handlers
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.api import calendar, health, onboarding, routine, session, ws_voice
from app.config import AppConfig, load_config
from app.db.engine import init_db
from app.utils.logging import setup_logging

HOST = "127.0.0.1"  # ADR-002: P0 local-only binding
PORT = 8000


class _InterceptHandler(logging.Handler):
    """Route stdlib logging (e.g. Pipecat internals) through loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno  # type: ignore[assignment]
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _load_adapter(
    name: str, loader: Callable[[AppConfig], object], config: AppConfig
) -> object | None:
    try:
        adapter = loader(config)
        logger.info("{} adapter loaded", name)
        return adapter
    except Exception as e:  # noqa: BLE001 — degrade gracefully, /health reports the gap
        logger.error("{} adapter failed to load: {}", name, e)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)

    app.state.config = None
    app.state.llm = None
    app.state.stt = None
    app.state.stt_service = None    # Pipecat STTService bound to FasterWhisperClient (ADR-005)
    app.state.tts = None
    app.state.tts_service = None    # Pipecat TTSService bound to the active client (ADR-006)
    # VAD adapter: Pipecat SileroVADAnalyzer is constructed per ws_voice session
    # (ADR-007/011); no separate lifespan-loaded VAD adapter is needed.

    try:
        config = load_config()
        app.state.config = config
    except Exception as e:  # noqa: BLE001 — without config we still serve /health
        logger.error("Config load failed — DB and adapters not initialized: {}", e)
        yield
        return

    try:
        await init_db()
    except Exception as e:  # noqa: BLE001 — adapters may still work without the DB
        logger.error("DB initialization failed: {}", e)

    from app.adapters.llm import get_llm_adapter
    from app.adapters.stt import get_stt_adapter
    from app.adapters.tts import get_tts_adapter

    app.state.llm = _load_adapter("LLM", get_llm_adapter, config)
    app.state.stt = _load_adapter("STT", get_stt_adapter, config)
    app.state.tts = _load_adapter("TTS", get_tts_adapter, config)

    # Bind the FasterWhisperClient to its Pipecat service (ADR-005/012). The
    # heavy `WhisperModel.load` already happened in get_stt_adapter; the service
    # wraps it so ws_voice can mount the same instance per connection.
    if app.state.stt is not None:
        try:
            from app.adapters.stt.faster_whisper_client import FasterWhisperClient
            from app.pipecat_services.whisper_service import LocalFitWhisperSTTService

            if isinstance(app.state.stt, FasterWhisperClient):
                app.state.stt_service = LocalFitWhisperSTTService(app.state.stt)
                logger.info("STT pipecat service bound: LocalFitWhisperSTTService")
        except Exception as e:  # noqa: BLE001 — adapter present but Pipecat bind failed
            logger.error("STT pipecat service bind failed: {}", e)

    # Bind the active TTS client to its Pipecat service so ws_voice can mount
    # the same instance per connection (model load happens once at lifespan).
    if app.state.tts is not None:
        try:
            from app.adapters.tts.qwen3_client import Qwen3TTSClient

            if isinstance(app.state.tts, Qwen3TTSClient):
                from app.pipecat_services.qwen3_tts_service import Qwen3TTSService

                app.state.tts_service = Qwen3TTSService(app.state.tts)
            else:
                from app.adapters.tts.melo_client import MeloTTSClient
                from app.pipecat_services.melo_tts_service import MeloTTSService

                if isinstance(app.state.tts, MeloTTSClient):
                    app.state.tts_service = MeloTTSService(app.state.tts)
            logger.info("TTS pipecat service bound: {}", type(app.state.tts_service).__name__)
        except Exception as e:  # noqa: BLE001 — adapter present but Pipecat bind failed
            logger.error("TTS pipecat service bind failed: {}", e)

    if app.state.llm is not None:
        await app.state.llm.warmup()  # type: ignore[attr-defined]

    yield
    logger.info("LocalFit AI shutting down")


app = FastAPI(title="LocalFit AI", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(session.router)
app.include_router(routine.router)
app.include_router(onboarding.router)
app.include_router(calendar.router)
app.include_router(ws_voice.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=HOST, port=PORT)
