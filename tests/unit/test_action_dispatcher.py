"""ActionDispatcherProcessor — propose / start / log dispatch (ADR-013)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from pipecat.frames.frames import Frame, TextFrame
from pipecat.tests.utils import run_test

from app.core.coach_response import (
    LogConditionAction,
    ProposeSetAction,
    StartCountingAction,
)
from app.core.confirm_slot import ConfirmSlot
from app.pipecat_services.frames import CoachActionFrame
from app.pipecat_services.processors.action_dispatcher import ActionDispatcherProcessor


async def _drive(disp: ActionDispatcherProcessor, frames: list[Frame]) -> list[Frame]:
    down, _ = await run_test(disp, frames_to_send=frames)
    return list(down)


async def test_propose_set_lands_in_slot() -> None:
    slot = ConfirmSlot()
    disp = ActionDispatcherProcessor(slot)
    proposal = ProposeSetAction(exercise="풀업", reps=5, sets=3, rest_sec=90)
    down = await _drive(disp, [CoachActionFrame(action=proposal)])
    assert slot.pending_proposal == proposal
    # ActionFrame must NOT reach downstream
    assert not any(isinstance(f, CoachActionFrame) for f in down)


async def test_start_counting_invokes_callback() -> None:
    slot = ConfirmSlot()
    cb = AsyncMock()
    disp = ActionDispatcherProcessor(slot, start_counting=cb)
    disp.allow_one_direct_start()  # 가드 우회 (사용자 확답 시뮬레이트)
    action = StartCountingAction(exercise="스쿼트", reps=12)
    await _drive(disp, [CoachActionFrame(action=action)])
    cb.assert_awaited_once()
    assert cb.call_args.args[0] == action


async def test_log_condition_invokes_callback() -> None:
    slot = ConfirmSlot()
    cb = AsyncMock()
    disp = ActionDispatcherProcessor(slot, log_condition=cb)
    action = LogConditionAction(fatigue_level=8, notes="다리 무거움")
    await _drive(disp, [CoachActionFrame(action=action)])
    cb.assert_awaited_once()
    assert cb.call_args.args[0] == action


async def test_text_frames_pass_through() -> None:
    slot = ConfirmSlot()
    disp = ActionDispatcherProcessor(slot)
    down = await _drive(disp, [TextFrame(text="hello")])
    assert any(isinstance(f, TextFrame) and f.text == "hello" for f in down)


async def test_callback_exception_swallowed() -> None:
    slot = ConfirmSlot()
    cb = AsyncMock(side_effect=RuntimeError("counting engine down"))
    disp = ActionDispatcherProcessor(slot, start_counting=cb)
    disp.allow_one_direct_start()
    # should not raise
    await _drive(disp, [CoachActionFrame(action=StartCountingAction(exercise="풀업", reps=5))])
    cb.assert_awaited_once()


async def test_start_counting_without_confirm_is_rejected() -> None:
    """LLM이 사용자 확답 없이 start_counting을 발행하면 거부 (2026-06-07 가드)."""
    slot = ConfirmSlot()
    cb = AsyncMock()
    disp = ActionDispatcherProcessor(slot, start_counting=cb)
    # allow_one_direct_start 호출 안 함 — 가드 활성 상태.
    await _drive(disp, [CoachActionFrame(action=StartCountingAction(exercise="푸시업", reps=10))])
    cb.assert_not_awaited()
