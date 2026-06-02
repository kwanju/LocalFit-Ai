"""ConfirmRuleProcessor — short-circuit user replies to a pending proposal
(ADR-013 §확답 룰, phase-5 §5-6).

Looks for accept/reject keywords. On accept while a proposal is pending,
emit a ``CoachActionFrame(StartCountingAction)`` + a short Korean ack and
drop the user frame so the LLM is skipped. On reject, just clear the slot
and let the LLM handle the turn. On no-match, leave the slot intact and
forward the frame as usual.
"""

from __future__ import annotations

import re

from loguru import logger
from pipecat.frames.frames import (
    Frame,
    InputTextRawFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from app.core.coach_response import StartCountingAction
from app.core.confirm_slot import ConfirmSlot
from app.pipecat_services.frames import CoachActionFrame

_ACCEPT_KEYWORDS: frozenset[str] = frozenset(
    {
        "좋아요", "좋아", "좋습니다",
        "시작", "시작하자", "시작할게", "시작해요", "시작합니다",
        "가자", "갑시다", "하자", "할게", "할게요",
        "그래", "응", "네", "예",
        "ok", "okay", "오케이", "콜", "yes",
    }
)
_REJECT_KEYWORDS: frozenset[str] = frozenset(
    {
        "아니", "아니요", "아냐", "싫어", "싫어요",
        "패스", "스킵", "나중에", "안 할래", "안할래", "그만",
    }
)

_TOKEN_RE = re.compile(r"[\w가-힣]+", re.UNICODE)
_ACK_TEXT: str = "시작할게요."


class ConfirmRuleProcessor(FrameProcessor):
    def __init__(self, slot: ConfirmSlot) -> None:
        super().__init__()
        self._slot = slot

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame | InputTextRawFrame):
            text = (frame.text or "").strip()
            if text:
                kind = _classify(text)
                if kind == "accept" and self._slot.has_pending:
                    proposal = self._slot.take()
                    if proposal is not None:
                        logger.info(
                            "ConfirmRuleProcessor: accept → start_counting({}, {})",
                            proposal.exercise, proposal.reps,
                        )
                        await self.push_frame(LLMFullResponseStartFrame(), direction)
                        await self.push_frame(
                            CoachActionFrame(
                                action=StartCountingAction(
                                    exercise=proposal.exercise,
                                    reps=proposal.reps,
                                )
                            ),
                            direction,
                        )
                        await self.push_frame(TextFrame(text=_ACK_TEXT), direction)
                        await self.push_frame(LLMFullResponseEndFrame(), direction)
                        return
                if kind == "reject":
                    logger.info("ConfirmRuleProcessor: reject → clear pending proposal")
                    self._slot.clear()

        await self.push_frame(frame, direction)


def _classify(text: str) -> str | None:
    tokens = {t.lower() for t in _TOKEN_RE.findall(text)}
    if tokens & _ACCEPT_KEYWORDS:
        return "accept"
    if tokens & _REJECT_KEYWORDS:
        return "reject"
    # Multi-token phrases (e.g. "안 할래") — tokenizer splits them apart, so
    # fall back to substring match on the whitespace-stripped text.
    norm = text.lower().replace(" ", "")
    for kw in _ACCEPT_KEYWORDS:
        if " " in kw and kw.lower().replace(" ", "") in norm:
            return "accept"
    for kw in _REJECT_KEYWORDS:
        if " " in kw and kw.lower().replace(" ", "") in norm:
            return "reject"
    return None
