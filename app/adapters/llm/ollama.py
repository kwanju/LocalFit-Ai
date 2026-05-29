import asyncio
import logging
import sys
from collections.abc import AsyncIterator

import ollama

from app.adapters.llm.protocol import LLMMessage, LLMRequest
from app.config import AppConfig

logger = logging.getLogger(__name__)

# Cold-loading a 9B model into VRAM can take well over the coaching timeout,
# so warmup uses its own generous budget instead of llm.timeout_sec.
_WARMUP_TIMEOUT_SEC: float = 120.0
_WARMUP_KEEP_ALIVE: str = "1h"


class OllamaAdapter:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._model: str = config.llm.models[config.llm.active]
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
            logger.warning("LLM generate timed out after %.1fs", self._config.llm.timeout_sec)
            raise
        except Exception as e:
            logger.error("LLM generate failed: %s", e)
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
            logger.warning("LLM stream open timed out after %.1fs", self._config.llm.timeout_sec)
            raise
        except Exception as e:
            logger.error("LLM stream failed: %s", e)
            raise

    async def warmup(self) -> None:
        """Load the model into VRAM so the first real request isn't a cold start.

        Best-effort and self-contained: uses a long timeout (cold load > coaching
        timeout) and never raises — a failed warmup must not block startup.
        """
        try:
            await asyncio.wait_for(
                self._client.chat(
                    model=self._model,
                    messages=[{"role": "user", "content": "안녕"}],
                    options={"num_predict": 1},
                    keep_alive=_WARMUP_KEEP_ALIVE,
                    think=False,
                ),
                timeout=_WARMUP_TIMEOUT_SEC,
            )
            logger.info("LLM model warmed up: %s", self._model)
        except Exception as e:  # noqa: BLE001 — warmup is best-effort
            logger.warning("LLM warmup failed: %s", e)

    async def health(self) -> bool:
        try:
            await asyncio.wait_for(self._client.list(), timeout=3.0)
            return True
        except Exception as e:
            logger.warning("Ollama health check failed: %s", e)
            return False


async def _smoke_test(prompt: str) -> None:
    from app.config import load_config

    config = load_config()
    adapter = OllamaAdapter(config)

    if not await adapter.health():
        print("Ollama not available", file=sys.stderr)
        sys.exit(1)

    request = LLMRequest(messages=[LLMMessage(role="user", content=prompt)])

    print("--- generate ---")
    response = await adapter.generate(request)
    print(response)

    print("--- stream ---")
    async for chunk in adapter.stream(request):
        print(chunk, end="", flush=True)
    print()


if __name__ == "__main__":
    asyncio.run(_smoke_test(sys.argv[1] if len(sys.argv) > 1 else "안녕"))
