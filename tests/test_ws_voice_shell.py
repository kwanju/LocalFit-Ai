"""Integration tests for Phase 2 Pipecat shell (mock services + pipeline builder).

Covers:
- MockLLMProcessor: TextFrame → echo TextFrame (C2C roundtrip)
- MockLLMProcessor: TranscriptionFrame → echo TextFrame (S2S/S2C LLM step)
- MockSTTService: VAD-triggered AudioRawFrame → TranscriptionFrame (S2S/S2C STT step)
- MockTTSService: TextFrame → TTSAudioRawFrame (C2S/S2S TTS step)
- pipeline_builder: mode-based processor topology check

Uses pipecat.tests.utils.run_test for in-process pipeline testing (no real WS).
"""

import pytest
from pipecat.frames.frames import (
    AudioRawFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TextFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.tests.utils import run_test
from pipecat.utils.time import time_now_iso8601

from app.pipecat_services.mock_llm_service import MockLLMProcessor
from app.pipecat_services.mock_stt_service import MockSTTService
from app.pipecat_services.mock_tts_service import MockTTSService
from app.pipecat_services.pipeline_builder import SessionMode, build_pipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SILENCE_100MS = bytes(16000 // 10 * 2)  # 100ms @ 16kHz int16 mono


# ---------------------------------------------------------------------------
# C2C: MockLLMProcessor — TextFrame in → echo TextFrame out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c2c_llm_text_echo() -> None:
    """C2C roundtrip: TextFrame → 'echo: {text}'."""
    down, _ = await run_test(
        MockLLMProcessor(),
        frames_to_send=[TextFrame(text="안녕")],
        expected_down_frames=[TextFrame],
    )
    assert len(down) == 1
    assert isinstance(down[0], TextFrame)
    assert down[0].text == "echo: 안녕"


# ---------------------------------------------------------------------------
# S2C / S2S: MockLLMProcessor — TranscriptionFrame in → echo TextFrame out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stt_to_llm_transcription_echo() -> None:
    """STT→LLM step: TranscriptionFrame → 'echo: 테스트'."""
    transcription = TranscriptionFrame(
        text="테스트",
        user_id="user",
        timestamp=time_now_iso8601(),
    )
    down, _ = await run_test(
        MockLLMProcessor(),
        frames_to_send=[transcription],
        expected_down_frames=[TextFrame],
    )
    assert len(down) == 1
    assert isinstance(down[0], TextFrame)
    assert down[0].text == "echo: 테스트"


# ---------------------------------------------------------------------------
# S2S / S2C: MockSTTService — VAD events + AudioRawFrame → TranscriptionFrame
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stt_vad_audio_to_transcription() -> None:
    """STT step: VAD start + audio + VAD stop → TranscriptionFrame('테스트').

    STTService passes other frames downstream too (VAD events, metadata, audio),
    so we assert on the TranscriptionFrame specifically rather than exact list.
    """
    audio_frame = AudioRawFrame(audio=_SILENCE_100MS, sample_rate=16000, num_channels=1)
    frames_to_send = [
        VADUserStartedSpeakingFrame(),
        audio_frame,
        VADUserStoppedSpeakingFrame(),
    ]
    down, _ = await run_test(
        MockSTTService(),
        frames_to_send=frames_to_send,
    )
    transcriptions = [f for f in down if isinstance(f, TranscriptionFrame)]
    frame_names = [type(f).__name__ for f in down]
    assert len(transcriptions) == 1, f"Expected 1 TranscriptionFrame, got {frame_names}"
    assert transcriptions[0].text == "테스트"
    assert transcriptions[0].finalized is True


# ---------------------------------------------------------------------------
# C2S / S2S: MockTTSService — TextFrame → TTSAudioRawFrame
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tts_text_to_audio_frame() -> None:
    """TTS step: TextFrame → TTSAudioRawFrame (100ms silence).

    TTSService may also pass through LLMFullResponseStartFrame/EndFrame and other
    system frames, so we assert on TTSAudioRawFrame specifically.
    """
    frames_to_send = [
        LLMFullResponseStartFrame(),
        TextFrame(text="운동 시작합시다"),
        LLMFullResponseEndFrame(),
    ]
    down, _ = await run_test(
        MockTTSService(),
        frames_to_send=frames_to_send,
    )
    audio_frames = [f for f in down if isinstance(f, TTSAudioRawFrame)]
    frame_names = [type(f).__name__ for f in down]
    assert len(audio_frames) >= 1, f"Expected TTSAudioRawFrame, got {frame_names}"
    assert len(audio_frames[0].audio) == len(_SILENCE_100MS)


# ---------------------------------------------------------------------------
# pipeline_builder: topology checks for each mode
# ---------------------------------------------------------------------------


class _PassthroughProc(FrameProcessor):
    """Stub transport input/output processor for topology tests."""

    async def process_frame(self, frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)


def _make_transport_stub():
    """Transport stub with real FrameProcessor nodes for build_pipeline."""

    class _TransportStub:
        def input(self):
            return _PassthroughProc()

        def output(self):
            return _PassthroughProc()

    return _TransportStub()


@pytest.mark.parametrize(
    "mode,has_stt,has_tts",
    [
        (SessionMode.s2s, True, True),
        (SessionMode.c2s, False, True),
        (SessionMode.c2c, False, False),
        (SessionMode.s2c, True, False),
    ],
)
def test_pipeline_topology(mode: SessionMode, has_stt: bool, has_tts: bool) -> None:
    """Pipeline builder wires correct STT/TTS nodes per mode."""
    transport = _make_transport_stub()
    pipeline = build_pipeline(transport, mode)  # type: ignore[arg-type]
    # pipeline.processors = [PipelineSource, user procs..., PipelineSink]
    procs = list(pipeline.processors)  # type: ignore[attr-defined]

    stt_count = sum(1 for p in procs if isinstance(p, MockSTTService))
    tts_count = sum(1 for p in procs if isinstance(p, MockTTSService))
    llm_count = sum(1 for p in procs if isinstance(p, MockLLMProcessor))

    assert llm_count == 1, f"mode={mode}: expected 1 LLM, got {llm_count}"
    assert (stt_count == 1) == has_stt, f"mode={mode}: STT mismatch"
    assert (tts_count == 1) == has_tts, f"mode={mode}: TTS mismatch"
