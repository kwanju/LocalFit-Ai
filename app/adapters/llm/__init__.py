from typing import Any

from app.adapters.llm.ollama_client import LLMMessage, LLMRequest, OllamaClient
from app.config import AppConfig


def get_llm_adapter(config: AppConfig) -> OllamaClient:
    return OllamaClient(config)


def __getattr__(name: str) -> Any:
    if name == "OllamaClient":
        return OllamaClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["get_llm_adapter", "OllamaClient", "LLMMessage", "LLMRequest"]
