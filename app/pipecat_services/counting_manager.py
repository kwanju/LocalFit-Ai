"""CountingManager — creates and manages CountingEngine instances per exercise
session (ADR-014 §트리거 경로, phase-6 §6-3).

Provides the high-level ``start(exercise, reps)`` interface that
``ActionDispatcherProcessor`` calls when a ``StartCountingAction`` is dispatched.
The engine itself lives in ``app.core`` (Domain Core, zero external deps);
this manager lives in ``pipecat_services`` because it wires the engine to the
Pipecat pipeline via ``CountingInjectProcessor``.

Dependency flow (ADR-012):
  api → pipecat_services/counting_manager → core/counting (ok)
                                          → processors/counting_inject (ok)
"""

from __future__ import annotations

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


class CountingManager:
    """Manages CountingEngine lifecycle across exercise sets.

    Usage (ws_voice.py):
        manager = CountingManager(config.counting)
        inject_proc = CountingInjectProcessor()
        manager.attach_inject_processor(inject_proc)
        # ... build pipeline with inject_proc ...
        manager.on_session_complete = async_callback
        # ActionDispatcher calls: await manager.start("푸시업", 10)
    """

    def __init__(self, config: CountingConfig) -> None:
        self._config = config
        self._engine: CountingEngine | None = None
        self._inject_proc: CountingInjectProcessor | None = None
        self._active_exercise: str = ""
        self._active_reps: int = 0
        self.on_session_complete: Callable[[CompleteEvent], Awaitable[None]] | None = None

    def attach_inject_processor(self, proc: CountingInjectProcessor) -> None:
        self._inject_proc = proc

    @property
    def is_active(self) -> bool:
        return self._engine is not None

    async def start(self, exercise: str, reps: int) -> None:
        """Start a new counting session, stopping any currently running engine."""
        if self._engine is not None:
            await self._engine.stop()

        mode = _EXERCISE_MODES.get(exercise, ExerciseMode.metronome)
        cfg = self._config
        enc_cfg = cfg.encouragement

        if mode == ExerciseMode.timer:
            interval = _PLANK_TICK_INTERVAL
            max_reps = 200          # not used in timer mode (target_duration_sec controls stop)
            target_dur: float | None = float(reps)
        else:
            interval = cfg.beat_interval_sec
            max_reps = reps
            target_dur = None

        enc_points = list(enc_cfg.points) if enc_cfg.enabled else []

        engine = CountingEngine(
            mode=mode,
            interval_sec=interval,
            on_beat=_noop_beat,       # overwritten by attach_engine below
            max_reps=max_reps,
            target_duration_sec=target_dur,
            exercise_name=exercise,
            cue_mode=cfg.cue_selection,
            start_delay_sec=cfg.start_delay_sec,
            encouragement_points=enc_points,
        )
        engine.on_complete = self._on_engine_complete

        if self._inject_proc is not None:
            self._inject_proc.attach_engine(engine)

        self._engine = engine
        self._active_exercise = exercise
        self._active_reps = reps

        logger.info(
            "CountingManager.start: exercise={} reps={} mode={} delay={:.1f}s",
            exercise, reps, mode.value, cfg.start_delay_sec,
        )
        await engine.start()

    async def stop(self) -> None:
        if self._engine is not None:
            await self._engine.stop()
            self._engine = None

    async def pause(self) -> None:
        if self._engine is not None:
            await self._engine.pause()
            self._engine = None
            logger.info("CountingManager: engine paused")

    async def _on_engine_complete(self, event: CompleteEvent) -> None:
        self._engine = None
        logger.info(
            "CountingManager: session complete — exercise={} reps={} elapsed={:.1f}s",
            event.exercise_name, event.reps_completed, event.elapsed_sec,
        )
        if self.on_session_complete is not None:
            try:
                await self.on_session_complete(event)
            except Exception as e:  # noqa: BLE001 — never break caller
                logger.error("CountingManager on_session_complete error: {}", e)
