"""UIControlProcessor — handles InputTransportMessageFrame control messages from
the browser UI (phase-7).

The JsonFrameSerializer routes any unrecognised JSON message from the client as
an InputTransportMessageFrame.  This processor intercepts those and maps them to
backend actions:

  {"type":"start_counting","exercise":"푸시업","reps":10} → counting_manager.start()
  {"type":"stop_counting"}                                → counting_manager.stop()
  {"type":"pause"}                                        → counting_manager.pause()
  {"type":"resume"}                                       → currently a no-op
  {"type":"end"}                                          → sends EndFrame downstream

All other frames (and unrecognised message types) are forwarded unchanged.

Positioning: insert near the start of the pipeline, after transport.input() but
before the STT/LLM processors, so control messages don't clutter downstream.
"""

from __future__ import annotations

from loguru import logger
from pipecat.frames.frames import EndFrame, Frame, InputTransportMessageFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from app.pipecat_services.counting_manager import CountingManager


class UIControlProcessor(FrameProcessor):
    """Routes InputTransportMessageFrame UI control commands to backend handlers."""

    def __init__(self, counting_manager: CountingManager | None = None) -> None:
        super().__init__()
        self._counting_manager = counting_manager

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, InputTransportMessageFrame):
            handled = await self._handle_control(frame.message)
            if handled:
                return  # swallow the control message

        await self.push_frame(frame, direction)

    async def _handle_control(self, msg: object) -> bool:
        if not isinstance(msg, dict):
            return False

        msg_type = msg.get("type")

        if msg_type == "start_counting":
            exercise = str(msg.get("exercise", ""))
            reps = int(msg.get("reps", 0))
            mode_str = str(msg.get("mode", "metronome"))
            target_sec = msg.get("target_duration_sec")
            if self._counting_manager is not None and exercise and reps > 0:
                try:
                    await self._counting_manager.start(exercise, reps)
                    logger.info("UIControl: start_counting exercise={} reps={}", exercise, reps)
                except Exception as e:  # noqa: BLE001
                    logger.error("UIControl: start_counting failed: {}", e)
            else:
                logger.debug("UIControl: start_counting ignored (no manager or missing params)")
            return True

        if msg_type == "stop_counting":
            if self._counting_manager is not None:
                try:
                    await self._counting_manager.stop()
                    logger.info("UIControl: stop_counting")
                except Exception as e:  # noqa: BLE001
                    logger.error("UIControl: stop_counting failed: {}", e)
            return True

        if msg_type == "pause":
            if self._counting_manager is not None:
                try:
                    await self._counting_manager.pause()
                    logger.info("UIControl: pause")
                except Exception as e:  # noqa: BLE001
                    logger.error("UIControl: pause failed: {}", e)
            return True

        if msg_type == "resume":
            logger.info("UIControl: resume (no-op in phase-7)")
            return True

        if msg_type == "end":
            logger.info("UIControl: end — sending EndFrame")
            await self.push_frame(EndFrame(), FrameDirection.DOWNSTREAM)
            return True

        # start / listen_start / listen_stop / audio_chunk variants are handled
        # upstream (JsonFrameSerializer or ignored); log unknown types at debug.
        if msg_type not in ("start", "listen_start", "listen_stop"):
            logger.debug("UIControl: unhandled message type={}", msg_type)
        return False
