"""tests/unit/test_set_complete_followup.py — on_complete → SetLog + follow-up LLM 호출
(phase-6 §6-5 / §6-7).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from app.config import CountingConfig, EncouragementConfig
from app.core.counting import CompleteEvent, CountingEngine, ExerciseMode
from app.pipecat_services.counting_manager import CountingManager
from app.pipecat_services.processors.counting_inject import CountingInjectProcessor


def _make_config(**kw) -> CountingConfig:
    defaults = dict(
        beat_interval_sec=0.05,
        max_reps=200,
        start_delay_sec=0.0,
        cue_selection="random",
        encouragement=EncouragementConfig(enabled=False),
    )
    defaults.update(kw)
    return CountingConfig(**defaults)


async def test_on_session_complete_called_after_engine_finishes() -> None:
    """CountingManager.on_session_complete must fire when engine reaches max_reps."""
    cfg = _make_config()
    manager = CountingManager(cfg)
    inject = CountingInjectProcessor()
    manager.attach_inject_processor(inject)

    completed: list[CompleteEvent] = []

    async def on_complete(event: CompleteEvent) -> None:
        completed.append(event)

    manager.on_session_complete = on_complete

    await manager.start("푸시업", 2)  # max_reps=2, interval=0.05s → done in ~0.2s
    await asyncio.sleep(0.8)

    assert len(completed) == 1
    assert completed[0].exercise_name == "푸시업"
    assert completed[0].reps_completed == 2


async def test_on_session_complete_receives_correct_exercise() -> None:
    cfg = _make_config()
    manager = CountingManager(cfg)
    inject = CountingInjectProcessor()
    manager.attach_inject_processor(inject)

    results: list[CompleteEvent] = []
    manager.on_session_complete = AsyncMock(side_effect=lambda e: results.append(e) or None)

    await manager.start("스쿼트", 3)
    await asyncio.sleep(1.0)

    manager.on_session_complete.assert_awaited_once()
    assert results[0].exercise_name == "스쿼트"


async def test_complete_event_has_elapsed_sec() -> None:
    cfg = _make_config()
    manager = CountingManager(cfg)
    inject = CountingInjectProcessor()
    manager.attach_inject_processor(inject)

    events: list[CompleteEvent] = []
    manager.on_session_complete = AsyncMock(side_effect=lambda e: events.append(e) or None)

    await manager.start("풀업", 2)
    await asyncio.sleep(0.8)

    assert events[0].elapsed_sec > 0.0


async def test_manager_is_not_active_after_complete() -> None:
    cfg = _make_config()
    manager = CountingManager(cfg)
    inject = CountingInjectProcessor()
    manager.attach_inject_processor(inject)
    manager.on_session_complete = AsyncMock()

    await manager.start("푸시업", 2)
    await asyncio.sleep(0.8)

    assert not manager.is_active


async def test_complete_callback_exception_does_not_propagate() -> None:
    """Exception in on_session_complete must be swallowed (never crash the engine)."""
    cfg = _make_config()
    manager = CountingManager(cfg)
    inject = CountingInjectProcessor()
    manager.attach_inject_processor(inject)
    manager.on_session_complete = AsyncMock(side_effect=RuntimeError("db down"))

    await manager.start("스쿼트", 2)
    await asyncio.sleep(0.8)
    # If we get here, the exception was swallowed correctly


async def test_plank_timer_fires_complete_with_duration() -> None:
    """Timer mode (plank) complete event must carry duration_sec."""
    cfg = _make_config(beat_interval_sec=0.05)
    manager = CountingManager(cfg)
    inject = CountingInjectProcessor()
    manager.attach_inject_processor(inject)

    events: list[CompleteEvent] = []
    manager.on_session_complete = AsyncMock(side_effect=lambda e: events.append(e) or None)

    # reps=1 means target_duration_sec=1.0s, tick every 0.05s
    # Since CountingManager sets interval=1.0 for plank, use shorter target
    # Override: directly test the engine for plank mode
    engine = CountingEngine(
        mode=ExerciseMode.timer,
        interval_sec=0.05,
        on_beat=AsyncMock(),
        target_duration_sec=0.2,
        exercise_name="플랭크",
    )

    completed: list[CompleteEvent] = []

    async def on_done(e: CompleteEvent) -> None:
        completed.append(e)

    engine.on_complete = on_done
    await engine.start()
    await asyncio.sleep(0.8)

    assert len(completed) == 1
    assert completed[0].duration_sec is not None
    assert completed[0].duration_sec >= 0.2
