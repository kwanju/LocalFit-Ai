"""ConfirmRuleProcessor — accept/reject/no-match flows (ADR-013)."""

from __future__ import annotations

import pytest
from pipecat.frames.frames import Frame, TextFrame, TranscriptionFrame
from pipecat.tests.utils import run_test
from pipecat.utils.time import time_now_iso8601

from app.core.coach_response import (
    ProposePlanAction,
    ProposePlanAdjustmentAction,
    ProposeSetAction,
    StartCountingAction,
)
from app.core.confirm_slot import ConfirmSlot
from app.pipecat_services.frames import CoachActionFrame
from app.pipecat_services.processors.action_dispatcher import ActionDispatcherProcessor
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
    "reply",
    [
        "좋아요", "응", "네", "ok", "OK", "오케이", "콜", "시작하자", "그래", "하자",
        # 활용형/문장형 확답 (2026-06-08 fix: 정확 토큰만 보면 놓쳤던 케이스)
        "운동을 시작할게요", "시작할게요", "자 운동하자", "네 시작하죠",
        # 구어/슬랭 긍정형 확대 (2026-06-08 사용자 요청)
        "ㄱㄱ", "고고", "고고씽", "가즈아", "가시죠", "해보자", "당연하지", "ㅇㅋ", "넵", "예스",
    ],
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
    # 부정형은 accept stem(할게/해요/가요)을 품어도 reject가 우선이어야 함 (2026-06-08).
    "reply", ["아니", "싫어", "패스", "나중에", "안 할래", "스킵", "나중에 할게",
              "안 해요", "안 할게", "안 가요", "별로"]
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


@pytest.mark.parametrize(
    "reply", ["5세트로 하자", "휴식 60초로 시작", "20개로 하자", "다섯 세트로 가자"]
)
async def test_modifying_accept_forwarded_to_llm_not_auto_started(reply: str) -> None:
    """수정 의도가 담긴 확답은 기존 제안을 그대로 시작하면 안 됨 — LLM으로 통과 (2026-06-08).

    예: 코치가 '3세트' 제안 → 사용자 '5세트로 하자' → 3세트로 시작되면 버그.
    """
    slot = ConfirmSlot()
    slot.set(_proposal())  # 푸시업 10회 3세트
    frames = await _send(reply, slot)

    actions = [f for f in frames if isinstance(f, CoachActionFrame)]
    transcripts = [f for f in frames if isinstance(f, TranscriptionFrame)]
    assert actions == [], f"수정 확답 '{reply}' 인데 start_counting 자동 발행됨"
    assert len(transcripts) == 1, "LLM이 갱신 제안하도록 발화가 통과돼야 함"
    assert slot.has_pending  # 제안 유지 (LLM이 propose_set 으로 덮어씀)


async def test_no_match_keeps_slot_and_forwards() -> None:
    slot = ConfirmSlot()
    slot.set(_proposal())
    frames = await _send("오늘 날씨 어때요", slot)
    actions = [f for f in frames if isinstance(f, CoachActionFrame)]
    transcripts = [f for f in frames if isinstance(f, TranscriptionFrame)]
    assert actions == []
    assert len(transcripts) == 1
    assert slot.has_pending  # untouched


async def test_chat_input_text_raw_frame_accepts() -> None:
    """채팅 입력(InputTextRawFrame)도 확답으로 인식 — C2C 카운트 미시작 버그 (2026-06-08)."""
    from pipecat.frames.frames import InputTextRawFrame

    slot = ConfirmSlot()
    slot.set(_proposal())
    down, _ = await run_test(
        ConfirmRuleProcessor(slot),
        frames_to_send=[InputTextRawFrame(text="ㄱㄱ")],
    )
    actions = [f for f in down if isinstance(f, CoachActionFrame)]
    assert len(actions) == 1
    assert isinstance(actions[0].action, StartCountingAction)
    assert not slot.has_pending


