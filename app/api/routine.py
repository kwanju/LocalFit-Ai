"""Routine CRUD. Single-user (ADR-002): routines belong to DEFAULT_USER_ID implicitly."""


from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.engine import get_session
from app.db.models import DEFAULT_REST_SEC, Routine, RoutineExercise
from app.db.repositories import RoutineRepository

router = APIRouter(prefix="/routines", tags=["routine"])


class RoutineExerciseInput(BaseModel):
    exercise_id: int
    sets: int
    reps: int | None = None
    duration_sec: int | None = None
    rest_sec: int = DEFAULT_REST_SEC


class RoutineCreate(BaseModel):
    name: str
    description: str | None = None
    exercises: list[RoutineExerciseInput] = []


class RoutineDetail(BaseModel):
    routine: Routine
    exercises: list[RoutineExercise]


@router.post("", status_code=201)
async def create_routine(
    body: RoutineCreate, session: AsyncSession = Depends(get_session)
) -> RoutineDetail:
    routine_repo = RoutineRepository(session)
    routine = await routine_repo.create(name=body.name, description=body.description)
    links: list[RoutineExercise] = []
    for order_index, item in enumerate(body.exercises):
        link = await routine_repo.add_exercise(
            routine_id=routine.id,
            exercise_id=item.exercise_id,
            sets=item.sets,
            reps=item.reps,
            duration_sec=item.duration_sec,
            rest_sec=item.rest_sec,
            order_index=order_index,
        )
        links.append(link)
    return RoutineDetail(routine=routine, exercises=links)


@router.get("")
async def list_routines(session: AsyncSession = Depends(get_session)) -> list[Routine]:
    return await RoutineRepository(session).list_all()


@router.get("/{routine_id}")
async def get_routine(
    routine_id: int, session: AsyncSession = Depends(get_session)
) -> RoutineDetail:
    repo = RoutineRepository(session)
    routine = await repo.get_by_id(routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail="루틴을 찾을 수 없습니다.")
    exercises = await repo.list_exercises(routine_id)
    return RoutineDetail(routine=routine, exercises=exercises)


@router.delete("/{routine_id}", status_code=204)
async def delete_routine(routine_id: int, session: AsyncSession = Depends(get_session)) -> None:
    deleted = await RoutineRepository(session).delete(routine_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="루틴을 찾을 수 없습니다.")
