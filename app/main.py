"""FastAPI entrypoint. Lifespan loads config, initializes the DB, and constructs
adapters (ADR-014). Adapter construction is tolerant: a missing GPU/model leaves
that adapter unavailable (reported by /health) instead of crashing startup.
"""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health, onboarding, routine, session, ws_coach
from app.config import AppConfig, load_config
from app.db.engine import init_db

logger = logging.getLogger(__name__)

HOST = "127.0.0.1"  # ADR-002: P0 local-only binding
PORT = 8000


def _load_adapter(
    name: str, loader: Callable[[AppConfig], object], config: AppConfig
) -> object | None:
    try:
        adapter = loader(config)
        logger.info("%s adapter loaded", name)
        return adapter
    except Exception as e:  # noqa: BLE001 — degrade gracefully, /health reports the gap
        logger.error("%s adapter failed to load: %s", name, e)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.config = None
    app.state.llm = None
    app.state.stt = None
    app.state.tts = None

    try:
        config = load_config()
        app.state.config = config
    except Exception as e:  # noqa: BLE001 — without config we still serve /health
        logger.error("Config load failed — DB and adapters not initialized: %s", e)
        yield
        return

    try:
        await init_db()
    except Exception as e:  # noqa: BLE001 — adapters may still work without the DB
        logger.error("DB initialization failed: %s", e)

    from app.adapters.llm import get_llm_adapter
    from app.adapters.stt import get_stt_adapter
    from app.adapters.tts import get_tts_adapter

    app.state.llm = _load_adapter("LLM", get_llm_adapter, config)
    app.state.stt = _load_adapter("STT", get_stt_adapter, config)
    app.state.tts = _load_adapter("TTS", get_tts_adapter, config)

    yield
    logger.info("LocalFit AI shutting down")


app = FastAPI(title="LocalFit AI", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(session.router)
app.include_router(routine.router)
app.include_router(onboarding.router)
app.include_router(ws_coach.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=HOST, port=PORT)
