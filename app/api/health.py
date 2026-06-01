"""GET /health — backend + per-adapter status aggregation (ADR-014)."""

import asyncio

from fastapi import APIRouter, Request
from loguru import logger

router = APIRouter(tags=["health"])

_ADAPTER_NAMES: tuple[str, ...] = ("llm", "stt", "tts")


async def _probe(name: str, adapter: object | None) -> tuple[str, bool]:
    if adapter is None:
        return name, False
    try:
        return name, await adapter.health()  # type: ignore[attr-defined]
    except Exception as e:  # noqa: BLE001 — a probe failure must not break /health
        logger.warning("Health probe failed for %s: %s", name, e)
        return name, False


@router.get("/health")
async def health(request: Request) -> dict:
    state = request.app.state
    probes = [_probe(name, getattr(state, name, None)) for name in _ADAPTER_NAMES]
    adapters = dict(await asyncio.gather(*probes))
    status = "ok" if all(adapters.values()) else "degraded"
    return {"status": status, "backend": True, "adapters": adapters}
