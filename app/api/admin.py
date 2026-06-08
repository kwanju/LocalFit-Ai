"""Admin / 데이터 관리 엔드포인트 (테스트 및 신규 사용자 시나리오 검증용).

ADR-002 단일 사용자 가정이라 인증·권한이 없다. 모든 데이터를 비우거나(=신규 사용자)
운동 기록만 비우는(=온보딩은 유지) 두 가지 모드 제공.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.engine import get_session
from app.db.models import (
    ConditionLog,
    InteractionLog,
    Routine,
    RoutineExercise,
    SetLog,
    UserProfile,
    WorkoutSession,
)

router = APIRouter(prefix="/admin", tags=["admin"])


class ResetResult(BaseModel):
    cleared: dict[str, int]
    scope: str


@router.post("/reset")
async def reset_records(
    scope: str = Query(
        "history",
        description="'history' = 운동 기록만 / 'all' = 프로필·루틴 포함 전부",
        pattern="^(history|all)$",
    ),
    session: AsyncSession = Depends(get_session),
) -> ResetResult:
    """운동 기록(세션·세트·컨디션·대화) 또는 전체 데이터 비우기.

    - ``scope=history``: WorkoutSession / SetLog / ConditionLog / InteractionLog 삭제.
      온보딩(UserProfile, Routine, RoutineExercise) 은 보존 — 사용자가 같은 프로필로
      재테스트할 수 있도록.
    - ``scope=all``: 위 + UserProfile + Routine + RoutineExercise 까지 모두 삭제.
      Exercise seed 데이터는 보존(앱 부팅 시 자동 재생성 가능하지만 굳이 지우지 않음).
    """
    cleared: dict[str, int] = {}

    async def _delete(model, name: str) -> None:
        result = await session.execute(delete(model))
        cleared[name] = int(result.rowcount or 0)

    # ForeignKey 의존성 역순으로 삭제 (자식 → 부모).
    await _delete(InteractionLog, "interaction_log")
    await _delete(ConditionLog, "condition_log")
    await _delete(SetLog, "set_log")
    await _delete(WorkoutSession, "session")

    if scope == "all":
        await _delete(RoutineExercise, "routine_exercise")
        await _delete(Routine, "routine")
        await _delete(UserProfile, "user_profile")

    await session.commit()
    logger.info("admin.reset scope={} cleared={}", scope, cleared)
    return ResetResult(cleared=cleared, scope=scope)
