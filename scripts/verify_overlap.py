"""겹친 세션(이중 연결) 보호 검증 — ModelManager refcount (TTS executor shutdown 회귀).

dev StrictMode/재연결 레이스로 WS 두 개가 잠깐 겹치면, 한 세션 종료가 다른 세션의
모델을 unload 해 TTS executor 가 죽고 "cannot schedule new futures after shutdown" 가
반복됐다. 이 스크립트는 그 상황을 실제로 재현: 연결 2개 → 인사 대기 → #1 닫음 → #2 로
발화(C2S=TTS 합성 필요) → 백엔드 로그에 그 에러가 없으면 PASS.

    uv run --with websockets python scripts/verify_overlap.py
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets

REPO = Path(__file__).resolve().parent.parent
WS = "ws://127.0.0.1:8000/ws/voice?mode=C2S"
HEALTH = "http://127.0.0.1:8000/health"
LOG = REPO / "logs" / "overlap_backend.log"
ERR = "cannot schedule new futures after shutdown"


def _health_ok() -> bool:
    try:
        with urllib.request.urlopen(HEALTH, timeout=3) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


async def _await_greet(ws, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=end - time.monotonic())
        except (TimeoutError, websockets.ConnectionClosed):
            return False
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if msg.get("type") == "text" and (msg.get("text") or "").strip():
            return True
    return False


async def main() -> int:
    proc = None
    if not _health_ok():
        LOG.parent.mkdir(exist_ok=True)
        log = open(LOG, "w")  # noqa: SIM115
        proc = subprocess.Popen(
            ["uv", "run", "python", "-m", "app.main"], cwd=str(REPO), stdout=log, stderr=log
        )
        end = time.monotonic() + 60
        while time.monotonic() < end and not _health_ok():
            time.sleep(2)
    else:
        print("⚠️ 외부 백엔드 사용 중 — 로그 검사는 logs/overlap_backend.log 가 아닐 수 있음")

    if not _health_ok():
        print("❌ 백엔드 미가동")
        return 2

    ok_after = True
    try:
        # 두 연결을 거의 동시에 연다(이중 연결 재현).
        ws1 = await websockets.connect(WS, max_size=None, open_timeout=10)
        ws2 = await websockets.connect(WS, max_size=None, open_timeout=10)
        print("  연결 2개 오픈")
        # 둘 다 인사까지(모델 공유 로드) 대기.
        await _await_greet(ws1, 90)
        await _await_greet(ws2, 90)
        print("  양쪽 인사 수신(모델 로드 공유됨)")

        # #1 닫음 → 백엔드가 unload 하면 안 됨(#2 활성).
        await ws1.close()
        print("  #1 닫음")
        await asyncio.sleep(8)  # unload 가 잘못 일어났다면 이 사이에 실행됨

        # #2 로 발화 → C2S 라 TTS 합성 필요. executor 가 죽었으면 여기서 에러.
        await ws2.send(json.dumps({"type": "text", "text": "좋아 바로 시작하자"}))
        got = await _await_greet(ws2, 40)
        print(f"  #2 발화 후 응답 수신: {got}")
        await ws2.close()
    except Exception as e:  # noqa: BLE001
        print(f"  transport 예외: {e}")
        ok_after = False
    finally:
        await asyncio.sleep(2)
        if proc is not None:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
            else:
                proc.terminate()

    # 백엔드 로그에 TTS executor shutdown 에러가 있으면 FAIL.
    err_found = False
    if proc is not None and LOG.exists():
        err_found = ERR in LOG.read_text(encoding="utf-8", errors="ignore")

    print("\n=== 판정 ===")
    print(f"  {'❌' if err_found else '✅'} TTS executor 'cannot schedule' 에러 {'발생' if err_found else '없음'}")
    print(f"  {'✅' if ok_after else '❌'} #1 종료 후 #2 정상 사용")
    passed = (not err_found) and ok_after
    print(f"\n{'PASS ✅' if passed else 'FAIL ❌'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
