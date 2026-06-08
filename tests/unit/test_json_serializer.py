"""Unit tests for JsonFrameSerializer (phase-7 §7-6).

Verifies that the JSON ↔ Pipecat frame mapping works correctly for all
message types used in the browser WebSocket protocol.
"""

from __future__ import annotations

import base64
import json

import pytest
from pipecat.frames.frames import (
    InputAudioRawFrame,
    InputTransportMessageFrame,
    InterruptionFrame,
    OutputAudioRawFrame,
    OutputTransportMessageFrame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.utils.time import time_now_iso8601

from app.core.safety import DangerLevel
from app.pipecat_services.frames import SafetyResponseFrame
from app.pipecat_services.json_frame_serializer import JsonFrameSerializer


@pytest.fixture()
def serializer() -> JsonFrameSerializer:
    return JsonFrameSerializer()


# ---------------------------------------------------------------------------
# Serialize: server → client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_serialize_text_frame(serializer: JsonFrameSerializer) -> None:
    data = await serializer.serialize(TextFrame(text="안녕하세요"))
    assert isinstance(data, str)
    obj = json.loads(data)
    assert obj == {"type": "text", "text": "안녕하세요"}


@pytest.mark.asyncio
async def test_serialize_safety_response_frame(serializer: JsonFrameSerializer) -> None:
    frame = SafetyResponseFrame(text="운동을 중단하세요", level=DangerLevel.HIGH)
    data = await serializer.serialize(frame)
    assert isinstance(data, str)
    obj = json.loads(data)
    assert obj["type"] == "text"
    assert obj["safety"] is True
    assert obj["safety_level"] == "high"
    assert obj["text"] == "운동을 중단하세요"


@pytest.mark.asyncio
async def test_serialize_output_audio_frame(serializer: JsonFrameSerializer) -> None:
    pcm = bytes(3200)  # 100ms @ 16kHz int16 mono
    frame = OutputAudioRawFrame(audio=pcm, sample_rate=24000, num_channels=1)
    data = await serializer.serialize(frame)
    assert isinstance(data, str)
    obj = json.loads(data)
    assert obj["type"] == "audio"
    assert obj["sample_rate"] == 24000
    assert base64.b64decode(obj["data"]) == pcm


@pytest.mark.asyncio
async def test_serialize_transcription_frame(serializer: JsonFrameSerializer) -> None:
    frame = TranscriptionFrame(
        text="푸시업 10개", user_id="user", timestamp=time_now_iso8601(), finalized=True
    )
    data = await serializer.serialize(frame)
    assert isinstance(data, str)
    obj = json.loads(data)
    assert obj == {"type": "transcription", "text": "푸시업 10개", "final": True}


@pytest.mark.asyncio
async def test_serialize_interruption_frame(serializer: JsonFrameSerializer) -> None:
    data = await serializer.serialize(InterruptionFrame())
    assert isinstance(data, str)
    assert json.loads(data) == {"type": "interrupt"}


@pytest.mark.asyncio
async def test_serialize_transport_message_frame(serializer: JsonFrameSerializer) -> None:
    msg = {"type": "beat", "rep": 5, "phase": "up", "elapsed_sec": 10.0}
    data = await serializer.serialize(OutputTransportMessageFrame(message=msg))
    assert isinstance(data, str)
    # Should be the message dict itself, not wrapped
    assert json.loads(data) == msg


@pytest.mark.asyncio
async def test_serialize_unknown_frame_returns_none(serializer: JsonFrameSerializer) -> None:
    from pipecat.frames.frames import StartFrame
    data = await serializer.serialize(StartFrame())
    assert data is None


# ---------------------------------------------------------------------------
# Deserialize: client → server
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deserialize_text(serializer: JsonFrameSerializer) -> None:
    from pipecat.frames.frames import InputTextRawFrame

    raw = json.dumps({"type": "text", "text": "스쿼트 시작해 주세요"})
    frame = await serializer.deserialize(raw)
    # 채팅 입력은 InputTextRawFrame 이어야 SafetyGuard/ConfirmRule 이 '사용자 입력'으로
    # 처리한다 (2026-06-08 fix: 순수 TextFrame 이면 채팅 확답·안전 키워드가 무시됨).
    assert type(frame) is InputTextRawFrame, f"expected InputTextRawFrame, got {type(frame)}"
    assert frame.text == "스쿼트 시작해 주세요"


@pytest.mark.asyncio
async def test_deserialize_audio_chunk(serializer: JsonFrameSerializer) -> None:
    pcm = bytes(3200)
    raw = json.dumps({
        "type": "audio",
        "data": base64.b64encode(pcm).decode(),
        "sample_rate": 16000,
    })
    frame = await serializer.deserialize(raw)
    assert isinstance(frame, InputAudioRawFrame)
    assert frame.audio == pcm
    assert frame.sample_rate == 16000


@pytest.mark.asyncio
async def test_deserialize_interrupt(serializer: JsonFrameSerializer) -> None:
    raw = json.dumps({"type": "interrupt"})
    frame = await serializer.deserialize(raw)
    assert isinstance(frame, InterruptionFrame)


@pytest.mark.asyncio
async def test_deserialize_unknown_becomes_transport_message(serializer: JsonFrameSerializer) -> None:
    msg = {"type": "start_counting", "exercise": "풀업", "reps": 10}
    raw = json.dumps(msg)
    frame = await serializer.deserialize(raw)
    assert isinstance(frame, InputTransportMessageFrame)
    assert frame.message == msg


@pytest.mark.asyncio
async def test_deserialize_bad_json_returns_none(serializer: JsonFrameSerializer) -> None:
    frame = await serializer.deserialize("not json {{")
    assert frame is None


@pytest.mark.asyncio
async def test_deserialize_bytes_input(serializer: JsonFrameSerializer) -> None:
    raw = json.dumps({"type": "text", "text": "hello"}).encode()
    frame = await serializer.deserialize(raw)
    assert isinstance(frame, TextFrame)
    assert frame.text == "hello"
