"""Session orchestrator — wires adapters + core modules into the 4-mode pipeline.

# DEPRECATED — Phase 2에서 pipecat_services/ws_voice.py + Pipecat 파이프라인으로 대체.
# 이 파일은 Phase 2 진입 전까지 참조용으로 유지. audio·VAD·sentence 처리는 Phase 2에서 제거.
# ADR-012 위반 (core가 adapters import): orchestrator 자체가 Phase 2에서 폐기됨.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from loguru import logger

from app.adapters.stt.faster_whisper_client import STTResult
from app.adapters.tts.qwen3_client import TTSRequest
from app.core.counting import BeatEvent, CountingEngine, ExerciseMode
from app.core.intent import IntentClassifier, IntentType
from app.core.safety import DangerLevel, SafetyGuard, SafetyResult
from app.core.state_machine import SessionState, transition

_HALT_LEVELS: frozenset[DangerLevel] = frozenset(
    {DangerLevel.MODERATE, DangerLevel.HIGH, DangerLevel.EMERGENCY}
)


class SessionMode(StrEnum):
    """Input→output channel combination. Duplicated from app.db.models to keep core pure."""

    s2s = "s2s"  # voice in  → voice out
    c2s = "c2s"  # text in   → voice out
    c2c = "c2c"  # text in   → text out
    s2c = "s2c"  # voice in  → text out


_VOICE_INPUT_MODES: frozenset[SessionMode] = frozenset({SessionMode.s2s, SessionMode.s2c})
_VOICE_OUTPUT_MODES: frozenset[SessionMode] = frozenset({SessionMode.s2s, SessionMode.c2s})

_STATE_TO_DB_STATUS: dict[SessionState, str] = {
    SessionState.COMPLETED: "completed",
    SessionState.ABORTED: "cancelled",
    SessionState.EMERGENCY_STOPPED: "cancelled",
}
_DEFAULT_DB_STATUS = "in_progress"


class SessionPersister(Protocol):
    """Minimal DB write surface the orchestrator needs (injected, ADR-007 repository)."""

    async def update_status(self, session_id: int, status: str) -> None: ...


@dataclass
class InteractionResult:
    user_text: str
    response_text: str
    state: SessionState
    intent: IntentType | None = None
    response_audio: bytes | None = None
    safety_triggered: bool = False
    safety_level: DangerLevel | None = None


@dataclass
class _ActiveTasks:
    llm: asyncio.Task[str] | None = None
    tts: asyncio.Task[bytes] | None = None


class SessionOrchestrator:
    def __init__(
        self,
        *,
        intent: IntentClassifier,
        safety: SafetyGuard,
        mode: SessionMode,
        stt: Any | None = None,
        tts: Any | None = None,
        persister: SessionPersister | None = None,
        on_beat: Callable[[BeatEvent], Awaitable[None]] | None = None,
        session_id: int | None = None,
    ) -> None:
        if mode in _VOICE_INPUT_MODES and stt is None:
            raise ValueError(f"Mode {mode.value} requires an STT adapter")
        if mode in _VOICE_OUTPUT_MODES and tts is None:
            raise ValueError(f"Mode {mode.value} requires a TTS adapter")
        self._intent = intent
        self._safety = safety
        self._mode = mode
        self._stt = stt
        self._tts = tts
        self._persister = persister
        self._on_beat = on_beat
        self._session_id = session_id
        self._state = SessionState.IDLE
        self._resume_state: SessionState | None = None
        self._counting: CountingEngine | None = None
        self._active = _ActiveTasks()
        self._interrupted = False

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def mode(self) -> SessionMode:
        return self._mode

    async def start_session(self, session_id: int | None = None) -> None:
        if session_id is not None:
            self._session_id = session_id
        await self._to_state(SessionState.EXERCISING)

    async def advance_to(self, target: SessionState) -> None:
        if target in (SessionState.COMPLETED, SessionState.ABORTED):
            await self.stop_counting()
        await self._to_state(target)

    async def pause(self) -> None:
        await self.stop_counting()
        self._resume_state = self._state
        await self._to_state(SessionState.PAUSED)

    async def resume(self) -> None:
        target = self._resume_state or SessionState.EXERCISING
        self._resume_state = None
        await self._to_state(target)

    async def end_session(self) -> None:
        await self.stop_counting()
        await self._to_state(SessionState.ABORTED)

    async def handle_voice_input(
        self, audio_bytes: bytes, sample_rate: int = 16000
    ) -> InteractionResult:
        if self._stt is None:
            raise RuntimeError("handle_voice_input requires an STT adapter")
        result: STTResult = await self._stt.transcribe(audio_bytes, sample_rate)
        return await self._handle_text(result.text)

    async def handle_text_input(self, text: str) -> InteractionResult:
        return await self._handle_text(text)

    async def _handle_text(self, text: str) -> InteractionResult:
        self._interrupted = False
        safety = self._safety.check(text)
        if safety.is_unsafe:
            return await self._handle_safety(text, safety)

        intent = await self._intent.classify(text)
        response_text = await self._run_llm(intent, text)
        if response_text is None:
            return InteractionResult(
                user_text=text, response_text="", state=self._state, intent=intent
            )
        audio = await self._run_tts(response_text)
        return InteractionResult(
            user_text=text,
            response_text=response_text,
            state=self._state,
            intent=intent,
            response_audio=audio,
        )

    async def interrupt(self) -> None:
        """Cancel in-flight LLM/TTS work. Counting is intentionally left running."""
        self._interrupted = True
        await self._cancel_active()
        logger.info("Session interrupted: LLM/TTS cancelled, counting preserved")

    async def start_counting(
        self,
        exercise_mode: ExerciseMode,
        interval_sec: float,
        max_reps: int,
        target_duration_sec: float | None = None,
    ) -> None:
        if self._on_beat is None:
            raise RuntimeError("start_counting requires an on_beat callback")
        await self.stop_counting()
        self._counting = CountingEngine(
            mode=exercise_mode,
            interval_sec=interval_sec,
            on_beat=self._on_beat,
            max_reps=max_reps,
            target_duration_sec=target_duration_sec,
        )
        await self._counting.start()

    async def stop_counting(self) -> None:
        if self._counting is not None:
            await self._counting.stop()
            self._counting = None

    @property
    def current_rep(self) -> int:
        return self._counting.current_rep if self._counting else 0

    async def _run_llm(self, intent: IntentType, text: str) -> str | None:
        task = asyncio.create_task(self._intent.respond(intent, text))
        self._active.llm = task
        try:
            return await task
        except asyncio.CancelledError:
            if self._interrupted:
                return None
            raise
        finally:
            self._active.llm = None

    async def _run_tts(self, response_text: str) -> bytes | None:
        if self._mode not in _VOICE_OUTPUT_MODES or self._tts is None:
            return None
        task = asyncio.create_task(self._tts.synthesize(TTSRequest(text=response_text)))
        self._active.tts = task
        try:
            return await task
        except asyncio.CancelledError:
            if self._interrupted:
                return None
            raise
        finally:
            self._active.tts = None

    async def _handle_safety(self, text: str, safety: SafetyResult) -> InteractionResult:
        level = safety.level
        if level in _HALT_LEVELS:
            await self._cancel_active()
            await self.stop_counting()
            target = (
                SessionState.EMERGENCY_STOPPED
                if level == DangerLevel.EMERGENCY
                else SessionState.INJURY_ALERT
            )
            await self._to_state(target)
        response = safety.response or ""
        audio = await self._run_tts(response)
        logger.info("Safety interceptor fired: level={} state={}", level, self._state.value)
        return InteractionResult(
            user_text=text,
            response_text=response,
            state=self._state,
            intent="injury",
            response_audio=audio,
            safety_triggered=True,
            safety_level=level,
        )

    async def _cancel_active(self) -> None:
        for task in (self._active.llm, self._active.tts):
            if task is not None and not task.done():
                task.cancel()

    async def _to_state(self, target: SessionState) -> None:
        self._state = transition(self._state, target)
        await self._persist_status()

    async def _persist_status(self) -> None:
        if self._persister is None or self._session_id is None:
            return
        status = _STATE_TO_DB_STATUS.get(self._state, _DEFAULT_DB_STATUS)
        try:
            await self._persister.update_status(self._session_id, status)
        except Exception as e:  # noqa: BLE001 — persistence failure must not crash session
            logger.error("Failed to persist session status: {}", e)
