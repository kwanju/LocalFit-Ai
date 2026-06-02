"""ActionDispatcherProcessor — consumes ``CoachActionFrame`` emitted by
``StructuredOllamaProcessor`` and runs the side effects (ADR-013 §액션 디스패처,
phase-5 §5-7).

This processor sits AFTER the LLM and BEFORE the sentence aggregator + TTS.
``CoachActionFrame`` itself is swallowed (not forwarded) so it never reaches
the TTS; ``TextFrame`` and everything else are passed through.

CountingEngine wiring is deliberately optional — phase-6 will connect it.
``ConditionRepository`` write is also optional (NULL repo just logs) so this
processor stays usable in pipelines that run without a DB session.
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
from app.pipecat_services.frames import CoachActionFrame

# Phase-6 will replace this with a real CountingEngine.start(exercise, reps).
StartCountingFn = Callable[[StartCountingAction], Awaitable[None]]
LogConditionFn = Callable[[LogConditionAction], Awaitable[None]]


class ActionDispatcherProcessor(FrameProcessor):
    def __init__(
        self,
        slot: ConfirmSlot,
        *,
        start_counting: StartCountingFn | None = None,
        log_condition: LogConditionFn | None = None,
    ) -> None:
        super().__init__()
        self._slot = slot
        self._start_counting = start_counting
        self._log_condition = log_condition

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
            logger.info(
                "dispatch start_counting: exercise={} reps={}",
                action.exercise, action.reps,
            )
            if self._start_counting is not None:
                try:
                    await self._start_counting(action)
                except Exception as e:  # noqa: BLE001 — logged, never break pipeline
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
                except Exception as e:  # noqa: BLE001 — logged, never break pipeline
                    logger.error("log_condition dispatch failed: {}", e)
            return

        logger.warning("dispatch: unknown action type {}", type(action).__name__)
