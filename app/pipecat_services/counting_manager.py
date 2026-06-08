"""CountingManager — creates and manages CountingEngine instances per exercise
session (ADR-014 §트리거 경로, phase-6 §6-3).

Provides the high-level ``start(exercise, reps, sets, rest_sec)`` interface that
``ActionDispatcherProcessor`` calls when a ``StartCountingAction`` is dispatched.
The engine itself lives in ``app.core`` (Domain Core, zero external deps);
this manager lives in ``pipecat_services`` because it wires the engine to the
Pipecat pipeline via ``CountingInjectProcessor``.

2026-06-07 — 다회 세트(multi-set) 지원: ``start(..., sets=N, rest_sec=R)`` 호출 시
한 세트가 끝나면 휴식 카운트다운 → 다음 세트 자동 시작 → ... 마지막 세트 끝나면
``on_session_complete`` 콜백 (ws_voice의 SetLog 기록 + 자동 follow-up LLM).

Dependency flow (ADR-012):
  api → pipecat_services/counting_manager → core/counting (ok)
                                          → processors/counting_inject (ok)
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

from loguru import logger

from app.config import CountingConfig
from app.core.counting import (
    BeatEvent,
    CompleteEvent,
    CountingEngine,
    ExerciseMode,
)
from app.pipecat_services.processors.counting_inject import CountingInjectProcessor

_EXERCISE_MODES: dict[str, ExerciseMode] = {
    "풀업": ExerciseMode.metronome,
    "푸시업": ExerciseMode.metronome,
    "스쿼트": ExerciseMode.metronome,
    "플랭크": ExerciseMode.timer,
}
_PLANK_TICK_INTERVAL: float = 1.0  # plank 카운트다운은 1초 단위


async def _noop_beat(event: BeatEvent) -> None:  # noqa: ARG001
    pass


# 휴식 중 UI/오디오 안내 콜백. 처음, 중간(10초 남음), 끝 알림용.
RestNotifier = Callable[[int, int, int], Awaitable[None]]
"""(remaining_sec, set_number_completed, total_sets) → 호출.

