"""CoachResponse — structured LLM output for the active coach (ADR-013).

Discriminated union on the ``type`` field so instructor + Ollama JSON mode can
parse mixed action lists. ``text`` has a hard ``max_length=500`` safety cap;
soft length targets per response type live in ``ACTIVE_COACH_PROTOCOL``.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

Exercise = Literal["풀업", "푸시업", "스쿼트", "플랭크"]


class ProposeSetAction(BaseModel):
    type: Literal["propose_set"] = "propose_set"
    exercise: Exercise
    reps: int = Field(ge=1, le=100)
    # sets/rest_sec 는 기본값을 둔다 — LLM(qwen3.5:9b)이 format=schema 에도 이 필드를
    # 누락하는 경우가 있어(2026-06-12), 누락 시 합리적 기본값으로 채워 응답 실패를 막는다.
    # StartCountingAction 과 동일 정책.
    sets: int = Field(default=1, ge=1, le=10)
    rest_sec: int = Field(default=60, ge=15, le=300)


class StartCountingAction(BaseModel):
    type: Literal["start_counting"] = "start_counting"
    exercise: Exercise
    reps: int = Field(ge=1, le=100)
    # 사용자 피드백 (2026-06-07): 단일 세트 말고 처음에 N세트·휴식까지 결정.
    sets: int = Field(default=1, ge=1, le=10)
    rest_sec: int = Field(default=60, ge=15, le=300)


class LogConditionAction(BaseModel):
    type: Literal["log_condition"] = "log_condition"
    fatigue_level: int = Field(ge=1, le=10)
    # ADR-023 근육통 1–5 (선택). 강도 조절 *제안*의 입력이며, 자동 변경은 하지 않는다.
    soreness: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = None


class RecordConstraintAction(BaseModel):
    """1층 부상·제약 저장 (ADR-025). 안전 직결이라 확답 없이 즉시 저장된다."""

    type: Literal["record_constraint"] = "record_constraint"
    kind: Literal["injury", "constraint"]
    text: str = Field(min_length=1, max_length=200)
    severity: str | None = None


class RememberFactAction(BaseModel):
    """2층 자유텍스트 메모 누적 (ADR-025). 부드러운 선호·맥락."""

    type: Literal["remember_fact"] = "remember_fact"
    text: str = Field(min_length=1, max_length=200)
    tags: list[str] = Field(default_factory=list)


class PlanGoalItem(BaseModel):
    """주간 플랜의 종목별 목표 한 칸 (ADR-024)."""

    exercise: Exercise
    # 주간 목표 횟수(세션 수). 보통 1–7. 상한은 하루 2회까지 여유로 14.
    target_count: int = Field(ge=1, le=14)
    # 세션당 권장 반복(횟수 종목) 또는 유지 초(플랭크). 누락 시 합리적 기본값.
    reps: int = Field(default=10, ge=1, le=300)


class ProposePlanAction(BaseModel):
    """주간 목표 제안 (ADR-024). **확답 게이트 통과 후에만** 저장된다 — LLM 이 발행해도
    곧바로 적용되지 않고 제안 슬롯에 들어간다(자동 변경 금지, 회고 ConfirmRule 정신)."""

    type: Literal["propose_plan"] = "propose_plan"
    goals: list[PlanGoalItem] = Field(min_length=1)
    note: str | None = None


class ProposePlanAdjustmentAction(BaseModel):
    """기존 주간 플랜 조정 제안 (ADR-024). 컨디션·목표 실패에 따른 강도/목표 변경 *제안*.
    **확답 게이트 통과 후에만** 적용된다(자동 변경 금지)."""

    type: Literal["propose_plan_adjustment"] = "propose_plan_adjustment"
    exercise: Exercise
    # 새 주간 목표 횟수. 0 = 이번 주 해당 종목 목표를 비움.
    new_target_count: int = Field(ge=0, le=14)
    reason: str | None = None


class BaselineEntry(BaseModel):
    """첫 체력검증 기준선 한 칸 (ADR-028/025 1층). metric: 횟수 종목="reps",
    플랭크 등 시간 종목="duration_sec". value 는 자가보고 최대치(시작 강도가 아닌 기준선)."""

    exercise: Exercise
    metric: Literal["reps", "duration_sec"] = "reps"
    value: int = Field(ge=1, le=600)


class SetBaselineAction(BaseModel):
    """첫 체력검증 결과 저장 (ADR-028). 코치가 온보딩 시드를 대화로 확인·보정한 뒤
    발행한다 — 자가보고 + 보수적 시작이라 부상 기록처럼 즉시 1층 ``fitness_baseline``
    에 저장된다(별도 확답 게이트 없음). 실제 운동 *시작*은 함께 내는 ``propose_set`` 의
    확답 게이트가 막으므로 "동의 없이 첫 루틴 미확정" 회귀 가드는 유지된다."""

    type: Literal["set_baseline"] = "set_baseline"
    entries: list[BaselineEntry] = Field(min_length=1)
    note: str | None = None


class ProposeCalendarSyncAction(BaseModel):
    """이번 주 플랜을 Google Calendar 에 등록할지 제안 (ADR-022 §9-2). **확답 게이트
    통과 후에만** 실제 등록된다 — LLM 이 발행해도 곧바로 쓰지 않고 제안 슬롯에 들어간다
    (자동 등록 금지, 회고 ConfirmRule 정신). 페이로드가 없는 건 등록 대상이 활성 주간
    플랜(ADR-024)으로 고정이기 때문 — 코치는 "캘린더에 등록할까요?" 만 청한다."""

    type: Literal["propose_calendar_sync"] = "propose_calendar_sync"
    note: str | None = None


CoachAction = Annotated[
    ProposeSetAction
    | StartCountingAction
    | LogConditionAction
    | RecordConstraintAction
    | RememberFactAction
    | ProposePlanAction
    | ProposePlanAdjustmentAction
    | SetBaselineAction
    | ProposeCalendarSyncAction,
    Field(discriminator="type"),
]


class CoachResponse(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    actions: list[CoachAction] = Field(default_factory=list)
