"""CoachResponse Pydantic schema — discriminated union + length cap (ADR-013)."""

import pytest
from pydantic import ValidationError

from app.core.coach_response import (
    CoachResponse,
    LogConditionAction,
    ProposeSetAction,
    StartCountingAction,
)


class TestActionSchemas:
    def test_propose_set_valid(self) -> None:
        a = ProposeSetAction(exercise="푸시업", reps=10, sets=3, rest_sec=60)
        assert a.type == "propose_set"
        assert a.model_dump()["type"] == "propose_set"

    def test_start_counting_valid(self) -> None:
        a = StartCountingAction(exercise="스쿼트", reps=15)
        assert a.type == "start_counting"

    def test_log_condition_valid(self) -> None:
        a = LogConditionAction(fatigue_level=7, notes="평소보다 무거움")
        assert a.type == "log_condition"
        assert a.notes == "평소보다 무거움"

    @pytest.mark.parametrize(
        "exercise", ["벤치프레스", "데드리프트", "운동", ""]
    )
    def test_unknown_exercise_rejected(self, exercise: str) -> None:
        with pytest.raises(ValidationError):
            ProposeSetAction(exercise=exercise, reps=10, sets=3, rest_sec=60)

    @pytest.mark.parametrize("reps", [0, -1, 101])
    def test_reps_bounds(self, reps: int) -> None:
        with pytest.raises(ValidationError):
            StartCountingAction(exercise="풀업", reps=reps)

    @pytest.mark.parametrize("rest", [10, 14, 301, 999])
    def test_rest_sec_bounds(self, rest: int) -> None:
        with pytest.raises(ValidationError):
            ProposeSetAction(exercise="풀업", reps=8, sets=3, rest_sec=rest)


class TestCoachResponse:
    def test_text_only(self) -> None:
        r = CoachResponse(text="안녕하세요!")
        assert r.text == "안녕하세요!"
        assert r.actions == []

    def test_with_mixed_actions(self) -> None:
        r = CoachResponse(
            text="푸시업 10개 어떠세요?",
            actions=[
                ProposeSetAction(exercise="푸시업", reps=10, sets=3, rest_sec=60),
                LogConditionAction(fatigue_level=5),
            ],
        )
        assert len(r.actions) == 2
        assert isinstance(r.actions[0], ProposeSetAction)
        assert isinstance(r.actions[1], LogConditionAction)

    def test_text_required(self) -> None:
        with pytest.raises(ValidationError):
            CoachResponse(text="", actions=[])

    def test_hard_cap_500(self) -> None:
        with pytest.raises(ValidationError):
            CoachResponse(text="가" * 501)

    def test_discriminated_union_parses_from_dict(self) -> None:
        r = CoachResponse.model_validate(
            {
                "text": "시작해요!",
                "actions": [
                    {"type": "start_counting", "exercise": "스쿼트", "reps": 12},
                ],
            }
        )
        assert isinstance(r.actions[0], StartCountingAction)
        assert r.actions[0].reps == 12

    def test_missing_type_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CoachResponse.model_validate(
                {"text": "x", "actions": [{"exercise": "풀업", "reps": 5}]}
            )

    def test_json_schema_includes_actions(self) -> None:
        # instructor injects this schema into the system prompt.
        schema = CoachResponse.model_json_schema()
        assert "text" in schema["properties"]
        assert "actions" in schema["properties"]
