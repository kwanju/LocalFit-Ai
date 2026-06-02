"""tests/unit/test_counting_cues.py — cue pool 비어있지 않음 + 5종 이상 보장 (phase-6 §6-7)."""

import pytest

from app.core.counting_cues import (
    BEAT_CUES,
    ENCOURAGEMENT_CUES,
    get_beat_pool,
    get_encouragement_pool,
    pick_cue,
)

_EXERCISES = ["풀업", "푸시업", "스쿼트", "플랭크"]
_METRONOME_PHASES = {"풀업": ["up", "down"], "푸시업": ["down", "up"], "스쿼트": ["down", "up"]}
_TIMER_PHASE = "tick"
_ENC_POINTS = ["first_third", "second_third", "last"]


@pytest.mark.parametrize("exercise", _EXERCISES)
def test_beat_cue_pool_not_empty(exercise: str) -> None:
    assert exercise in BEAT_CUES, f"No cue pool for exercise: {exercise}"
    for phase, pool in BEAT_CUES[exercise].items():
        assert len(pool) >= 3, f"{exercise}/{phase}: pool has <3 cues ({len(pool)})"


def test_beat_cue_pool_5_or_more() -> None:
    """ADR-014: 각 cue 풀은 5종 권장."""
    for ex, phases in BEAT_CUES.items():
        for phase, pool in phases.items():
            assert len(pool) >= 5, f"{ex}/{phase}: expected ≥5 cues, got {len(pool)}"


@pytest.mark.parametrize("point", _ENC_POINTS)
def test_encouragement_pool_not_empty(point: str) -> None:
    assert point in ENCOURAGEMENT_CUES
    pool = ENCOURAGEMENT_CUES[point]
    assert len(pool) >= 3, f"Encouragement pool '{point}' has <3 entries"


def test_all_encouragement_points_present() -> None:
    for point in _ENC_POINTS:
        assert point in ENCOURAGEMENT_CUES


def test_plank_cue_pool_has_n_placeholder() -> None:
    pool = BEAT_CUES["플랭크"]["tick"]
    assert any("{N}" in cue for cue in pool), "플랭크 cue pool must contain {N} template"


def test_get_beat_pool_returns_correct_pool() -> None:
    pool = get_beat_pool("푸시업", "up")
    assert pool == BEAT_CUES["푸시업"]["up"]


def test_get_beat_pool_unknown_exercise_returns_fallback() -> None:
    pool = get_beat_pool("런지", "up")
    assert len(pool) >= 1


def test_get_encouragement_pool_known_point() -> None:
    pool = get_encouragement_pool("second_third")
    assert pool == ENCOURAGEMENT_CUES["second_third"]


def test_get_encouragement_pool_unknown_returns_fallback() -> None:
    pool = get_encouragement_pool("unknown_point")
    assert len(pool) >= 1


def test_pick_cue_random_returns_pool_member() -> None:
    pool = ["A", "B", "C"]
    result = pick_cue(pool, mode="random")
    assert result in pool


def test_pick_cue_sequential_uses_index() -> None:
    pool = ["X", "Y", "Z"]
    assert pick_cue(pool, mode="sequential", index=0) == "X"
    assert pick_cue(pool, mode="sequential", index=1) == "Y"
    assert pick_cue(pool, mode="sequential", index=2) == "Z"
    assert pick_cue(pool, mode="sequential", index=3) == "X"  # wraps


def test_pick_cue_n_substitution() -> None:
    pool = ["{N}초!"]
    result = pick_cue(pool, mode="sequential", index=0, remaining_sec=15.7)
    assert result == "15초!"


def test_pick_cue_n_elapsed_fallback() -> None:
    pool = ["{N}초!"]
    result = pick_cue(pool, mode="sequential", index=0, elapsed_sec=5.0)
    assert result == "5초!"


def test_pick_cue_empty_pool_returns_empty() -> None:
    assert pick_cue([]) == ""
