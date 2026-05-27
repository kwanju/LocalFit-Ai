from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass
class TTSRequest:
    text: str
    voice: str = "default"
    speed: float = 1.0


class TTSAdapter(Protocol):
    async def synthesize(self, request: TTSRequest) -> bytes: ...  # WAV bytes
    async def stream(self, request: TTSRequest) -> AsyncIterator[bytes]: ...
    async def health(self) -> bool: ...
