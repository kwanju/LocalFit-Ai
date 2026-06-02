"""Korean text sanitization helpers (ADR-013 §한자 후처리).

qwen3:8b occasionally slips Hanja words into Korean responses (a known v1 issue
preserved as a v3 utility). ``strip_non_korean_cjk`` removes CJK Unified
Ideographs but keeps Hangul, ASCII, punctuation, and emojis untouched. Applied
only to ``CoachResponse.text`` — action payloads are predefined Hangul enums
and need no sanitization.
"""

import re

# CJK Unified Ideographs blocks that the model occasionally emits despite the
# Korean-only instruction. Hangul syllables (가-힣) and Jamo are NOT in
# these ranges, so they pass through untouched.
_HANJA_RE = re.compile(
    r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0002FFFF]+"
)
# Collapse the whitespace gaps left behind after removal.
_WS_RE = re.compile(r"[ \t]{2,}")


def strip_non_korean_cjk(text: str) -> str:
    """Remove CJK Hanja characters while preserving Hangul, ASCII, punctuation."""
    cleaned = _HANJA_RE.sub("", text)
    cleaned = _WS_RE.sub(" ", cleaned)
    return cleaned.strip()
