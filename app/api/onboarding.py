"""Onboarding (PRD 부록 A): profile + fitness assessment → first routine.

Single-user (ADR-002): profile is always DEFAULT_USER_ID. Routine generation
logic lives in app.core.onboarding; this layer only persists (api 얇게).
"""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.onboarding import (
    PLANK,
    PULLUP,
    PUSHUP,
    SQUAT,
    default_routine_for_level,
    routine_from_assessment,
)
from app.db.engine import get_session
from app.db.models import FitnessLevel, Routine, RoutineExercise, UserProfile
from app.db.repositories import ExerciseRepository, RoutineRepository, UserProfileRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

_FIRST_ROUTINE_NAME: str = "첫 루틴"
_FIRST_ROUTINE_DESC: str = "온보딩 자동 생성 루틴"


class AssessmentInput(BaseModel):
    pullup_max: int | None = None
    pushup_max: int | None = None
    squat_max: int | None = None
    plank_max_sec: int | None = None

    def to_maxes(self) -> dict[str, int]:
        raw = {
            PULLUP: self.pullup_max,
            PUSHUP: self.pushup_max,
            SQUAT: self.squat_max,
            PLANK: self.plank_max_sec,
        }
        return {name: value for name, value in raw.items() if value is not None}


class OnboardingRequest(BaseModel):
    name: str = "사용자"
    age: int | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    fitness_level: FitnessLevel = FitnessLevel.beginner
    available_times: list[str] = []
    goal: str | None = None
    # If provided (부록 A-2 측정), overrides the self-evaluation defaults (부록 A-3).
    assessment: AssessmentInput | None = None


class OnboardingResult(BaseModel):
    profile: UserProfile
    routine: Routine
    exercises: list[RoutineExercise]


class OnboardingStatus(BaseModel):
    onboarded: bool
    profile: UserProfile | None = None


@router.get("")
async def get_onboarding(session: AsyncSession = Depends(get_session)) -> OnboardingStatus:
    profile = await UserProfileRepository(session).get()
    return OnboardingStatus(onboarded=profile is not None, profile=profile)


@router.post("", status_code=201)
async def submit_onboarding(
    body: OnboardingRequest, session: AsyncSession = Depends(get_session)
) -> OnboardingResult:
    profile = await UserProfileRepository(session).upsert(
        name=body.name,
        fitness_level=body.fitness_level,
        available_times=body.available_times,
        goal=body.goal,
        age=body.age,
        weight_kg=body.weight_kg,
        height_cm=body.height_cm,
    )

    maxes = body.assessment.to_maxes() if body.assessment else {}
    prescriptions = (
        routine_from_assessment(maxes)
        if maxes
        else default_routine_for_level(body.fitness_level.value)
    )

    routine_repo = RoutineRepository(session)
    exercise_repo = ExerciseRepository(session)
    routine = await routine_repo.create(name=_FIRST_ROUTINE_NAME, description=_FIRST_ROUTINE_DESC)

    links: list[RoutineExercise] = []
    order_index = 0
    for prescription in prescriptions:
        exercise = await exercise_repo.get_by_name(prescription.exercise_name)
        if exercise is None:
            logger.warning("Onboarding: seed exercise '%s' missing", prescription.exercise_name)
            continue
        link = await routine_repo.add_exercise(
            routine_id=routine.id,
            exercise_id=exercise.id,
            sets=prescription.sets,
            reps=prescription.reps,
            duration_sec=prescription.duration_sec,
            order_index=order_index,
        )
        links.append(link)
        order_index += 1

    logger.info("Onboarding complete: profile=%d routine=%d", profile.id, routine.id)
    return OnboardingResult(profile=profile, routine=routine, exercises=links)
