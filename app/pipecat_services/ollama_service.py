"""StructuredOllamaProcessor — single-call instructor + Ollama LLM stage.

Sits where Pipecat's ``OllamaLLMService`` would live, but does one
``response_model=CoachResponse`` request per user turn instead of streaming
chat completions. The downstream sees:

  * ``CoachActionFrame`` for each ``CoachResponse.actions`` element, then
  * ``TextFrame(coach_response.text)`` (Hanja-stripped) for ``SentenceAggregator``
    + TTS — or whatever the C2C-mode pipeline does with text.

Conversation history is kept per-instance (one processor per WebSocket
connection, matching ws_voice's per-request construction).

ADR refs: 013 §LLM 호출 / 응답 스키마 / 한자 후처리, 012 §LLM 호출, 018 지연.
"""

from __future__ import annotations

import asyncio
from typing import Any

import instructor
from loguru import logger
from openai import AsyncOpenAI
from pipecat.frames.frames import (
    EndFrame,
    ErrorFrame,
    Frame,
    InputTextRawFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from app.config import AppConfig
from app.core.coach_context import CoachContextBuilder
from app.core.coach_response import CoachResponse
from app.core.text_sanitize import strip_non_korean_cjk
from app.messages import MSG_COACHING_UNAVAILABLE
from app.pipecat_services.frames import CoachActionFrame
from app.prompts.coaching import ACTIVE_COACH_PROTOCOL, SAFETY_SYSTEM_PREFIX
from app.utils.latency import LatencyTracker

_HISTORY_MAX_TURNS: int = 12  # keeps system + ~6 user/assistant pairs


class StructuredOllamaProcessor(FrameProcessor):
    """FrameProcessor that turns one user TextFrame/TranscriptionFrame into a
    structured ``CoachResponse`` via instructor, then emits actions + text.
    """

    def __init__(
        self,
        config: AppConfig,
        context_builder: CoachContextBuilder | None = None,
        *,
        ollama_base_url: str | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._context_builder = context_builder
        self._model_name = config.llm.model
        base_url = ollama_base_url or _derive_openai_base(config.llm.host)
        self._instructor = instructor.from_openai(
            AsyncOpenAI(base_url=base_url, api_key="ollama"),
            mode=instructor.Mode.JSON,
        )
        self._history: list[dict[str, str]] = []
        self._max_retries = config.coach.instructor.max_retries
        self._timeout_sec = config.llm.timeout_sec
        self._lock = asyncio.Lock()

    @property
    def history(self) -> list[dict[str, str]]:
        return list(self._history)

    def reset_history(self) -> None:
        self._history.clear()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if _is_user_input(frame) and frame.text.strip():
            await self._run_turn(frame.text.strip(), direction)
            return

        if isinstance(frame, EndFrame):
            self._history.clear()

        await self.push_frame(frame, direction)

    async def _run_turn(self, user_text: str, direction: FrameDirection) -> None:
        async with self._lock:
            with LatencyTracker("e2e.c2c") as e2e:
                try:
                    response = await self._generate(user_text)
                except Exception as e:  # noqa: BLE001 — never break the pipeline
                    logger.error("structured LLM call failed: {}", e)
                    await self.push_frame(ErrorFrame(error=str(e)), direction)
                    await self.push_frame(TextFrame(text=MSG_COACHING_UNAVAILABLE), direction)
                    e2e.stop()
                    return

                await self._emit_response(response, direction)

    async def _generate(self, user_text: str) -> CoachResponse:
        context_str = ""
        if self._context_builder is not None:
            try:
                context_str = await self._context_builder.build(
                    recent_sessions=getattr(
                        self._config.coach, "context_recent_sessions", 5
                    ),
                )
            except Exception as e:  # noqa: BLE001 — context is best-effort
                logger.warning("CoachContextBuilder failed, continuing without: {}", e)
                context_str = ""

        system_content = SAFETY_SYSTEM_PREFIX + "\n\n" + ACTIVE_COACH_PROTOCOL
        if context_str:
            system_content += "\n\n[사용자 컨텍스트]\n" + context_str

        messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]
        messages.extend(self._history)
        messages.append({"role": "user", "content": user_text})

        with LatencyTracker("llm.generate_structured"):
            response = await asyncio.wait_for(
                self._instructor.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    response_model=CoachResponse,
                    max_retries=self._max_retries,
                ),
                timeout=self._timeout_sec * (self._max_retries + 1),
            )

        # sanitize once, then persist to history (so the model sees the cleaned form)
        cleaned = strip_non_korean_cjk(response.text)
        response.text = cleaned or response.text
        self._history.append({"role": "user", "content": user_text})
        self._history.append({"role": "assistant", "content": response.text})
        self._truncate_history()
        return response

    async def _emit_response(self, response: CoachResponse, direction: FrameDirection) -> None:
        await self.push_frame(LLMFullResponseStartFrame(), direction)
        for action in response.actions:
            await self.push_frame(CoachActionFrame(action=action), direction)
        if response.text:
            await self.push_frame(TextFrame(text=response.text), direction)
        await self.push_frame(LLMFullResponseEndFrame(), direction)

    def _truncate_history(self) -> None:
        if len(self._history) > _HISTORY_MAX_TURNS:
            # drop oldest user/assistant pair to keep the system message budget
            del self._history[: len(self._history) - _HISTORY_MAX_TURNS]


def _is_user_input(frame: Frame) -> bool:
    """User-input frames the LLM should react to.

    Exactly: STT transcripts (``TranscriptionFrame``) and UI/injected user text
    (``InputTextRawFrame``).  Plain ``TextFrame`` is *system text to speak* —
    ConfirmRule acks ("시작할게요."), rest announcements ("3/3 세트 시작!"), and
    beat cues — and must NOT wake the LLM.  Treating plain TextFrame as user
    input caused the LLM to fire on every spoken cue during counting, starving
    the GPU and timing out ("코치 연결 문제", 2026-06-08 fix).  System turns that
    *should* drive the LLM (proactive opener, set-complete follow-up) are
    injected as ``InputTextRawFrame`` by ws_voice for this reason.
    """
    return isinstance(frame, TranscriptionFrame | InputTextRawFrame)


def _derive_openai_base(host: str) -> str:
    """``http://127.0.0.1:11434`` → ``http://127.0.0.1:11434/v1`` (Ollama OpenAI-compat)."""
    host = host.rstrip("/")
    return host if host.endswith("/v1") else f"{host}/v1"


def patch_instructor_for_tests(processor: StructuredOllamaProcessor, fake: Any) -> None:
    """Test helper — swap the instructor client with a mock."""
    processor._instructor = fake  # noqa: SLF001
