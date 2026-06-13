"""ActionDispatcherProcessor — consumes ``CoachActionFrame`` emitted by
``StructuredOllamaProcessor`` and runs the side effects (ADR-013 §액션 디스패처,
phase-5 §5-7).

Phase-6: ``CountingManager`` is injected and called for ``StartCountingAction``
(ADR-014 §트리거 경로). The legacy ``start_counting`` callable is kept for
backward compat with unit tests that don't use a full ``CountingManager``.

This processor sits AFTER the LLM and BEFORE the sentence aggregator + TTS.
``CoachActionFrame`` itself is swallowed (not forwarded) so it never reaches
the TTS; ``TextFrame`` and everything else are passed through.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from loguru import logger
from pipecat.frames.frames import Frame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from app.core.coach_response import (
    LogConditionAction,
    ProposePlanAction,
    ProposePlanAdjustmentAction,
    ProposeSetAction,
    RecordConstraintAction,
    RememberFactAction,
    StartCountingAction,
)
from app.core.confirm_slot import ConfirmSlot
from app.pipecat_services.counting_manager import CountingManager
from app.pipecat_services.frames import CoachActionFrame

StartCountingFn = Callable[[StartCountingAction], Awaitable[None]]
LogConditionFn = Callable[[LogConditionAction], Awaitable[None]]
RecordConstraintFn = Callable[[RecordConstraintAction], Awaitable[None]]
RememberFactFn = Callable[[RememberFactAction], Awaitable[None]]
CommitPlanFn = Callable[[ProposePlanAction], Awaitable[None]]
CommitPlanAdjustmentFn = Callable[[ProposePlanAdjustmentAction], Awaitable[None]]


class ActionDispatcherProcessor(FrameProcessor):
    def allow_one_direct_start(self) -> None:
        """ConfirmRule이 사용자 확답을 받아 직접 start_counting 을 emit 할 때 호출."""
        self._allow_direct_start = True

    def allow_one_plan_commit(self) -> None:
        """ConfirmRule이 플랜 제안에 대한 사용자 확답을 받아 commit 을 트리거할 때 호출
        (ADR-024). 한 번 쓰면 리셋 — 확답 없는 LLM 플랜 발행은 절대 저장 안 됨."""
        self._allow_plan_commit = True

    def __init__(
        self,
        slot: ConfirmSlot,
        *,
        start_counting: StartCountingFn | None = None,
        log_condition: LogConditionFn | None = None,
        record_constraint: RecordConstraintFn | None = None,
        remember_fact: RememberFactFn | None = None,
        commit_plan: CommitPlanFn | None = None,
        commit_plan_adjustment: CommitPlanAdjustmentFn | None = None,
        counting_manager: CountingManager | None = None,
    ) -> None:
        super().__init__()
        self._slot = slot
        self._start_counting = start_counting
        self._log_condition = log_condition
        self._record_constraint = record_constraint
        self._remember_fact = remember_fact
        self._commit_plan = commit_plan
        self._commit_plan_adjustment = commit_plan_adjustment
        self._counting_manager = counting_manager
        # 사용자 확답 없이 직전 turn에 start_counting 들어왔는지 추적 (가드).
        # LLM이 propose_set 발행 시 True, start_counting 처리 후 False 로 리셋.
        self._allow_direct_start: bool = False
        # 플랜 commit 가드 (ADR-024) — 확답 없는 플랜 변경 금지.
        self._allow_plan_commit: bool = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, CoachActionFrame) and frame.action is not None:
            await self._dispatch(frame.action)
            return  # don't forward CoachActionFrame to TTS

        await self.push_frame(frame, direction)

    async def _dispatch(self, action) -> None:
        if isinstance(action, ProposeSetAction):
            self._slot.set(action)
            logger.info(
                "dispatch propose_set: exercise={} reps={} sets={} rest={}s",
                action.exercise, action.reps, action.sets, action.rest_sec,
            )
            return

        if isinstance(action, StartCountingAction):
            # 가드: 사용자 확답 없이는 LLM 마음대로 운동 시작 못 함 (2026-06-07 사용자 피드백).
            # ConfirmRule에서 검증된 accept-keyword 응답일 때만 has_pending 이 막 비워졌으니
            # _allow_direct_start 가 True (ConfirmRule이 직접 만든 액션). LLM 이 자기 마음대로
            # 발행한 액션은 모두 거부.
            if not self._allow_direct_start:
                # 이미 카운팅 진행 중이면 LLM의 자발적 start_counting 은 정상 흐름의
                # 잡음(엔진이 주도 중)이므로 경고 없이 조용히 무시 (2026-06-07 폭주 fix).
                if self._counting_manager is not None and self._counting_manager.is_active:
                    logger.debug(
                        "start_counting ignored — counting already in progress; "
                        "exercise={} (LLM 자발 발행, 정상)",
                        action.exercise,
                    )
                    return
                # 사용자 확답 없이 LLM이 발행한 start_counting 은 직접 시작하면 안 되지만,
                # 그냥 버리면 사용자가 바꾼 운동(예: "플랭크로 하자")이 슬롯에 반영 안 돼
                # 다음 확답("ㄱㄱ")이 *이전* 제안(푸시업)을 시작시킨다(2026-06-09 버그).
                # → **제안(pending proposal)으로 전환**해 슬롯을 갱신한다. 실제 시작은
                #    여전히 사용자 확답이 ConfirmRule 을 거쳐야 일어난다.
                self._slot.set(
                    ProposeSetAction(
                        exercise=action.exercise,
                        reps=action.reps,
                        sets=action.sets,
                        rest_sec=action.rest_sec,
                    )
                )
                logger.info(
                    "start_counting(미확답) → 제안으로 전환: exercise={} reps={} sets={} rest={}s",
                    action.exercise, action.reps, action.sets, action.rest_sec,
                )
                return
            self._allow_direct_start = False  # 한 번 쓰면 리셋.
            logger.info(
                "dispatch start_counting: exercise={} reps={} sets={} rest={}s",
                action.exercise, action.reps, action.sets, action.rest_sec,
            )
            if self._counting_manager is not None:
                try:
                    # multi-set 지원 (2026-06-07).
                    await self._counting_manager.start(
                        action.exercise,
                        action.reps,
                        sets=action.sets,
                        rest_sec=action.rest_sec,
                    )
                except Exception as e:  # noqa: BLE001 — logged, never break pipeline
                    logger.error("counting_manager.start dispatch failed: {}", e)
            elif self._start_counting is not None:
                try:
                    await self._start_counting(action)
                except Exception as e:  # noqa: BLE001
                    logger.error("start_counting dispatch failed: {}", e)
            return

        if isinstance(action, LogConditionAction):
            logger.info(
                "dispatch log_condition: fatigue={} notes={}",
                action.fatigue_level, action.notes,
            )
            if self._log_condition is not None:
                try:
                    await self._log_condition(action)
                except Exception as e:  # noqa: BLE001
                    logger.error("log_condition dispatch failed: {}", e)
            return

        if isinstance(action, RecordConstraintAction):
            # 안전 직결 — 확답 없이 즉시 저장 (ADR-025, 2026-06-10 사용자 결정).
            logger.info(
                "dispatch record_constraint: kind={} text={} severity={}",
                action.kind, action.text, action.severity,
            )
            if self._record_constraint is not None:
                try:
                    await self._record_constraint(action)
                except Exception as e:  # noqa: BLE001
                    logger.error("record_constraint dispatch failed: {}", e)
            return

        if isinstance(action, RememberFactAction):
            logger.info("dispatch remember_fact: text={} tags={}", action.text, action.tags)
            if self._remember_fact is not None:
                try:
                    await self._remember_fact(action)
                except Exception as e:  # noqa: BLE001
                    logger.error("remember_fact dispatch failed: {}", e)
            return

        if isinstance(action, ProposePlanAction):
            # 확답 게이트 (ADR-024): 사용자 확답 없이는 플랜을 저장하지 않는다. LLM 발행은
            # 제안 슬롯에만 들어가고, 실제 commit 은 ConfirmRule 이 확답을 받아
            # allow_one_plan_commit() 를 켠 뒤 같은 액션을 재발행할 때만 일어난다.
            if not self._allow_plan_commit:
                self._slot.set_plan(action)
                logger.info(
                    "dispatch propose_plan (pending, 확답 대기): goals={}",
                    [(g.exercise, g.target_count) for g in action.goals],
                )
                return
            self._allow_plan_commit = False
            logger.info(
                "dispatch commit_plan: goals={}",
                [(g.exercise, g.target_count) for g in action.goals],
            )
            if self._commit_plan is not None:
                try:
                    await self._commit_plan(action)
                except Exception as e:  # noqa: BLE001
                    logger.error("commit_plan dispatch failed: {}", e)
            return

        if isinstance(action, ProposePlanAdjustmentAction):
            if not self._allow_plan_commit:
                self._slot.set_plan(action)
                logger.info(
                    "dispatch propose_plan_adjustment (pending, 확답 대기): "
                    "exercise={} new_target={}",
                    action.exercise, action.new_target_count,
                )
                return
            self._allow_plan_commit = False
            logger.info(
                "dispatch commit_plan_adjustment: exercise={} new_target={}",
                action.exercise, action.new_target_count,
            )
            if self._commit_plan_adjustment is not None:
                try:
                    await self._commit_plan_adjustment(action)
                except Exception as e:  # noqa: BLE001
                    logger.error("commit_plan_adjustment dispatch failed: {}", e)
            return

        logger.warning("dispatch: unknown action type {}", type(action).__name__)
