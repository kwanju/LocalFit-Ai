"""Phase v4-4 — 플랜 순수 도메인 로직 (app/core/plan.py, ADR-024).

일자 분배(균등)·진척 요약·요일 라벨. 외부 의존 없는 순수 함수라 DB 없이 검증한다.
"""

import pytest

from app.core.plan import (
    GoalProgress,
    distribute_weekdays,
    summarize_progress,
    weekday_label,
)


class TestDistributeWeekdays:
    def test_zero_or_negative_is_empty(self) -> None:
        assert distribute_weekdays(0) == []
        assert distribute_weekdays(-3) == []

    def test_one_is_monday(self) -> None:
        assert distribute_weekdays(1) == [0]

    def test_three_spread_evenly(self) -> None:
        # 월·수·금 — 한 주에 고르게.
        assert distribute_weekdays(3) == [0, 2, 4]

    def test_seven_fills_each_day(self) -> None:
        assert distribute_weekdays(7) == [0, 1, 2, 3, 4, 5, 6]

    @pytest.mark.parametrize("count", [1, 2, 3, 4, 5, 6, 7])
    def test_length_matches_count_within_week(self, count: int) -> None:
        days = distribute_weekdays(count)
        assert len(days) == count
        assert all(0 <= d <= 6 for d in days)
        # 정렬 보존(이른 요일부터).
        assert days == sorted(days)

    def test_over_a_week_allows_duplicate_days(self) -> None:
        # 하루 2회 등 — 주당 일수 초과 시 요일이 중복될 수 있다.
        days = distribute_weekdays(10)
        assert len(days) == 10
        assert all(0 <= d <= 6 for d in days)


class TestWeekdayLabel:
    def test_known_days(self) -> None:
        assert weekday_label(0) == "월"
        assert weekday_label(6) == "일"

    def test_out_of_range(self) -> None:
        assert weekday_label(7) == ""
        assert weekday_label(-1) == ""


class TestSummarizeProgress:
    def test_empty_is_none(self) -> None:
        assert summarize_progress([]) is None

    def test_summary_line(self) -> None:
        items = [
            GoalProgress("푸시업", target_count=3, completed_count=1, reps=10),
            GoalProgress("스쿼트", target_count=2, completed_count=0, reps=15),
        ]
        out = summarize_progress(items)
        assert out == "이번 주 목표: 푸시업 1/3회, 스쿼트 0/2회"

    def test_is_done_flag(self) -> None:
        assert GoalProgress("플랭크", 2, 2, 30).is_done is True
        assert GoalProgress("플랭크", 2, 1, 30).is_done is False
