// Screen Wake Lock (ADR-009): keep the screen on during long counting (plank).
// Re-acquires after the tab returns to the foreground, since the browser drops
// the lock on visibility change.

import { useCallback, useEffect, useRef, useState } from "react";

interface WakeLockControls {
  active: boolean;
  supported: boolean;
  request: () => Promise<void>;
  release: () => Promise<void>;
}

export function useWakeLock(): WakeLockControls {
  const supported = typeof navigator !== "undefined" && "wakeLock" in navigator;
  const sentinelRef = useRef<WakeLockSentinel | null>(null);
  const wantedRef = useRef(false);
  const [active, setActive] = useState(false);

  const acquire = useCallback(async () => {
    if (!supported) return;
    try {
      const sentinel = await navigator.wakeLock.request("screen");
      sentinelRef.current = sentinel;
      setActive(true);
      sentinel.addEventListener("release", () => setActive(false));
    } catch (err) {
      console.warn("Wake lock request failed", err);
      setActive(false);
    }
  }, [supported]);

  const request = useCallback(async () => {
    wantedRef.current = true;
    await acquire();
  }, [acquire]);

  const release = useCallback(async () => {
    wantedRef.current = false;
    try {
      await sentinelRef.current?.release();
    } catch (err) {
      console.warn("Wake lock release failed", err);
    }
    sentinelRef.current = null;
    setActive(false);
  }, []);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible" && wantedRef.current && !sentinelRef.current) {
        void acquire();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      void sentinelRef.current?.release();
    };
  }, [acquire]);

  return { active, supported, request, release };
}
