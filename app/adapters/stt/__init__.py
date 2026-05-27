from app.adapters.stt.protocol import STTAdapter, STTResult
from app.adapters.stt.vad import SileroVADWrapper, VADSegment
from app.adapters.stt.whisper import FasterWhisperAdapter
from app.config import AppConfig


def get_stt_adapter(config: AppConfig) -> STTAdapter:
    return FasterWhisperAdapter(config)


__all__ = [
    "get_stt_adapter",
    "STTAdapter",
    "STTResult",
    "FasterWhisperAdapter",
    "SileroVADWrapper",
    "VADSegment",
]
