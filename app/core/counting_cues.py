"""Beat cue pools for CountingEngine.

사용자 피드백 (2026-06-04): 카운팅은 "하나, 둘, 셋…" 숫자만. 박자 멘트는 인지 부담만
키운다. 격려 멘트(`ENCOURAGEMENT_CUES`)는 1/3, 2/3, 마지막 시점에만 끼워서 1렙 단위
모노톤 카운팅의 단조로움을 깬다. 플랭크(timer)는 "{N}초!" 카운트다운 유지.

NOTE: 메트로놈 모드 카운팅은 ``CountingEngine._select_metronome_cue``가 ``rep`` 번호로
직접 ``_KOREAN_REP_NAMES`` 를 인덱스해서 cue를 만든다. 그래서 ``BEAT_CUES`` 의 metronome
운동 항목은 의도적으로 비워둠.
"""

from __future__ import annotations

import random as _random_mod

# 한국어 순서 명. 1~20렙은 고유어, 21+는 "21회" 등 한자어 fallback.
_KOREAN_REP_NAMES: tuple[str, ...] = (
    "하나", "둘", "셋", "넷", "다섯",
    "여섯", "일곱", "여덟", "아홉", "열",
    "열하나", "열둘", "열셋", "열넷", "열다섯",
    "열여섯", "열일곱", "열여덟", "열아홉", "스물",
)


def count_word(rep: int) -> str:
    """렙 번호 → 카운팅 cue. 1-indexed (1 → "하나", 20 → "스물", 21+ → "21회")."""
    if rep < 1:
        return ""
    if rep <= len(_KOREAN_REP_NAMES):
        return f"{_KOREAN_REP_NAMES[rep - 1]}!"
    return f"{rep}회!"


# 세트 서수 — TTS가 "2/3"을 "삼분의이"로 읽는 문제 방지 (2026-06-08). "두 번째" 등 native 서수.
_KOREAN_ORDINALS: tuple[str, ...] = (
    "첫", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉", "열",
)


def set_ordinal(n: int) -> str:
    """세트 번호 → 한국어 서수 ("첫 번째", "두 번째", … 11+ → "11번째")."""
    if 1 <= n <= len(_KOREAN_ORDINALS):
        return f"{_KOREAN_ORDINALS[n - 1]} 번째"
    return f"{n}번째"


# 플랭크(timer) tick cue 풀. 메트로놈 운동은 ``count_word`` 로 직접 처리.
BEAT_CUES: dict[str, dict[str, list[str]]] = {
    "플랭크": {
        "tick": [
            "{N}초!",
            "{N}초 남았어요",
            "{N}초, 코어에 힘!",
            "{N}초, 호흡!",
            "{N}초, 버텨요!",
        ],
    },
}

# ADR-014 §진행 격려 멘트 (1/3, 2/3, 마지막 1렙 시점)
ENCOURAGEMENT_CUES: dict[str, list[str]] = {
    "first_third": [
        "좋아요, 호흡 유지!",
        "리듬 좋아요!",
        "잘하고 있어요!",
    ],
    "second_third": [
        "거의 다 왔어요!",
        "조금만 더!",
        "마지막까지!",
    ],
    "last": [
        "마지막!",
        "한 번 더 끝!",
        "완성!",
    ],
    # 플랭크(timer) 완료 시 1회 — 유지 중엔 무음, 끝에만 격려 (2026-06-09 사용자 요청).
    "timer_done": [
        "완성! 잘하셨어요!",
        "끝! 잘 버텼어요!",
        "수고했어요!",
    ],
}

_FALLBACK_BEAT: list[str] = []  # 메트로놈은 count_word 직접 사용, fallback 미사용
_FALLBACK_ENC: list[str] = ["잘하고 있어요!", "조금만 더!", "완성!"]


def get_beat_pool(exercise: str, phase: str) -> list[str]:
    """Return the cue pool for *exercise* + *phase*; falls back to a default pool.

    Metronome 운동에서는 ``CountingEngine``이 ``count_word`` 로 직접 cue를 만들고
    이 함수는 ``tick`` (플랭크) 에서만 의미가 있음.
    """
    return BEAT_CUES.get(exercise, {}).get(phase, _FALLBACK_BEAT)


def get_encouragement_pool(point: str) -> list[str]:
    """Return the encouragement pool for *point* (first_third / second_third / last)."""
    return ENCOURAGEMENT_CUES.get(point, _FALLBACK_ENC)


def pick_cue(
    pool: list[str],
    *,
    mode: str = "random",
    index: int = 0,
    rng: _random_mod.Random | None = None,
    remaining_sec: float | None = None,
    elapsed_sec: float | None = None,
) -> str:
    """Select one cue from *pool*.

    Args:
        pool: Cue strings to select from.
        mode: ``"random"`` (default) or ``"sequential"``.
        index: Position used when ``mode == "sequential"`` (caller manages counter).
        rng: Optional :class:`random.Random` for reproducible selection in tests.
        remaining_sec: Substituted for ``{N}`` in plank-style templates (remaining).
        elapsed_sec: Substituted for ``{N}`` when *remaining_sec* is ``None``.
    """
    if not pool:
        return ""

    if mode == "sequential":
        text = pool[index % len(pool)]
    else:
        r = rng if rng is not None else _random_mod
        text = r.choice(pool)  # type: ignore[arg-type]

    if "{N}" in text:
        if remaining_sec is not None:
            n = max(0, int(remaining_sec))
        elif elapsed_sec is not None:
            n = int(elapsed_sec)
        else:
            n = 0
        text = text.replace("{N}", str(n))

    return text
