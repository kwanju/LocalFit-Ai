"""실세션 E2E 시나리오 스위트 — 변경 후 돌리는 "깊은 검증" 게이트.

단위 테스트(mock)가 못 잡는 이음새(실제 GPU 모델 로드·WS 스트리밍·실 DB·모드 전환)를
실제 백엔드에 붙어 시나리오별로 검증한다. 백엔드를 직접 띄우고(기본) 끝나면 트리킬한다.

사용:
    uv run --with websockets python scripts/verify_scenarios.py
    uv run --with websockets python scripts/verify_scenarios.py --only self_report,mode_switch
    uv run --with websockets python scripts/verify_scenarios.py --external-backend

판정: HARD 체크가 모두 통과하면 exit 0. SOFT(내용 추정) 체크는 정보용(LLM 비결정성이라
실패해도 스위트를 깨지 않음 — 사람이 보고 판단). 각 시나리오는 콜드스타트(~20s) 때문에
순차로 수 분 걸린다(빠른 단위 테스트가 아니라 가끔 돌리는 통합 게이트).
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from verify_session import run  # same dir (scripts/)

REPO = Path(__file__).resolve().parent.parent
HEALTH = "http://127.0.0.1:8000/health"


# ── DB 직접 접근(setup 정리 + postcheck 단정) ──────────────────────────────
# 백엔드와 같은 SQLite(data/localfit.db)를 읽고/지운다. mock 이 아니라 실제 기록을 확인해
# "테스트는 통과하는데 실제론 안 되는" 간극을 메운다.
_db_ready = False


async def _ensure_db() -> None:
    global _db_ready
    if not _db_ready:
        from app.db.engine import init_db

        await init_db()
        _db_ready = True


async def _clear(*, sessions: bool = False, baselines: bool = False, memory: bool = False) -> None:
    await _ensure_db()
    from sqlalchemy import delete

    from app.db.engine import create_db_session
    from app.db.models import (
        ConditionLog,
        FitnessBaseline,
        MemoryFact,
        SetLog,
        UserMemory,
        WorkoutSession,
    )

    async with create_db_session() as db:
        if memory:
            await db.execute(delete(UserMemory))
            await db.execute(delete(MemoryFact))
        if baselines:
            await db.execute(delete(FitnessBaseline))
        if sessions:
            await db.execute(delete(SetLog))
            await db.execute(delete(ConditionLog))
            await db.execute(delete(WorkoutSession))
        await db.commit()


async def _constraints() -> list:
    await _ensure_db()
    from app.db.engine import create_db_session
    from app.db.repositories import MemoryRepository

    async with create_db_session() as db:
        return await MemoryRepository(db).get_constraints()


async def _baselines() -> list:
    await _ensure_db()
    from app.db.engine import create_db_session
    from app.db.repositories import MemoryRepository

    async with create_db_session() as db:
        return await MemoryRepository(db).get_baseline()


# ── 백엔드 관리 ────────────────────────────────────────────────────────────
def _health_ok() -> bool:
    try:
        with urllib.request.urlopen(HEALTH, timeout=3) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def _start_backend() -> subprocess.Popen:
    log = open(REPO / "logs" / "scenario_backend.log", "w")  # noqa: SIM115
    print(f"  백엔드 기동: uv run python -m app.main (cwd={REPO})")
    return subprocess.Popen(
        ["uv", "run", "python", "-m", "app.main"],
        cwd=str(REPO), stdout=log, stderr=log,
    )


def _kill_backend(proc: subprocess.Popen) -> None:
    # uv→python 손자 고아 방지: Windows 는 트리킬(lib.rs 와 동일 사유).
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
        )
    else:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:  # noqa: BLE001
        proc.kill()


def _wait_health(deadline_sec: float) -> bool:
    end = time.monotonic() + deadline_sec
    while time.monotonic() < end:
        if _health_ok():
            return True
        time.sleep(2)
    return False


# ── 체크 헬퍼 ──────────────────────────────────────────────────────────────
# 반환: (라벨, 통과여부, soft여부)
Check = tuple[str, bool, bool]


def _bringup(r: dict) -> list[Check]:
    opener = _joined(r["opener_texts"])
    # opener 가 LLM 실패 fallback(MSG_COACHING_UNAVAILABLE) 이면 텍스트는 왔어도 진짜
    # 인사가 아니다 — soft 로 표시해 간헐적 opener 실패를 정직하게 드러낸다.
    real_opener = bool(opener) and "코치 연결에 문제" not in opener
    return [
        ("WS 연결", r["connected"], False),
        ("에러 없음(모델 로드 성공)", r["error"] is None, False),
        ("session_started 수신", r["session_started"], False),
        ("코치 인사(opener) 수신", len(r["opener_texts"]) > 0, False),
        ("opener 가 LLM 실패 fallback 아님", real_opener, True),
    ]


def _joined(texts: list[str]) -> str:
    return " ".join(texts)


# ── 시나리오 정의 ──────────────────────────────────────────────────────────
def _check_self_report(r: dict) -> list[Check]:
    reply = _joined(r["reply_texts"])
    return [
        *_bringup(r),
        ("사용자 발화에 코치 응답", len(r["reply_texts"]) > 0, False),
        ("자가보고 50 유지(ADR-032)", "50" in reply, True),
        ("30으로 깎지 않음", "30" not in reply, True),
    ]


def _check_condition(r: dict) -> list[Check]:
    reply = _joined(r["reply_texts"])
    soft = any(k in reply for k in ("가볍", "가벼", "부담", "줄", "쉬", "낮", "무리"))
    return [
        *_bringup(r),
        ("컨디션 발화에 코치 응답", len(r["reply_texts"]) > 0, False),
        ("강도 완화 뉘앙스(ADR-023)", soft, True),
    ]


def _check_mode_switch(r: dict) -> list[Check]:
    same = r.get("switch_session_id") == r.get("opener_session_id")
    return [
        *_bringup(r),
        ("전환 시 세션 이어받기(resumed)", bool(r.get("switch_resumed")), False),
        ("전환 시 opener 재발화 안 함", len(r["switch_texts"]) == 0, False),
        ("전환 후 같은 세션 id 유지", same, False),
    ]


def _check_replied(r: dict) -> list[Check]:
    return [*_bringup(r), ("사용자 발화에 코치 응답", len(r["reply_texts"]) > 0, False)]


def _check_safety_tone(r: dict) -> list[Check]:
    reply = _joined(r["opener_texts"] + r["reply_texts"])
    nag = any(k in reply for k in ("전문의", "의료", "면책", "무리하지", "보수적으로"))
    return [*_bringup(r), ("안전 잔소리/면책 문구 없음(ADR-033)", not nag, True)]


# ── async postcheck (실 DB 단정) ───────────────────────────────────────────
async def _post_injury_recorded(r: dict) -> list[Check]:
    cons = await _constraints()
    return [
        ("코치 응답 수신", len(r["reply_texts"]) > 0, False),
        ("실제 통증→1층 제약 저장(안전 회귀)", len(cons) > 0, False),
    ]


async def _post_constraint_shoulder(r: dict) -> list[Check]:
    cons = await _constraints()
    has = len(cons) > 0
    shoulder = any("어깨" in getattr(c, "text", "") for c in cons)
    return [
        ("부상 발화→제약 저장(ADR-025)", has, False),
        ("제약 텍스트에 '어깨'", shoulder, True),
    ]


async def _post_baseline_saved(r: dict) -> list[Check]:
    bl = await _baselines()
    return [
        ("응답 수신(정지 안 함, B#5)", len(r["reply_texts"]) > 0, False),
        ("자가보고→기준선 저장(ADR-028)", len(bl) > 0, True),
    ]


SCENARIOS = {
    "c2c_opener": dict(desc="C2C 세션 브링업+인사", mode="C2C", check=_bringup),
    "self_report": dict(
        desc="자가보고 우선(50 유지)", mode="C2C",
        say="스쿼트 50개 가능해", check=_check_self_report,
    ),
    "condition": dict(
        desc="컨디션 기반 완화 제안", mode="C2C",
        say="오늘 좀 피곤해서 가볍게 하고 싶어", check=_check_condition,
    ),
    "mode_switch": dict(
        desc="모드 전환 연속성(B#6)", mode="C2C", switch="C2S", check=_check_mode_switch
    ),
    "c2s_opener": dict(desc="C2S 세션 브링업+인사", mode="C2S", check=_bringup),
    "s2s_opener": dict(desc="S2S 브링업(음성 입력 없이 로드+인사)", mode="S2S", check=_bringup),
    "injury_intercept": dict(
        desc="실제 통증은 여전히 가로채 제약 저장(안전 회귀)", mode="C2C",
        setup=lambda: _clear(memory=True), say="무릎이 아파요",
        check=_check_replied, postcheck=_post_injury_recorded,
    ),
    "memory_constraint": dict(
        desc="부상 발화→1층 제약 저장(ADR-025/phase2)", mode="C2C",
        setup=lambda: _clear(memory=True), say="왼쪽 어깨가 아파서 오늘 무리 못 해",
        check=_check_replied, postcheck=_post_constraint_shoulder,
    ),
    "first_session_baseline": dict(
        desc="첫 세션 자가보고→기준선(ADR-028, 정지 방지 B#5)", mode="C2C",
        setup=lambda: _clear(sessions=True, baselines=True, memory=True),
        say=[
            "푸시업 15개, 스쿼트 20개 할 수 있어. 그걸 기준으로 잡아줘",
            "응 맞아, 그렇게 저장해줘",
        ],
        check=_check_replied, postcheck=_post_baseline_saved,
    ),
    "safety_tone": dict(
        desc="평소 안전 잔소리 없음(ADR-033)", mode="C2C",
        say="좋아 바로 시작하자", check=_check_safety_tone,
    ),
}


async def _run_one(name: str, spec: dict, timeout: float) -> tuple[bool, list[Check]]:
    print(f"\n── [{name}] {spec['desc']} ──")
    if spec.get("setup"):
        await spec["setup"]()
    r = await run(spec["mode"], spec.get("say"), spec.get("switch"), timeout)
    checks = list(spec["check"](r))
    if spec.get("postcheck") and not r["error"]:
        checks += await spec["postcheck"](r)
    for label, ok, soft in checks:
        mark = "✅" if ok else ("ℹ️ " if soft else "❌")
        kind = " (soft)" if soft else ""
        print(f"    {mark} {label}{kind}")
    hard_ok = all(ok for _, ok, soft in checks if not soft)
    return hard_ok, checks


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="쉼표구분 시나리오 이름(부분집합)")
    ap.add_argument("--timeout", type=float, default=90.0, help="콜드스타트+인사 대기(초)")
    ap.add_argument("--external-backend", action="store_true", help="이미 떠 있는 8000 사용")
    args = ap.parse_args()

    names = (
        [n.strip() for n in args.only.split(",")] if args.only else list(SCENARIOS)
    )
    unknown = [n for n in names if n not in SCENARIOS]
    if unknown:
        print(f"알 수 없는 시나리오: {unknown}\n가능: {list(SCENARIOS)}")
        return 2

    proc = None
    if not args.external_backend:
        if _health_ok():
            print("  이미 8000 에 백엔드가 떠 있음 — 그걸 사용(트리킬 안 함).")
            args.external_backend = True
        else:
            proc = _start_backend()
            if not _wait_health(60):
                print("❌ 백엔드가 60s 안에 안 떴습니다. logs/scenario_backend.log 확인.")
                if proc:
                    _kill_backend(proc)
                return 2
            print("  백엔드 준비 완료.")

    results: dict[str, bool] = {}
    try:
        for name in names:
            hard_ok, _ = await _run_one(name, SCENARIOS[name], args.timeout)
            results[name] = hard_ok
    finally:
        if proc is not None:
            _kill_backend(proc)
            print("\n  백엔드 트리킬 완료.")

    print("\n=== 시나리오 요약 ===")
    for name in names:
        print(f"  {'PASS ✅' if results[name] else 'FAIL ❌'}  {name} — {SCENARIOS[name]['desc']}")
    all_ok = all(results.values())
    print(f"\n{'ALL PASS ✅' if all_ok else 'SUITE FAIL ❌ (HARD 체크 실패)'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
