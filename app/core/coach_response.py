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
    sets: int = Field(ge=1, le=10)
    rest_sec: int = Field(ge=15, le=300)


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
    notes: str | None = None


CoachAction = Annotated[
    ProposeSetAction | StartCountingAction | LogConditionAction,
    Field(discriminator="type"),
]


class CoachResponse(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    actions: list[CoachAction] = Field(default_factory=list)
