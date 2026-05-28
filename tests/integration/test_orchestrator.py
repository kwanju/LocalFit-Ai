"""Integration tests for SessionOrchestrator using mock adapters (phase-4a).

Covers: 4-mode routing (S2S/C2S/C2C/S2C), injury interceptor (any state),
interrupt (LLM/TTS cancelled, counting preserved), and DB status persistence.
"""

import asyncio
from collections.abc import AsyncIterator

import pytest

from app.adapters.llm.protocol import LLMRequest
from app.adapters.stt.protocol import STTResult
from app.adapters.tts.protocol import TTSRequest
from app.core.counting import BeatEvent, ExerciseMode
from app.core.intent import IntentClassifier
from app.core.orchestrator import SessionMode, SessionOrchestrator
from app.core.safety import DangerLevel, SafetyGuard
from app.core.state_machine import SessionState

# --- Mock adapters (ADR-010 Protocol compliant) --------------------------

_CLASSIFY_MARKER = "JSON 형식"  # appears only in the intent-classify prompt


class MockLLM:
    def __init__(self) -> None:
        self.generate_calls = 0
        self.respond_calls = 0
        self.classify_intent = "general"
        self.respond_text = "좋아요! 천천히 호흡하면서 계속해봐요."
        self.respond_delay = 0.0

    async def generate(self, request: LLMRequest) -> str:
        self.generate_calls += 1
        user_content = request.messages[-1].content
        if _CLASSIFY_MARKER in user_content:
            return f'{{"intent": "{self.classify_intent}"}}'
        self.respond_calls += 1
        if self.respond_delay:
            await asyncio.sleep(self.respond_delay)
        return self.respond_text

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        yield await self.generate(request)

    async def health(self) -> bool:
        return True


class MockSTT:
    def __init__(self, text: str = "오늘 컨디션 좋아요") -> None:
        self.text = text
        self.transcribe_calls = 0

    async def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> STTResult:
        self.transcribe_calls += 1
        return STTResult(text=self.text, language="ko", duration_ms=500)

    async def health(self) -> bool:
        return True


class MockTTS:
    def __init__(self) -> None:
        self.synthesize_calls = 0
        self.synth_delay = 0.0

    async def synthesize(self, request: TTSRequest) -> bytes:
        self.synthesize_calls += 1
        if self.synth_delay:
            await asyncio.sleep(self.synth_delay)
        return b"RIFF\x00\x00\x00\x00WAVE"

    async def stream(self, request: TTSRequest) -> AsyncIterator[bytes]:
        yield await self.synthesize(request)

    async def health(self) -> bool:
        return True


class MockPersister:
    def __init__(self) -> None:
        self.updates: list[tuple[int, str]] = []

    async def update_status(self, session_id: int, status: str) -> None:
        self.updates.append((session_id, status))


# --- Fixtures -------------------------------------------------------------


@pytest.fixture
def llm() -> MockLLM:
    return MockLLM()


@pytest.fixture
def intent(llm: MockLLM) -> IntentClassifier:
    return IntentClassifier(llm)


@pytest.fixture
def safety() -> SafetyGuard:
    return SafetyGuard()


def build(
    mode: SessionMode,
    intent: IntentClassifier,
    safety: SafetyGuard,
    *,
    stt: MockSTT | None = None,
    tts: MockTTS | None = None,
    persister: MockPersister | None = None,
    on_beat=None,
    session_id: int | None = None,
) -> SessionOrchestrator:
    return SessionOrchestrator(
        intent=intent,
        safety=safety,
        mode=mode,
        stt=stt,
        tts=tts,
        persister=persister,
        on_beat=on_beat,
        session_id=session_id,
    )


# --- 4-mode routing -------------------------------------------------------


async def test_c2c_text_in_text_out(intent: IntentClassifier, safety: SafetyGuard) -> None:
    orch = build(SessionMode.c2c, intent, safety)
    result = await orch.handle_text_input("스쿼트 폼 알려줘")
    assert result.response_text != ""
    assert result.response_audio is None  # no TTS in C2C
    assert result.intent == "general"


