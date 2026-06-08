from typing import Any

from app.adapters.tts.qwen3_client import Qwen3TTSClient, TTSRequest
from app.config import AppConfig


def get_tts_adapter(config: AppConfig) -> Any:
    """Return the configured TTS client (ADR-006: faster-qwen3-tts only).

    MeloTTS was removed 2026-06-08 — qwen3(faster) is the sole TTS backend.
    """
    name = config.tts.active
    if name == "qwen3":
        return Qwen3TTSClient(config)
    raise ValueError(f"Unknown TTS adapter: {name} (only 'qwen3' is supported)")


__all__ = ["get_tts_adapter", "TTSRequest", "Qwen3TTSClient"]
