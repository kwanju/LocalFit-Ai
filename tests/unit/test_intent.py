import asyncio
from unittest.mock import AsyncMock

import pytest

from app.core.intent import IntentClassifier
from app.messages import MSG_COACHING_UNAVAILABLE, MSG_LLM_TIMEOUT
from app.prompts.coaching import SAFETY_SYSTEM_PREFIX


@pytest.fixture
def mock_llm() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def classifier(mock_llm: AsyncMock) -> IntentClassifier:
    return IntentClassifier(llm=mock_llm, timeout_sec=1.0)


class TestClassify:
    @pytest.mark.parametrize(
        "response_json,expected",
        [
            ('{"intent": "body_state"}', "body_state"),
            ('{"intent": "schedule"}', "schedule"),
            ('{"intent": "feedback"}', "feedback"),
            ('{"intent": "goal"}', "goal"),
            ('{"intent": "injury"}', "injury"),
            ('{"intent": "general"}', "general"),
        ],
    )
    async def test_all_intents(
        self, classifier: IntentClassifier, mock_llm: AsyncMock, response_json: str, expected: str
    ) -> None:
        mock_llm.generate = AsyncMock(return_value=response_json)
        assert await classifier.classify("테스트 입력") == expected

    async def test_unknown_intent_falls_back_to_general(
        self, classifier: IntentClassifier, mock_llm: AsyncMock
    ) -> None:
        mock_llm.generate = AsyncMock(return_value='{"intent": "shopping"}')
        assert await classifier.classify("테스트 입력") == "general"

    async def test_invalid_json_falls_back_to_general(
        self, classifier: IntentClassifier, mock_llm: AsyncMock
    ) -> None:
        mock_llm.generate = AsyncMock(return_value="죄송합니다, 답변을 드릴 수 없어요.")
        assert await classifier.classify("테스트 입력") == "general"

    async def test_timeout_falls_back_to_general(
        self, classifier: IntentClassifier, mock_llm: AsyncMock
    ) -> None:
        async def slow(*_args, **_kwargs):
            await asyncio.sleep(10)
            return '{"intent": "general"}'

        mock_llm.generate = slow
        assert await classifier.classify("테스트 입력") == "general"

    async def test_json_embedded_in_text(
        self, classifier: IntentClassifier, mock_llm: AsyncMock
    ) -> None:
        mock_llm.generate = AsyncMock(
            return_value='네, 분석하겠습니다! {"intent": "feedback"} 이상입니다.'
        )
        assert await classifier.classify("운동 폼이 맞나요?") == "feedback"

    async def test_safety_system_prefix_is_first_message(
        self, classifier: IntentClassifier, mock_llm: AsyncMock
    ) -> None:
        mock_llm.generate = AsyncMock(return_value='{"intent": "general"}')
        await classifier.classify("테스트")
        request = mock_llm.generate.call_args[0][0]
        assert request.messages[0].role == "system"
        assert request.messages[0].content == SAFETY_SYSTEM_PREFIX


class TestRespond:
    async def test_returns_llm_output(
        self, classifier: IntentClassifier, mock_llm: AsyncMock
    ) -> None:
        mock_llm.generate = AsyncMock(return_value="오늘 컨디션이 어떠신가요?")
        result = await classifier.respond("body_state", "좀 피곤해요")
        assert result == "오늘 컨디션이 어떠신가요?"

    async def test_timeout_returns_timeout_message(
        self, classifier: IntentClassifier, mock_llm: AsyncMock
    ) -> None:
        async def slow(*_args, **_kwargs):
            await asyncio.sleep(10)
            return "response"

        mock_llm.generate = slow
        result = await classifier.respond("general", "안녕하세요")
        assert result == MSG_LLM_TIMEOUT

    async def test_exception_returns_unavailable_message(
        self, classifier: IntentClassifier, mock_llm: AsyncMock
    ) -> None:
        mock_llm.generate = AsyncMock(side_effect=ConnectionError("Ollama down"))
        result = await classifier.respond("general", "안녕하세요")
        assert result == MSG_COACHING_UNAVAILABLE

    async def test_safety_prefix_in_respond_messages(
        self, classifier: IntentClassifier, mock_llm: AsyncMock
    ) -> None:
        mock_llm.generate = AsyncMock(return_value="좋아요!")
        await classifier.respond("goal", "오늘 스쿼트 100개 목표예요")
        request = mock_llm.generate.call_args[0][0]
        assert request.messages[0].role == "system"
        assert request.messages[0].content == SAFETY_SYSTEM_PREFIX

    async def test_unknown_intent_uses_general_template(
        self, classifier: IntentClassifier, mock_llm: AsyncMock
    ) -> None:
        mock_llm.generate = AsyncMock(return_value="안녕하세요!")
        # "unknown" is not a valid IntentType — fallback to general template
        result = await classifier.respond("unknown", "테스트")  # type: ignore[arg-type]
        assert result == "안녕하세요!"
