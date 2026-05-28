from typing import Any

from app.adapters.llm.protocol import LLMAdapter, LLMMessage, LLMRequest
from app.config import AppConfig


def get_llm_adapter(config: AppConfig) -> LLMAdapter:
    from app.adapters.llm.ollama import OllamaAdapter

    return OllamaAdapter(config)


def __getattr__(name: str) -> Any:
    # Lazy access so importing the protocol does not pull in the ollama dependency.
    if name == "OllamaAdapter":
        from app.adapters.llm.ollama import OllamaAdapter

        return OllamaAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["get_llm_adapter", "LLMAdapter", "LLMMessage", "LLMRequest"]
