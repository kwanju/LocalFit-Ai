"""tests/unit/test_action_dispatcher_counting.py — StartCountingAction → engine.start
(phase-6 §6-3 / §6-7).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from pipecat.frames.frames import TextFrame
from pipecat.tests.utils import run_test

from app.core.coach_response import StartCountingAction
from app.core.confirm_slot import ConfirmSlot
from app.pipecat_services.frames import CoachActionFrame
from app.pipecat_services.processors.action_dispatcher import ActionDispatcherProcessor


async def _drive(disp: ActionDispatcherProcessor, frames) -> list:
    down, _ = await run_test(disp, frames_to_send=frames)
    return list(down)


async def test_counting_manager_start_called_on_action() -> None:
    """StartCountingAction must call counting_manager.start(exercise, reps)."""
    mock_manager = MagicMock()
    mock_manager.start = AsyncMock()

    slot = ConfirmSlot()
    disp = ActionDispatcherProcessor(slot, counting_manager=mock_manager)
    action = StartCountingAction(exercise="푸시업", reps=10)
    await _drive(disp, [CoachActionFrame(action=action)])

    mock_manager.start.assert_awaited_once_with("푸시업", 10)


async def test_counting_manager_takes_priority_over_callable() -> None:
    """When counting_manager is provided, start_counting callable is ignored."""
    mock_manager = MagicMock()
    mock_manager.start = AsyncMock()
    legacy_cb = AsyncMock()

    slot = ConfirmSlot()
    disp = ActionDispatcherProcessor(slot, start_counting=legacy_cb, counting_manager=mock_manager)
    action = StartCountingAction(exercise="스쿼트", reps=15)
    await _drive(disp, [CoachActionFrame(action=action)])

    mock_manager.start.assert_awaited_once()
    legacy_cb.assert_not_awaited()


async def test_counting_manager_exception_swallowed() -> None:
    """Exception from counting_manager.start must not break the pipeline."""
    mock_manager = MagicMock()
    mock_manager.start = AsyncMock(side_effect=RuntimeError("engine failed"))

    slot = ConfirmSlot()
    disp = ActionDispatcherProcessor(slot, counting_manager=mock_manager)
    action = StartCountingAction(exercise="풀업", reps=5)
    # Should not raise
    await _drive(disp, [CoachActionFrame(action=action)])
    mock_manager.start.assert_awaited_once()


async def test_no_counting_manager_falls_back_to_callable() -> None:
    """Without counting_manager, legacy start_counting callable is used."""
    cb = AsyncMock()
    slot = ConfirmSlot()
    disp = ActionDispatcherProcessor(slot, start_counting=cb)
    action = StartCountingAction(exercise="스쿼트", reps=12)
    await _drive(disp, [CoachActionFrame(action=action)])
    cb.assert_awaited_once()


async def test_action_frame_not_forwarded_downstream() -> None:
    """CoachActionFrame must be swallowed by dispatcher, not forwarded."""
    mock_manager = MagicMock()
    mock_manager.start = AsyncMock()

    slot = ConfirmSlot()
    disp = ActionDispatcherProcessor(slot, counting_manager=mock_manager)
    action = StartCountingAction(exercise="풀업", reps=5)
    down = await _drive(disp, [CoachActionFrame(action=action)])

    assert not any(isinstance(f, CoachActionFrame) for f in down)


async def test_other_frames_still_pass_through() -> None:
    """Non-action frames must still pass through even when counting_manager is set."""
    mock_manager = MagicMock()
    mock_manager.start = AsyncMock()

    slot = ConfirmSlot()
    disp = ActionDispatcherProcessor(slot, counting_manager=mock_manager)
    down = await _drive(disp, [TextFrame(text="계속하자")])

    assert any(isinstance(f, TextFrame) and f.text == "계속하자" for f in down)
