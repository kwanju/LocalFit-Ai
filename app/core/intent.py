import asyncio
import json
from typing import Any, Literal, get_args

from loguru import logger

# NOTE: importing from adapters violates ADR-012 (core should not import adapters).
# IntentClassifier will be rewritten as a pure domain function in Phase 5 (ADR-013 instructor).
from app.adapters.llm.ollama_client import LLMMessage, LLMRequest
from app.messages import MSG_COACHING_UNAVAILABLE, MSG_LLM_TIMEOUT
from app.prompts.coaching import (
    INTENT_CLASSIFY_PROMPT_PREFIX,
    INTENT_RESPONSE_PROMPT_PREFIXES,
    SAFETY_SYSTEM_PREFIX,
)

IntentType = Literal["body_state", "schedule", "feedback", "goal", "injury", "general"]

_VALID_INTENTS: frozenset[str] = frozenset(get_args(IntentType))

_DEFAULT_TIMEOUT_SEC: float = 4.0
_CLASSIFY_TEMPERATURE: float = 0.1
_CLASSIFY_MAX_TOKENS: int = 64
_RESPOND_TEMPERATURE: float = 0.7
_RESPOND_MAX_TOKENS: int = 256


class IntentClassifier:
    def __init__(self, llm: Any, timeout_sec: float = _DEFAULT_TIMEOUT_SEC) -> None:
        self._llm = llm
        self._timeout_sec = timeout_sec

    async def classify(self, user_input: str) -> IntentType:
        """Classify user intent into one of 6 categories. Falls back to 'general' on any failure."""
        request = LLMRequest(
            messages=[
                LLMMessage(role="system", content=SAFETY_SYSTEM_PREFIX),
                LLMMessage(role="user", content=INTENT_CLASSIFY_PROMPT_PREFIX + user_input),
            ],
            temperature=_CLASSIFY_TEMPERATURE,
            max_tokens=_CLASSIFY_MAX_TOKENS,
        )
        try:
            raw = await asyncio.wait_for(self._llm.generate(request), timeout=self._timeout_sec)
            return self._parse_intent(raw)
        except TimeoutError:
            logger.warning("Intent classification timed out — falling back to 'general'")
            return "general"
        except Exception as e:
            logger.warning("Intent classification failed: {} — falling back to 'general'", e)
            return "general"

    async def respond(self, intent: IntentType, user_input: str) -> str:
        """Generate a coaching response for the given intent."""
        prefix = INTENT_RESPONSE_PROMPT_PREFIXES.get(
            intent, INTENT_RESPONSE_PROMPT_PREFIXES["general"]
        )
        request = LLMRequest(
            messages=[
                LLMMessage(role="system", content=SAFETY_SYSTEM_PREFIX),
                LLMMessage(role="user", content=prefix + user_input),
            ],
            temperature=_RESPOND_TEMPERATURE,
            max_tokens=_RESPOND_MAX_TOKENS,
        )
        try:
            return await asyncio.wait_for(self._llm.generate(request), timeout=self._timeout_sec)
        except TimeoutError:
            logger.warning("LLM respond timeout for intent={}", intent)
            return MSG_LLM_TIMEOUT
        except Exception as e:
            logger.error("LLM respond failed for intent={}: {}", intent, e)
            return MSG_COACHING_UNAVAILABLE

    def _parse_intent(self, raw: str) -> IntentType:
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON object in LLM response")
            data = json.loads(raw[start:end])
            intent = str(data.get("intent", "")).lower().strip()
            if intent in _VALID_INTENTS:
                return intent  # type: ignore[return-value]
            logger.warning("Unknown intent '{}' — falling back to 'general'", intent)
            return "general"
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Intent parse error: {} — falling back to 'general'", e)
            return "general"
