"""MockLLMProcessor — Phase 2 mock LLM for pipeline shell testing.

Subclasses FrameProcessor (not LLMService — Phase 2 mock only).
Intercepts TranscriptionFrame and TextFrame; pushes TextFrame("echo: {text}").
All other frames (StartFrame, EndFrame, etc.) are passed through unchanged.
Real LLM (instructor + Ollama) is wired in Phase 5.
"""

from loguru import logger
from pipecat.frames.frames import Frame, TextFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class MockLLMProcessor(FrameProcessor):
    """Echo processor: text/transcription in → 'echo: {text}' out.

    All non-text frames are passed through unchanged so that system frames
    (StartFrame, EndFrame, CancelFrame, VAD events, etc.) propagate normally.
    """

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame):
            logger.debug("MockLLMProcessor: TranscriptionFrame '{}' → echo", frame.text)
            await self.push_frame(TextFrame(text=f"echo: {frame.text}"), direction)
        elif isinstance(frame, TextFrame) and not frame.text.startswith("echo: "):
            logger.debug("MockLLMProcessor: TextFrame '{}' → echo", frame.text)
            await self.push_frame(TextFrame(text=f"echo: {frame.text}"), direction)
        else:
            # Pass all other frames (StartFrame, EndFrame, VAD frames, etc.) downstream.
            await self.push_frame(frame, direction)
