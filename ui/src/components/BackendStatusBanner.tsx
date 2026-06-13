// Sidecar-down banner (phase v4-6, 6-3). Sits at the app shell so it's visible
// on every screen. When the FastAPI sidecar dies, the user gets a clear Korean
// notice + a one-tap restart (Tauri invokes start_backend; in a plain browser it
// just retries the health check and tells the user to start the backend).

import { useState } from "react";
import { useBackendHealth } from "@/hooks/useBackendHealth";
import { inTauri, restartBackend } from "@/api/tauri";

export function BackendStatusBanner() {
  const { status, check } = useBackendHealth();
  const [restarting, setRestarting] = useState(false);

  if (status !== "down") return null;

  const tauri = inTauri();

  const handleRestart = async () => {
    setRestarting(true);
    try {
      await restartBackend();
    } catch (err) {
      console.warn("Backend restart failed", err);
    } finally {
      // Give the sidecar a moment to bind before re-checking; the poll will
      // flip the banner away once /health responds.
      window.setTimeout(() => {
        setRestarting(false);
        check();
      }, 1500);
    }
  };

  return (
    <div className="flex items-center justify-between gap-2 bg-rose-900/80 px-3 py-2 text-sm text-rose-50">
      <span>
        백엔드 연결이 끊겼어요.
        {tauri ? " 코치를 다시 시작할게요." : " 백엔드를 실행한 뒤 다시 시도해 주세요."}
      </span>
      <button
        type="button"
        onClick={() => void handleRestart()}
        disabled={restarting}
        className="shrink-0 rounded bg-rose-600 px-3 py-1 font-semibold text-white disabled:opacity-50"
      >
        {restarting ? "재시작 중…" : tauri ? "재시작" : "재시도"}
      </button>
    </div>
  );
}
