"""Model lifecycle endpoints — app-open prewarm (ADR-030 (b)).

``POST /prewarm`` is called by the Tauri shell when the app is opened/focused
(user intent) so the heavy models start loading before the user hits 시작,
cutting perceived cold start. This is NOT a scheduler/background preload —
ADR-030 forbids that because a background load would fight a running game for
VRAM. Fire-and-forget: returns immediately while the load runs in the
background; a VRAM failure is logged and the eventual 세션 시작 retries and
surfaces the 부족 안내 (ws_voice).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from loguru import logger

router = APIRouter(tags=["lifecycle"])


@router.post("/prewarm")
async def prewarm(request: Request) -> dict:
    """Kick off an app-open model preload. Returns the current load state."""
    manager = getattr(request.app.state, "models", None)
    if manager is None:
        return {"status": "unavailable"}
    if manager.loaded:
        return {"status": "loaded"}

    async def _bg_load() -> None:
        try:
            await manager.load()
            logger.info("prewarm: models loaded (app-open intent)")
        except Exception as e:  # noqa: BLE001 — prewarm is best-effort; 세션 시작 retries
            logger.warning("prewarm load failed (session start will retry): {}", e)

    asyncio.create_task(_bg_load())
    return {"status": "loading"}
