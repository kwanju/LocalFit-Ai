"""VRAM 라이프사이클 실측 검증 (ADR-030 — phase v4-7 DoD).

게임과 공존: 앱 idle 엔 모델 0, 세션 시작 때만 로드(~12GB), 종료 때 완전 반환,
반복 세션에 누수 0. nvidia-smi 로 idle/loaded/unloaded 를 실측해 단정한다.

사용 (백엔드 8000 떠 있어야 함, 또는 --manage-backend):
    uv run --with websockets python scripts/verify_vram.py --manage-backend

판정: HARD — 로드 시 idle 대비 +LOAD_MIN_MIB 이상 증가, 종료 후 idle±TOL 복귀,
2회 반복에도 누수 없음. exit 0=PASS.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets

REPO = Path(__file__).resolve().parent.parent
WS = "ws://127.0.0.1:8000/ws/voice?mode=S2S"  # S2S = STT+TTS+LLM 전부 로드(최대 VRAM)
HEALTH = "http://127.0.0.1:8000/health"

LOAD_MIN_MIB = 3000   # 로드 시 최소 증가량(STT+TTS+LLM 이면 보통 ~12GB)
TOL_MIB = 1500        # 종료 후 idle 복귀 허용 오차(파편화/캐시 여유)


def _vram_used() -> int:
    """현재 GPU 사용 VRAM(MiB). 첫 GPU 기준."""
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True,
    )
    return int(out.stdout.strip().splitlines()[0])


def _health_ok() -> bool:
    try:
        with urllib.request.urlopen(HEALTH, timeout=3) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


async def _one_session(timeout: float) -> tuple[int, float]:
    """세션을 열어 모델 로드(인사 수신)까지 간 뒤 loaded VRAM 과 콜드스타트 시간을 잰다.
    세션은 닫는다(언로드 트리거)."""
    t0 = time.monotonic()
    loaded_mib = 0
    async with websockets.connect(WS, max_size=None, open_timeout=10) as ws:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=deadline - time.monotonic())
            except (TimeoutError, websockets.ConnectionClosed):
                break
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                continue
            if msg.get("type") == "text" and (msg.get("text") or "").strip():
                # 인사 수신 = 모델 로드 완료 시점.
                loaded_mib = _vram_used()
                break
    cold = time.monotonic() - t0
    return loaded_mib, cold


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manage-backend", action="store_true")
    ap.add_argument("--timeout", type=float, default=90.0)
    args = ap.parse_args()

    proc = None
    if args.manage_backend and not _health_ok():
        log = open(REPO / "logs" / "vram_backend.log", "w")  # noqa: SIM115
        proc = subprocess.Popen(
            ["uv", "run", "python", "-m", "app.main"], cwd=str(REPO), stdout=log, stderr=log
        )
        end = time.monotonic() + 60
        while time.monotonic() < end and not _health_ok():
            time.sleep(2)

    if not _health_ok():
        print("❌ 백엔드 미가동(8000). --manage-backend 또는 수동 기동 필요.")
        return 2

    try:
        # 모델 미로드 안정화 잠깐 대기 후 idle 측정.
        await asyncio.sleep(3)
        idle = _vram_used()
        print(f"  idle VRAM           = {idle} MiB")

        loaded1, cold1 = await _one_session(args.timeout)
        print(
            f"  세션1 loaded VRAM   = {loaded1} MiB  "
            f"(콜드스타트 {cold1:.1f}s, Δ={loaded1 - idle})"
        )
        await asyncio.sleep(10)  # 언로드(keep_alive=0 + empty_cache) 안정화 대기
        after1 = _vram_used()
        print(f"  세션1 종료 후 VRAM  = {after1} MiB  (idle 대비 Δ={after1 - idle})")

        loaded2, cold2 = await _one_session(args.timeout)
        print(f"  세션2 loaded VRAM   = {loaded2} MiB  (콜드스타트 {cold2:.1f}s)")
        await asyncio.sleep(10)
        after2 = _vram_used()
        print(f"  세션2 종료 후 VRAM  = {after2} MiB  (idle 대비 Δ={after2 - idle})")
    finally:
        if proc is not None:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
            else:
                proc.terminate()

    checks = [
        ("세션 로드 시 VRAM 증가(모델 적재)", loaded1 - idle >= LOAD_MIN_MIB),
        ("세션1 종료 후 idle 복귀", abs(after1 - idle) <= TOL_MIB),
        ("세션2 종료 후 idle 복귀(반복 누수 0)", abs(after2 - idle) <= TOL_MIB),
    ]
    print("\n=== 판정 ===")
    for label, ok in checks:
        print(f"  {'✅' if ok else '❌'} {label}")
    all_ok = all(ok for _, ok in checks)
    print(f"\n{'PASS ✅' if all_ok else 'FAIL ❌'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