async def test_accept_without_proposal_passes_through() -> None:
    slot = ConfirmSlot()  # empty
    frames = await _send("좋아요", slot)
    actions = [f for f in frames if isinstance(f, CoachActionFrame)]
    transcripts = [f for f in frames if isinstance(f, TranscriptionFrame)]
    assert actions == []
    assert len(transcripts) == 1


# --- ADR-024 플랜 제안 확답 게이트 -----------------------------------------


async def _send_with_dispatcher(
    text: str, slot: ConfirmSlot, dispatcher: ActionDispatcherProcessor
) -> list[Frame]:
    down, _ = await run_test(
        ConfirmRuleProcessor(slot, dispatcher=dispatcher),
        frames_to_send=[
            TranscriptionFrame(text=text, user_id="u", timestamp=time_now_iso8601())
        ],
    )
    return list(down)


async def test_accept_plan_emits_commit_and_arms_dispatcher() -> None:
    """플랜 제안에 확답하면 같은 액션을 재발행하고 dispatcher 의 commit 가드를 켠다."""
    slot = ConfirmSlot()
    plan = ProposePlanAction(goals=[{"exercise": "푸시업", "target_count": 3, "reps": 10}])
    slot.set_plan(plan)
    dispatcher = ActionDispatcherProcessor(slot)

    frames = await _send_with_dispatcher("좋아요", slot, dispatcher)

    actions = [f for f in frames if isinstance(f, CoachActionFrame)]
    assert len(actions) == 1
    assert isinstance(actions[0].action, ProposePlanAction)
    # commit 가드가 켜짐 — dispatcher 가 이 액션을 받으면 저장한다.
    assert dispatcher._allow_plan_commit is True  # noqa: SLF001
    assert not slot.has_pending_plan
    ack = next(f for f in frames if type(f) is TextFrame)
    assert "목표" in ack.text


async def test_accept_plan_adjustment_emits_action_without_premature_ack() -> None:
    """조정 확답은 액션만 발행하고 commit 가드를 켜되, **확정 ack 는 말하지 않는다** —
    실제 적용 결과(활성 플랜 유무)는 commit 콜백 follow-up 이 안내한다(D-2 후속)."""
    slot = ConfirmSlot()
    slot.set_plan(ProposePlanAdjustmentAction(exercise="푸시업", new_target_count=2))
    dispatcher = ActionDispatcherProcessor(slot)
    frames = await _send_with_dispatcher("응", slot, dispatcher)
    actions = [f for f in frames if isinstance(f, CoachActionFrame)]
    assert isinstance(actions[0].action, ProposePlanAdjustmentAction)
    assert dispatcher._allow_plan_commit is True  # noqa: SLF001
    assert not slot.has_pending_plan
    # 미리 "조정할게요" 류 확정 ack 를 말하지 않는다.
    assert [f for f in frames if type(f) is TextFrame] == []


async def test_reject_plan_clears_pending() -> None:
    slot = ConfirmSlot()
    slot.set_plan(ProposePlanAction(goals=[{"exercise": "스쿼트", "target_count": 2}]))
    frames = await _send("아니요", slot)
    actions = [f for f in frames if isinstance(f, CoachActionFrame)]
    transcripts = [f for f in frames if isinstance(f, TranscriptionFrame)]
    assert actions == []
    assert len(transcripts) == 1  # LLM 으로 통과
    assert not slot.has_pending_plan


async def test_modifying_accept_keeps_plan_for_llm() -> None:
    """수정 의도가 담긴 확답("2회로 줄이자")은 자동 commit 하지 않고 LLM 으로 통과."""
    slot = ConfirmSlot()
    slot.set_plan(ProposePlanAction(goals=[{"exercise": "푸시업", "target_count": 3}]))
    frames = await _send("2회로 줄이자", slot)
    actions = [f for f in frames if isinstance(f, CoachActionFrame)]
    transcripts = [f for f in frames if isinstance(f, TranscriptionFrame)]
    assert actions == []
    assert len(transcripts) == 1
    assert slot.has_pending_plan  # 제안 유지 (LLM 이 갱신 제안으로 덮음)
