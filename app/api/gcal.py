"""Google Calendar 연동 API — ``/api/gcal`` (ADR-022).

⚠️ ADR-020 운동 히트맵의 ``/api/calendar`` (``app/api/calendar.py``)와 **다른** 네임스페이스다.
히트맵은 로컬 DB 통계, 여기는 외부 Google Calendar(OAuth2 Desktop). 절대 섞지 않는다
(phase-9 명세 ⚠️).

확답 게이트(ADR-022/013, 자동 등록 금지): 운동 일정 등록은 ``/plan/preview`` 로 먼저
보여주고, 사용자가 명시적으로 ``confirm=true`` 를 보낸 ``/plan/register`` 에서만 쓴다.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import GoogleCalendarConfig
from app.pipecat_services.calendar_sync import CalendarSyncService

router = APIRouter(prefix="/api/gcal", tags=["gcal"])


def _gcal_config(request: Request) -> GoogleCalendarConfig:
    config = getattr(request.app.state, "config", None)
    return config.google_calendar if config is not None else GoogleCalendarConfig()


def _service(request: Request) -> CalendarSyncService:
    return CalendarSyncService(_gcal_config(request))


class StatusOut(BaseModel):
    enabled: bool
    connected: bool


@router.get("/status")
async def status(request: Request) -> StatusOut:
    """연동 상태. ``connected=false`` 면 UI 가 "연동하기" 버튼을 노출(미연동 = 로컬 fallback)."""
    cfg = _gcal_config(request)
    svc = _service(request)
    return StatusOut(enabled=cfg.enabled, connected=await svc.is_connected())


@router.post("/connect")
async def connect(request: Request) -> StatusOut:
    """OAuth2 Desktop 동의 흐름 1회 실행(로컬 브라우저) → 토큰 keyring 저장.

    사용자가 명시적으로 "연동" 을 누를 때만 호출한다. 비활성/실패는 안내 후 미연동 유지.
    """
    cfg = _gcal_config(request)
    if not cfg.enabled:
        raise HTTPException(status_code=400, detail="캘린더 연동이 설정에서 비활성화되어 있습니다.")
    from app.adapters.calendar.oauth import CalendarAuthError, run_desktop_flow

    try:
        await asyncio.to_thread(run_desktop_flow, cfg.credentials_path)
    except CalendarAuthError as e:
        # 사용자 안내(한국어) — 무시하지 않고 그대로 전달(ADR-018).
        raise HTTPException(status_code=400, detail=str(e)) from e
    return StatusOut(enabled=cfg.enabled, connected=await _service(request).is_connected())


@router.post("/disconnect")
async def disconnect(request: Request) -> StatusOut:
    """연동 해제(토큰 삭제). 이후 캘린더 기능은 로컬 fallback 으로 degrade."""
    from app.adapters.calendar.oauth import disconnect as _disconnect

    await asyncio.to_thread(_disconnect)
    cfg = _gcal_config(request)
    return StatusOut(enabled=cfg.enabled, connected=False)


class GapsOut(BaseModel):
    connected: bool
    hint: str | None


@router.get("/gaps")
async def gaps(request: Request) -> GapsOut:
    """오늘 빈 시간 힌트(§9-3). 미연동/오프라인이면 ``hint=null`` 로 degrade."""
    svc = _service(request)
    connected = await svc.is_connected()
    hint = await svc.today_gap_hint() if connected else None
    return GapsOut(connected=connected, hint=hint)


class ProposedEventOut(BaseModel):
    exercise: str
    start: str
    end: str
    summary: str


@router.post("/plan/preview")
async def plan_preview(request: Request) -> list[ProposedEventOut]:
    """활성 주간 플랜에서 등록할 운동 이벤트 미리보기(§9-2). **쓰지 않는다** — 확답 게이트
    1단계. UI 가 이 목록을 보여주고 사용자가 확인하면 ``/plan/register`` 를 호출한다."""
    events = await _service(request).preview_plan_events()
    return [
        ProposedEventOut(
            exercise=e.exercise,
            start=e.start.isoformat(),
            end=e.end.isoformat(),
            summary=e.summary,
        )
        for e in events
    ]


class RegisterRequest(BaseModel):
    confirm: bool = False  # 자동 등록 금지(ADR-022/013) — 명시적 true 일 때만 쓴다.


class RegisterResultOut(BaseModel):
    created: int
    skipped: int
    events: list[ProposedEventOut]


@router.post("/plan/register")
async def plan_register(body: RegisterRequest, request: Request) -> RegisterResultOut:
    """확답 게이트 2단계 — ``confirm=true`` 일 때만 캘린더에 실제 등록(§9-2).

    동의 없는(``confirm`` 누락/false) 요청은 ``400`` 으로 거부한다 — 회귀 가드.
    미연동이면 created=0(로컬 fallback, 코칭 영향 없음).
    """
    if not body.confirm:
        raise HTTPException(
            status_code=400, detail="등록하려면 confirm=true 로 사용자 확인이 필요합니다."
        )
    cfg = _gcal_config(request)
    if not cfg.enabled:
        raise HTTPException(status_code=400, detail="캘린더 연동이 비활성화되어 있습니다.")
    result = await _service(request).register_plan_events()
    return RegisterResultOut(
        created=result.created,
        skipped=result.skipped,
        events=[
            ProposedEventOut(
                exercise=e.exercise,
                start=e.start.isoformat(),
                end=e.end.isoformat(),
                summary=e.summary,
            )
            for e in result.events
        ],
    )
