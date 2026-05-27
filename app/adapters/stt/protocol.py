from dataclasses import dataclass
from typing import Protocol


@dataclass
class STTResult:
    text: str
    language: str
    duration_ms: int


class STTAdapter(Protocol):
    async def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> STTResult: ...
    async def health(self) -> bool: ...
