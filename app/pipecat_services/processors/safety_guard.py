"""SafetyGuardProcessor — intercepts user transcripts for injury/emergency
keywords and bypasses the LLM with a fixed-template Korean response (ADR-013
§면책·안전, phase-5 §5-5).

Phase-6 additions (ADR-014 §인터럽트 정책):
- Pause keyword detection: "그만/잠깐/멈춰" → ``counting_manager.pause()`` then
  forward the frame to LLM (coach responds naturally).
- Injury/emergency keyword: additionally calls ``counting_manager.stop()`` before
  the existing LLM-bypass response so counting stops immediately.

Domain logic (keyword patterns + level classification) lives in
``app.core.safety.SafetyGuard``; this processor is just the Pipecat glue.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

from loguru import logger
from pipecat.frames.frames import (
    Frame,
    InputTextRawFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from app.core.coach_response import RecordConstraintAction
from app.core.safety import DangerLevel, SafetyGuard
from app.messages import MSG_CONSTRAINT_REMEMBERED
from app.pipecat_services.counting_manager import CountingManager
from app.pipecat_services.frames import SafetyResponseFrame

_PAUSE_KEYWORDS: frozenset[str] = frozenset(
    {"그만", "잠깐", "멈춰", "멈추", "스톱", "중단"}
)
_TOKEN_RE = re.compile(r"[\w가-힣]+", re.UNICODE)

# 부위 통증·부상만 1층 제약으로 승격. EMERGENCY(급성)·LOW(일시 피로)는 제외 —
# 영구 제약이 아니다 (ADR-025 안전 키워드 규칙 승격).
_PERSIST_LEVELS: frozenset[DangerLevel] = frozenset(
    {DangerLevel.MODERATE, DangerLevel.HIGH}
)

RecordConstraintFn = Callable[[RecordConstraintAction], Awaitable[None]]


def _has_pause_keyword(text: str) -> bool:
    # Substring match is used so polite suffix forms like "그만요" → "그만" still trigger.
    normalized = text.lower().replace(" ", "")
    return any(kw in normalized for kw in _PAUSE_KEYWORDS)


class SafetyGuardProcessor(FrameProcessor):
    """Bypass the LLM when an injury/emergency keyword fires.

    Behaviour
    ---------
    * Pause keyword ("그만" etc.) while counting is active → pause engine,
      pass frame through to LLM (coach responds naturally).
    * ``TranscriptionFrame`` / ``InputTextRawFrame`` carrying an unsafe phrase →
      stop counting engine (if active) + emit safety response bypassing LLM.
    * Safe frames and all non-user-text frames are passed through unchanged.

    Per ADR-013 §면책·안전, no automated 119 dispatch — the response message is
    advisory only.
    """

    def __init__(
        self,
        guard: SafetyGuard | None = None,
        counting_manager: CountingManager | None = None,
        record_constraint: RecordConstraintFn | None = None,
    ) -> None:
        super().__init__()
        self._guard = guard or SafetyGuard()
        self._counting_manager = counting_manager
        self._record_constraint = record_constraint

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame | InputTextRawFrame):
            text = (frame.text or "").strip()
            if text:
                # Pause detection: keyword found → pause engine, let LLM respond
                if self._counting_manager is not None and _has_pause_keyword(text):
                    logger.info("SafetyGuardProcessor: pause keyword detected, pausing engine")
                    try:
                        await self._counting_manager.pause()
                    except Exception as e:  # noqa: BLE001
                        logger.error("SafetyGuardProcessor: counting pause failed: {}", e)

                # Safety check: injury/emergency → stop engine + bypass LLM
                result = self._guard.check(text)
                if result.is_unsafe and result.response:
                    logger.info(
                        "SafetyGuardProcessor: bypassing LLM (level={}, kw={})",
                        result.level.value if result.level else None,
                        result.matched_keywords,
                    )
                    if self._counting_manager is not None:
                        try:
                            await self._counting_manager.stop()
                        except Exception as e:  # noqa: BLE001
                            logger.error("SafetyGuardProcessor: counting stop failed: {}", e)
                    # 부위 통증·부상은 1층 제약으로 즉시 승격 + 통지 (ADR-025).
                    # LLM 우회 경로라 여기가 키워드 매칭 부상의 유일한 저장 지점.
                    response_text = result.response
                    if await self._maybe_record(text, result.level):
                        response_text = f"{response_text} {MSG_CONSTRAINT_REMEMBERED}"
                    await self.push_frame(LLMFullResponseStartFrame(), direction)
                    await self.push_frame(
                        SafetyResponseFrame(text=response_text, level=result.level),
                        direction,
                    )
                    await self.push_frame(LLMFullResponseEndFrame(), direction)
                    return

        await self.push_frame(frame, direction)

    async def _maybe_record(self, text: str, level: DangerLevel | None) -> bool:
        """부위 통증·부상(MODERATE/HIGH)이면 1층 제약으로 즉시 저장. 저장하면 True."""
        if self._record_constraint is None or level not in _PERSIST_LEVELS:
            return False
        try:
            await self._record_constraint(
                RecordConstraintAction(kind="injury", text=text.strip())
            )
            return True
        except Exception as e:  # noqa: BLE001 — never break the safety response
            logger.error("SafetyGuardProcessor: record_constraint failed: {}", e)
            return False
