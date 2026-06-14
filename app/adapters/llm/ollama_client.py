import asyncio
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass

import ollama
from loguru import logger

from app.config import AppConfig

_WARMUP_TIMEOUT_SEC: float = 120.0  # survives a cold qwen3.5:9b load (ADR-029/030)


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
    think: bool = False  # Qwen3 thinking mode — False for fast coaching responses


class OllamaClient:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._model: str = config.llm.model
        self._client = ollama.AsyncClient(host=config.llm.host)

    async def generate(self, request: LLMRequest) -> str:
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        options = {"temperature": request.temperature, "num_predict": request.max_tokens}

        try:
            response = await asyncio.wait_for(
                self._client.chat(
                    model=self._model,
                    messages=messages,
                    options=options,
                    keep_alive=request.keep_alive,
                    think=request.think,
                ),
                timeout=self._config.llm.timeout_sec,
            )
            return response.message.content or ""
        except TimeoutError:
            logger.warning("LLM generate timed out after {:.1f}s", self._config.llm.timeout_sec)
            raise
        except Exception as e:
            logger.error("LLM generate failed: {}", e)
            raise

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        options = {"temperature": request.temperature, "num_predict": request.max_tokens}

        try:
            response_iter = await asyncio.wait_for(
                self._client.chat(
                    model=self._model,
                    messages=messages,
                    options=options,
                    keep_alive=request.keep_alive,
                    think=request.think,
                    stream=True,
                ),
                timeout=self._config.llm.timeout_sec,
            )
            async for chunk in response_iter:
                content = chunk.message.content
                if content:
                    yield content
        except TimeoutError:
            logger.warning("LLM stream open timed out after {:.1f}s", self._config.llm.timeout_sec)
            raise
        except Exception as e:
            logger.error("LLM stream failed: {}", e)
            raise

    async def warmup(self, keep_alive: str | None = None) -> None:
        """Load the model into VRAM so the first real request isn't a cold start.

        ADR-030 on-demand: ``keep_alive`` keeps the model resident for the
        session (defaults to ``config.llm.keep_alive``); the session-end
        :meth:`unload` drops it again. Best-effort: long timeout, never raises.
        """
        ka = keep_alive or self._config.llm.keep_alive
        try:
            await asyncio.wait_for(
                self._client.chat(
                    model=self._model,
                    messages=[{"role": "user", "content": "안녕"}],
                    options={"num_predict": 1},
                    keep_alive=ka,
                    think=False,
                ),
                timeout=_WARMUP_TIMEOUT_SEC,
            )
            logger.info("LLM model warmed up: {} (keep_alive={})", self._model, ka)
        except Exception as e:  # noqa: BLE001 — warmup is best-effort
            logger.warning("LLM warmup failed: {}", e)

    async def unload(self) -> None:
        """Drop the model from Ollama VRAM immediately (ADR-030 session end).

        Sends a minimal request with ``keep_alive=0`` so Ollama unloads the
        weights now instead of after the idle timer. Best-effort: never raises.
        """
        try:
            await asyncio.wait_for(
                self._client.chat(
                    model=self._model,
                    messages=[{"role": "user", "content": "안녕"}],
                    options={"num_predict": 1},
                    keep_alive="0s",
                    think=False,
                ),
                timeout=_WARMUP_TIMEOUT_SEC,
            )
            logger.info("LLM model unloaded (keep_alive=0): {}", self._model)
        except Exception as e:  # noqa: BLE001 — best-effort
            logger.warning("LLM unload failed: {}", e)

    async def health(self) -> bool:
        try:
            await asyncio.wait_for(self._client.list(), timeout=3.0)
            return True
        except Exception as e:
            logger.warning("Ollama health check failed: {}", e)
            return False


async def _smoke_test(prompt: str) -> None:
    from app.config import load_config

    config = load_config()
    client = OllamaClient(config)

    if not await client.health():
        print("Ollama not available", file=sys.stderr)
        sys.exit(1)

    request = LLMRequest(messages=[LLMMessage(role="user", content=prompt)])

    print("--- generate ---")
    response = await client.generate(request)
    print(response)

    print("--- stream ---")
    async for chunk in client.stream(request):
        print(chunk, end="", flush=True)
    print()


if __name__ == "__main__":
    asyncio.run(_smoke_test(sys.argv[1] if len(sys.argv) > 1 else "안녕"))
