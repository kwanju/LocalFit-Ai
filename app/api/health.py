"""GET /health — backend + per-adapter + pipecat status aggregation."""

import asyncio

from fastapi import APIRouter, Request
from loguru import logger

router = APIRouter(tags=["health"])

_ADAPTER_NAMES: tuple[str, ...] = ("llm", "stt", "tts")

_PIPECAT_OK: bool = False
try:
    from app.pipecat_services.pipeline_builder import build_pipeline  # noqa: F401

    _PIPECAT_OK = True
except Exception as e:
    logger.warning("Pipecat pipeline_builder import failed: {}", e)


async def _probe(name: str, adapter: object | None) -> tuple[str, bool]:
    if adapter is None:
        return name, False
    try:
        return name, await adapter.health()  # type: ignore[attr-defined]
    except Exception as e:  # noqa: BLE001 — a probe failure must not break /health
        logger.warning("Health probe failed for {}: {}", name, e)
        return name, False


@router.get("/health")
async def health(request: Request) -> dict:
    state = request.app.state
    probes = [_probe(name, getattr(state, name, None)) for name in _ADAPTER_NAMES]
    adapters = dict(await asyncio.gather(*probes))
    status = "ok" if all(adapters.values()) else "degraded"
    return {"status": status, "backend": True, "pipecat": _PIPECAT_OK, "adapters": adapters}