``remaining_sec`` 가 ``rest_sec`` (시작), ``10`` (10초 남음), ``0`` (끝) 시점에 호출.
"""


class CountingManager:
    """Manages CountingEngine lifecycle across exercise sets (multi-set 지원)."""

    def __init__(self, config: CountingConfig) -> None:
        self._config = config
        self._engine: CountingEngine | None = None
        self._inject_proc: CountingInjectProcessor | None = None
        self._active_exercise: str = ""
        self._active_reps: int = 0
        self._active_sets: int = 1
        self._active_rest_sec: int = 60
        self._current_set: int = 0
        self._rest_task: asyncio.Task[None] | None = None
        self.on_session_complete: Callable[[CompleteEvent], Awaitable[None]] | None = None
        # 매 세트 완료 시 호출 (SetLog 기록용). 인자: (event, set_number, total_sets).
        self.on_set_complete: (
            Callable[[CompleteEvent, int, int], Awaitable[None]] | None
        ) = None
        # ws_voice가 휴식 안내(메시지) 를 UI/TTS로 보낼 수 있도록 노출.
        self.on_rest_event: RestNotifier | None = None

    def attach_inject_processor(self, proc: CountingInjectProcessor) -> None:
        self._inject_proc = proc

    @property
    def is_active(self) -> bool:
        return self._engine is not None or self._rest_task is not None

    async def start(
        self,
        exercise: str,
        reps: int,
        *,
        sets: int = 1,
        rest_sec: int | None = None,
    ) -> None:
        """Start a new counting session (multi-set 가능).

        Args:
            exercise: 운동명 (풀업/푸시업/스쿼트/플랭크).
            reps: 세트당 반복 수 (플랭크는 초).
            sets: 총 세트 수 (>=1).
            rest_sec: 세트 간 휴식 초. None이면 ``config.counting.rest_default_sec``.
        """
        await self._cancel_rest_task()
        if self._engine is not None:
            await self._engine.stop()

        self._active_exercise = exercise
        self._active_reps = reps
        self._active_sets = max(1, sets)
        self._active_rest_sec = (
            int(rest_sec) if rest_sec is not None else int(self._config.rest_default_sec)
        )
        self._current_set = 0
        await self._start_next_set()

    async def stop(self) -> None:
        await self._cancel_rest_task()
        if self._engine is not None:
            await self._engine.stop()
            self._engine = None

    async def pause(self) -> None:
        await self._cancel_rest_task()
        if self._engine is not None:
            await self._engine.pause()
            self._engine = None
            logger.info("CountingManager: engine paused")

    # --- internal --------------------------------------------------------------

    async def _start_next_set(self) -> None:
        self._current_set += 1
        cfg = self._config
        enc_cfg = cfg.encouragement
        mode = _EXERCISE_MODES.get(self._active_exercise, ExerciseMode.metronome)

        if mode == ExerciseMode.timer:
            interval = _PLANK_TICK_INTERVAL
            max_reps = 200          # not used in timer mode (target_duration_sec controls stop)
            target_dur: float | None = float(self._active_reps)
        else:
            interval = cfg.beat_interval_sec
            max_reps = self._active_reps
            target_dur = None

        enc_points = list(enc_cfg.points) if enc_cfg.enabled else []

        engine = CountingEngine(
            mode=mode,
            interval_sec=interval,
            on_beat=_noop_beat,       # overwritten by attach_engine below
            max_reps=max_reps,
            target_duration_sec=target_dur,
            exercise_name=self._active_exercise,
            cue_mode=cfg.cue_selection,
            start_delay_sec=cfg.start_delay_sec,
            encouragement_points=enc_points,
            set_number=self._current_set,
            total_sets=self._active_sets,
        )
        engine.on_complete = self._on_engine_complete

        if self._inject_proc is not None:
            self._inject_proc.attach_engine(engine)

        self._engine = engine
        logger.info(
            "CountingManager.start_set: exercise={} reps={} set={}/{} rest={}s delay={:.1f}s",
            self._active_exercise,
            self._active_reps,
            self._current_set,
            self._active_sets,
            self._active_rest_sec,
            cfg.start_delay_sec,
        )
        await engine.start()

    async def _on_engine_complete(self, event: CompleteEvent) -> None:
        self._engine = None
        completed_set = self._current_set
        logger.info(
            "CountingManager: set {}/{} complete — reps={} elapsed={:.1f}s",
            completed_set,
            self._active_sets,
            event.reps_completed,
            event.elapsed_sec,
        )

        # 매 세트 SetLog 기록 콜백 (있으면).
        if self.on_set_complete is not None:
            try:
                await self.on_set_complete(event, completed_set, self._active_sets)
            except Exception as e:  # noqa: BLE001 — never break caller
                logger.error("CountingManager on_set_complete error: {}", e)

        # 마지막 세트가 아니면 휴식 → 다음 세트 자동 시작.
        if completed_set < self._active_sets:
            self._rest_task = asyncio.create_task(self._rest_then_next())
            return

        # 마지막 세트 완료 → 외부 콜백 호출 (follow-up LLM 등).
        if self.on_session_complete is not None:
            try:
                await self.on_session_complete(event)
            except Exception as e:  # noqa: BLE001 — never break caller
                logger.error("CountingManager on_session_complete error: {}", e)

    async def _rest_then_next(self) -> None:
        rest = self._active_rest_sec
        set_done = self._current_set
        total = self._active_sets
        try:
            # 시작 안내.
            await self._fire_rest_event(rest, set_done, total)
            # 10초 남았을 때 알림(휴식이 10초 초과일 때만).
            if rest > 10:
                await asyncio.sleep(rest - 10)
                await self._fire_rest_event(10, set_done, total)
                await asyncio.sleep(10)
            else:
                await asyncio.sleep(rest)
            # 휴식 종료.
            await self._fire_rest_event(0, set_done, total)
        except asyncio.CancelledError:
            return
        finally:
            self._rest_task = None
        await self._start_next_set()

    async def _fire_rest_event(self, remaining: int, set_done: int, total: int) -> None:
        if self.on_rest_event is None:
            return
        try:
            await self.on_rest_event(remaining, set_done, total)
        except Exception as e:  # noqa: BLE001 — rest notifications are best-effort
            logger.error("CountingManager on_rest_event error: {}", e)

    async def _cancel_rest_task(self) -> None:
        if self._rest_task is None:
            return
        self._rest_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._rest_task
        self._rest_task = None
