import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

from loguru import logger

from app.utils.timer import beat_scheduler


class ExerciseMode(StrEnum):
    metronome = "metronome"  # pullup, pushup, squat — alternating up/down phases
    timer = "timer"          # plank — elapsed-time ticks


@dataclass
class BeatEvent:
    rep: int          # completed rep count (increments on "down" phase)
    phase: str        # "up" | "down" (metronome) | "tick" (timer)
    elapsed_sec: float


class CountingEngine:
    """LLM-independent beat engine. Run as an asyncio.Task via start()."""

    def __init__(
        self,
        mode: ExerciseMode,
        interval_sec: float,
        on_beat: Callable[[BeatEvent], Awaitable[None]],
        max_reps: int = 200,
        target_duration_sec: float | None = None,
    ) -> None:
        self._mode = mode
        self._interval_sec = interval_sec
        self._on_beat = on_beat
        self._max_reps = max_reps
        self._target_duration_sec = target_duration_sec
        self._rep: int = 0
        self._phase: str = "up"
        self._start_time: float | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def current_rep(self) -> int:
        return self._rep

    @property
    def elapsed_sec(self) -> float:
        if self._start_time is None:
            return 0.0
        return time.monotonic() - self._start_time

    async def start(self) -> None:
        if self._task is not None:
            logger.warning("CountingEngine.start() called while already running")
            return
        self._start_time = time.monotonic()
        self._rep = 0
        self._phase = "up"
        callback = (
            self._metronome_tick if self._mode == ExerciseMode.metronome else self._timer_tick
        )
        self._task = asyncio.create_task(beat_scheduler(self._interval_sec, callback))
        logger.info(
            "CountingEngine started: mode=%s interval=%.2fs", self._mode.value, self._interval_sec
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        logger.info(
            "CountingEngine stopped: reps=%d elapsed=%.1fs", self._rep, self.elapsed_sec
        )

    async def pause(self) -> None:
        """Pause is implemented as stop; resume by calling start() again."""
        await self.stop()

    async def _metronome_tick(self) -> None:
        await self._on_beat(
            BeatEvent(rep=self._rep, phase=self._phase, elapsed_sec=self.elapsed_sec)
        )
        if self._phase == "down":
            self._rep += 1
            if self._rep >= self._max_reps:
                logger.info("CountingEngine: max reps reached (%d)", self._rep)
                task = asyncio.current_task()
                if task:
                    task.cancel()
                return
        self._phase = "down" if self._phase == "up" else "up"

    async def _timer_tick(self) -> None:
        elapsed = self.elapsed_sec
        await self._on_beat(BeatEvent(rep=0, phase="tick", elapsed_sec=elapsed))
        if self._target_duration_sec is not None and elapsed >= self._target_duration_sec:
            logger.info("CountingEngine: target duration reached (%.1fs)", elapsed)
            task = asyncio.current_task()
            if task:
                task.cancel()
