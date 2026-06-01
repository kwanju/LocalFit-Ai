from typing import TYPE_CHECKING, Any

from app.adapters.stt.faster_whisper_client import FasterWhisperClient, STTResult
from app.config import AppConfig

if TYPE_CHECKING:
    from app.adapters.stt.vad import SileroVADWrapper


def get_stt_adapter(config: AppConfig) -> FasterWhisperClient:
    return FasterWhisperClient(config)


def get_vad_adapter(config: AppConfig) -> "SileroVADWrapper":
    from app.adapters.stt.vad import SileroVADWrapper

    return SileroVADWrapper(config)


def __getattr__(name: str) -> Any:
    if name == "FasterWhisperClient":
        return FasterWhisperClient
    if name in ("SileroVADWrapper", "VADSegment"):
        from app.adapters.stt.vad import SileroVADWrapper, VADSegment

        return {"SileroVADWrapper": SileroVADWrapper, "VADSegment": VADSegment}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "get_stt_adapter",
    "get_vad_adapter",
    "STTResult",
    "FasterWhisperClient",
    "SileroVADWrapper",
    "VADSegment",
]
