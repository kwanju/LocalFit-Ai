"""SafetyGuardProcessor — intercepts user transcripts for injury/emergency
keywords and bypasses the LLM with a fixed-template Korean response (ADR-013
§면책·안전, phase-5 §5-5).

Domain logic (keyword patterns + level classification) lives in
``app.core.safety.SafetyGuard``; this processor is just the Pipecat glue.
"""

from __future__ import annotations

from loguru import logger
from pipecat.frames.frames import (
    Frame,
    InputTextRawFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from app.core.safety import SafetyGuard
from app.pipecat_services.frames import SafetyResponseFrame


class SafetyGuardProcessor(FrameProcessor):
    """Bypass the LLM when an injury/emergency keyword fires.

    Behaviour
    ---------
    * ``TranscriptionFrame`` / ``InputTextRawFrame`` carrying an unsafe phrase →
      emit ``LLMFullResponseStartFrame`` + ``SafetyResponseFrame`` +
      ``LLMFullResponseEndFrame`` downstream and **drop** the user frame so
      ``StructuredOllamaProcessor`` never sees it.
    * Safe frames and all non-user-text frames are passed through unchanged.

    Per ADR-013 §면책·안전, no automated 119 dispatch — the response message is
    advisory only.
    """

    def __init__(self, guard: SafetyGuard | None = None) -> None:
        super().__init__()
        self._guard = guard or SafetyGuard()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame | InputTextRawFrame):
            text = (frame.text or "").strip()
            if text:
                result = self._guard.check(text)
                if result.is_unsafe and result.response:
                    logger.info(
                        "SafetyGuardProcessor: bypassing LLM (level={}, kw={})",
                        result.level.value if result.level else None,
                        result.matched_keywords,
                    )
                    await self.push_frame(LLMFullResponseStartFrame(), direction)
                    await self.push_frame(
                        SafetyResponseFrame(
                            text=result.response, level=result.level
                        ),
                        direction,
                    )
                    await self.push_frame(LLMFullResponseEndFrame(), direction)
                    return

        await self.push_frame(frame, direction)
