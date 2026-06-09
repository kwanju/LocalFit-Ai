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
    """StartCountingAction must call counting_manager.start with sets/rest_sec (2026-06-07)."""
    mock_manager = MagicMock()
    mock_manager.start = AsyncMock()

    slot = ConfirmSlot()
    disp = ActionDispatcherProcessor(slot, counting_manager=mock_manager)
    disp.allow_one_direct_start()
    action = StartCountingAction(exercise="푸시업", reps=10, sets=3, rest_sec=45)
    await _drive(disp, [CoachActionFrame(action=action)])

    mock_manager.start.assert_awaited_once_with("푸시업", 10, sets=3, rest_sec=45)


async def test_counting_manager_takes_priority_over_callable() -> None:
    """When counting_manager is provided, start_counting callable is ignored."""
    mock_manager = MagicMock()
    mock_manager.start = AsyncMock()
    legacy_cb = AsyncMock()

    slot = ConfirmSlot()
    disp = ActionDispatcherProcessor(slot, start_counting=legacy_cb, counting_manager=mock_manager)
    disp.allow_one_direct_start()
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
    disp.allow_one_direct_start()
    action = StartCountingAction(exercise="풀업", reps=5)
    # Should not raise
    await _drive(disp, [CoachActionFrame(action=action)])
    mock_manager.start.assert_awaited_once()


async def test_no_counting_manager_falls_back_to_callable() -> None:
    """Without counting_manager, legacy start_counting callable is used."""
    cb = AsyncMock()
    slot = ConfirmSlot()
    disp = ActionDispatcherProcessor(slot, start_counting=cb)
    disp.allow_one_direct_start()
    action = StartCountingAction(exercise="스쿼트", reps=12)
    await _drive(disp, [CoachActionFrame(action=action)])
    cb.assert_awaited_once()


async def test_spontaneous_start_while_counting_active_is_swallowed() -> None:
    """카운팅 진행 중 LLM 자발 start_counting(미확답)은 조용히 무시 — start 호출 X.

    2026-06-07 폭주 fix.
    """
    mock_manager = MagicMock()
    mock_manager.start = AsyncMock()
    mock_manager.is_active = True  # @property → 속성 접근 (호출 아님)

    slot = ConfirmSlot()
    disp = ActionDispatcherProcessor(slot, counting_manager=mock_manager)
    # allow_one_direct_start() 호출 안 함 → 확답 없는 자발 발행
    action = StartCountingAction(exercise="푸시업", reps=10, sets=3, rest_sec=30)
    await _drive(disp, [CoachActionFrame(action=action)])

    mock_manager.start.assert_not_awaited()


async def test_spontaneous_start_while_idle_converts_to_proposal() -> None:
    """미카운팅 + 미확답 start_counting 은 직접 시작 X, 대신 *제안*으로 전환돼 슬롯 갱신.

    2026-06-09 버그: '플랭크로 하자'에 LLM이 start_counting(플랭크) 발행→거부됐는데 슬롯이
    이전(푸시업) 그대로라 다음 'ㄱㄱ'가 푸시업을 시작시켰다. 이제 슬롯이 플랭크로 갱신된다.
    """
    from app.core.coach_response import ProposeSetAction

    mock_manager = MagicMock()
    mock_manager.start = AsyncMock()
    mock_manager.is_active = False  # @property → 속성 접근 (호출 아님)

    slot = ConfirmSlot()
    disp = ActionDispatcherProcessor(slot, counting_manager=mock_manager)
    action = StartCountingAction(exercise="플랭크", reps=30, sets=1, rest_sec=30)
    await _drive(disp, [CoachActionFrame(action=action)])

    mock_manager.start.assert_not_awaited()  # 직접 시작은 안 함
    assert slot.has_pending
    pending = slot.pending_proposal
    assert isinstance(pending, ProposeSetAction)
    assert pending.exercise == "플랭크" and pending.reps == 30 and pending.sets == 1


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
