"""ActionDispatcherProcessor — propose / start / log dispatch (ADR-013)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from pipecat.frames.frames import (
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TextFrame,
)
from pipecat.tests.utils import run_test

from app.core.coach_response import (
    LogConditionAction,
    ProposeCalendarSyncAction,
    ProposePlanAction,
    ProposePlanAdjustmentAction,
    ProposeSetAction,
    RecordConstraintAction,
    RememberFactAction,
    SetBaselineAction,
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
    action = LogConditionAction(fatigue_level=8, soreness=4, notes="다리 무거움")
    await _drive(disp, [CoachActionFrame(action=action)])
    cb.assert_awaited_once()
    assert cb.call_args.args[0] == action


async def test_log_condition_does_not_change_intensity() -> None:
    """ADR-023/024 회귀 가드: 컨디션 기록은 사용자 확답 없이 강도를 자동 변경하지 않는다.

    log_condition 디스패치가 카운팅을 시작하거나 제안 슬롯을 채우면 안 된다 — 강도 조절은
    propose_set → ConfirmRule 확답 경로로만 일어난다."""
    slot = ConfirmSlot()
    manager = AsyncMock(is_active=False)
    disp = ActionDispatcherProcessor(
        slot, log_condition=AsyncMock(), counting_manager=manager
    )
    await _drive(
        disp, [CoachActionFrame(action=LogConditionAction(fatigue_level=9, soreness=5))]
    )
    manager.start.assert_not_called()
    assert not slot.has_pending


async def test_record_constraint_invokes_callback() -> None:
    """ADR-025 — record_constraint 는 확답 없이 즉시 콜백 호출(안전 직결)."""
    slot = ConfirmSlot()
    cb = AsyncMock()
    disp = ActionDispatcherProcessor(slot, record_constraint=cb)
    action = RecordConstraintAction(kind="injury", text="왼쪽 어깨 통증")
    await _drive(disp, [CoachActionFrame(action=action)])
    cb.assert_awaited_once()
    assert cb.call_args.args[0] == action


async def test_remember_fact_invokes_callback() -> None:
    slot = ConfirmSlot()
    cb = AsyncMock()
    disp = ActionDispatcherProcessor(slot, remember_fact=cb)
    action = RememberFactAction(text="아침 운동을 선호함", tags=["선호"])
    await _drive(disp, [CoachActionFrame(action=action)])
    cb.assert_awaited_once()
    assert cb.call_args.args[0] == action


async def test_set_baseline_invokes_callback() -> None:
    """ADR-028 — set_baseline 은 (대화로 확인된) 자가보고치라 확답 없이 즉시 저장."""
    slot = ConfirmSlot()
    cb = AsyncMock()
    disp = ActionDispatcherProcessor(slot, set_baseline=cb)
    action = SetBaselineAction(
        entries=[{"exercise": "푸시업", "metric": "reps", "value": 15}]
    )
    await _drive(disp, [CoachActionFrame(action=action)])
    cb.assert_awaited_once()
    assert cb.call_args.args[0] == action
    # 기준선 저장은 운동 시작이 아니다 — 슬롯/카운팅을 건드리면 안 됨.
    assert not slot.has_pending


async def test_set_baseline_does_not_start_counting() -> None:
    """회귀 가드: 기준선 저장이 카운팅을 직접 시작시키지 않는다(시작은 propose_set 확답)."""
    slot = ConfirmSlot()
    manager = AsyncMock(is_active=False)
    disp = ActionDispatcherProcessor(
        slot, set_baseline=AsyncMock(), counting_manager=manager
    )
    await _drive(
        disp,
        [CoachActionFrame(action=SetBaselineAction(entries=[{"exercise": "스쿼트", "value": 20}]))],
    )
    manager.start.assert_not_called()


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


# --- ADR-024 플랜 확답 게이트 (회귀 가드) ----------------------------------


async def test_propose_plan_without_confirm_does_not_commit() -> None:
    """회귀 가드: 사용자 확답 없이 LLM 이 propose_plan 을 내면 **저장 안 함** — 제안 슬롯에만
    들어가야 한다(회고가 경고한 '확답 없이 플랜 변경' 패턴 차단, ADR-024)."""
    slot = ConfirmSlot()
    commit = AsyncMock()
    disp = ActionDispatcherProcessor(slot, commit_plan=commit)
    action = ProposePlanAction(goals=[{"exercise": "푸시업", "target_count": 3, "reps": 10}])
    await _drive(disp, [CoachActionFrame(action=action)])
    commit.assert_not_awaited()           # 저장 금지
    assert slot.has_pending_plan          # 제안만 보류
    assert slot.pending_plan == action


async def test_propose_plan_commits_only_after_allow() -> None:
    """확답(ConfirmRule)이 allow_one_plan_commit() 를 켠 뒤에만 commit 콜백이 호출된다."""
    slot = ConfirmSlot()
    commit = AsyncMock()
    disp = ActionDispatcherProcessor(slot, commit_plan=commit)
    disp.allow_one_plan_commit()  # 사용자 확답 시뮬레이트
    action = ProposePlanAction(goals=[{"exercise": "스쿼트", "target_count": 2, "reps": 15}])
    await _drive(disp, [CoachActionFrame(action=action)])
    commit.assert_awaited_once()
    assert commit.call_args.args[0] == action
    assert not slot.has_pending_plan


async def test_plan_adjustment_without_confirm_does_not_apply() -> None:
    """회귀 가드: 조정 제안도 확답 없이는 적용 안 됨(자동 변경 금지)."""
    slot = ConfirmSlot()
    commit = AsyncMock()
    disp = ActionDispatcherProcessor(slot, commit_plan_adjustment=commit)
    action = ProposePlanAdjustmentAction(exercise="푸시업", new_target_count=2)
    await _drive(disp, [CoachActionFrame(action=action)])
    commit.assert_not_awaited()
    assert slot.has_pending_plan


async def test_plan_adjustment_commits_only_after_allow() -> None:
    slot = ConfirmSlot()
    commit = AsyncMock()
    disp = ActionDispatcherProcessor(slot, commit_plan_adjustment=commit)
    disp.allow_one_plan_commit()
    action = ProposePlanAdjustmentAction(exercise="푸시업", new_target_count=2)
    await _drive(disp, [CoachActionFrame(action=action)])
    commit.assert_awaited_once()
    assert commit.call_args.args[0] == action


async def test_allow_plan_commit_resets_after_one_use() -> None:
    """가드는 한 번 쓰면 리셋 — 다음 LLM 발행은 다시 제안으로만 보류된다."""
    slot = ConfirmSlot()
    commit = AsyncMock()
    disp = ActionDispatcherProcessor(slot, commit_plan=commit)
    disp.allow_one_plan_commit()
    a1 = ProposePlanAction(goals=[{"exercise": "풀업", "target_count": 1, "reps": 5}])
    a2 = ProposePlanAction(goals=[{"exercise": "스쿼트", "target_count": 2, "reps": 15}])
    await _drive(disp, [CoachActionFrame(action=a1)])
    await _drive(disp, [CoachActionFrame(action=a2)])
    commit.assert_awaited_once()          # 첫 번째만 commit
    assert slot.pending_plan == a2        # 두 번째는 다시 보류


async def test_calendar_sync_without_confirm_does_not_register() -> None:
    """회귀 가드 (ADR-022 §9-2): 확답 없이 LLM 이 propose_calendar_sync 를 내면 **등록
    안 함** — 제안 슬롯에만 들어가야 한다(자동 등록 금지)."""
    slot = ConfirmSlot()
    commit = AsyncMock()
    disp = ActionDispatcherProcessor(slot, commit_calendar_sync=commit)
    action = ProposeCalendarSyncAction()
    await _drive(disp, [CoachActionFrame(action=action)])
    commit.assert_not_awaited()              # 등록 금지
    assert slot.has_pending_calendar         # 제안만 보류
    assert slot.pending_calendar == action


async def test_calendar_sync_commits_only_after_allow() -> None:
    """확답(ConfirmRule)이 allow_one_calendar_commit() 를 켠 뒤에만 등록 콜백이 호출된다."""
    slot = ConfirmSlot()
    commit = AsyncMock()
    disp = ActionDispatcherProcessor(slot, commit_calendar_sync=commit)
    disp.allow_one_calendar_commit()  # 사용자 확답 시뮬레이트
    action = ProposeCalendarSyncAction()
    await _drive(disp, [CoachActionFrame(action=action)])
    commit.assert_awaited_once()
    assert not slot.has_pending_calendar


async def test_set_baseline_without_proposal_triggers_followup() -> None:
    """말-행동 안전망(ADR-032): set_baseline 만 내고 propose_set 이 없으면 첫 세션이
    정지하므로 follow-up 을 요청해야 한다."""
    slot = ConfirmSlot()
    followup = AsyncMock()
    disp = ActionDispatcherProcessor(slot, set_baseline=AsyncMock(), request_followup=followup)
    baseline = SetBaselineAction(entries=[{"exercise": "스쿼트", "metric": "reps", "value": 50}])
    await _drive(
        disp,
        [
            LLMFullResponseStartFrame(),
            CoachActionFrame(action=baseline),
            LLMFullResponseEndFrame(),
        ],
    )
    followup.assert_awaited_once()


async def test_set_baseline_with_proposal_no_followup() -> None:
    """같은 응답에 propose_set 이 함께 오면(ADR-028 정상 경로) follow-up 은 없다."""
    slot = ConfirmSlot()
    followup = AsyncMock()
    disp = ActionDispatcherProcessor(slot, set_baseline=AsyncMock(), request_followup=followup)
    baseline = SetBaselineAction(entries=[{"exercise": "스쿼트", "metric": "reps", "value": 50}])
    proposal = ProposeSetAction(exercise="스쿼트", reps=35, sets=3, rest_sec=60)
    await _drive(
        disp,
        [
            LLMFullResponseStartFrame(),
            CoachActionFrame(action=baseline),
            CoachActionFrame(action=proposal),
            LLMFullResponseEndFrame(),
        ],
    )
    followup.assert_not_awaited()
