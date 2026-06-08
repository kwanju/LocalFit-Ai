"""tests/unit/test_counting_cues.py — cue pool 검증 + count_word (2026-06-04 개정)."""

import pytest

from app.core.counting_cues import (
    BEAT_CUES,
    ENCOURAGEMENT_CUES,
    count_word,
    get_beat_pool,
    get_encouragement_pool,
    pick_cue,
)

# 메트로놈 운동은 count_word("하나", "둘", …)로 직접 카운트하므로 BEAT_CUES에 등재하지 않음.
# 플랭크(timer)만 BEAT_CUES["플랭크"]["tick"] 풀을 가진다.
_TIMER_EXERCISES = ["플랭크"]
_ENC_POINTS = ["first_third", "second_third", "last"]


@pytest.mark.parametrize("exercise", _TIMER_EXERCISES)
def test_beat_cue_pool_not_empty(exercise: str) -> None:
    assert exercise in BEAT_CUES, f"No cue pool for exercise: {exercise}"
    for phase, pool in BEAT_CUES[exercise].items():
        assert len(pool) >= 3, f"{exercise}/{phase}: pool has <3 cues ({len(pool)})"


def test_beat_cue_pool_5_or_more() -> None:
    """타이머(플랭크) cue 풀은 5종 권장."""
    for ex, phases in BEAT_CUES.items():
        for phase, pool in phases.items():
            assert len(pool) >= 5, f"{ex}/{phase}: expected ≥5 cues, got {len(pool)}"


def test_count_word_korean_ordinals() -> None:
    assert count_word(1) == "하나!"
    assert count_word(2) == "둘!"
    assert count_word(10) == "열!"
    assert count_word(20) == "스물!"


def test_count_word_fallback_above_20() -> None:
    assert count_word(21) == "21회!"
    assert count_word(99) == "99회!"


def test_count_word_zero_or_negative_returns_empty() -> None:
    assert count_word(0) == ""
    assert count_word(-1) == ""


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


def test_get_beat_pool_plank_tick() -> None:
    pool = get_beat_pool("플랭크", "tick")
    assert pool == BEAT_CUES["플랭크"]["tick"]


def test_get_beat_pool_unknown_returns_empty() -> None:
    # 메트로놈 운동(풀업/푸시업/스쿼트)이나 등재되지 않은 운동은 빈 풀.
    # CountingEngine은 메트로놈 운동에서 count_word를 직접 쓰므로 풀은 안 쓰임.
    assert get_beat_pool("푸시업", "up") == []
    assert get_beat_pool("런지", "up") == []


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


def test_set_ordinal_korean_native() -> None:
    """세트 서수는 native 한국어 ("두 번째") — TTS가 "2/3"을 분수로 읽던 문제 (2026-06-08)."""
    from app.core.counting_cues import set_ordinal

    assert set_ordinal(1) == "첫 번째"
    assert set_ordinal(2) == "두 번째"
    assert set_ordinal(3) == "세 번째"
    assert set_ordinal(4) == "네 번째"
    assert set_ordinal(10) == "열 번째"
    assert set_ordinal(11) == "11번째"  # 11+ fallback