async def test_s2s_voice_in_voice_out(
    intent: IntentClassifier, safety: SafetyGuard, llm: MockLLM
) -> None:
    stt, tts = MockSTT(), MockTTS()
    orch = build(SessionMode.s2s, intent, safety, stt=stt, tts=tts)
    result = await orch.handle_voice_input(b"\x00\x01")
    assert stt.transcribe_calls == 1
    assert tts.synthesize_calls == 1
    assert result.response_audio is not None
    assert result.user_text == "오늘 컨디션 좋아요"


async def test_c2s_text_in_voice_out(intent: IntentClassifier, safety: SafetyGuard) -> None:
    tts = MockTTS()
    orch = build(SessionMode.c2s, intent, safety, tts=tts)
    result = await orch.handle_text_input("한 세트 더 할래요")
    assert tts.synthesize_calls == 1
    assert result.response_audio is not None


async def test_s2c_voice_in_text_out(intent: IntentClassifier, safety: SafetyGuard) -> None:
    stt, tts = MockSTT(), MockTTS()
    orch = build(SessionMode.s2c, intent, safety, stt=stt, tts=tts)
    result = await orch.handle_voice_input(b"\x00\x01")
    assert stt.transcribe_calls == 1
    assert tts.synthesize_calls == 0  # no voice output in S2C
    assert result.response_audio is None


async def test_mode_requires_adapters(intent: IntentClassifier, safety: SafetyGuard) -> None:
    with pytest.raises(ValueError):
        build(SessionMode.s2s, intent, safety)  # missing stt/tts
    with pytest.raises(ValueError):
        build(SessionMode.c2s, intent, safety)  # missing tts
    with pytest.raises(ValueError):
        build(SessionMode.s2c, intent, safety)  # missing stt


# --- Injury interceptor ---------------------------------------------------


async def test_injury_emergency_bypasses_llm(
    intent: IntentClassifier, safety: SafetyGuard, llm: MockLLM
) -> None:
    orch = build(SessionMode.c2c, intent, safety)
    await orch.start_session()
    result = await orch.handle_text_input("숨이 안 쉬어져요")
    assert result.safety_triggered is True
    assert result.safety_level == DangerLevel.EMERGENCY
    assert orch.state == SessionState.EMERGENCY_STOPPED
    assert llm.generate_calls == 0  # LLM never reached


async def test_injury_moderate_halts_to_injury_alert(
    intent: IntentClassifier, safety: SafetyGuard
) -> None:
    orch = build(SessionMode.c2c, intent, safety)
    await orch.start_session()
    result = await orch.handle_text_input("무릎이 아파요")
    assert result.safety_triggered is True
    assert result.safety_level == DangerLevel.MODERATE
    assert orch.state == SessionState.INJURY_ALERT


async def test_injury_intercepts_from_any_state(
    intent: IntentClassifier, safety: SafetyGuard
) -> None:
    orch = build(SessionMode.c2c, intent, safety)
    await orch.start_session()  # EXERCISING
    # A normal coaching turn keeps us exercising
    await orch.handle_text_input("좋아요 계속할게요")
    assert orch.state == SessionState.EXERCISING
    # Injury fired mid-session must still intercept
    result = await orch.handle_text_input("찢어지는 느낌이에요")
    assert result.safety_triggered is True
    assert orch.state == SessionState.INJURY_ALERT


async def test_injury_low_keeps_exercising(
    intent: IntentClassifier, safety: SafetyGuard
) -> None:
    orch = build(SessionMode.c2c, intent, safety)
    await orch.start_session()
    result = await orch.handle_text_input("좀 피곤해요")
    assert result.safety_triggered is True
    assert result.safety_level == DangerLevel.LOW
    assert orch.state == SessionState.EXERCISING  # gentle nudge, no halt


