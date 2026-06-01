import re
from dataclasses import dataclass, field
from enum import StrEnum

from loguru import logger

from app.prompts.safety import SAFETY_RESPONSES


class DangerLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    EMERGENCY = "emergency"


# Checked in priority order: EMERGENCY first, then HIGH, MODERATE, LOW
_LEVEL_ORDER: list[DangerLevel] = [
    DangerLevel.EMERGENCY,
    DangerLevel.HIGH,
    DangerLevel.MODERATE,
    DangerLevel.LOW,
]

_DANGER_PATTERNS: dict[DangerLevel, list[re.Pattern[str]]] = {
    DangerLevel.EMERGENCY: [
        re.compile(p)
        for p in [
            r"숨.{0,4}막혀",           # 숨이 막혀요
            r"숨.{0,4}안.{0,4}쉬",     # 숨이 안 쉬어져요
            r"숨.{0,4}못.{0,4}쉬",     # 숨을 못 쉬겠어요
            r"호흡.{0,4}곤란",          # 호흡 곤란이에요
            r"가슴.{0,4}눌",            # 가슴이 눌려요
            r"가슴.{0,4}조여",          # 가슴이 조여와요
            r"실신",                    # 실신할 것 같아요
            r"의식.{0,4}잃",            # 의식을 잃을 것 같아요
            r"쓰러질.{0,4}것",          # 쓰러질 것 같아요
            r"어지러워.{0,4}쓰러",      # 어지러워서 쓰러질 것 같아
        ]
    ],
    DangerLevel.HIGH: [
        re.compile(p)
        for p in [
            r"찢어지",                  # 찢어지는 느낌이에요
            r"뚝.{0,4}소리",            # 뚝 소리가 났어요
            r"뚝하",                    # 뚝하는 소리
            r"우두둑",                  # 우두둑 소리가 났어요
            r"극심한.{0,4}통증",        # 극심한 통증이 느껴져요
            r"심한.{0,4}통증",          # 심한 통증이에요
            r"못.{0,4}움직",            # 못 움직이겠어요
            r"접질",                    # 발목이 접질렸어요
            r"삐었",                    # 발목을 삐었어요
        ]
    ],
    DangerLevel.MODERATE: [
        re.compile(p)
        for p in [
            r"무릎.{0,4}아파",          # 무릎이 아파요
            r"어깨.{0,4}아파",          # 어깨가 아파요
            r"허리.{0,4}아파",          # 허리가 아파요
            r"손목.{0,4}아파",          # 손목이 아파요
            r"발목.{0,4}아파",          # 발목이 아파요
            r"쑤셔",                    # 허리가 쑤셔요
            r"저려",                    # 팔이 저려요
            r"욱신",                    # 어깨가 욱신거려요
            r"결려",                    # 허리가 결려요
        ]
    ],
    DangerLevel.LOW: [
        re.compile(p)
        for p in [
            r"뻐근",                    # 몸이 뻐근해요
            r"피곤",                    # 너무 피곤해요
            r"힘들어",                  # 좀 힘들어요
            r"지쳐",                    # 많이 지쳐요
            r"지치",                    # 지치네요 (지치다 어간)
            r"몸.{0,4}안.{0,4}좋",     # 몸이 안 좋아요
        ]
    ],
}


@dataclass
class SafetyResult:
    is_unsafe: bool
    level: DangerLevel | None
    matched_keywords: list[str] = field(default_factory=list)
    response: str | None = None


class SafetyGuard:
    """Rule-based safety checker — no LLM calls. Emergency bypasses LLM entirely."""

    def check(self, text: str) -> SafetyResult:
        for level in _LEVEL_ORDER:
            matched = [p.pattern for p in _DANGER_PATTERNS[level] if p.search(text)]
            if matched:
                logger.info(
                    "Safety check: level=%s matched=%s", level.value, matched
                )
                return SafetyResult(
                    is_unsafe=True,
                    level=level,
                    matched_keywords=matched,
                    response=SAFETY_RESPONSES.get(level.value),
                )
        return SafetyResult(is_unsafe=False, level=None)
