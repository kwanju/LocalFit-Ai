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
    ProposeSetAction,
    StartCountingAction,
)
from app.core.confirm_slot import ConfirmSlot
from app.pipecat_services.counting_manager import CountingManager
from app.pipecat_services.frames import CoachActionFrame

StartCountingFn = Callable[[StartCountingAction], Awaitable[None]]
LogConditionFn = Callable[[LogConditionAction], Awaitable[None]]


class ActionDispatcherProcessor(FrameProcessor):
    def allow_one_direct_start(self) -> None:
        """ConfirmRule이 사용자 확답을 받아 직접 start_counting 을 emit 할 때 호출."""
        self._allow_direct_start = True

    def __init__(
        self,
        slot: ConfirmSlot,
        *,
        start_counting: StartCountingFn | None = None,
        log_condition: LogConditionFn | None = None,
        counting_manager: CountingManager | None = None,
    ) -> None:
        super().__init__()
        self._slot = slot
        self._start_counting = start_counting
        self._log_condition = log_condition
        self._counting_manager = counting_manager
        # 사용자 확답 없이 직전 turn에 start_counting 들어왔는지 추적 (가드).
        # LLM이 propose_set 발행 시 True, start_counting 처리 후 False 로 리셋.
        self._allow_direct_start: bool = False

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

        logger.warning("dispatch: unknown action type {}", type(action).__name__)
