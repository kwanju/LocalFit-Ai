"""Google Calendar API 클라이언트 (ADR-022).

``googleapiclient`` 의 동기 호출을 얇게 감싼다 — free/busy 읽기, 운동 이벤트 등록,
오늘 운동 이벤트 읽기. 호출은 모두 **동기**(blocking)이므로 async 컨텍스트에서는
호출부가 ``asyncio.to_thread`` 로 감싼다(``calendar_sync``).

ADR-012: adapters 는 ``app.core`` 를 import 하지 않는다 — 그래서 여기서는 ``BusyInterval``
같은 core 타입을 쓰지 않고 평범한 ``(start, end)`` 튜플을 돌려준다. core 타입 변환은
``pipecat_services`` 계층이 한다.

시각은 로컬 wall-clock naive ``datetime`` 으로 주고받는다(단일 사용자, ADR-002). 내부에서
RFC3339(타임존 포함)로 변환해 Google 에 보내고, 응답은 로컬 naive 로 되돌린다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from loguru import logger

# 외부 Google HTTP 호출 상한(초). httplib2 기본은 None(무한 대기)이라 블랙홀 네트워크에서
# to_thread 워커가 영영 안 풀린다 — 명시 타임아웃으로 막는다(코드리뷰 D-5).
_HTTP_TIMEOUT_SEC = 10


def _to_rfc3339(dt: datetime) -> str:
    """naive 로컬 ``datetime`` → 타임존 오프셋이 붙은 RFC3339 문자열."""
    return dt.astimezone().isoformat()


def _from_rfc3339(value: str) -> datetime | None:
    """RFC3339 문자열 → 로컬 naive ``datetime``. 날짜만(종일 일정)이면 None."""
    if not value or "T" not in value:  # all-day 이벤트(date only)는 busy 판정에서 제외
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _parse_event_dt(node: dict) -> tuple[datetime | None, bool]:
    """events().list 의 start/end 노드 → ``(로컬 naive datetime, all_day)``.

    ``dateTime`` 키면 시각 있는 일반 일정, ``date`` 키면 종일(all-day) 일정이다.
    파싱 실패/빈 노드는 ``(None, …)`` 로 돌려 호출부가 건너뛴다.
    """
    date_time = node.get("dateTime")
    if date_time:
        return _from_rfc3339(date_time), False
    date_only = node.get("date")
    if date_only:
        try:
            return datetime.fromisoformat(date_only), True
        except ValueError:
            return None, True
    return None, False


@dataclass(frozen=True)
class WorkoutEvent:
    """등록/조회된 운동 이벤트 한 칸(평문 값 객체 — core 타입 아님)."""

    event_id: str
    start: datetime
    summary: str


@dataclass(frozen=True)
class CalEvent:
    """캘린더의 임의 일정 한 칸(운동 마커 무관 전체 일정 — ADR-034 보기용 값 객체).

    ``all_day`` 면 ``start``/``end`` 는 그 날짜 자정 기준(시각 의미 없음, 표시만).
    """

    event_id: str
    summary: str
    start: datetime
    end: datetime
    all_day: bool


class GoogleCalendarClient:
    """단일 사용자 본인 캘린더(ADR-002) 대상 동기 클라이언트.

    ``connect()`` 가 저장된 자격증명으로 빌드한다. 미연동/오프라인이면 None 을 돌려주고,
    호출부는 로컬 fallback 으로 degrade 한다(ADR-022 안 행복한 경로).
    """

    def __init__(self, service, calendar_id: str = "primary") -> None:
        self._service = service
        self._calendar_id = calendar_id

    @classmethod
    def connect(cls, calendar_id: str = "primary") -> GoogleCalendarClient | None:
        from app.adapters.calendar.oauth import get_credentials

        creds = get_credentials()
        if creds is None:
            return None
        try:
            import httplib2
            from google_auth_httplib2 import AuthorizedHttp
            from googleapiclient.discovery import build

            # credentials= 대신 타임아웃 있는 http= 주입(둘은 배타) — 모든 호출에 상한.
            authed_http = AuthorizedHttp(creds, http=httplib2.Http(timeout=_HTTP_TIMEOUT_SEC))
            service = build("calendar", "v3", http=authed_http, cache_discovery=False)
        except Exception as e:  # noqa: BLE001 — 라이브러리/네트워크 오류 → 미연동 degrade
            logger.error("calendar service build failed: {}", e)
            return None
        return cls(service, calendar_id)

    def list_busy(self, time_min: datetime, time_max: datetime) -> list[tuple[datetime, datetime]]:
        """``time_min``~``time_max`` 의 바쁜 구간 ``(start, end)`` 목록(로컬 naive)."""
        body = {
            "timeMin": _to_rfc3339(time_min),
            "timeMax": _to_rfc3339(time_max),
            "items": [{"id": self._calendar_id}],
        }
        resp = self._service.freebusy().query(body=body).execute()
        cal = resp.get("calendars", {}).get(self._calendar_id, {})
        out: list[tuple[datetime, datetime]] = []
        for slot in cal.get("busy", []):
            start = _from_rfc3339(slot.get("start", ""))
            end = _from_rfc3339(slot.get("end", ""))
            if start is not None and end is not None:
                out.append((start, end))
        return out

    def insert_workout_event(
        self, start: datetime, end: datetime, summary: str, description: str | None = None
    ) -> str:
        """운동 이벤트 등록 → event id. ``summary`` 는 읽기 필터 마커 겸용."""
        body = {
            "summary": summary,
            "description": description or "",
            "start": {"dateTime": _to_rfc3339(start)},
            "end": {"dateTime": _to_rfc3339(end)},
            # 우리가 만든 이벤트만 골라 읽기 위한 사적 마커(다른 일정과 구분).
            "extendedProperties": {"private": {"localfit": "workout"}},
        }
        event = self._service.events().insert(calendarId=self._calendar_id, body=body).execute()
        return event.get("id", "")

    def list_workout_events(
        self, time_min: datetime, time_max: datetime
    ) -> list[WorkoutEvent]:
        """우리가 등록한 운동 이벤트(localfit=workout 마커)만 조회 → 시작 시각 목록.

        스케줄러 소스(ADR-027/§9-4)에 쓴다 — 캘린더에 잡힌 운동 이벤트의 시작 시각을
        그 날의 운동 리마인드 슬롯으로 삼는다.
        """
        resp = (
            self._service.events()
            .list(
                calendarId=self._calendar_id,
                timeMin=_to_rfc3339(time_min),
                timeMax=_to_rfc3339(time_max),
                singleEvents=True,
                orderBy="startTime",
                privateExtendedProperty="localfit=workout",
            )
            .execute()
        )
        out: list[WorkoutEvent] = []
        for item in resp.get("items", []):
            start = _from_rfc3339(item.get("start", {}).get("dateTime", ""))
            if start is not None:
                out.append(
                    WorkoutEvent(
                        event_id=item.get("id", ""),
                        start=start,
                        summary=item.get("summary", ""),
                    )
                )
        return out

    # ── 경량 CRUD (ADR-034): 전체 일정 보기/생성/삭제 ──────────────────────
    def list_events(self, time_min: datetime, time_max: datetime) -> list[CalEvent]:
        """``time_min``~``time_max`` 의 **모든** 일정(운동 마커 무관). 종일 일정 포함."""
        resp = (
            self._service.events()
            .list(
                calendarId=self._calendar_id,
                timeMin=_to_rfc3339(time_min),
                timeMax=_to_rfc3339(time_max),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        out: list[CalEvent] = []
        for item in resp.get("items", []):
            start, all_day = _parse_event_dt(item.get("start", {}))
            end, _ = _parse_event_dt(item.get("end", {}))
            if start is None:
                continue
            out.append(
                CalEvent(
                    event_id=item.get("id", ""),
                    summary=item.get("summary", "") or "(제목 없음)",
                    start=start,
                    end=end or start,
                    all_day=all_day,
                )
            )
        return out

    def insert_event(self, start: datetime, end: datetime, summary: str) -> str:
        """운동 마커 없는 일반 일정 생성 → event id(사용자가 앱에서 직접 잡는 일정)."""
        body = {
            "summary": summary,
            "start": {"dateTime": _to_rfc3339(start)},
            "end": {"dateTime": _to_rfc3339(end)},
        }
        event = self._service.events().insert(calendarId=self._calendar_id, body=body).execute()
        return event.get("id", "")

    def delete_event(self, event_id: str) -> None:
        """일정 삭제(우리 마커 무관 — 사용자가 목록에서 고른 임의 일정)."""
        self._service.events().delete(calendarId=self._calendar_id, eventId=event_id).execute()
