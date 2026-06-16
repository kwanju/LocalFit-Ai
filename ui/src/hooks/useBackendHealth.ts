// Sidecar liveness watch (phase v4-6, 6-3 / ADR-031 "안 행복한 경로").
// Polls /health so the UI can detect a dead FastAPI sidecar (Python+models) and
// offer a restart. /health is cheap and always returns backend:true when the
// process is reachable; a fetch failure means the sidecar is down or still
// coming up (≈30s cold start, spike §2).
//
// State machine (so we don't flash a scary banner during the normal cold start):
//   starting → up        once /health responds
//   up       → down      after the sidecar was reachable and then FAILS_TO_DOWN
//                        consecutive polls (debounced)
// We only surface "down" if it was ever "up", so launch-time loading reads as
// "starting", not "끊김". The debounce matters because a session's model load
// (GPU/CUDA init) can briefly stall the event loop and time out a single poll —
// that transient blip must not flash the scary "연결 끊김" banner (phase v4-6 보강).

import { useCallback, useEffect, useRef, useState } from "react";
import { getHealth } from "@/api/client";

export type BackendStatus = "starting" | "up" | "down";

const POLL_MS = 5000;
// 연속 실패가 이만큼 쌓여야 "down" — 단발 타임아웃(모델 로드 중 정체 등) 오탐 방지.
const FAILS_TO_DOWN = 3;

export function useBackendHealth(): { status: BackendStatus; check: () => void } {
  const [status, setStatus] = useState<BackendStatus>("starting");
  const everUp = useRef(false);
  const failStreak = useRef(0);
  const timer = useRef<number | null>(null);

  const check = useCallback(async () => {
    try {
      await getHealth();
      everUp.current = true;
      failStreak.current = 0;
      setStatus("up");
    } catch {
      failStreak.current += 1;
      // 부팅 전(한 번도 안 떠봄)엔 계속 "starting". 떠 있다 끊긴 경우만,
      // 그것도 연속 FAILS_TO_DOWN 회 이상일 때만 "down"으로 확정.
      if (everUp.current && failStreak.current >= FAILS_TO_DOWN) {
        setStatus("down");
      } else if (!everUp.current) {
        setStatus("starting");
      }
    }
  }, []);

  useEffect(() => {
    void check();
    timer.current = window.setInterval(() => void check(), POLL_MS);
    return () => {
      if (timer.current !== null) window.clearInterval(timer.current);
    };
  }, [check]);

  return { status, check };
}
