from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMRequest:
    messages: list[LLMMessage]
    temperature: float = 0.7
    max_tokens: int = 512
    keep_alive: str = "1h"
    think: bool = False  # Qwen3.5 thinking mode — False for fast coaching responses


class LLMAdapter(Protocol):
    async def generate(self, request: LLMRequest) -> str: ...
    async def stream(self, request: LLMRequest) -> AsyncIterator[str]: ...
    async def health(self) -> bool: ...
