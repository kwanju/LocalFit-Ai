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

from app.api import health, onboarding, routine, session
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
    app.state.tts = None
    app.state.vad = None

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
    from app.adapters.stt import get_stt_adapter, get_vad_adapter
    from app.adapters.tts import get_tts_adapter

    app.state.llm = _load_adapter("LLM", get_llm_adapter, config)
    app.state.stt = _load_adapter("STT", get_stt_adapter, config)
    app.state.tts = _load_adapter("TTS", get_tts_adapter, config)
    app.state.vad = _load_adapter("VAD", get_vad_adapter, config)

    if app.state.llm is not None:
        await app.state.llm.warmup()  # type: ignore[attr-defined]

    yield
    logger.info("LocalFit AI shutting down")


app = FastAPI(title="LocalFit AI", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(session.router)
app.include_router(routine.router)
app.include_router(onboarding.router)
# ws_coach.router — DEPRECATED, removed in Phase 1. Replaced by ws_voice in Phase 2.


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=HOST, port=PORT)
