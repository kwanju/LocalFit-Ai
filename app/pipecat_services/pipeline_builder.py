"""pipeline_builder — assembles a Pipecat Pipeline for a given 4-mode session.

ADR-009 §4-모드 분리:
  S2S : STT on  + TTS on
  C2S : STT off + TTS on   (UI sends TextFrame directly)
  C2C : STT off + TTS off
  S2C : STT on  + TTS off

Phase 2: all services are mocks; replaced by real services in Phase 3-5.
"""

from enum import StrEnum

from loguru import logger
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.aggregators.sentence import SentenceAggregator
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.transports.websocket.fastapi import FastAPIWebsocketTransport

from app.pipecat_services.mock_llm_service import MockLLMProcessor
from app.pipecat_services.mock_stt_service import MockSTTService
from app.pipecat_services.mock_tts_service import MockTTSService


class SessionMode(StrEnum):
    s2s = "S2S"
    c2s = "C2S"
    c2c = "C2C"
    s2c = "S2C"


def build_pipeline(
    transport: FastAPIWebsocketTransport,
    mode: SessionMode | str,
    *,
    llm_processor: FrameProcessor | None = None,
    stt_service: FrameProcessor | None = None,
    tts_service: FrameProcessor | None = None,
) -> Pipeline:
    """Build a mode-specific Pipecat pipeline.

    Args:
        transport: The FastAPIWebsocketTransport to use for I/O.
        mode: One of S2S / C2S / C2C / S2C.
        llm_processor: Override default MockLLMProcessor (for future phases).
        stt_service: Override default MockSTTService (for future phases).
        tts_service: Override default MockTTSService.  Pass the lifespan-loaded
            Qwen3/Melo service for real audio output (ADR-006).

    Returns:
        A configured Pipeline (not yet running).
    """
    if isinstance(mode, str):
        mode = SessionMode(mode.upper())

    llm = llm_processor or MockLLMProcessor()
    stt = stt_service or MockSTTService()
    tts = tts_service or MockTTSService()

    processors: list[FrameProcessor] = [transport.input()]

    use_stt = mode in (SessionMode.s2s, SessionMode.s2c)
    use_tts = mode in (SessionMode.s2s, SessionMode.c2s)

    if use_stt:
        processors.append(stt)

    processors.append(llm)

    if use_tts:
        # Sentence-batch TTS (ADR-006): SentenceAggregator buffers streaming
        # TextFrames into sentence-sized chunks before they hit the TTS service.
        processors.append(SentenceAggregator())
        processors.append(tts)

    processors.append(transport.output())

    logger.info("Pipeline assembled: mode={} processors={}", mode.value, len(processors))
    return Pipeline(processors)
