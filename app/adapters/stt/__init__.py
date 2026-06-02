from app.adapters.stt.faster_whisper_client import FasterWhisperClient, STTResult
from app.config import AppConfig


def get_stt_adapter(config: AppConfig) -> FasterWhisperClient:
    return FasterWhisperClient(config)


__all__ = [
    "get_stt_adapter",
    "STTResult",
    "FasterWhisperClient",
]
