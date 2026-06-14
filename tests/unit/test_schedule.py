"""Phase v4-8 — 능동 알림 스케줄 순수 로직 (app/core/schedule.py, ADR-027).

음소거 야간 래핑·리드타임·catchup·중복 방지·pending 판정. 외부 의존 없는 순수
함수라 DB 없이 시각만 넣어 검증한다(에이전트가 먼저 잡는다 — testing-strategy).
"""

from datetime import date, datetime, time

from app.core.schedule import (
    KIND_CHECKIN,
    KIND_WORKOUT,
    ScheduleSlot,
    compute_due,
    in_mute_window,
    parse_hhmm,
    pending,
    reminders_for_day,
)

WORKOUT = ScheduleSlot(KIND_WORKOUT, time(18, 0), "운동", "시작할까요?")
CHECKIN = ScheduleSlot(KIND_CHECKIN, time(9, 0), "체크인", "컨디션 기록")


class TestParseHhmm:
    def test_valid(self) -> None:
        assert parse_hhmm("18:00") == time(18, 0)
        assert parse_hhmm("07:30") == time(7, 30)
        assert parse_hhmm(" 9:05 ") == time(9, 5)

    def test_invalid_returns_none(self) -> None:
        for bad in [None, "", "18", "18:60", "24:00", "aa:bb", "18:00:00", "-1:00"]:
            assert parse_hhmm(bad) is None, bad


class TestMuteWindow:
    def test_none_or_equal_means_no_mute(self) -> None:
        assert not in_mute_window(time(23, 0), None, time(7, 0))
        assert not in_mute_window(time(23, 0), time(22, 0), None)
        assert not in_mute_window(time(22, 0), time(22, 0), time(22, 0))

    def test_same_day_window(self) -> None:
        # 13:00–14:00
        assert in_mute_window(time(13, 30), time(13, 0), time(14, 0))
        assert not in_mute_window(time(14, 0), time(13, 0), time(14, 0))  # end 배타
        assert not in_mute_window(time(12, 59), time(13, 0), time(14, 0))

    def test_overnight_wrap(self) -> None:
        # 22:00–07:00 (자정 넘김)
        start, end = time(22, 0), time(7, 0)
        assert in_mute_window(time(23, 0), start, end)
        assert in_mute_window(time(2, 0), start, end)
        assert in_mute_window(time(22, 0), start, end)   # start 포함
        assert not in_mute_window(time(7, 0), start, end)  # end 배타
        assert not in_mute_window(time(12, 0), start, end)


class TestRemindersForDay:
    def test_workout_fires_lead_before(self) -> None:
        today = date(2026, 6, 14)
        [r] = reminders_for_day(today, [WORKOUT], lead_minutes=10)
        assert r.scheduled_for == datetime(2026, 6, 14, 18, 0)
        assert r.fire_at == datetime(2026, 6, 14, 17, 50)
        assert r.kind == KIND_WORKOUT
        assert r.key == "workout|2026-06-14|18:00"

    def test_checkin_no_lead(self) -> None:
        today = date(2026, 6, 14)
        [r] = reminders_for_day(today, [CHECKIN], lead_minutes=10)
        assert r.fire_at == r.scheduled_for == datetime(2026, 6, 14, 9, 0)

    def test_negative_lead_clamped(self) -> None:
        [r] = reminders_for_day(date(2026, 6, 14), [WORKOUT], lead_minutes=-5)
        assert r.fire_at == r.scheduled_for


class TestComputeDue:
    KW = dict(lead_minutes=10, mute_start=None, mute_end=None, catchup_minutes=30)

    def test_due_at_fire_time(self) -> None:
        now = datetime(2026, 6, 14, 17, 50)  # 18:00 운동 - 10 lead
        due = compute_due(now, [WORKOUT], fired_keys=set(), **self.KW)
        assert [r.key for r in due] == ["workout|2026-06-14|18:00"]

    def test_not_due_before_fire(self) -> None:
        now = datetime(2026, 6, 14, 17, 49)
        assert compute_due(now, [WORKOUT], fired_keys=set(), **self.KW) == []

    def test_catchup_window(self) -> None:
        # fire 17:50, catchup 30m → 18:20 까지 따라잡음
        assert compute_due(datetime(2026, 6, 14, 18, 19), [WORKOUT], fired_keys=set(), **self.KW)
        assert compute_due(datetime(2026, 6, 14, 18, 21), [WORKOUT], fired_keys=set(), **self.KW) == []

    def test_fired_key_deduped(self) -> None:
        now = datetime(2026, 6, 14, 17, 55)
        fired = {"workout|2026-06-14|18:00"}
        assert compute_due(now, [WORKOUT], fired_keys=fired, **self.KW) == []

    def test_mute_suppresses_toast(self) -> None:
        now = datetime(2026, 6, 14, 23, 0)
        late = ScheduleSlot(KIND_WORKOUT, time(23, 0), "운동", "야간")
        kw = dict(self.KW, mute_start=time(22, 0), mute_end=time(7, 0))
        assert compute_due(now, [late], fired_keys=set(), **kw) == []


class TestPending:
    def test_lists_past_unacked(self) -> None:
        now = datetime(2026, 6, 14, 19, 0)
        p = pending(now, [WORKOUT, CHECKIN], lead_minutes=10, acked_keys=set())
        assert {r.key for r in p} == {"workout|2026-06-14|18:00", "checkin|2026-06-14|09:00"}

    def test_excludes_acked(self) -> None:
        now = datetime(2026, 6, 14, 19, 0)
        p = pending(
            now, [WORKOUT], lead_minutes=10, acked_keys={"workout|2026-06-14|18:00"}
        )
        assert p == []

    def test_excludes_future(self) -> None:
        now = datetime(2026, 6, 14, 8, 0)  # 체크인 09:00 아직, 운동도 아직
        assert pending(now, [WORKOUT, CHECKIN], lead_minutes=10, acked_keys=set()) == []

    def test_ignores_mute(self) -> None:
        # 음소거여도 앱 내 목록엔 보여야 함 — pending 은 mute 인자 자체가 없다.
        now = datetime(2026, 6, 14, 23, 30)
        late = ScheduleSlot(KIND_WORKOUT, time(23, 0), "운동", "야간")
        assert pending(now, [late], lead_minutes=0, acked_keys=set())
