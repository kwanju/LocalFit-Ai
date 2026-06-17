"""Google Calendar 연동 API — ``/api/gcal`` (ADR-022).

⚠️ ADR-020 운동 히트맵의 ``/api/calendar`` (``app/api/calendar.py``)와 **다른** 네임스페이스다.
히트맵은 로컬 DB 통계, 여기는 외부 Google Calendar(OAuth2 Desktop). 절대 섞지 않는다
(phase-9 명세 ⚠️).

확답 게이트(ADR-022/013, 자동 등록 금지): 운동 일정 등록은 ``/plan/preview`` 로 먼저
보여주고, 사용자가 명시적으로 ``confirm=true`` 를 보낸 ``/plan/register`` 에서만 쓴다.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request
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


# ── 경량 CRUD: 내 일정 보기/추가/삭제 (ADR-034) ────────────────────────────
# ⚠️ 운동 플랜 등록(/plan/*)의 확답 게이트와 별개다. 여기는 사용자가 기록 탭에서 직접
# 누르는 명시 액션이라 즉시 반영한다(미리보기 단계 없음).


class CalEventOut(BaseModel):
    id: str
    summary: str
    start: str  # ISO (종일이면 날짜 자정)
    end: str
    all_day: bool


class EventsOut(BaseModel):
    connected: bool  # 미연동이면 events=[] + connected=false → UI 가 연동 안내로 degrade
    events: list[CalEventOut]


@router.get("/events")
async def list_events(
    request: Request,
    from_: str = Query(alias="from"),
    to: str = Query(alias="to"),
) -> EventsOut:
    """``from``~``to``(ISO) 구간의 전체 일정. 미연동/오류면 빈 목록 + connected=false."""
    try:
        time_min = datetime.fromisoformat(from_)
        time_max = datetime.fromisoformat(to)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="from/to 는 ISO 날짜·시각이어야 합니다.") from e
    svc = _service(request)
    connected = await svc.is_connected()
    events = await svc.list_events(time_min, time_max) if connected else []
    return EventsOut(
        connected=connected,
        events=[
            CalEventOut(
                id=e.event_id,
                summary=e.summary,
                start=e.start.isoformat(),
                end=e.end.isoformat(),
                all_day=e.all_day,
            )
            for e in events
        ],
    )


class CreateEventRequest(BaseModel):
    summary: str
    start: str  # ISO 시작 시각
    duration_min: int = 30


@router.post("/events")
async def create_event(body: CreateEventRequest, request: Request) -> CalEventOut:
    """사용자가 기록 탭에서 직접 잡는 일정 생성(명시 액션 = 즉시 반영, ADR-034)."""
    cfg = _gcal_config(request)
    if not cfg.enabled:
        raise HTTPException(status_code=400, detail="캘린더 연동이 비활성화되어 있습니다.")
    try:
        start = datetime.fromisoformat(body.start)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="start 는 ISO 날짜·시각이어야 합니다.") from e
    summary = body.summary.strip()
    if not summary:
        raise HTTPException(status_code=400, detail="일정 제목을 입력해 주세요.")
    event_id = await _service(request).create_event(summary, start, body.duration_min)
    if event_id is None:
        raise HTTPException(status_code=400, detail="캘린더에 연동되어 있지 않습니다.")
    end = start + timedelta(minutes=max(5, body.duration_min))
    return CalEventOut(
        id=event_id, summary=summary, start=start.isoformat(), end=end.isoformat(), all_day=False
    )


@router.delete("/events/{event_id}", status_code=204)
async def delete_event(event_id: str, request: Request) -> None:
    """일정 삭제. 미연동/오류면 400(UI 가 안내). 성공은 204."""
    ok = await _service(request).delete_event(event_id)
    if not ok:
        raise HTTPException(status_code=400, detail="일정을 삭제하지 못했습니다.")


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
