"""pipeline_builder — assembles a Pipecat Pipeline for a given 4-mode session.

ADR-009 §4-모드 분리:
  S2S : STT on  + TTS on
  C2S : STT off + TTS on   (UI sends TextFrame directly)
  C2C : STT off + TTS off
  S2C : STT on  + TTS off

VAD (ADR-007/011): SileroVADAnalyzer drives a VADProcessor inserted between the
transport input and STT for S2S/S2C. Smart Turn is structurally allowed but
gated by `config.vad.use_smart_turn` (default false, P1).

Phase 5 (ADR-013): SafetyGuard → ConfirmRule → StructuredOllama →
ActionDispatcher replaces the v1 echo MockLLMProcessor. ws_voice.py passes a
real ``StructuredOllamaProcessor`` (and the ConfirmSlot it shares with
ActionDispatcher); if it omits them — e.g. shell-only tests — the builder
falls back to MockLLMProcessor to preserve phase-2 behaviour.

Phase 6 (ADR-014): ``CountingInjectProcessor`` is inserted between
``ActionDispatcherProcessor`` and ``SentenceAggregator`` so beat cues flow
through the same TTS queue as LLM response text.
"""

from enum import StrEnum

from loguru import logger
from pipecat.audio.vad.vad_analyzer import VADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.aggregators.sentence import SentenceAggregator
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.transports.websocket.fastapi import FastAPIWebsocketTransport

from app.core.confirm_slot import ConfirmSlot
from app.pipecat_services.mock_llm_service import MockLLMProcessor
from app.pipecat_services.mock_stt_service import MockSTTService
from app.pipecat_services.mock_tts_service import MockTTSService
from app.pipecat_services.processors.action_dispatcher import ActionDispatcherProcessor
from app.pipecat_services.processors.confirm_rule import ConfirmRuleProcessor
from app.pipecat_services.processors.safety_guard import SafetyGuardProcessor


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
    vad_analyzer: VADAnalyzer | None = None,
    safety_processor: FrameProcessor | None = None,
    confirm_processor: FrameProcessor | None = None,
    action_dispatcher: FrameProcessor | None = None,
    confirm_slot: ConfirmSlot | None = None,
    counting_inject: FrameProcessor | None = None,
) -> Pipeline:
    """Build a mode-specific Pipecat pipeline.

    Args:
        transport: The FastAPIWebsocketTransport to use for I/O.
        mode: One of S2S / C2S / C2C / S2C.
        llm_processor: Override default MockLLMProcessor (phase-5 wires
            ``StructuredOllamaProcessor`` here).
        stt_service: Override default MockSTTService.
        tts_service: Override default MockTTSService.
        vad_analyzer: Optional Pipecat VADAnalyzer.
        safety_processor / confirm_processor / action_dispatcher: Phase-5
            ADR-013 processors. When omitted, the builder constructs defaults
            backed by ``confirm_slot`` (or a fresh one).
        confirm_slot: Shared slot for ConfirmRule + ActionDispatcher. Provide
            when ws_voice needs access to inspect the pending proposal.
        counting_inject: Phase-6 ``CountingInjectProcessor`` — inserted between
            ActionDispatcher and SentenceAggregator. Omit for non-counting tests.
    """
    if isinstance(mode, str):
        mode = SessionMode(mode.upper())

    llm = llm_processor or MockLLMProcessor()
    stt = stt_service or MockSTTService()
    tts = tts_service or MockTTSService()

    slot = confirm_slot or ConfirmSlot()
    safety = safety_processor or SafetyGuardProcessor()
    confirm = confirm_processor or ConfirmRuleProcessor(slot)
    dispatcher = action_dispatcher or ActionDispatcherProcessor(slot)

    processors: list[FrameProcessor] = [transport.input()]

    use_stt = mode in (SessionMode.s2s, SessionMode.s2c)
    use_tts = mode in (SessionMode.s2s, SessionMode.c2s)

    if use_stt:
        # SileroVADAnalyzer (ADR-007) emits VADUserStarted/Stopped frames that
        # SegmentedSTTService consumes to bracket transcription.
        if vad_analyzer is not None:
            processors.append(VADProcessor(vad_analyzer=vad_analyzer))
        processors.append(stt)

    # ADR-013 coach pipeline: safety → confirm → LLM → dispatcher.
    processors.append(safety)
    processors.append(confirm)
    processors.append(llm)
    processors.append(dispatcher)

    # ADR-014 phase-6: counting beat inject (between dispatcher and TTS).
    if counting_inject is not None:
        processors.append(counting_inject)

    if use_tts:
        # Sentence-batch TTS (ADR-006): SentenceAggregator buffers streaming
        # TextFrames into sentence-sized chunks before they hit the TTS service.
        processors.append(SentenceAggregator())
        processors.append(tts)

    processors.append(transport.output())

    logger.info(
        "Pipeline assembled: mode={} processors={} vad={} counting_inject={}",
        mode.value,
        len(processors),
        vad_analyzer is not None,
        counting_inject is not None,
    )
    return Pipeline(processors)
