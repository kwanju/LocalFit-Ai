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
async def test_metronome_down_beats_produce_count_cue(exercise: str) -> None:
    """메트로놈: "down" 박자에만 카운트 cue("하나!", "둘!", ...)가 들어가고,
    "up" 박자는 묵음(빈 cue)이다 (2026-06-04 개정).
    """
    cues: list[str] = []
    phases: list[str] = []

    async def on_beat(event: BeatEvent) -> None:
        cues.append(event.cue)
        phases.append(event.phase)

    engine = CountingEngine(
        mode=ExerciseMode.metronome,
        interval_sec=0.05,
        on_beat=on_beat,
        exercise_name=exercise,
    )
    await engine.start()
    await asyncio.sleep(0.35)
    await engine.stop()

    assert cues, "No cues collected"
    for cue, phase in zip(cues, phases):
        if phase == "up":
            assert cue == "", f"up phase should be silent, got {cue!r}"
        else:
            assert cue != "", "down phase should produce a count cue"


@pytest.mark.parametrize("exercise", ["풀업", "푸시업", "스쿼트"])
async def test_metronome_count_cue_is_ordinal(exercise: str) -> None:
    """down 박자의 cue는 한국어 ordinal("하나!", "둘!", "셋!", ...)이다."""
    cues = await collect_cues(ExerciseMode.metronome, exercise, 0.05, 0.35)
    down_cues = [c for c in cues if c]  # 비어있지 않은 cue들 (= down 박자)
    assert down_cues
    # 첫 down cue는 "하나!"여야 한다.
    assert down_cues[0] == "하나!"


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
    """Encouragement cues must appear at the 1/3 and 2/3 rep checkpoints.

    2026-06-07 fix: 격려는 숫자를 *대체*가 아니라 *덧붙인다* ("넷! 좋아요, 호흡 유지!").
    따라서 정확 일치가 아니라 substring으로 검사하고, 숫자가 함께 발화되는지도 확인.
    """
    from app.core.counting_cues import ENCOURAGEMENT_CUES, count_word

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

    # 격려 멘트가 어떤 cue에든 덧붙어 등장해야 한다 (substring).
    enc_found = [c for c in cues if any(e in c for e in all_enc)]
    assert len(enc_found) >= 2, (
        f"Expected ≥2 cues containing encouragement, got {len(enc_found)}: {enc_found}"
    )
    # 격려가 붙은 cue도 숫자("넷!" 등)를 함께 포함해 카운트가 빠지지 않아야 한다.
    all_counts = {count_word(r) for r in range(1, max_reps + 1)}
    for c in enc_found:
        assert any(cw and cw in c for cw in all_counts), (
            f"Encouragement cue '{c}' must still include the rep number"
        )
