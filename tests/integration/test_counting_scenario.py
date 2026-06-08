"""실제 객체를 엮어 카운팅 시나리오를 구동하는 통합 테스트 (GPU/Ollama 불필요).

배경 (2026-06-07 회고 §2-3, §4-3): 단위 테스트는 mock 편중이라 런타임 배선 버그를
못 잡았다. 예) ``CountingManager.is_active`` 는 ``@property`` 인데 dispatcher가
``is_active()`` 로 호출 → ``'bool' object is not callable`` 런타임 에러. mock manager는
``is_active()`` 호출이 통과돼 단위 테스트가 잘못된 이유로 초록불이었다.

여기서는 **실제 CountingManager / CountingEngine / CountingInjectProcessor /
ActionDispatcher / ConfirmRule** 을 엮어 시나리오를 구동하고, ErrorFrame(파이프라인
예외) 이 뜨면 실패시킨다 — 사용자가 클릭으로 잡던 에러를 자동으로 잡는다.
"""

from __future__ import annotations

import asyncio

import pytest
from pipecat.frames.frames import ErrorFrame
from pipecat.tests.utils import run_test

from app.config import load_config
from app.core.coach_response import ProposeSetAction, StartCountingAction
from app.core.confirm_slot import ConfirmSlot
from app.pipecat_services.counting_manager import CountingManager
from app.pipecat_services.frames import CoachActionFrame
from app.pipecat_services.processors.action_dispatcher import ActionDispatcherProcessor
from app.pipecat_services.processors.counting_inject import CountingInjectProcessor

pytestmark = pytest.mark.asyncio


def _fast_counting_config():
    """실제 CountingConfig를 짧은 박자로 복제 — 테스트가 1초 내에 끝나도록."""
    cfg = load_config().counting
    return cfg.model_copy(update={"beat_interval_sec": 0.02, "start_delay_sec": 0.0})


def _assert_no_error_frame(frames) -> None:
    errors = [f for f in frames if isinstance(f, ErrorFrame)]
    assert not errors, f"파이프라인에서 ErrorFrame 발생: {[e.error for e in errors]}"


def _capture_inject_beats(inject: CountingInjectProcessor) -> list:
    """inject.push_frame을 가로채 다운스트림으로 나가는 frame을 수집."""
    captured: list = []

    async def _cap(frame, direction=None) -> None:
        captured.append(frame)

    inject.push_frame = _cap  # type: ignore[method-assign]
    return captured


# ---------------------------------------------------------------------------
# 시나리오 A — 자발(미확답) start_counting 이 실제 manager 를 거쳐도 안 터진다
#   (is_active @property 호출 버그 회귀 방어)
# ---------------------------------------------------------------------------


async def test_spontaneous_start_real_manager_no_error_frame() -> None:
    """미확답 start_counting → 실제 CountingManager.is_active 접근 → ErrorFrame 없어야."""
    manager = CountingManager(_fast_counting_config())
    slot = ConfirmSlot()
    disp = ActionDispatcherProcessor(slot, counting_manager=manager)

    # allow_one_direct_start() 호출 안 함 → 자발 발행. 이 경로가 is_active 를 만진다.
    action = StartCountingAction(exercise="푸시업", reps=10, sets=3, rest_sec=30)
    down, up = await run_test(disp, frames_to_send=[CoachActionFrame(action=action)])

    _assert_no_error_frame(list(down) + list(up))
    assert not manager.is_active, "미확답 발행은 카운팅을 시작시키면 안 됨"


# ---------------------------------------------------------------------------
# 시나리오 B — 확답 → 실제 엔진이 돌고 카운트 cue 가 빠짐없이 나온다 (Fix 2A)
# ---------------------------------------------------------------------------


async def test_confirmed_start_runs_engine_and_counts_all_reps() -> None:
    """확답 start → 실제 엔진 박자 → '하나/둘/셋' 모두 발화 (격려는 덧붙음, 숫자 안 빠짐)."""
    from pipecat.frames.frames import TTSSpeakFrame

    manager = CountingManager(_fast_counting_config())
    inject = CountingInjectProcessor()
    manager.attach_inject_processor(inject)
    captured = _capture_inject_beats(inject)

    slot = ConfirmSlot()
    disp = ActionDispatcherProcessor(slot, counting_manager=manager)

    # 확답 흐름 그대로: 가드 한 번 풀고 StartCountingAction 디스패치.
    disp.allow_one_direct_start()
    await disp._dispatch(StartCountingAction(exercise="푸시업", reps=3, sets=1, rest_sec=15))

    assert manager.is_active, "확답 후 카운팅이 시작돼야 함"

    # 엔진이 3렙(=down 3회)을 셀 때까지 대기 (메트로놈 up/down 교대 → rep당 2틱).
    for _ in range(100):
        await asyncio.sleep(0.02)
        if not manager.is_active:  # max_reps 도달 후 엔진 자가 종료
            break

    cue_texts = [f.text for f in captured if isinstance(f, TTSSpeakFrame)]
    joined = " ".join(cue_texts)
    # 하나·둘·셋이 모두 등장해야 한다 (격려가 숫자를 대체하던 버그 회귀 방어).
    for n in ("하나", "둘", "셋"):
        assert n in joined, f"카운트 '{n}' 누락 — cues={cue_texts}"

    await manager.stop()


