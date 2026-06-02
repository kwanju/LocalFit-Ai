"""ConfirmRuleProcessor — accept/reject/no-match flows (ADR-013)."""

from __future__ import annotations

import pytest
from pipecat.frames.frames import Frame, TextFrame, TranscriptionFrame
from pipecat.tests.utils import run_test
from pipecat.utils.time import time_now_iso8601

from app.core.coach_response import ProposeSetAction, StartCountingAction
from app.core.confirm_slot import ConfirmSlot
from app.pipecat_services.frames import CoachActionFrame
from app.pipecat_services.processors.confirm_rule import ConfirmRuleProcessor


async def _send(text: str, slot: ConfirmSlot) -> list[Frame]:
    down, _ = await run_test(
        ConfirmRuleProcessor(slot),
        frames_to_send=[
            TranscriptionFrame(text=text, user_id="u", timestamp=time_now_iso8601())
        ],
    )
    return list(down)


def _proposal() -> ProposeSetAction:
    return ProposeSetAction(exercise="푸시업", reps=10, sets=3, rest_sec=60)


@pytest.mark.parametrize(
    "reply", ["좋아요", "응", "네", "ok", "OK", "오케이", "콜", "시작하자", "그래", "하자"]
)
async def test_accept_dispatches_start_counting(reply: str) -> None:
    slot = ConfirmSlot()
    slot.set(_proposal())
    frames = await _send(reply, slot)
    actions = [f for f in frames if isinstance(f, CoachActionFrame)]
    transcripts = [f for f in frames if isinstance(f, TranscriptionFrame)]
    assert len(actions) == 1
    assert isinstance(actions[0].action, StartCountingAction)
    assert actions[0].action.exercise == "푸시업"
    assert actions[0].action.reps == 10
    # original transcript dropped (LLM bypassed)
    assert transcripts == []
    assert not slot.has_pending
    # short ack text
    text = next(f for f in frames if type(f) is TextFrame)
    assert "시작" in text.text


@pytest.mark.parametrize(
    "reply", ["아니", "싫어", "패스", "나중에", "안 할래", "스킵"]
)
async def test_reject_clears_slot_and_forwards_to_llm(reply: str) -> None:
    slot = ConfirmSlot()
    slot.set(_proposal())
    frames = await _send(reply, slot)
    actions = [f for f in frames if isinstance(f, CoachActionFrame)]
    transcripts = [f for f in frames if isinstance(f, TranscriptionFrame)]
    assert actions == []
    assert len(transcripts) == 1  # forwarded to LLM
    assert not slot.has_pending


async def test_no_match_keeps_slot_and_forwards() -> None:
    slot = ConfirmSlot()
    slot.set(_proposal())
    frames = await _send("오늘 날씨 어때요", slot)
    actions = [f for f in frames if isinstance(f, CoachActionFrame)]
    transcripts = [f for f in frames if isinstance(f, TranscriptionFrame)]
    assert actions == []
    assert len(transcripts) == 1
    assert slot.has_pending  # untouched


async def test_accept_without_proposal_passes_through() -> None:
    slot = ConfirmSlot()  # empty
    frames = await _send("좋아요", slot)
    actions = [f for f in frames if isinstance(f, CoachActionFrame)]
    transcripts = [f for f in frames if isinstance(f, TranscriptionFrame)]
    assert actions == []
    assert len(transcripts) == 1
