from app.adapters.llm.ollama import OllamaAdapter
from app.adapters.llm.protocol import LLMAdapter, LLMMessage, LLMRequest
from app.config import AppConfig


def get_llm_adapter(config: AppConfig) -> LLMAdapter:
    return OllamaAdapter(config)


__all__ = ["get_llm_adapter", "LLMAdapter", "LLMMessage", "LLMRequest"]
