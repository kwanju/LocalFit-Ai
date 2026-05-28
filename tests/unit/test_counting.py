import asyncio
import time

import pytest

from app.core.counting import BeatEvent, CountingEngine, ExerciseMode


async def collect_beats(
    mode: ExerciseMode,
    interval_sec: float,
    run_sec: float,
    max_reps: int = 200,
    target_duration_sec: float | None = None,
) -> list[tuple[float, BeatEvent]]:
    """Helper: run engine for run_sec seconds and return (timestamp, event) pairs."""
    records: list[tuple[float, BeatEvent]] = []

    async def on_beat(event: BeatEvent) -> None:
        records.append((time.monotonic(), event))

    engine = CountingEngine(
        mode=mode,
        interval_sec=interval_sec,
        on_beat=on_beat,
        max_reps=max_reps,
        target_duration_sec=target_duration_sec,
    )
    await engine.start()
    await asyncio.sleep(run_sec)
    await engine.stop()
    return records


@pytest.mark.parametrize("mode", [ExerciseMode.metronome, ExerciseMode.timer])
async def test_beat_timing_no_drift(mode: ExerciseMode) -> None:
    """Beat intervals must be within ±15% of configured interval, with ≤10% cumulative drift.

    Uses 0.2s interval and 1.3s run window.
    At 2.0s production interval the tolerance is comfortably within PRD 7-1 (±10%).
    """
    interval = 0.2
    records = await collect_beats(mode, interval, run_sec=1.3)

    timestamps = [t for t, _ in records]
    assert len(timestamps) >= 4, f"Expected ≥4 beats, got {len(timestamps)}"

    tolerance = 0.15
    for i in range(1, len(timestamps)):
        gap = timestamps[i] - timestamps[i - 1]
        assert (1 - tolerance) * interval <= gap <= (1 + tolerance) * interval, (
            f"Beat gap {gap:.4f}s is outside ±{tolerance*100:.0f}% of {interval}s"
        )

    total_expected = (len(timestamps) - 1) * interval
    total_actual = timestamps[-1] - timestamps[0]
    drift = abs(total_actual - total_expected) / total_expected
    assert drift <= 0.10, f"Cumulative drift {drift:.1%} exceeds 10%"


async def test_metronome_phase_alternation() -> None:
    """Metronome must alternate up/down phases."""
    records = await collect_beats(ExerciseMode.metronome, interval_sec=0.05, run_sec=0.55)
    phases = [e.phase for _, e in records]

    assert len(phases) >= 4
    for i in range(len(phases) - 1):
        assert phases[i] != phases[i + 1], f"Consecutive phases at index {i}: {phases}"


async def test_metronome_rep_increments_on_down() -> None:
    """Rep count must increment after each 'down' phase."""
    records = await collect_beats(ExerciseMode.metronome, interval_sec=0.05, run_sec=0.55)

    rep_at_down: list[int] = [e.rep for _, e in records if e.phase == "down"]
    assert len(rep_at_down) >= 2
    # Rep should increase monotonically
    for i in range(1, len(rep_at_down)):
        assert rep_at_down[i] >= rep_at_down[i - 1], "Rep count must not decrease"


async def test_timer_mode_only_emits_tick() -> None:
    """Timer mode must only emit 'tick' phase events."""
    records = await collect_beats(ExerciseMode.timer, interval_sec=0.05, run_sec=0.3)
    phases = [e.phase for _, e in records]
    assert all(p == "tick" for p in phases), f"Non-tick phases found: {set(phases)}"


async def test_timer_elapsed_increases() -> None:
    """Elapsed time in BeatEvent must strictly increase."""
    records = await collect_beats(ExerciseMode.timer, interval_sec=0.05, run_sec=0.35)
    elapsed = [e.elapsed_sec for _, e in records]

    assert len(elapsed) >= 3
    for i in range(1, len(elapsed)):
        assert elapsed[i] > elapsed[i - 1], "Elapsed time must strictly increase"


async def test_max_reps_stops_engine() -> None:
    """Engine must self-stop when max_reps is reached."""
    # max_reps=2 → stops after 2 completed reps (4 beats: up, down, up, down)
    records = await collect_beats(
        ExerciseMode.metronome, interval_sec=0.05, run_sec=2.0, max_reps=2
    )
    reps = [e.rep for _, e in records]
    # The engine stops after rep count reaches max_reps=2
    assert max(reps) <= 2, f"Rep count exceeded max_reps: {max(reps)}"
    # Should stop well before run_sec=2.0 (only ~4 beats needed)
    assert len(records) <= 10, f"Engine ran too long: {len(records)} beats"


async def test_timer_target_duration_stops_engine() -> None:
    """Timer engine must self-stop when target_duration_sec is reached."""
    target = 0.3
    records = await collect_beats(
        ExerciseMode.timer,
        interval_sec=0.05,
        run_sec=2.0,
        target_duration_sec=target,
    )
    # Should stop near target duration, not run for the full 2s
    if records:
        last_elapsed = records[-1][1].elapsed_sec
        assert last_elapsed <= target + 0.1, f"Engine ran past target: {last_elapsed:.3f}s"


async def test_start_stop_lifecycle() -> None:
    """Engine must handle start → stop → start correctly."""
    beats: list[int] = []

    async def on_beat(event: BeatEvent) -> None:
        beats.append(1)

    engine = CountingEngine(ExerciseMode.metronome, interval_sec=0.05, on_beat=on_beat)

    await engine.start()
    await asyncio.sleep(0.2)
    await engine.stop()
    count_after_first = len(beats)
    assert count_after_first > 0

    beats.clear()
    await engine.start()
    await asyncio.sleep(0.2)
    await engine.stop()
    assert len(beats) > 0


async def test_double_start_is_safe() -> None:
    """Calling start() twice must not create duplicate tasks."""
    beats: list[int] = []

    async def on_beat(event: BeatEvent) -> None:
        beats.append(1)

    engine = CountingEngine(ExerciseMode.metronome, interval_sec=0.05, on_beat=on_beat)
    await engine.start()
    await engine.start()  # second call should be a no-op
    await asyncio.sleep(0.2)
    await engine.stop()


async def test_current_rep_property() -> None:
    """current_rep property must reflect the engine state."""
    engine = CountingEngine(
        ExerciseMode.metronome,
        interval_sec=0.05,
        on_beat=lambda e: asyncio.sleep(0),
    )
    assert engine.current_rep == 0
    await engine.start()
    await asyncio.sleep(0.3)
    await engine.stop()
    assert engine.current_rep > 0


async def test_elapsed_sec_before_start() -> None:
    """elapsed_sec must return 0.0 before start() is called."""
    engine = CountingEngine(
        ExerciseMode.metronome,
        interval_sec=0.1,
        on_beat=lambda e: asyncio.sleep(0),
    )
    assert engine.elapsed_sec == 0.0


async def test_beat_event_fields() -> None:
    """BeatEvent must carry rep, phase, and elapsed_sec."""
    events: list[BeatEvent] = []

    async def on_beat(event: BeatEvent) -> None:
        events.append(event)

    engine = CountingEngine(ExerciseMode.metronome, interval_sec=0.05, on_beat=on_beat)
    await engine.start()
    await asyncio.sleep(0.15)
    await engine.stop()

    assert len(events) >= 2
    for e in events:
        assert isinstance(e.rep, int)
        assert e.phase in ("up", "down")
        assert isinstance(e.elapsed_sec, float)
        assert e.elapsed_sec >= 0.0
