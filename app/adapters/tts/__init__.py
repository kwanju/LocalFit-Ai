from typing import Any

from app.adapters.tts.protocol import TTSAdapter, TTSRequest
from app.config import AppConfig


def get_tts_adapter(config: AppConfig) -> TTSAdapter:
    # Implementation imported lazily so protocol-only imports (e.g. the core
    # orchestrator) don't pull in the heavy torch dependency.
    from app.adapters.tts.qwen3 import Qwen3TTSAdapter

    registry = {"qwen3": Qwen3TTSAdapter}
    name = config.tts.active
    if name not in registry:
        raise ValueError(f"Unknown TTS adapter: {name}")
    return registry[name](config)


def __getattr__(name: str) -> Any:
    if name == "Qwen3TTSAdapter":
        from app.adapters.tts.qwen3 import Qwen3TTSAdapter

        return Qwen3TTSAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["get_tts_adapter", "TTSAdapter", "TTSRequest", "Qwen3TTSAdapter"]
