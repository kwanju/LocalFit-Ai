from typing import Any

from app.adapters.tts.qwen3_client import Qwen3TTSClient, TTSRequest
from app.config import AppConfig


def get_tts_adapter(config: AppConfig) -> Any:
    """Return the configured TTS client (ADR-006 toggle: qwen3 | melo)."""
    name = config.tts.active
    if name == "qwen3":
        return Qwen3TTSClient(config)
    if name == "melo":
        from app.adapters.tts.melo_client import MeloTTSClient
        return MeloTTSClient(config)
    raise ValueError(f"Unknown TTS adapter: {name}")


def __getattr__(name: str) -> Any:
    if name == "Qwen3TTSClient":
        return Qwen3TTSClient
    if name == "MeloTTSClient":
        from app.adapters.tts.melo_client import MeloTTSClient
        return MeloTTSClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["get_tts_adapter", "TTSRequest", "Qwen3TTSClient", "MeloTTSClient"]
