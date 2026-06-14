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
    """Backend liveness + current model load state (ADR-030 redefined semantics).

    ``adapters`` no longer means "resident" — under on-demand lifecycle they are
    all false while idle and true only during a loaded session. ``status`` is
    "ok" whenever the backend responds; the UI keys off reachability, not the
    adapter flags. ``models_loaded`` exposes the ModelManager state.
    """
    manager = getattr(request.app.state, "models", None)
    loaded = bool(manager is not None and manager.loaded)
    adapters = dict.fromkeys(_ADAPTER_NAMES, False)
    if loaded:
        probes = [_probe(name, getattr(manager, name, None)) for name in _ADAPTER_NAMES]
        adapters = dict(await asyncio.gather(*probes))
    return {
        "status": "ok",
        "backend": True,
        "pipecat": _PIPECAT_OK,
        "models_loaded": loaded,
        "adapters": adapters,
    }
