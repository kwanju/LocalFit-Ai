"""strip_non_korean_cjk — keep Hangul, drop Hanja (ADR-013 §한자 후처리)."""

import pytest

from app.core.text_sanitize import strip_non_korean_cjk


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("안녕하세요", "안녕하세요"),
        ("푸시업 10개 시작!", "푸시업 10개 시작!"),
        ("運動 시작합시다", "시작합시다"),                 # CJK ideograph removed
        ("좋아요. 健康 우선이에요", "좋아요. 우선이에요"),
        ("ok 좋아요", "ok 좋아요"),                       # ASCII kept
        ("空白  처리", "처리"),
    ],
)
def test_strip(raw: str, expected: str) -> None:
    assert strip_non_korean_cjk(raw) == expected


def test_emoji_kept() -> None:
    assert strip_non_korean_cjk("좋아요 💪") == "좋아요 💪"


def test_only_hanja_returns_empty() -> None:
    assert strip_non_korean_cjk("運動健康") == ""
