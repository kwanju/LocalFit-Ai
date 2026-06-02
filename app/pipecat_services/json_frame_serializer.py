"""JsonFrameSerializer — JSON text ↔ Pipecat frame serializer for browser clients.

Replaces ProtobufFrameSerializer so the browser can communicate with the
Pipecat pipeline without a protobuf library (ADR-009/011 §phase-7).

Wire format (all messages are JSON text WebSocket frames):

Client → Server:
  {"type":"text",  "text":"..."}                        → TextFrame
  {"type":"audio", "data":"<base64 PCM16LE>",
                   "sample_rate":16000}                 → InputAudioRawFrame
  {"type":"interrupt"}                                  → InterruptionFrame
  any other JSON object                                 → InputTransportMessageFrame

Server → Client:
  TextFrame          → {"type":"text",  "text":"...", "safety":false}
  OutputAudioRawFrame→ {"type":"audio", "data":"<base64 PCM16LE>",
                        "sample_rate":<N>}
  TranscriptionFrame → {"type":"transcription", "text":"...", "final":<bool>}
  InterruptionFrame  → {"type":"interrupt"}
  OutputTransportMessageFrame → JSON.dumps(frame.message)  (flat, no wrapping)
  SafetyResponseFrame         → {"type":"text","text":"...","safety":true,
                                 "safety_level":"<level>"}
"""

from __future__ import annotations

import base64
import json
from typing import Any

from loguru import logger
from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    InputTransportMessageFrame,
    InterruptionFrame,
    OutputAudioRawFrame,
    OutputTransportMessageFrame,
    OutputTransportMessageUrgentFrame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.serializers.base_serializer import FrameSerializer

from app.pipecat_services.frames import SafetyResponseFrame


class JsonFrameSerializer(FrameSerializer):
    """JSON text serializer for browser WebSocket clients (phase-7)."""

    async def serialize(self, frame: Frame) -> str | bytes | None:
        # Check subclasses before base classes (SafetyResponseFrame < TextFrame,
        # TranscriptionFrame < TextFrame — wrong order would silently downcast them).
        if isinstance(frame, SafetyResponseFrame):
            level = frame.level.value if frame.level is not None else None
            return json.dumps({"type": "text", "text": frame.text, "safety": True, "safety_level": level})

        if isinstance(frame, TranscriptionFrame):
            return json.dumps({
                "type": "transcription",
                "text": frame.text,
                "final": frame.finalized,
            })

        if isinstance(frame, TextFrame):
            return json.dumps({"type": "text", "text": frame.text})

        if isinstance(frame, OutputAudioRawFrame):
            return json.dumps({
                "type": "audio",
                "data": base64.b64encode(frame.audio).decode(),
                "sample_rate": frame.sample_rate,
            })

        if isinstance(frame, InterruptionFrame):
            return json.dumps({"type": "interrupt"})

        if isinstance(frame, (OutputTransportMessageFrame, OutputTransportMessageUrgentFrame)):
            msg = frame.message
            if isinstance(msg, dict):
                return json.dumps(msg)
            if isinstance(msg, str):
                return msg
            return json.dumps({"type": "message", "data": msg})

        return None

    async def deserialize(self, data: str | bytes) -> Frame | None:
        try:
            if isinstance(data, bytes):
                data = data.decode()
            obj: dict[str, Any] = json.loads(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("JsonFrameSerializer: invalid JSON — {}", exc)
            return None

        msg_type = obj.get("type")

        if msg_type == "text":
            text = obj.get("text", "")
            if not isinstance(text, str):
                return None
            return TextFrame(text=text)

        if msg_type == "audio":
            raw_data = obj.get("data", "")
            sample_rate = int(obj.get("sample_rate", 16000))
            try:
                pcm = base64.b64decode(raw_data)
            except Exception:  # noqa: BLE001
                logger.warning("JsonFrameSerializer: bad base64 audio data")
                return None
            return InputAudioRawFrame(audio=pcm, sample_rate=sample_rate, num_channels=1)

        # Legacy field name from v1 UI (audio_b64 / pcm_b64)
        if msg_type in ("audio_chunk", "audio") and "pcm_b64" in obj:
            raw_data = obj["pcm_b64"]
            sample_rate = int(obj.get("sample_rate", 16000))
            try:
                pcm = base64.b64decode(raw_data)
            except Exception:  # noqa: BLE001
                logger.warning("JsonFrameSerializer: bad base64 pcm_b64")
                return None
            return InputAudioRawFrame(audio=pcm, sample_rate=sample_rate, num_channels=1)

        if msg_type == "interrupt":
            return InterruptionFrame()

        # Everything else (start, pause, resume, end, start_counting, stop_counting, …)
        # → InputTransportMessageFrame for UIControlProcessor to handle.
        return InputTransportMessageFrame(message=obj)
