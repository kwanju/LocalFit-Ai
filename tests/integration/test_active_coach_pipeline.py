"""End-to-end pipeline tests for the active-coach stack (ADR-013).

Uses ``pipecat.tests.utils.run_test`` to drive the assembled C2C pipeline with
a mocked ``StructuredOllamaProcessor.instructor``. No real Ollama, no DB.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pipecat.frames.frames import InputTextRawFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.tests.utils import run_test

from app.config import load_config
from app.core.coach_response import (
    CoachResponse,
    ProposeSetAction,
    StartCountingAction,
)
from app.core.confirm_slot import ConfirmSlot
from app.pipecat_services.frames import SafetyResponseFrame
from app.pipecat_services.ollama_service import StructuredOllamaProcessor
from app.pipecat_services.processors.action_dispatcher import ActionDispatcherProcessor
from app.pipecat_services.processors.confirm_rule import ConfirmRuleProcessor
from app.pipecat_services.processors.safety_guard import SafetyGuardProcessor
from app.prompts.coaching import PROACTIVE_OPENER_USER_MESSAGE


def _client_mock(response: CoachResponse) -> SimpleNamespace:
    """Ollama native client mock — ``chat`` returns ``{"message":{"content": JSON}}``."""
    return SimpleNamespace(
        chat=AsyncMock(return_value={"message": {"content": response.model_dump_json()}})
    )


def _build_coach_pipeline(
    llm: StructuredOllamaProcessor,
    slot: ConfirmSlot,
    *,
    start_counting_cb=None,
) -> Pipeline:
    return Pipeline(
        [
            SafetyGuardProcessor(),
            ConfirmRuleProcessor(slot),
            llm,
            ActionDispatcherProcessor(slot, start_counting=start_counting_cb),
        ]
    )


@pytest.mark.asyncio
async def test_llm_direct_start_counting_converts_to_proposal() -> None:
    """C2C: LLM이 사용자 확답 없이 start_counting 을 내면 가드가 *제안*으로 전환한다.

    2026-06-09 가드(ActionDispatcher): 확답 없는 직접 시작은 자동 실행하지 않고
    ProposeSetAction 으로 슬롯에 남긴다(LLM 이 마음대로 운동을 시작하지 못함). 실제
    시작은 ConfirmRule 확답 경로로만 일어나며 unit test 로 별도 검증한다.
    """
    config = load_config()
    cb = AsyncMock()
    slot = ConfirmSlot()
    llm = StructuredOllamaProcessor(config)
    llm._client = _client_mock(
        CoachResponse(
            text="푸시업 10개 시작할게요!",
            actions=[StartCountingAction(exercise="푸시업", reps=10)],
        )
    )

    pipeline = _build_coach_pipeline(llm, slot, start_counting_cb=cb)
    await run_test(pipeline, frames_to_send=[InputTextRawFrame(text="푸시업 10개 시작하자")])

    # 가드: 콜백은 호출되지 않고, 제안만 슬롯에 들어간다(자동 시작 금지).
    cb.assert_not_awaited()
    assert slot.has_pending
    assert slot.pending_proposal.exercise == "푸시업"
    assert slot.pending_proposal.reps == 10


@pytest.mark.asyncio
async def test_safety_keyword_bypasses_llm() -> None:
    """C2C: injury keyword → SafetyResponseFrame, LLM never called."""
    config = load_config()
    slot = ConfirmSlot()
    llm = StructuredOllamaProcessor(config)
    _no_call = CoachResponse(text="LLM should not be called").model_dump_json()
    chat = AsyncMock(return_value={"message": {"content": _no_call}})
    llm._client = SimpleNamespace(chat=chat)

    pipeline = _build_coach_pipeline(llm, slot)
    from pipecat.frames.frames import TranscriptionFrame
    from pipecat.utils.time import time_now_iso8601

    down, _ = await run_test(
        pipeline,
        frames_to_send=[
            TranscriptionFrame(
                text="허리가 아파요", user_id="u", timestamp=time_now_iso8601()
            )
        ],
    )

    chat.assert_not_called()
    assert any(isinstance(f, SafetyResponseFrame) for f in down)


# Two-turn "propose then accept" is intentionally NOT a pipeline-level test —
# Pipecat processes frames concurrently per stage so back-to-back frames race
# (turn 2 can reach ConfirmRule before turn 1's proposal has landed in the slot).
# In production the user always waits for TTS, so the race never happens.
# The chain is verified by the unit tests:
#   - tests/unit/test_action_dispatcher.py::test_propose_set_lands_in_slot
#   - tests/unit/test_confirm_rule.py::test_accept_dispatches_start_counting


@pytest.mark.asyncio
async def test_proactive_opener_message_triggers_llm() -> None:
    """Proactive opener: PROACTIVE_OPENER_USER_MESSAGE inject → 1 LLM call."""
    config = load_config()
    slot = ConfirmSlot()
    llm = StructuredOllamaProcessor(config)
    chat = AsyncMock(
        return_value={
            "message": {
                "content": CoachResponse(
                    text="안녕하세요! 가볍게 스쿼트 15회 어떠세요?",
                    actions=[ProposeSetAction(exercise="스쿼트", reps=15, sets=3, rest_sec=60)],
                ).model_dump_json()
            }
        }
    )
    llm._client = SimpleNamespace(chat=chat)

    pipeline = _build_coach_pipeline(llm, slot)
    await run_test(pipeline, frames_to_send=[InputTextRawFrame(text=PROACTIVE_OPENER_USER_MESSAGE)])

    chat.assert_awaited_once()
    # the proposal landed in the slot
    assert slot.has_pending
    assert slot.pending_proposal.exercise == "스쿼트"