# ---------------------------------------------------------------------------
# 시나리오 C — 카운팅 도중 자발 start_counting 은 조용히 무시(엔진 재시작 X, 에러 X)
# ---------------------------------------------------------------------------


async def test_spontaneous_start_while_active_is_ignored() -> None:
    """카운팅 진행 중 LLM 자발 start_counting → 엔진 재시작 안 함, 예외 없음 (Fix 2C)."""
    manager = CountingManager(_fast_counting_config())
    inject = CountingInjectProcessor()
    manager.attach_inject_processor(inject)
    _capture_inject_beats(inject)

    slot = ConfirmSlot()
    disp = ActionDispatcherProcessor(slot, counting_manager=manager)

    # 1) 확답으로 푸시업 시작
    disp.allow_one_direct_start()
    await disp._dispatch(StartCountingAction(exercise="푸시업", reps=50, sets=1, rest_sec=15))
    assert manager.is_active
    engine_before = manager._engine

    # 2) 진행 중 LLM 이 자발적으로 다른 운동 start_counting (미확답) — 무시돼야
    await disp._dispatch(StartCountingAction(exercise="플랭크", reps=30, sets=1, rest_sec=15))
    assert manager._engine is engine_before, "진행 중 자발 발행이 엔진을 갈아치우면 안 됨"

    await manager.stop()
    assert not manager.is_active


# ---------------------------------------------------------------------------
# 시나리오 D — propose → "시작" 확답 전체 흐름을 파이프라인으로 (ErrorFrame 감시)
# ---------------------------------------------------------------------------


async def test_full_confirm_flow_through_pipeline_no_error() -> None:
    """제안 적재 → '시작' Transcription → confirm·dispatcher·manager 전 구간 ErrorFrame 없음."""
    from pipecat.frames.frames import TranscriptionFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.utils.time import time_now_iso8601

    from app.pipecat_services.processors.confirm_rule import ConfirmRuleProcessor

    manager = CountingManager(_fast_counting_config())
    inject = CountingInjectProcessor()
    manager.attach_inject_processor(inject)

    slot = ConfirmSlot()
    slot.set(ProposeSetAction(exercise="스쿼트", reps=2, sets=1, rest_sec=15))
    disp = ActionDispatcherProcessor(slot, counting_manager=manager)
    confirm = ConfirmRuleProcessor(slot, dispatcher=disp)

    pipeline = Pipeline([confirm, disp])
    down, up = await run_test(
        pipeline,
        frames_to_send=[
            TranscriptionFrame(text="시작", user_id="u", timestamp=time_now_iso8601())
        ],
    )

    _assert_no_error_frame(list(down) + list(up))
    assert manager.is_active, "'시작' 확답으로 카운팅이 시작돼야 함"
    await manager.stop()


# ---------------------------------------------------------------------------
# 시나리오 E — C2C 채팅 확답(InputTextRawFrame) 으로도 카운팅이 시작된다
#   (채팅 입력이 TextFrame이라 ConfirmRule을 통과하던 버그 회귀 방어, 2026-06-08)
# ---------------------------------------------------------------------------


async def test_chat_confirm_starts_counting() -> None:
    """채팅 'ㄱㄱ'(InputTextRawFrame) → confirm·dispatcher·manager → 카운팅 시작, 에러 없음."""
    from pipecat.frames.frames import InputTextRawFrame
    from pipecat.pipeline.pipeline import Pipeline

    from app.pipecat_services.processors.confirm_rule import ConfirmRuleProcessor

    manager = CountingManager(_fast_counting_config())
    inject = CountingInjectProcessor()
    manager.attach_inject_processor(inject)

    slot = ConfirmSlot()
    slot.set(ProposeSetAction(exercise="푸시업", reps=2, sets=1, rest_sec=15))
    disp = ActionDispatcherProcessor(slot, counting_manager=manager)
    confirm = ConfirmRuleProcessor(slot, dispatcher=disp)

    pipeline = Pipeline([confirm, disp])
    down, up = await run_test(pipeline, frames_to_send=[InputTextRawFrame(text="ㄱㄱ")])

    _assert_no_error_frame(list(down) + list(up))
    assert manager.is_active, "채팅 'ㄱㄱ' 확답으로 카운팅이 시작돼야 함"
    await manager.stop()
