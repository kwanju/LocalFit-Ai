from typing import Any

from app.adapters.tts.qwen3_client import Qwen3TTSClient, TTSRequest
from app.config import AppConfig


def get_tts_adapter(config: AppConfig) -> Qwen3TTSClient:
    registry = {"qwen3": Qwen3TTSClient}
    name = config.tts.active
    if name not in registry:
        raise ValueError(f"Unknown TTS adapter: {name}")
    return registry[name](config)


def __getattr__(name: str) -> Any:
    if name == "Qwen3TTSClient":
        return Qwen3TTSClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["get_tts_adapter", "TTSRequest", "Qwen3TTSClient"]
