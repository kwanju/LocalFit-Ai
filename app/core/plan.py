"""운동 플랜 순수 도메인 로직 (ADR-024).

일자 분배(주간 목표 횟수 → 요일 배치)와 진척 요약은 외부 의존이 없는 순수 함수로
둔다(ADR-012 core 규칙 — DB/Pipecat/instructor import 금지). ``PlanRepository`` 가
이 함수들을 호출해 ``PlanDay`` 행을 만들고 코치 컨텍스트 문자열을 조립한다.
"""

from __future__ import annotations

from dataclasses import dataclass

_DAYS_PER_WEEK: int = 7
# 요일 한글 약칭 (0=월 … 6=일). 컨텍스트/진척 요약 표기에 사용.
_WEEKDAY_KO: tuple[str, ...] = ("월", "화", "수", "목", "금", "토", "일")


def distribute_weekdays(target_count: int, *, days_per_week: int = _DAYS_PER_WEEK) -> list[int]:
    """주간 목표 횟수를 한 주에 **고르게** 펼친 요일 인덱스 목록(0=월 … 6=일).

    예: 3회 → [0, 2, 4](월·수·금), 2회 → [0, 3], 1회 → [0].
    ``target_count`` 이 주당 일수보다 많으면(예: 하루 2회) 요일이 중복될 수 있고,
    중복은 같은 요일에 두 칸을 둔다(정렬 보존). 0 이하면 빈 목록.
    """
    if target_count <= 0:
        return []
    days = max(days_per_week, 1)
    # 균등 분배: i 번째 칸을 round(i * days / count) 요일에 배치.
    return [min((i * days) // target_count, days - 1) for i in range(target_count)]


def weekday_label(weekday: int) -> str:
    """요일 인덱스 → 한글 약칭. 범위 밖이면 빈 문자열."""
    if 0 <= weekday < len(_WEEKDAY_KO):
        return _WEEKDAY_KO[weekday]
    return ""


@dataclass(frozen=True)
class PlanGoalSpec:
    """플랜 생성 입력 — 종목별 주간 목표(횟수·세션당 반복). ``PlanRepository`` 가
    이를 받아 ``WeeklyGoal`` + 분배된 ``PlanDay`` 행으로 펼친다."""

    exercise: str
    target_count: int
    reps: int


@dataclass(frozen=True)
class GoalProgress:
    """종목별 진척 — 컨텍스트/요약용 값 객체."""

    exercise: str
    target_count: int
    completed_count: int
    reps: int

    @property
    def is_done(self) -> bool:
        return self.completed_count >= self.target_count


def summarize_progress(items: list[GoalProgress]) -> str | None:
    """주간 목표·진척을 한 줄 한국어로. 비면 None.

    예: "이번 주 목표: 푸시업 1/3회, 스쿼트 0/2회".
    """
    if not items:
        return None
    parts = [f"{g.exercise} {g.completed_count}/{g.target_count}회" for g in items]
    return "이번 주 목표: " + ", ".join(parts)
