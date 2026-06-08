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
        # 좋다 계열
        "좋아요", "좋아", "좋습니다", "좋지", "좋네", "좋고",
        # 시작/하다 계열 (활용형은 부분 문자열 매칭으로도 잡힘 — "시작"이 대표 stem)
        "시작", "시작하자", "시작할게", "시작해요", "시작합니다", "시작하죠",
        "하자", "할게", "할게요", "하죠", "하시죠", "해요", "해보자", "해볼게", "해볼까", "할래",
        # 가다/진행 계열
        "가자", "가즈아", "갑시다", "가시죠", "가요", "고고", "고고씽", "고", "ㄱㄱ", "ㄱ",
        # 동의/긍정 구어
        "그래", "그럼", "그러자", "그렇게", "당연", "물론", "오케이", "콜",
        "응", "네", "예", "넵", "넹", "ㅇㅇ", "ㅇㅋ",
        # 영어/외래
        "ok", "okay", "yes", "예스", "고고고",
    }
)
_REJECT_KEYWORDS: frozenset[str] = frozenset(
    {
        "아니", "아니요", "아냐", "싫어", "싫어요", "별로",
        "패스", "스킵", "나중에", "그만", "관둬", "관두",
        # 부정형 stem — accept stem(할게/해요/가요 등)보다 먼저 검사돼 우선 (2026-06-08).
        "안할", "안 할", "안해", "안 해", "안하", "안가", "안 가", "못해", "못하",
    }
)

_TOKEN_RE = re.compile(r"[\w가-힣]+", re.UNICODE)
_ACK_TEXT: str = "시작할게요."


class ConfirmRuleProcessor(FrameProcessor):
    def __init__(
        self,
        slot: ConfirmSlot,
        dispatcher: object | None = None,
    ) -> None:
        super().__init__()
        self._slot = slot
        # ActionDispatcher 의 가드(LLM 자체 발행 start_counting 차단)를 잠깐 풀기 위한 참조.
        # 순환 import 방지 위해 구체 타입 대신 object 로 받음 (allow_one_direct_start 만 호출).
        self._dispatcher = dispatcher

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame | InputTextRawFrame):
            text = (frame.text or "").strip()
            if text:
                kind = _classify(text)
                # 수정 의도가 담긴 확답("5세트로 하자", "휴식 60초로 시작")은 단순 수락이
                # 아니다 — 기존 제안을 그대로 시작하면 사용자 변경을 무시한다(2026-06-08).
                # LLM이 갱신된 propose_set 을 내도록 통과시킨다(가드는 그대로 유지).
                if kind == "accept" and _has_quantity_modifier(text):
                    kind = None
                if kind == "accept" and self._slot.has_pending:
                    proposal = self._slot.take()
                    if proposal is not None:
                        logger.info(
                            "ConfirmRuleProcessor: accept → start_counting"
                            "(exercise={} reps={} sets={} rest={}s)",
                            proposal.exercise,
                            proposal.reps,
                            proposal.sets,
                            proposal.rest_sec,
                        )
                        # ActionDispatcher 가드 한 번 풀어줌 — 사용자 확답이 있었으므로.
                        if self._dispatcher is not None and hasattr(
                            self._dispatcher, "allow_one_direct_start"
                        ):
                            self._dispatcher.allow_one_direct_start()
                        await self.push_frame(LLMFullResponseStartFrame(), direction)
                        # sets/rest_sec 도 proposal 그대로 전달 — 다회 세트 자동 진행
                        # (사용자 피드백 2026-06-07).
                        await self.push_frame(
                            CoachActionFrame(
                                action=StartCountingAction(
                                    exercise=proposal.exercise,
                                    reps=proposal.reps,
                                    sets=proposal.sets,
                                    rest_sec=proposal.rest_sec,
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


def _matches(tokens: set[str], norm: str, keywords: frozenset[str]) -> bool:
    """키워드 매칭. 1글자(네/응/예 등)는 정확 토큰만 — 오탐 방지.

    2글자 이상은 공백 제거 텍스트의 부분 문자열로 매칭한다. 한국어 활용형
    (예: "시작할게요" ⊇ "시작", "운동하자" ⊇ "하자") 을 잡기 위함 — 정확 토큰
    매칭만 쓰면 "운동을 시작할게요" 같은 평범한 확답을 놓친다 (2026-06-08 fix).
    """
    for kw in keywords:
        k = kw.lower().replace(" ", "")
        if len(k) <= 1:
            if k in tokens:
                return True
        elif k in norm:
            return True
    return False


# 수량/계획 수정 신호. 단순 확답(좋아/시작/ㄱㄱ)엔 절대 안 나오는 토큰들.
_MODIFIER_KEYWORDS: tuple[str, ...] = ("세트", "휴식", "회", "개", "초", "분")


def _has_quantity_modifier(text: str) -> bool:
    """확답에 수량/계획 변경이 섞였는지 — 숫자 또는 단위 키워드 포함 여부.

    "5세트로 하자", "휴식 60초로 시작", "20개로 줄이자" 처럼 사용자가 제안을 *바꾸면서*
    수락하는 경우를 잡아, 기존 제안을 그대로 시작하지 않고 LLM 갱신 제안으로 넘긴다.
    """
    if any(ch.isdigit() for ch in text):
        return True
    return any(kw in text for kw in _MODIFIER_KEYWORDS)


def _classify(text: str) -> str | None:
    tokens = {t.lower() for t in _TOKEN_RE.findall(text)}
    norm = text.lower().replace(" ", "")
    # 거부를 먼저 검사 — 부정형("나중에 할게", "안 할래")이 수락보다 우선.
    if _matches(tokens, norm, _REJECT_KEYWORDS):
        return "reject"
    if _matches(tokens, norm, _ACCEPT_KEYWORDS):
        return "accept"
    return None
