// Sidecar liveness watch (phase v4-6, 6-3 / ADR-031 "안 행복한 경로").
// Polls /health so the UI can detect a dead FastAPI sidecar (Python+models) and
// offer a restart. /health is cheap and always returns backend:true when the
// process is reachable; a fetch failure means the sidecar is down or still
// coming up (≈30s cold start, spike §2).
//
// State machine (so we don't flash a scary banner during the normal cold start):
//   starting → up        once /health responds
//   up       → down      after the sidecar was reachable and then stops responding
// We only surface "down" if it was ever "up", so launch-time loading reads as
// "starting", not "끊김".

import { useCallback, useEffect, useRef, useState } from "react";
import { getHealth } from "@/api/client";

export type BackendStatus = "starting" | "up" | "down";

const POLL_MS = 5000;

export function useBackendHealth(): { status: BackendStatus; check: () => void } {
  const [status, setStatus] = useState<BackendStatus>("starting");
  const everUp = useRef(false);
  const timer = useRef<number | null>(null);

  const check = useCallback(async () => {
    try {
      await getHealth();
      everUp.current = true;
      setStatus("up");
    } catch {
      setStatus(everUp.current ? "down" : "starting");
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
