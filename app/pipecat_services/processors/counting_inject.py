"""CountingInjectProcessor — routes CountingEngine beat events into the Pipecat
pipeline as TextFrames (ADR-014 §CountingInjectProcessor, phase-6 §6-2).

The processor is a passthrough for ordinary pipeline frames.  Beat cues are
injected via ``attach_engine``: the engine's ``on_beat`` is wired to
``_inject_beat``, which calls ``push_frame`` downstream from within the
engine's asyncio task.  Because Pipecat's ``push_frame`` is non-blocking
(asyncio-safe), this does not stall the beat scheduler.

Positioning: inserted BEFORE ``SentenceAggregator`` so beat cues flow
``TextFrame → SentenceAggregator → TTS`` in the same queue as LLM response
text (option B from phase-6 spec: Pipecat queue serialises them).
"""

from __future__ import annotations

from loguru import logger
from pipecat.frames.frames import Frame, TextFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from app.core.counting import BeatEvent, CountingEngine


class CountingInjectProcessor(FrameProcessor):
    """Translates CountingEngine beat events into downstream TextFrames."""

    def __init__(self) -> None:
        super().__init__()

    def attach_engine(self, engine: CountingEngine) -> None:
        """Wire *engine*'s on_beat callback to this processor."""
        engine.on_beat = self._inject_beat
        logger.debug("CountingInjectProcessor: attached to engine {}", id(engine))

    async def _inject_beat(self, event: BeatEvent) -> None:
        if event.cue:
            logger.debug("CountingInjectProcessor: beat cue='{}'", event.cue)
            await self.push_frame(TextFrame(text=event.cue), FrameDirection.DOWNSTREAM)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
