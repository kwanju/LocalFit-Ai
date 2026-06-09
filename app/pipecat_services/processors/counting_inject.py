"""CountingInjectProcessor — routes CountingEngine beat events into the Pipecat
pipeline as TextFrames (ADR-014 §CountingInjectProcessor, phase-6 §6-2).

The processor is a passthrough for ordinary pipeline frames.  Beat cues are
injected via ``attach_engine``: the engine's ``on_beat`` is wired to
``_inject_beat``, which calls ``push_frame`` downstream from within the
engine's asyncio task.  Because Pipecat's ``push_frame`` is non-blocking
(asyncio-safe), this does not stall the beat scheduler.

Beat cues are emitted as ``TTSSpeakFrame`` (NOT ``TextFrame``).  Pipecat's
``TTSService`` buffers incoming ``TextFrame`` text through its internal sentence
aggregator, so short punctuation-only cues ("하나!", "둘!") with no trailing
space accumulate and synthesise in one batched, delayed blob ("하나!둘!셋!넷!")
— the count audio lags the beats and plays bunched (2026-06-08 fix).
``TTSSpeakFrame`` bypasses that aggregation: each cue is synthesised immediately
and individually, in sync with the beat.  (In non-TTS modes the frame has no
consumer and is dropped by the serializer; the UI counter is driven by the
separate ``beat_meta`` message either way.)
"""

from __future__ import annotations

from loguru import logger
from pipecat.frames.frames import (
    Frame,
    OutputTransportMessageFrame,
    TTSSpeakFrame,
)
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
        # 2026-06-07 sync 재설계 (B+C 하이브리드):
        # 1) cue 가 있는 박자만 (메트로놈 down / 플랭크 초 카운트 / 격려) 오디오를 만든다.
        # 2) cue audio 앞에 `beat_meta` 메시지를 보내 UI가 audio 와 짝지을 수 있게.
        #    UI는 beat_meta 를 pending 큐에 저장 → audio 도착 시 oldest meta 꺼냄 →
        #    playPcm 의 onStart 콜백 (audio 재생 시작 시점) 에 카운터 업데이트.
        # cue 가 빈 박자 (메트로놈 up 묵음) 는 meta msg 도 push 안 함 — UI 변화 없음.
        if not event.cue:
            return
        logger.debug(
            "CountingInjectProcessor: beat kind={} rep={} cue='{}'",
            event.cue_kind, event.rep, event.cue,
        )
        # BeatEvent.rep 는 완료된 rep 수 (down 시점엔 아직 +1 전). 카운트 cue는
        # "지금 세는 횟수"가 직관적이므로 +1 해서 1-indexed로 표시.
        display_rep = (
            event.rep + 1 if event.cue_kind == "count" and event.phase == "down"
            else event.rep
        )
        meta_msg = OutputTransportMessageFrame(message={
            "type": "beat_meta",
            "kind": event.cue_kind,          # "count" | "encouragement" | "tick"
            "rep": display_rep,
            "phase": event.phase,
            "set_number": event.set_number,
            "total_sets": event.total_sets,
            "elapsed_sec": round(event.elapsed_sec, 2),
        })
        # meta 먼저 push — TTS 합성 대기 없이 즉시 UI 도달.
        await self.push_frame(meta_msg, FrameDirection.DOWNSTREAM)
        # 그 다음 cue — TTSSpeakFrame 으로 즉시 개별 합성 (집계 우회).
        await self.push_frame(TTSSpeakFrame(text=event.cue), FrameDirection.DOWNSTREAM)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
