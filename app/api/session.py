"""Session REST endpoints. Live coaching runs over /ws/coach; these manage records."""


from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.engine import get_session
from app.db.models import SessionMode, SessionStatus, WorkoutSession
from app.db.repositories import SessionRepository

router = APIRouter(prefix="/sessions", tags=["session"])

_DEFAULT_RECENT_LIMIT: int = 10


class SessionCreate(BaseModel):
    mode: SessionMode = SessionMode.c2c
    routine_id: int | None = None


@router.post("", status_code=201)
async def create_session(
    body: SessionCreate, session: AsyncSession = Depends(get_session)
) -> WorkoutSession:
    repo = SessionRepository(session)
    return await repo.create(mode=body.mode.value, routine_id=body.routine_id)


@router.get("")
async def list_sessions(
    limit: int = _DEFAULT_RECENT_LIMIT, session: AsyncSession = Depends(get_session)
) -> list[WorkoutSession]:
    repo = SessionRepository(session)
    return await repo.get_recent(limit=limit)


@router.get("/{session_id}")
async def get_session_by_id(
    session_id: int, session: AsyncSession = Depends(get_session)
) -> WorkoutSession:
    repo = SessionRepository(session)
    ws = await repo.get_by_id(session_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return ws


@router.post("/{session_id}/end")
async def end_session(
    session_id: int, session: AsyncSession = Depends(get_session)
) -> WorkoutSession:
    repo = SessionRepository(session)
    ws = await repo.end_session(session_id, SessionStatus.completed)
    if ws is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return ws
