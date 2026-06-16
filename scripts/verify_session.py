"""실제 세션 E2E 검증 하니스 (수동 검증 자동화).

단위 테스트는 어댑터를 mock 하므로 실제 GPU 모델 로드·WS 파이프라인·스트리밍을
전혀 안 건드린다(ADR-019). 이 스크립트는 **진짜 백엔드에 진짜 WS 로 붙어** 한 세션을
구동하고, 코치가 모델 로드→인사→응답까지 가는지 검증한다 — "테스트는 통과하는데 실행만
하면 터지는" 이음새(model load, streaming, 콜드스타트)를 사람 없이 잡기 위함.

사용 (백엔드가 127.0.0.1:8000 에 떠 있어야 함 — `uv run python -m app.main`):
    uv run --with websockets python scripts/verify_session.py --mode C2C
    uv run --with websockets python scripts/verify_session.py --mode C2C --say "스쿼트 50개 가능해"
    uv run --with websockets python scripts/verify_session.py --mode C2C --switch C2S

종료코드 0=PASS, 1=FAIL (CI/루프에서 판정 가능).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

import websockets

BASE = "ws://127.0.0.1:8000/ws/voice"


async def _drain(ws, results: dict, *, until: float, label: str) -> None:
    """until(monotonic) 까지 메시지를 받아 분류·출력한다."""
    while True:
        remaining = until - time.monotonic()
        if remaining <= 0:
            return
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        except (TimeoutError, websockets.ConnectionClosed):
            return
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            continue
        t = msg.get("type")
        if t == "coach_preparing":
            results["preparing"] = True
            print("  … 코치 준비 중(모델 로드 중)")
        elif t == "session_started":
            results["session_started"] = True
            # 단계별(opener/switch) resumed 를 따로 기록 — 모드 전환 판정이 정확해진다.
            results[f"{label}_resumed"] = bool(msg.get("resumed", False))
            results[f"{label}_session_id"] = msg.get("session_id")
            print(
                f"  ▶ session_started: id={msg.get('session_id')} "
                f"mode={msg.get('mode')} resumed={msg.get('resumed', False)}"
            )
        elif t == "error":
            results["error"] = msg.get("message")
            print(f"  ✗ ERROR: {msg.get('message')}")
        elif t == "text":
            text = (msg.get("text") or "").strip()
            if text:
                results[f"{label}_texts"].append(text)
                print(f"  🗣 코치[{label}]: {text}")


async def run(mode: str, say: str | None, switch: str | None, timeout: float) -> dict:
    results: dict = {
        "connected": False, "preparing": False, "session_started": False,
        "error": None, "opener_texts": [], "reply_texts": [], "switch_texts": [],
    }
    url = f"{BASE}?mode={mode.upper()}"
    try:
        async with websockets.connect(url, max_size=None, open_timeout=10) as ws:
            results["connected"] = True
            print(f"  연결됨: {url}")
            # 콜드스타트(모델 로드 ~30s) + 인사까지 대기.
            await _drain(ws, results, until=time.monotonic() + timeout, label="opener")

            if say and results["opener_texts"] and not results["error"]:
                print(f"  나: {say}")
                await ws.send(json.dumps({"type": "text", "text": say}))
                await _drain(ws, results, until=time.monotonic() + 40, label="reply")

            if switch and not results["error"]:
                # 모드 전환 = resume 재연결(프론트 switchMode 와 동일하게 resume=1).
                print(f"  --- 모드 전환 → {switch.upper()} (resume) ---")
        if switch and results["connected"] and not results["error"]:
            url2 = f"{BASE}?mode={switch.upper()}&resume=1"
            async with websockets.connect(url2, max_size=None, open_timeout=10) as ws2:
                await _drain(ws2, results, until=time.monotonic() + 40, label="switch")
    except Exception as e:  # noqa: BLE001
        results["error"] = results["error"] or f"connect/transport: {e}"
    return results


def _verdict(r: dict, say: str | None, switch: str | None) -> tuple[bool, list[str]]:
    checks: list[tuple[str, bool]] = [
        ("WS 연결", r["connected"]),
        ("에러 없음(모델 로드 성공)", r["error"] is None),
        ("session_started 수신", r["session_started"]),
        ("코치 인사(opener) 수신", len(r["opener_texts"]) > 0),
    ]
    if say:
        checks.append(("사용자 발화에 코치 응답", len(r["reply_texts"]) > 0))
    if switch:
        # 전환 후 session_started 가 resumed=True 면 같은 세션 이어받음(버그 B #6).
        same_session = r.get("switch_session_id") == r.get("opener_session_id")
        checks.append(("모드 전환 시 세션 이어받기(resumed)", bool(r.get("switch_resumed"))))
        checks.append(("모드 전환 시 opener 재발화 안 함", len(r["switch_texts"]) == 0))
        checks.append(("모드 전환 후 같은 세션 id 유지", same_session))
    lines = [f"  {'✅' if ok else '❌'} {name}" for name, ok in checks]
    return all(ok for _, ok in checks), lines


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="C2C")
    ap.add_argument("--say", default=None, help="인사 후 보낼 사용자 발화")
    ap.add_argument("--switch", default=None, help="인사 후 전환할 모드(연속성 검증)")
    ap.add_argument("--timeout", type=float, default=90.0, help="콜드스타트+인사 대기(초)")
    args = ap.parse_args()

    print(f"=== 세션 검증 시작 (mode={args.mode}) ===")
    t0 = time.monotonic()
    r = await run(args.mode, args.say, args.switch, args.timeout)
    elapsed = time.monotonic() - t0

    print(f"\n=== 결과 ({elapsed:.1f}s) ===")
    ok, lines = _verdict(r, args.say, args.switch)
    print("\n".join(lines))
    if r.get("reply_texts"):
        print(f"  (응답 요약: {r['reply_texts'][0][:60]})")
    print(f"\n{'PASS ✅' if ok else 'FAIL ❌'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
