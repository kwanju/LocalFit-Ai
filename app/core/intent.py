import asyncio
import json
import logging
from typing import Literal, get_args

from app.adapters.llm.protocol import LLMAdapter, LLMMessage, LLMRequest
from app.messages import MSG_COACHING_UNAVAILABLE, MSG_LLM_TIMEOUT
from app.prompts.coaching import (
    INTENT_CLASSIFY_PROMPT_PREFIX,
    INTENT_RESPONSE_PROMPT_PREFIXES,
    SAFETY_SYSTEM_PREFIX,
)

logger = logging.getLogger(__name__)

IntentType = Literal["body_state", "schedule", "feedback", "goal", "injury", "general"]

_VALID_INTENTS: frozenset[str] = frozenset(get_args(IntentType))

_DEFAULT_TIMEOUT_SEC: float = 4.0


class IntentClassifier:
    def __init__(self, llm: LLMAdapter, timeout_sec: float = _DEFAULT_TIMEOUT_SEC) -> None:
        self._llm = llm
        self._timeout_sec = timeout_sec

    async def classify(self, user_input: str) -> IntentType:
        """Classify user intent into one of 6 categories. Falls back to 'general' on any failure."""
        request = LLMRequest(
            messages=[
                LLMMessage(role="system", content=SAFETY_SYSTEM_PREFIX),
                LLMMessage(role="user", content=INTENT_CLASSIFY_PROMPT_PREFIX + user_input),
            ],
            temperature=0.1,
            max_tokens=64,
        )
        try:
            raw = await asyncio.wait_for(self._llm.generate(request), timeout=self._timeout_sec)
            return self._parse_intent(raw)
        except asyncio.TimeoutError:
            logger.warning("Intent classification timed out — falling back to 'general'")
            return "general"
        except Exception as e:
            logger.warning("Intent classification failed: %s — falling back to 'general'", e)
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
            temperature=0.7,
            max_tokens=256,
        )
        try:
            return await asyncio.wait_for(self._llm.generate(request), timeout=self._timeout_sec)
        except asyncio.TimeoutError:
            logger.warning("LLM respond timeout for intent=%s", intent)
            return MSG_LLM_TIMEOUT
        except Exception as e:
            logger.error("LLM respond failed for intent=%s: %s", intent, e)
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
            logger.warning("Unknown intent '%s' — falling back to 'general'", intent)
            return "general"
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Intent parse error: %s — falling back to 'general'", e)
            return "general"
