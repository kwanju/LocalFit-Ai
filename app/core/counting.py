import asyncio
import contextlib
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

from loguru import logger

from app.core.counting_cues import (
    count_word,
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
    # 2026-06-07 sync 개선용: UI가 audio msg와 짝지을 때 카운트/격려 구분.
    cue_kind: str = "count"      # "count" | "encouragement" | "tick" | ""
    set_number: int = 1          # 현재 진행 중인 세트 (1-indexed)
    total_sets: int = 1


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
        # 2026-06-07: multi-set sync용. CountingManager가 매 세트 fresh engine을 만들 때 세트 정보 주입.
        set_number: int = 1,
        total_sets: int = 1,
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
        self._set_number = set_number
        self._total_sets = total_sets

        self._rep: int = 0
        self._phase: str = "up"
        self._start_time: float | None = None
        self._task: asyncio.Task[None] | None = None

        # Cue state (phase-6)
        self._seq_counters: dict[str, int] = {}
        self._fired_enc: set[int] = set()  # indices of already-fired encouragement points
        # cue_kind 추적용 — 마지막 _select_*_cue 호출이 격려를 골랐는지 카운트를 골랐는지
        # _metronome_tick / _timer_tick 가 BeatEvent에 실어 보낼 수 있도록.
        self._last_cue_kind: str = "count"

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
            BeatEvent(
                rep=self._rep,
                phase=self._phase,
                elapsed_sec=self.elapsed_sec,
                cue=cue,
                cue_kind=self._last_cue_kind,
                set_number=self._set_number,
                total_sets=self._total_sets,
            )
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
        # 플랭크(timer): 유지 중엔 깔끔한 초 카운트("1초","2초",…)만 — "힘내요/N초 남았어요"
        # 류 잡담을 매초 하던 게 TTS를 밀어 실제 시간과 어긋났다(2026-06-09 사용자 피드백).
        # 짧은 "N초"는 1초 간격에 안 밀린다. 완료 시 격려 1회.
        elapsed = self.elapsed_sec
        done = self._target_duration_sec is not None and elapsed >= self._target_duration_sec
        if done:
            cue = self._pick(get_encouragement_pool("timer_done"), "enc_timer_done")
            self._last_cue_kind = "encouragement"
        else:
            # 숫자만 카운트 ("1","2","3"… → "일,이,삼"). 매초 "초"를 붙이면 거슬려서 제거
            # (2026-06-09 사용자 피드백).
            cue = str(round(elapsed))
            self._last_cue_kind = "tick"
        await self._on_beat(
            BeatEvent(
                rep=0,
                phase="tick",
                elapsed_sec=elapsed,
                cue=cue,
                cue_kind=self._last_cue_kind,
                set_number=self._set_number,
                total_sets=self._total_sets,
            )
        )
        if done:
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
        # 메트로놈 모드: "up"은 묵음(빈 cue → 오디오 송신 생략), "down"에서 다음 rep을 카운트.
        # "down" 시점에는 격려가 우선 — 1/3, 2/3, 마지막 시점이 트리거되면 격려 멘트로 대체.
        if self._phase != "down":
            self._last_cue_kind = ""
            return ""

        next_rep = self._rep + 1
        if self._max_reps > 0 and self._encouragement_points:
            progress = next_rep / self._max_reps
            for i, threshold in enumerate(self._encouragement_points):
                if progress >= threshold and i not in self._fired_enc:
                    self._fired_enc.add(i)
                    pool_key = _ENC_POOL_KEYS[min(i, len(_ENC_POOL_KEYS) - 1)]
                    enc = self._pick(get_encouragement_pool(pool_key), f"enc_{pool_key}")
                    # 격려는 숫자를 *대체*가 아니라 *덧붙인다* — "넷! 좋아요, 호흡 유지!"
                    # (2026-06-07 fix: 격려 시점에 넷·일곱·열이 통째로 빠지던 문제).
                    # cue_kind는 count 유지 → UI 카운터도 정상 증가/표시.
                    self._last_cue_kind = "count"
                    return f"{count_word(next_rep)} {enc}".strip()

        self._last_cue_kind = "count"
        return count_word(next_rep)

    def _pick(self, pool: list[str], counter_key: str, **kw: float | None) -> str:
        idx = self._seq_counters.get(counter_key, 0)
        text = pick_cue(pool, mode=self._cue_mode, index=idx, rng=self._rng, **kw)
        if self._cue_mode == "sequential":
            self._seq_counters[counter_key] = idx + 1
        return text
