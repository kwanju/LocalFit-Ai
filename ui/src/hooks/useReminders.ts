// Reminder scheduler (ADR-027). The lightweight, model-free path: a JS poll loop
// in the always-resident webview asks the sidecar what's due (/schedule/due) and
// fires a native OS toast for each, then refreshes the in-app pending list
// (/schedule/pending) that drives the ReminderBanner.
//
// Why the webview owns the timer (not a Rust thread / new HTTP dep): hiding the
// window to tray does NOT stop the webview's JS timers — the process stays alive,
// so setTimeout keeps firing while in the tray. The sidecar holds no models at
// idle (ADR-030), so this whole path is lightweight. Browser dev: notify() no-ops,
// so only the in-app banner shows (still testable without Tauri).
//
// Dedup, mute-window suppression, and missed-reminder recovery all live server-side
// (app/core/schedule.py); this hook is just the trigger + display glue.

import { useCallback, useEffect, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import {
  ackReminder,
  getDueReminders,
  getNotificationSettings,
  getPendingReminders,
  type Reminder,
} from "@/api/client";
import { inTauri, notify } from "@/api/tauri";

const DEFAULT_POLL_MS = 60_000;

export interface UseReminders {
  pending: Reminder[];
  ack: (key?: string) => void;
  refresh: () => void;
}

export function useReminders(): UseReminders {
  const [pending, setPending] = useState<Reminder[]>([]);
  const pollMsRef = useRef(DEFAULT_POLL_MS);

  const refreshPending = useCallback(async () => {
    try {
      setPending(await getPendingReminders());
    } catch {
      // Backend unreachable — keep the last known list; next tick retries.
    }
  }, []);

  const fireDue = useCallback(async () => {
    try {
      const due = await getDueReminders(); // server marks these fired (no repeat)
      for (const r of due) await notify(r.title, r.body);
    } catch {
      // Best-effort: a missed poll is recovered by the server-side catchup window.
    }
  }, []);

  const ack = useCallback(async (key?: string) => {
    // Optimistic: drop locally so the banner closes immediately.
    setPending((prev) => (key ? prev.filter((r) => r.key !== key) : []));
    try {
      await ackReminder(key);
    } catch {
      // Failed ack resurfaces on the next /pending poll — acceptable.
    }
  }, []);

  // Pull the poll interval from settings once (falls back to 60s).
  useEffect(() => {
    let cancelled = false;
    getNotificationSettings()
      .then((s) => {
        if (!cancelled && s.poll_interval_sec > 0) pollMsRef.current = s.poll_interval_sec * 1000;
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // Poll loop. Self-rescheduling setTimeout reads pollMsRef each tick so a settings
  // change takes effect on the next cycle without re-mounting the effect.
  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;
    const tick = async () => {
      await fireDue();
      await refreshPending();
      if (!stopped) timer = window.setTimeout(() => void tick(), pollMsRef.current);
    };
    void tick();

    // Reopening from the tray (Rust emits "app-shown") = re-check now, so a missed
    // reminder surfaces immediately on app-open (8-3 routing + 8-4 missed recovery).
    let unlisten: Promise<() => void> | undefined;
    if (inTauri()) {
      unlisten = listen("app-shown", () => {
        void fireDue();
        void refreshPending();
      });
    }
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
      if (unlisten) void unlisten.then((off) => off());
    };
  }, [fireDue, refreshPending]);

  return { pending, ack, refresh: refreshPending };
}
