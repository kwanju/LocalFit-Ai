from typing import TYPE_CHECKING, Any

from app.adapters.stt.protocol import STTAdapter, STTResult
from app.config import AppConfig

if TYPE_CHECKING:
    from app.adapters.stt.vad import SileroVADWrapper


def get_stt_adapter(config: AppConfig) -> STTAdapter:
    from app.adapters.stt.whisper import FasterWhisperAdapter

    return FasterWhisperAdapter(config)


def get_vad_adapter(config: AppConfig) -> "SileroVADWrapper":
    from app.adapters.stt.vad import SileroVADWrapper

    return SileroVADWrapper(config)


def __getattr__(name: str) -> Any:
    # Lazy access so importing the protocol does not pull in numpy/torch.
    if name == "FasterWhisperAdapter":
        from app.adapters.stt.whisper import FasterWhisperAdapter

        return FasterWhisperAdapter
    if name in ("SileroVADWrapper", "VADSegment"):
        from app.adapters.stt.vad import SileroVADWrapper, VADSegment

        return {"SileroVADWrapper": SileroVADWrapper, "VADSegment": VADSegment}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "get_stt_adapter",
    "get_vad_adapter",
    "STTAdapter",
    "STTResult",
    "FasterWhisperAdapter",
    "SileroVADWrapper",
    "VADSegment",
]