async def test_injury_low_does_not_stop_counting(
    intent: IntentClassifier, safety: SafetyGuard
) -> None:
    beats: list[BeatEvent] = []

    async def on_beat(event: BeatEvent) -> None:
        beats.append(event)

    orch = build(SessionMode.c2c, intent, safety, on_beat=on_beat)
    await orch.start_session()
    await orch.start_counting(ExerciseMode.metronome, interval_sec=0.05, max_reps=200)
    result = await orch.handle_text_input("좀 피곤해요")
    assert result.safety_level == DangerLevel.LOW

    beats_after = len(beats)
    await asyncio.sleep(0.2)  # LOW must not halt counting
    assert len(beats) > beats_after

    await orch.stop_counting()


async def test_injury_voice_mode_synthesizes_response(
    intent: IntentClassifier, safety: SafetyGuard
) -> None:
    tts = MockTTS()
    orch = build(SessionMode.s2s, intent, safety, stt=MockSTT(), tts=tts)
    result = await orch.handle_text_input("어깨가 아파요")
    assert result.safety_triggered is True
    assert result.response_audio is not None  # safety message spoken in voice mode
    assert tts.synthesize_calls == 1


# --- Interrupt (cancel LLM/TTS, keep counting) ----------------------------


async def test_interrupt_cancels_llm_keeps_counting(
    intent: IntentClassifier, safety: SafetyGuard, llm: MockLLM
) -> None:
    beats: list[BeatEvent] = []

    async def on_beat(event: BeatEvent) -> None:
        beats.append(event)

    orch = build(SessionMode.c2c, intent, safety, on_beat=on_beat)
    await orch.start_session()
    await orch.start_counting(ExerciseMode.metronome, interval_sec=0.05, max_reps=200)

    llm.respond_delay = 1.0  # slow coaching response
    handle = asyncio.create_task(orch.handle_text_input("폼이 맞나요?"))
    await asyncio.sleep(0.1)  # let classify finish and respond start; counting ticks

    await orch.interrupt()
    result = await handle
    assert result.response_text == ""  # coaching response was cancelled

    beats_at_interrupt = len(beats)
    await asyncio.sleep(0.2)  # counting must keep running
    assert len(beats) > beats_at_interrupt

    await orch.stop_counting()


async def test_interrupt_cancels_tts(
    intent: IntentClassifier, safety: SafetyGuard
) -> None:
    tts = MockTTS()
    tts.synth_delay = 1.0
    orch = build(SessionMode.s2s, intent, safety, stt=MockSTT(), tts=tts)

    handle = asyncio.create_task(orch.handle_text_input("좋아요"))
    await asyncio.sleep(0.1)  # classify + respond done, TTS in flight
    await orch.interrupt()
    result = await handle
    assert result.response_audio is None  # TTS cancelled


# --- DB persistence -------------------------------------------------------


async def test_status_persisted_on_transitions(
    intent: IntentClassifier, safety: SafetyGuard
) -> None:
    persister = MockPersister()
    orch = build(SessionMode.c2c, intent, safety, persister=persister, session_id=7)
    await orch.start_session()  # -> EXERCISING
    await orch.advance_to(SessionState.COOLDOWN)
    await orch.advance_to(SessionState.COMPLETED)
    assert (7, "in_progress") in persister.updates
    assert (7, "completed") in persister.updates


async def test_pause_resume_cycle(intent: IntentClassifier, safety: SafetyGuard) -> None:
    orch = build(SessionMode.c2c, intent, safety)
    await orch.start_session()  # EXERCISING
    await orch.pause()
    assert orch.state == SessionState.PAUSED
    await orch.resume()
    assert orch.state == SessionState.EXERCISING


async def test_emergency_persists_cancelled(
    intent: IntentClassifier, safety: SafetyGuard
) -> None:
    persister = MockPersister()
    orch = build(SessionMode.c2c, intent, safety, persister=persister, session_id=9)
    await orch.start_session()
    await orch.handle_text_input("가슴이 조여와요")
    assert (9, "cancelled") in persister.updates


async def test_no_persist_without_session_id(
    intent: IntentClassifier, safety: SafetyGuard
) -> None:
    persister = MockPersister()
    orch = build(SessionMode.c2c, intent, safety, persister=persister)  # no session_id
    await orch.start_session()
    assert persister.updates == []
