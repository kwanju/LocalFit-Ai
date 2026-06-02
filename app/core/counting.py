import asyncio
import contextlib
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

from loguru import logger

from app.core.counting_cues import (
    get_beat_pool,
    get_encouragement_pool,
    pick_cue,
)
from app.utils.timer import beat_scheduler


class ExerciseMode(StrEnum):
    metronome = "metronome"  # pullup, pushup, squat — alternating up/down phases
    timer = "timer"          # plank — elapsed-time ticks


@dataclass
class BeatEvent:
    rep: int          # completed rep count (increments on "down" phase)
    phase: str        # "up" | "down" (metronome) | "tick" (timer)
    elapsed_sec: float
    cue: str = ""     # beat or encouragement text (phase-6 addition)


@dataclass
class CompleteEvent:
    reps_completed: int
    elapsed_sec: float
    exercise_name: str = ""
    duration_sec: float | None = None  # set for timer mode (plank)


# Sorted mapping from encouragement threshold rank to pool key
_ENC_POOL_KEYS: list[str] = ["first_third", "second_third", "last"]


class CountingEngine:
    """LLM-independent beat engine. Run as an asyncio.Task via start()."""

    def __init__(
        self,
        mode: ExerciseMode,
        interval_sec: float,
        on_beat: Callable[[BeatEvent], Awaitable[None]],
        max_reps: int = 200,
        target_duration_sec: float | None = None,
        # phase-6 additions — all optional for backward compat
        exercise_name: str = "",
        cue_mode: str = "random",
        start_delay_sec: float = 0.0,
        encouragement_points: list[float] | None = None,
        rng_seed: int | None = None,
    ) -> None:
        self._mode = mode
        self._interval_sec = interval_sec
        self._on_beat = on_beat
        self._max_reps = max_reps
        self._target_duration_sec = target_duration_sec
        self._exercise_name = exercise_name
        self._cue_mode = cue_mode
        self._start_delay_sec = start_delay_sec
        self._encouragement_points: list[float] = sorted(encouragement_points or [])
        self._rng = random.Random(rng_seed)

        self._rep: int = 0
        self._phase: str = "up"
        self._start_time: float | None = None
        self._task: asyncio.Task[None] | None = None

        # Cue state (phase-6)
        self._seq_counters: dict[str, int] = {}
        self._fired_enc: set[int] = set()  # indices of already-fired encouragement points

        # on_complete is settable after construction (phase-6)
        self.on_complete: Callable[[CompleteEvent], Awaitable[None]] | None = None

    # --- on_beat property (settable for CountingInjectProcessor wiring) ---

    @property
    def on_beat(self) -> Callable[[BeatEvent], Awaitable[None]]:
        return self._on_beat

    @on_beat.setter
    def on_beat(self, fn: Callable[[BeatEvent], Awaitable[None]]) -> None:
        self._on_beat = fn

    # --- public interface ---

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
        self._seq_counters.clear()
        self._fired_enc.clear()
        callback = (
            self._metronome_tick if self._mode == ExerciseMode.metronome else self._timer_tick
        )
        self._task = asyncio.create_task(
            beat_scheduler(
                self._interval_sec,
                callback,
                initial_delay_sec=self._start_delay_sec,
            )
        )
        logger.info(
            "CountingEngine started: mode=%s interval=%.2fs delay=%.1fs",
            self._mode.value, self._interval_sec, self._start_delay_sec,
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

    # --- internal tick handlers ---

    async def _metronome_tick(self) -> None:
        cue = self._select_metronome_cue()
        await self._on_beat(
            BeatEvent(rep=self._rep, phase=self._phase, elapsed_sec=self.elapsed_sec, cue=cue)
        )
        if self._phase == "down":
            self._rep += 1
            if self._rep >= self._max_reps:
                logger.info("CountingEngine: max reps reached (%d)", self._rep)
                await self._fire_complete()
                task = asyncio.current_task()
                if task:
                    task.cancel()
                return
        self._phase = "down" if self._phase == "up" else "up"

    async def _timer_tick(self) -> None:
        elapsed = self.elapsed_sec
        cue = self._select_timer_cue(elapsed)
        await self._on_beat(BeatEvent(rep=0, phase="tick", elapsed_sec=elapsed, cue=cue))
        if self._target_duration_sec is not None and elapsed >= self._target_duration_sec:
            logger.info("CountingEngine: target duration reached (%.1fs)", elapsed)
            await self._fire_complete(duration_sec=elapsed)
            task = asyncio.current_task()
            if task:
                task.cancel()

    async def _fire_complete(self, duration_sec: float | None = None) -> None:
        if self.on_complete is not None:
            with contextlib.suppress(Exception):
                await self.on_complete(
                    CompleteEvent(
                        reps_completed=self._rep,
                        elapsed_sec=self.elapsed_sec,
                        exercise_name=self._exercise_name,
                        duration_sec=duration_sec,
                    )
                )

    # --- cue selection helpers ---

    def _select_metronome_cue(self) -> str:
        # Check encouragement at "down" phase (rep increment point)
        if self._phase == "down" and self._max_reps > 0 and self._encouragement_points:
            next_rep = self._rep + 1
            progress = next_rep / self._max_reps
            for i, threshold in enumerate(self._encouragement_points):
                if progress >= threshold and i not in self._fired_enc:
                    self._fired_enc.add(i)
                    pool_key = _ENC_POOL_KEYS[min(i, len(_ENC_POOL_KEYS) - 1)]
                    pool = get_encouragement_pool(pool_key)
                    return self._pick(pool, f"enc_{pool_key}")

        pool = get_beat_pool(self._exercise_name, self._phase)
        return self._pick(pool, f"beat_{self._phase}")

    def _select_timer_cue(self, elapsed: float) -> str:
        target = self._target_duration_sec or 0.0
        remaining = max(0.0, target - elapsed)

        # Check encouragement based on elapsed time progress
        if target > 0 and self._encouragement_points:
            progress = elapsed / target
            for i, threshold in enumerate(self._encouragement_points):
                if progress >= threshold and i not in self._fired_enc:
                    self._fired_enc.add(i)
                    pool_key = _ENC_POOL_KEYS[min(i, len(_ENC_POOL_KEYS) - 1)]
                    pool = get_encouragement_pool(pool_key)
                    return self._pick(pool, f"enc_{pool_key}")

        pool = get_beat_pool(self._exercise_name, "tick")
        return self._pick(pool, "beat_tick", remaining_sec=remaining)

    def _pick(self, pool: list[str], counter_key: str, **kw: float | None) -> str:
        idx = self._seq_counters.get(counter_key, 0)
        text = pick_cue(pool, mode=self._cue_mode, index=idx, rng=self._rng, **kw)
        if self._cue_mode == "sequential":
            self._seq_counters[counter_key] = idx + 1
        return text
