"""Unit tests for app.core.onboarding routine generation (PRD 부록 A-2/A-3)."""

from app.core.onboarding import (
    PLANK,
    PULLUP,
    PUSHUP,
    SQUAT,
    default_routine_for_level,
    routine_from_assessment,
)


def test_default_beginner_has_four_exercises() -> None:
    by_name = {p.exercise_name: p for p in default_routine_for_level("beginner")}
    assert set(by_name) == {PULLUP, PUSHUP, SQUAT, PLANK}
    assert by_name[PULLUP].sets == 3 and by_name[PULLUP].reps == 3
    assert by_name[PUSHUP].reps == 8
    assert by_name[SQUAT].reps == 10


def test_default_plank_is_timer_based() -> None:
    plank = {p.exercise_name: p for p in default_routine_for_level("beginner")}[PLANK]
    assert plank.duration_sec == 20
    assert plank.reps is None


def test_default_advanced_values() -> None:
    by_name = {p.exercise_name: p for p in default_routine_for_level("advanced")}
    assert by_name[PULLUP].reps == 10
    assert by_name[PLANK].duration_sec == 60


def test_unknown_level_falls_back_to_beginner() -> None:
    assert default_routine_for_level("zzz") == default_routine_for_level("beginner")


def test_assessment_applies_multipliers() -> None:
    by_name = {
        p.exercise_name: p
        for p in routine_from_assessment({PULLUP: 10, PUSHUP: 20, SQUAT: 20, PLANK: 100})
    }
    assert by_name[PULLUP].reps == 6  # round(10 * 0.6)
    assert by_name[PUSHUP].reps == 13  # round(20 * 0.65)
    assert by_name[SQUAT].reps == 13  # round(20 * 0.65)
    assert by_name[PLANK].duration_sec == 70  # round(100 * 0.7)


def test_assessment_uses_only_provided_exercises() -> None:
    prescriptions = routine_from_assessment({PULLUP: 5})
    assert [p.exercise_name for p in prescriptions] == [PULLUP]


def test_assessment_floors_at_one_rep() -> None:
    pullup = routine_from_assessment({PULLUP: 1})[0]
    assert pullup.reps == 1  # max(1, round(1 * 0.6))
