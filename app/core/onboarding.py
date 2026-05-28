"""Onboarding routine generation (PRD 부록 A).

Pure Python — no FastAPI / SQLModel / adapter imports (CLAUDE.md §4). Produces
exercise prescriptions; the API layer maps them to seeded Exercise rows and
persists them through the repository (ADR-007).
"""

from dataclasses import dataclass

# Seeded exercise names (app.db.models.EXERCISE_SEED). Duplicated here to keep core pure.
PULLUP = "풀업"
PUSHUP = "푸시업"
SQUAT = "스쿼트"
PLANK = "플랭크"

# 플랭크 is timer-based (duration); the rest are rep-based (PRD 부록 A-2).
_TIMER_EXERCISES: frozenset[str] = frozenset({PLANK})

_DEFAULT_SETS: int = 3

# 부록 A-3 자가 평가 기본값 (sets are _DEFAULT_SETS; values are reps, or seconds for 플랭크).
_SELF_EVAL: dict[str, dict[str, int]] = {
    "beginner": {PULLUP: 3, PUSHUP: 8, SQUAT: 10, PLANK: 20},
    "intermediate": {PULLUP: 6, PUSHUP: 12, SQUAT: 15, PLANK: 30},
    "advanced": {PULLUP: 10, PUSHUP: 20, SQUAT: 20, PLANK: 60},
}

# 부록 A-2 체력 측정 → 초기 처방 계수 (max × multiplier).
_ASSESSMENT_MULTIPLIER: dict[str, float] = {
    PULLUP: 0.6,
    PUSHUP: 0.65,
    SQUAT: 0.65,
    PLANK: 0.7,
}


@dataclass
class ExercisePrescription:
    exercise_name: str
    sets: int
    reps: int | None = None
    duration_sec: int | None = None


def _prescribe(name: str, value: int) -> ExercisePrescription:
    if name in _TIMER_EXERCISES:
        return ExercisePrescription(exercise_name=name, sets=_DEFAULT_SETS, duration_sec=value)
    return ExercisePrescription(exercise_name=name, sets=_DEFAULT_SETS, reps=value)


def default_routine_for_level(fitness_level: str) -> list[ExercisePrescription]:
    """Self-evaluation default routine for a fitness level (부록 A-3)."""
    values = _SELF_EVAL.get(fitness_level, _SELF_EVAL["beginner"])
    return [_prescribe(name, value) for name, value in values.items()]


def routine_from_assessment(maxes: dict[str, int]) -> list[ExercisePrescription]:
    """Routine from measured maxima (부록 A-2). ``maxes`` keys are exercise names."""
    prescriptions: list[ExercisePrescription] = []
    for name, multiplier in _ASSESSMENT_MULTIPLIER.items():
        raw = maxes.get(name)
        if raw is None:
            continue
        prescriptions.append(_prescribe(name, max(1, round(raw * multiplier))))
    return prescriptions
