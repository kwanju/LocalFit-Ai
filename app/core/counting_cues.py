"""Beat cue pools for CountingEngine (ADR-014 §박자 멘트 풀).

All pools are plain constants — no external dependencies — so they live in
``app.core`` (Domain Core).  ``pick_cue`` supports both random and sequential
selection modes; pass an explicit ``random.Random`` instance for reproducible
tests.
"""

from __future__ import annotations

import random as _random_mod

# ADR-014 §박자 멘트 풀: 운동·구간별 cue 풀 (각 5종)
BEAT_CUES: dict[str, dict[str, list[str]]] = {
    "풀업": {
        "up": [
            "올라가요!",
            "당기세요!",
            "끌어올려요!",
            "한 번 더 당겨요!",
            "꽉 잡고!",
        ],
        "down": [
            "내려오세요",
            "천천히",
            "컨트롤",
            "버티며 내려요",
            "긴장 유지",
        ],
    },
    "푸시업": {
        "down": [
            "내려가요!",
            "천천히",
            "가슴까지!",
            "버티며",
            "코어 단단히",
        ],
        "up": [
            "올라와요!",
            "밀어내요!",
            "쭉 펴서!",
            "한 번 더!",
            "끝까지!",
        ],
    },
    "스쿼트": {
        "down": [
            "앉아요!",
            "엉덩이 뒤로!",
            "허벅지 평행!",
            "천천히",
            "무릎 발끝 방향!",
        ],
        "up": [
            "올라와요!",
            "쭉 펴서!",
            "엉덩이 조여요!",
            "발바닥 전체로!",
            "한 번 더!",
        ],
    },
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
}

_FALLBACK_BEAT: list[str] = ["준비", "버텨요", "계속", "좋아요", "한 번 더"]
_FALLBACK_ENC: list[str] = ["잘하고 있어요!", "조금만 더!", "완성!"]


def get_beat_pool(exercise: str, phase: str) -> list[str]:
    """Return the cue pool for *exercise* + *phase*; falls back to a default pool."""
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
