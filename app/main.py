"""FastAPI entrypoint. Lifespan loads config, initializes the DB, and constructs
adapters (ADR-012). Adapter construction is tolerant: a missing GPU/model leaves
that adapter unavailable (reported by /health) instead of crashing startup.
"""

import logging
import logging.handlers
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api import (
    admin,
    calendar,
    condition,
    health,
    lifecycle,
    onboarding,
    routine,
    session,
    ws_voice,
)
from app.config import load_config
from app.db.engine import init_db
from app.utils.logging import setup_logging

HOST = "127.0.0.1"  # ADR-002: P0 local-only binding
PORT = 8000

# The Tauri webview (ADR-031) serves the bundled UI from tauri.localhost, so REST
# calls to the 127.0.0.1 sidecar are cross-origin and need CORS. We allow only the
# Tauri webview origins (Windows uses http://tauri.localhost) plus the dev server —
# never the public network (binding stays 127.0.0.1, ADR-002). WebSocket (/ws/voice)
# is unaffected: browsers don't apply CORS to WS handshakes.
CORS_ORIGINS = [
    "http://tauri.localhost",
    "https://tauri.localhost",
    "tauri://localhost",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)

    app.state.config = None
    # ADR-030: heavy models are NOT loaded at startup (supersedes ADR-015 lifespan
    # warmup). The ModelManager loads STT+TTS+LLM on session start / app-open
    # prewarm and unloads on session end, so idle VRAM ≈ baseline (게임 공존).
    app.state.models = None
    # Pipecat *Service 인스턴스는 ws_voice가 매 연결마다 새로 만든다 (service_factory).
    # FrameProcessor는 단일 파이프라인 lifecycle에 묶이므로 공유 불가.
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

    # ADR-030: construct the manager only — no model load here. Loading happens
    # on ws_voice 세션 시작 or POST /prewarm, unloading on session end.
    from app.adapters.model_manager import ModelManager

    app.state.models = ModelManager(config)
    logger.info("ModelManager ready (on-demand load/unload, ADR-030) — idle VRAM at baseline")

    yield
    logger.info("LocalFit AI shutting down")


app = FastAPI(title="LocalFit AI", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(session.router)
app.include_router(routine.router)
app.include_router(onboarding.router)
app.include_router(calendar.router)
app.include_router(condition.router)
app.include_router(admin.router)
app.include_router(lifecycle.router)
app.include_router(ws_voice.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=HOST, port=PORT)
