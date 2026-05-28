import pytest

from app.core.safety import DangerLevel, SafetyGuard, SafetyResult
from app.messages import MSG_INJURY_EMERGENCY, MSG_INJURY_LOW, MSG_INJURY_MODERATE


@pytest.fixture
def guard() -> SafetyGuard:
    return SafetyGuard()


# ---------------------------------------------------------------------------
# EMERGENCY level
# ---------------------------------------------------------------------------
class TestEmergencyLevel:
    @pytest.mark.parametrize(
        "text",
        [
            "숨이 막혀서 못하겠어요",
            "숨이 안 쉬어져요",
            "숨을 못 쉬겠어요",
            "호흡 곤란이에요",
            "가슴이 눌려요",
            "가슴이 조여와요",
            "실신할 것 같아요",
            "의식을 잃을 것 같아요",
            "쓰러질 것 같아요",
            "어지러워서 쓰러질 것 같아",
        ],
    )
    def test_emergency_keywords(self, guard: SafetyGuard, text: str) -> None:
        result = guard.check(text)
        assert result.is_unsafe is True
        assert result.level == DangerLevel.EMERGENCY
        assert len(result.matched_keywords) > 0
        assert result.response is not None
        assert MSG_INJURY_EMERGENCY in result.response


# ---------------------------------------------------------------------------
# HIGH level
# ---------------------------------------------------------------------------
class TestHighLevel:
    @pytest.mark.parametrize(
        "text",
        [
            "무언가 찢어지는 느낌이에요",
            "뚝 소리가 났어요",
            "뚝하는 소리가 났어요",
            "우두둑 소리가 났어요",
            "극심한 통증이 느껴져요",
            "심한 통증이에요",
            "못 움직이겠어요",
            "발목이 접질렸어요",
            "발목을 삐었어요",
        ],
    )
    def test_high_keywords(self, guard: SafetyGuard, text: str) -> None:
        result = guard.check(text)
        assert result.is_unsafe is True
        assert result.level == DangerLevel.HIGH
        assert len(result.matched_keywords) > 0
        assert result.response is not None


# ---------------------------------------------------------------------------
# MODERATE level
# ---------------------------------------------------------------------------
class TestModerateLevel:
    @pytest.mark.parametrize(
        "text",
        [
            "무릎이 아파요",
            "어깨가 아파요",
            "허리가 아파요",
            "손목이 아파요",
            "발목이 아파요",
            "허리가 쑤셔요",
            "팔이 저려요",
            "어깨가 욱신거려요",
            "허리가 결려요",
        ],
    )
    def test_moderate_keywords(self, guard: SafetyGuard, text: str) -> None:
        result = guard.check(text)
        assert result.is_unsafe is True
        assert result.level == DangerLevel.MODERATE
        assert len(result.matched_keywords) > 0
        assert MSG_INJURY_MODERATE in result.response  # type: ignore[operator]


# ---------------------------------------------------------------------------
# LOW level
# ---------------------------------------------------------------------------
class TestLowLevel:
    @pytest.mark.parametrize(
        "text",
        [
            "몸이 뻐근해요",
            "너무 피곤해요",
            "좀 힘들어요",
            "많이 지쳐요",
            "지치네요",
            "몸이 안 좋아요",
        ],
    )
    def test_low_keywords(self, guard: SafetyGuard, text: str) -> None:
        result = guard.check(text)
        assert result.is_unsafe is True
        assert result.level == DangerLevel.LOW
        assert len(result.matched_keywords) > 0
        assert MSG_INJURY_LOW in result.response  # type: ignore[operator]


# ---------------------------------------------------------------------------
# Safe inputs (no injury keywords)
# ---------------------------------------------------------------------------
class TestSafeInputs:
    @pytest.mark.parametrize(
        "text",
        [
            "오늘 운동 시작해요",
            "스쿼트 10개 할게요",
            "좋아요! 힘내겠습니다",
            "오늘 목표는 풀업 5개예요",
            "운동 끝났어요",
            "다음 세트 언제 해요?",
            "오늘 날씨가 좋네요",
            "물 한 잔 마셔도 될까요?",
        ],
    )
    def test_safe_text_is_not_flagged(self, guard: SafetyGuard, text: str) -> None:
        result = guard.check(text)
        assert result.is_unsafe is False
        assert result.level is None
        assert result.response is None
        assert result.matched_keywords == []


# ---------------------------------------------------------------------------
# Priority & edge cases
# ---------------------------------------------------------------------------
def test_emergency_takes_priority_over_low(guard: SafetyGuard) -> None:
    """When multiple levels match, EMERGENCY must win."""
    result = guard.check("뻐근하고 숨이 막혀요")
    assert result.level == DangerLevel.EMERGENCY


def test_high_takes_priority_over_moderate(guard: SafetyGuard) -> None:
    """HIGH must win when both HIGH and MODERATE patterns match."""
    result = guard.check("무릎이 아파서 찢어지는 느낌이에요")
    assert result.level == DangerLevel.HIGH


def test_empty_string_is_safe(guard: SafetyGuard) -> None:
    result = guard.check("")
    assert result.is_unsafe is False


def test_result_is_dataclass(guard: SafetyGuard) -> None:
    result = guard.check("좀 힘들어요")
    assert isinstance(result, SafetyResult)
    assert isinstance(result.matched_keywords, list)


def test_matched_keywords_are_regex_patterns(guard: SafetyGuard) -> None:
    """Matched keywords must be non-empty strings (regex pattern strings)."""
    result = guard.check("숨이 막혀서 못하겠어요")
    assert all(isinstance(k, str) and len(k) > 0 for k in result.matched_keywords)
