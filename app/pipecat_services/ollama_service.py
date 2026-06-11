"""StructuredOllamaProcessor — single-call Ollama structured-output LLM stage.

Sits where Pipecat's ``OllamaLLMService`` would live, but does one
``format=CoachResponse`` request per user turn instead of streaming chat
completions. The downstream sees:

  * ``CoachActionFrame`` for each ``CoachResponse.actions`` element, then
  * ``TextFrame(coach_response.text)`` (Hanja-stripped) for ``SentenceAggregator``
    + TTS — or whatever the C2C-mode pipeline does with text.

Conversation history is kept per-instance (one processor per WebSocket
connection, matching ws_voice's per-request construction).

**Ollama native (`/api/chat`) 사용 이유 (2026-06-12, ADR-029 §thinking)**: qwen3.5:9b
는 thinking 모델이라 instructor(OpenAI-compat `/v1`) 경로로는 reasoning 이 num_ctx
를 다 채워 JSON 을 못 낸다(`finish_reason=length`, content 빈 문자열). `/v1` 은
``think``·``num_ctx`` 확장을 무시하므로, native ``ollama.AsyncClient`` 로 ``think=False``
+ ``format=schema`` + ``num_ctx`` 를 직접 전달한다. JSON 검증/재시도는 Pydantic
``model_validate_json`` + 루프로 대체(instructor 제거).

ADR refs: 013 §LLM 호출 / 응답 스키마 / 한자 후처리, 029 §thinking, 012, 018.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from loguru import logger
from ollama import AsyncClient
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
from pydantic import ValidationError

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
        client: AsyncClient | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._context_builder = context_builder
        self._model_name = config.llm.model
        self._llm_cfg = config.llm
        # Ollama native client — think/num_ctx 제어를 위해 /v1(instructor) 대신 사용.
        self._client = client or AsyncClient(host=config.llm.host)
        self._schema = CoachResponse.model_json_schema()
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
                self._call_structured(messages),
                timeout=self._timeout_sec * (self._max_retries + 1),
            )

        # sanitize once, then persist to history (so the model sees the cleaned form)
        cleaned = strip_non_korean_cjk(response.text)
        response.text = cleaned or response.text
        self._history.append({"role": "user", "content": user_text})
        self._history.append({"role": "assistant", "content": response.text})
        self._truncate_history()
        return response

    async def _call_structured(self, messages: list[dict[str, str]]) -> CoachResponse:
        """Ollama native structured-output 호출 + Pydantic 검증/재시도.

        ``think=False`` 로 reasoning 을 끄고 ``format=schema`` 로 JSON 을 강제한다.
        파싱 실패 시 ``max_retries`` 만큼 재호출(instructor 자동 재시도 대체).
        """
        options = {
            "num_ctx": self._llm_cfg.num_ctx,
            "num_predict": self._llm_cfg.num_predict,
            "temperature": self._llm_cfg.temperature,
        }
        last_err: Exception | None = None
        for attempt in range(self._max_retries + 1):
            result = await self._client.chat(
                model=self._model_name,
                messages=messages,
                format=self._schema,
                think=self._llm_cfg.think,
                options=options,
                keep_alive=self._llm_cfg.keep_alive,
            )
            content = result["message"]["content"]
            try:
                return _parse_coach_response(content)
            except (ValidationError, ValueError) as e:
                last_err = e
                logger.warning(
                    "CoachResponse 파싱 실패 (시도 {}/{}): {}",
                    attempt + 1,
                    self._max_retries + 1,
                    e,
                )
        raise last_err if last_err is not None else RuntimeError("LLM 구조화 응답 없음")

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


# qwen3.5:9b 가 format=schema enum 을 어겨 영어 운동명을 내는 경우가 있어 보정한다
# (Ollama structured 는 JSON 구조는 강제해도 enum 값까지는 강제 못 함, 2026-06-12).
_EXERCISE_ALIAS: dict[str, str] = {
    "pushup": "푸시업", "push-up": "푸시업", "push up": "푸시업",
    "pullup": "풀업", "pull-up": "풀업", "pull up": "풀업", "chinup": "풀업",
    "squat": "스쿼트", "squats": "스쿼트",
    "plank": "플랭크",
}


def _parse_coach_response(content: str) -> CoachResponse:
    """LLM content → CoachResponse. JSON 추출 + 영어 운동명 보정 후 검증."""
    data = json.loads(_extract_json(content))
    if isinstance(data, dict):
        for action in data.get("actions") or []:
            if not isinstance(action, dict):
                continue
            ex = action.get("exercise")
            if isinstance(ex, str):
                action["exercise"] = _EXERCISE_ALIAS.get(ex.strip().lower(), ex)
            # severity 는 Optional[str] 인데 모델이 정수(예: 3)를 넣기도 한다 — 문자열화.
            sev = action.get("severity")
            if sev is not None and not isinstance(sev, str):
                action["severity"] = str(sev)
    return CoachResponse.model_validate(data)


def _extract_json(content: str) -> str:
    """모델이 가끔 JSON 앞뒤에 자연어/코드펜스를 붙인다(format=schema 가 100% 강제는
    아님). 첫 ``{`` 부터 짝이 맞는 마지막 ``}`` 까지를 잘라 견고하게 파싱한다."""
    s = content.strip()
    if s.startswith("```"):
        # ```json ... ``` 코드펜스 제거
        fence = s.find("```", 3)
        if fence != -1:
            s = s[3:fence]
        s = s.removeprefix("json").strip()
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        return s[start : end + 1]
    return s


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


def patch_client_for_tests(processor: StructuredOllamaProcessor, fake: Any) -> None:
    """Test helper — swap the Ollama client with a mock (``chat`` returns a dict
    ``{"message": {"content": <CoachResponse JSON>}}``)."""
    processor._client = fake  # noqa: SLF001
