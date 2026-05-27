from app.adapters.tts.protocol import TTSAdapter, TTSRequest
from app.adapters.tts.qwen3 import Qwen3TTSAdapter
from app.config import AppConfig

_REGISTRY = {"qwen3": Qwen3TTSAdapter}


def get_tts_adapter(config: AppConfig) -> TTSAdapter:
    name = config.tts.active
    if name not in _REGISTRY:
        raise ValueError(f"Unknown TTS adapter: {name}")
    return _REGISTRY[name](config)


__all__ = ["get_tts_adapter", "TTSAdapter", "TTSRequest", "Qwen3TTSAdapter"]
