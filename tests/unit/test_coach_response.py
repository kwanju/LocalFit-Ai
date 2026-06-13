"""CoachResponse Pydantic schema — discriminated union + length cap (ADR-013)."""

import pytest
from pydantic import ValidationError

from app.core.coach_response import (
    CoachResponse,
    LogConditionAction,
    ProposePlanAction,
    ProposePlanAdjustmentAction,
    ProposeSetAction,
    SetBaselineAction,
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
        a = LogConditionAction(fatigue_level=7, soreness=4, notes="평소보다 무거움")
        assert a.type == "log_condition"
        assert a.soreness == 4
        assert a.notes == "평소보다 무거움"

    def test_log_condition_soreness_optional(self) -> None:
        a = LogConditionAction(fatigue_level=5)
        assert a.soreness is None

    @pytest.mark.parametrize("soreness", [0, 6, 10])
    def test_log_condition_soreness_bounds(self, soreness: int) -> None:
        with pytest.raises(ValidationError):
            LogConditionAction(fatigue_level=5, soreness=soreness)

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


class TestPlanActions:
    """ADR-024 — 주간 목표/조정 액션 스키마."""

    def test_propose_plan_valid(self) -> None:
        a = ProposePlanAction(
            goals=[{"exercise": "푸시업", "target_count": 3, "reps": 10}]
        )
        assert a.type == "propose_plan"
        assert a.goals[0].exercise == "푸시업"
        assert a.goals[0].target_count == 3

    def test_propose_plan_reps_default(self) -> None:
        a = ProposePlanAction(goals=[{"exercise": "스쿼트", "target_count": 2}])
        assert a.goals[0].reps == 10

    def test_propose_plan_requires_goal(self) -> None:
        with pytest.raises(ValidationError):
            ProposePlanAction(goals=[])

    @pytest.mark.parametrize("count", [0, 15, -1])
    def test_propose_plan_target_bounds(self, count: int) -> None:
        with pytest.raises(ValidationError):
            ProposePlanAction(goals=[{"exercise": "풀업", "target_count": count}])

    def test_propose_plan_adjustment_valid(self) -> None:
        a = ProposePlanAdjustmentAction(exercise="푸시업", new_target_count=2)
        assert a.type == "propose_plan_adjustment"

    def test_propose_plan_adjustment_allows_zero(self) -> None:
        # 0 = 이번 주 해당 종목 목표 비움.
        a = ProposePlanAdjustmentAction(exercise="스쿼트", new_target_count=0)
        assert a.new_target_count == 0

    def test_plan_actions_parse_in_union(self) -> None:
        r = CoachResponse.model_validate(
            {
                "text": "이번 주 푸시업 3회 어때요?",
                "actions": [
                    {
                        "type": "propose_plan",
                        "goals": [{"exercise": "푸시업", "target_count": 3, "reps": 10}],
                    },
                ],
            }
        )
        assert isinstance(r.actions[0], ProposePlanAction)


class TestBaselineAction:
    """ADR-028 — 첫 체력검증 기준선 저장 액션."""

    def test_set_baseline_valid(self) -> None:
        a = SetBaselineAction(
            entries=[
                {"exercise": "푸시업", "metric": "reps", "value": 15},
                {"exercise": "플랭크", "metric": "duration_sec", "value": 30},
            ]
        )
        assert a.type == "set_baseline"
        assert a.entries[0].exercise == "푸시업"
        assert a.entries[1].metric == "duration_sec"

    def test_metric_defaults_to_reps(self) -> None:
        a = SetBaselineAction(entries=[{"exercise": "스쿼트", "value": 20}])
        assert a.entries[0].metric == "reps"

    def test_requires_at_least_one_entry(self) -> None:
        with pytest.raises(ValidationError):
            SetBaselineAction(entries=[])

    @pytest.mark.parametrize("value", [0, -1, 601])
    def test_value_bounds(self, value: int) -> None:
        with pytest.raises(ValidationError):
            SetBaselineAction(entries=[{"exercise": "풀업", "value": value}])

    def test_unknown_exercise_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SetBaselineAction(entries=[{"exercise": "데드리프트", "value": 10}])

    def test_parses_in_union(self) -> None:
        r = CoachResponse.model_validate(
            {
                "text": "푸시업 15개 맞으시면 70%인 10개로 시작할게요.",
                "actions": [
                    {
                        "type": "set_baseline",
                        "entries": [{"exercise": "푸시업", "metric": "reps", "value": 15}],
                    }
                ],
            }
        )
        assert isinstance(r.actions[0], SetBaselineAction)


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
