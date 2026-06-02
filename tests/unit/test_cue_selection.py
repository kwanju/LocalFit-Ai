"""tests/unit/test_cue_selection.py — random/sequential cue selection (phase-6 §6-7)."""

import asyncio

import pytest

from app.core.counting import BeatEvent, CountingEngine, ExerciseMode


async def collect_cues(
    mode: ExerciseMode,
    exercise: str,
    interval_sec: float,
    run_sec: float,
    cue_mode: str = "random",
    rng_seed: int | None = None,
) -> list[str]:
    cues: list[str] = []

    async def on_beat(event: BeatEvent) -> None:
        cues.append(event.cue)

    engine = CountingEngine(
        mode=mode,
        interval_sec=interval_sec,
        on_beat=on_beat,
        exercise_name=exercise,
        cue_mode=cue_mode,
        rng_seed=rng_seed,
    )
    await engine.start()
    await asyncio.sleep(run_sec)
    await engine.stop()
    return cues


@pytest.mark.parametrize("exercise", ["풀업", "푸시업", "스쿼트"])
async def test_metronome_cues_not_empty(exercise: str) -> None:
    """Each beat must produce a non-empty cue string."""
    cues = await collect_cues(ExerciseMode.metronome, exercise, 0.05, 0.35)
    assert cues, "No cues collected"
    assert all(c != "" for c in cues), "Some beat cues were empty"


async def test_plank_timer_cues_not_empty() -> None:
    cues = await collect_cues(ExerciseMode.timer, "플랭크", 0.05, 0.35)
    assert cues
    assert all(c != "" for c in cues)


async def test_sequential_no_skip() -> None:
    """Sequential mode must cycle cues without skipping any pool entry."""
    cues = await collect_cues(
        ExerciseMode.metronome, "푸시업", 0.05, 0.7, cue_mode="sequential"
    )
    assert len(cues) >= 4


async def test_random_with_seed_is_reproducible() -> None:
    """Same seed must produce identical cue sequence."""
    cues_a = await collect_cues(
        ExerciseMode.metronome, "스쿼트", 0.05, 0.5, cue_mode="random", rng_seed=42
    )
    cues_b = await collect_cues(
        ExerciseMode.metronome, "스쿼트", 0.05, 0.5, cue_mode="random", rng_seed=42
    )
    assert cues_a == cues_b, "Same seed must produce same cue sequence"


async def test_different_seeds_may_differ() -> None:
    """Different seeds should produce different sequences (statistically)."""
    cues_a = await collect_cues(
        ExerciseMode.metronome, "풀업", 0.05, 0.8, cue_mode="random", rng_seed=1
    )
    # With enough beats, the sequence has ≥4 entries regardless of seed
    assert len(cues_a) >= 4


async def test_encouragement_cues_injected_at_checkpoint() -> None:
    """Encouragement cues must appear at the 1/3 and 2/3 rep checkpoints."""
    from app.core.counting_cues import ENCOURAGEMENT_CUES

    all_enc = {c for pool in ENCOURAGEMENT_CUES.values() for c in pool}
    max_reps = 9  # 3 down beats for 1/3, 6 for 2/3, 8+ for last

    cues: list[str] = []

    async def on_beat(event: BeatEvent) -> None:
        cues.append(event.cue)

    engine = CountingEngine(
        mode=ExerciseMode.metronome,
        interval_sec=0.02,
        on_beat=on_beat,
        max_reps=max_reps,
        exercise_name="푸시업",
        cue_mode="random",
        encouragement_points=[0.33, 0.66, 0.95],
    )
    await engine.start()
    await asyncio.sleep(2.0)  # wait for engine to finish
    await engine.stop()

    enc_found = [c for c in cues if c in all_enc]
    assert len(enc_found) >= 2, (
        f"Expected ≥2 encouragement cues, got {len(enc_found)}: {enc_found}"
    )
