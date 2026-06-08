"""UITextBroadcastProcessor — mirrors LLM/safety TextFrames to the UI as
``OutputTransportMessageFrame`` so the browser actually sees them.

Background:
  Pipecat 1.3.0 ``BaseOutputTransport.write_transport_frame()`` is a no-op by
  default, so plain ``TextFrame`` instances queued for the output transport are
  consumed by the audio task but never serialised to the WebSocket. Only
  ``OutputAudioRawFrame`` (handled by ``write_audio_frame``) and
  ``OutputTransportMessageFrame`` (handled by ``send_message``) reach the wire.

Behaviour:
  * ``TextFrame`` → emits one extra ``OutputTransportMessageFrame`` carrying
    ``{"type": "text", "text": <frame.text>}`` upstream-bound for the
    serializer, then forwards the original ``TextFrame`` downstream so
    ``SentenceAggregator → TTS`` still produces audio.
  * ``SafetyResponseFrame`` (a ``TextFrame`` subclass) → adds ``safety: true``
    and ``safety_level`` to the broadcast payload.
  * Beat-cue ``TextFrame`` from ``CountingInjectProcessor`` would also match,
    so this processor MUST sit BEFORE ``CountingInjectProcessor`` to avoid
    double-publishing beat cues (which already emit their own ``beat`` message).

Position: between ``ActionDispatcherProcessor`` and ``CountingInjectProcessor``
in the pipeline (see ``pipeline_builder``).
"""

from __future__ import annotations

from pipecat.frames.frames import Frame, OutputTransportMessageFrame, TextFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from app.pipecat_services.frames import SafetyResponseFrame


class UITextBroadcastProcessor(FrameProcessor):
    """Duplicate coach TextFrames as UI-bound transport messages."""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        # Subclass first — SafetyResponseFrame is also a TextFrame.
        if isinstance(frame, SafetyResponseFrame):
            text = (frame.text or "").strip()
            if text:
                level = frame.level.value if frame.level is not None else None
                await self.push_frame(
                    OutputTransportMessageFrame(
                        message={
                            "type": "text",
                            "text": frame.text,
                            "safety": True,
                            "safety_level": level,
                        }
                    ),
                    direction,
                )
        elif type(frame) is TextFrame:
            text = (frame.text or "").strip()
            if text:
                await self.push_frame(
                    OutputTransportMessageFrame(
                        message={"type": "text", "text": frame.text},
                    ),
                    direction,
                )

        await self.push_frame(frame, direction)
