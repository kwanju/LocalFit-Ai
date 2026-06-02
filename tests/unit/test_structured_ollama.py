"""StructuredOllamaProcessor — instructor-mocked unit tests (phase-5 §5-12).

Drives ``_run_turn`` directly with a monkeypatched ``push_frame`` to capture
the emitted frame stream. Skips the full Pipecat task lifecycle since these
are pure unit tests for the structured-LLM stage.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pipecat.frames.frames import Frame, TextFrame
from pipecat.processors.frame_processor import FrameDirection

from app.config import AppConfig, load_config
from app.core.coach_response import (
    CoachResponse,
    ProposeSetAction,
    StartCountingAction,
)
from app.pipecat_services.frames import CoachActionFrame
from app.pipecat_services.ollama_service import StructuredOllamaProcessor


def _make_instructor_mock(response: CoachResponse) -> SimpleNamespace:
    chat = SimpleNamespace(
        completions=SimpleNamespace(create=AsyncMock(return_value=response))
    )
    return SimpleNamespace(chat=chat)


@pytest.fixture
def config() -> AppConfig:
    return load_config()


def _capture(proc: StructuredOllamaProcessor) -> list[Frame]:
    captured: list[Frame] = []

    async def push(frame, direction=FrameDirection.DOWNSTREAM):
        captured.append(frame)

    proc.push_frame = push  # type: ignore[assignment]
    return captured


class TestRunTurn:
    async def test_emits_action_then_text(self, config: AppConfig) -> None:
        proc = StructuredOllamaProcessor(config)
        proc._instructor = _make_instructor_mock(
            CoachResponse(
                text="푸시업 10개 시작할게요!",
                actions=[StartCountingAction(exercise="푸시업", reps=10)],
            )
        )
        captured = _capture(proc)
        await proc._run_turn("푸시업 10개 시작하자", FrameDirection.DOWNSTREAM)

        kinds = [type(f).__name__ for f in captured]
        assert "LLMFullResponseStartFrame" in kinds
        assert "CoachActionFrame" in kinds
        assert "TextFrame" in kinds
        assert "LLMFullResponseEndFrame" in kinds
        text_frame = next(f for f in captured if isinstance(f, TextFrame))
        assert "푸시업" in text_frame.text

    async def test_strips_hanja_from_text(self, config: AppConfig) -> None:
        proc = StructuredOllamaProcessor(config)
        proc._instructor = _make_instructor_mock(
            CoachResponse(text="健康한 시작!", actions=[])
        )
        captured = _capture(proc)
        await proc._run_turn("안녕", FrameDirection.DOWNSTREAM)
        text_frame = next(f for f in captured if isinstance(f, TextFrame))
        assert "健康" not in text_frame.text
        assert "시작" in text_frame.text

    async def test_max_retries_propagated(self, config: AppConfig) -> None:
        proc = StructuredOllamaProcessor(config)
        create = AsyncMock(return_value=CoachResponse(text="ok"))
        proc._instructor = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        _capture(proc)
        await proc._run_turn("hi", FrameDirection.DOWNSTREAM)
        assert create.call_args.kwargs["max_retries"] == config.coach.instructor.max_retries
        assert create.call_args.kwargs["response_model"] is CoachResponse

    async def test_history_preserved_across_turns(self, config: AppConfig) -> None:
        proc = StructuredOllamaProcessor(config)
        create = AsyncMock(
            side_effect=[
                CoachResponse(text="첫 번째"),
                CoachResponse(text="두 번째"),
            ]
        )
        proc._instructor = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        _capture(proc)
        await proc._run_turn("안녕", FrameDirection.DOWNSTREAM)
        await proc._run_turn("운동할까", FrameDirection.DOWNSTREAM)

        second_messages = create.call_args_list[1].kwargs["messages"]
        roles = [m["role"] for m in second_messages]
        assert roles[0] == "system"
        pairs = [(m["role"], m["content"]) for m in second_messages]
        assert ("user", "안녕") in pairs
        assert ("assistant", "첫 번째") in pairs

    async def test_exception_pushes_fallback_text(self, config: AppConfig) -> None:
        proc = StructuredOllamaProcessor(config)
        create = AsyncMock(side_effect=RuntimeError("ollama down"))
        proc._instructor = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        captured = _capture(proc)
        await proc._run_turn("hi", FrameDirection.DOWNSTREAM)
        assert any(isinstance(f, TextFrame) and "코치" in f.text for f in captured)


class TestProposeActionEmission:
    async def test_propose_set_emitted_as_action_frame(self, config: AppConfig) -> None:
        proc = StructuredOllamaProcessor(config)
        proc._instructor = _make_instructor_mock(
            CoachResponse(
                text="스쿼트 15회 어떠세요?",
                actions=[
                    ProposeSetAction(exercise="스쿼트", reps=15, sets=3, rest_sec=60)
                ],
            )
        )
        captured = _capture(proc)
        await proc._run_turn("뭐 할까", FrameDirection.DOWNSTREAM)
        actions = [f for f in captured if isinstance(f, CoachActionFrame)]
        assert len(actions) == 1
        assert isinstance(actions[0].action, ProposeSetAction)
        assert actions[0].action.exercise == "스쿼트"
