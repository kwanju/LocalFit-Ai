"""컨디션 체크인 API — POST /api/condition/checkin (ADR-023).

세션 시작 전(또는 일일) 자가보고 체크인. ``session_id`` 없이 저장하고, 세션이 생성될 때
``ws_voice`` 가 가장 최근 미연결 체크인을 연결한다(ConditionRepository.link_latest_unlinked).

체크인은 선택형(ADR-023) — 모든 필드 생략 가능하다. 자유 메모는 ConditionLog.notes 에
보관하며, 부드러운 선호로의 메모리 2층(ADR-025) 승격은 대화 중 LLM(remember_fact)이 판단한다
(체크인 엔드포인트는 자동 승격하지 않는다). 로컬-only(ADR-002): 외부 건강 API 미연동.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from loguru import logger
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.engine import get_session
from app.db.repositories import ConditionRepository

router = APIRouter(prefix="/api/condition", tags=["condition"])


class CheckinRequest(BaseModel):
    # fatigue 는 기존 1–10 척도, soreness 는 ADR-023 의 1–5 척도. 모두 선택.
    fatigue: int | None = Field(default=None, ge=1, le=10)
    soreness: int | None = Field(default=None, ge=1, le=5)
    note: str | None = Field(default=None, max_length=500)


class CheckinResult(BaseModel):
    id: int
    saved: bool


@router.post("/checkin", status_code=201)
async def submit_checkin(
    body: CheckinRequest, session: AsyncSession = Depends(get_session)
) -> CheckinResult:
    note = body.note.strip() if body.note else None
    log = await ConditionRepository(session).create(
        fatigue_level=body.fatigue,
        soreness=body.soreness,
        notes=note or None,
    )
    assert log.id is not None  # commit+refresh 후 PK 보장
    logger.info(
        "condition checkin saved: id={} fatigue={} soreness={}",
        log.id,
        body.fatigue,
        body.soreness,
    )
    return CheckinResult(id=log.id, saved=True)
