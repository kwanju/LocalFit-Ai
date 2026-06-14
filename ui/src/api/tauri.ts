// Thin wrapper over the Tauri runtime so the React app can run in both the
// desktop shell (ADR-031) and a plain browser (dev). When not inside Tauri the
// helpers no-op, so screens stay browser-safe.

import { invoke, isTauri } from "@tauri-apps/api/core";

/** True when running inside the Tauri webview (vs. a plain browser tab). */
export function inTauri(): boolean {
  try {
    return isTauri();
  } catch {
    return false;
  }
}

/**
 * Ask the Tauri shell to (re)spawn the FastAPI sidecar. Returns true if a new
 * process was started, false if one was already running. Throws (string) on
 * spawn failure. No-op returning false outside Tauri.
 */
export async function restartBackend(): Promise<boolean> {
  if (!inTauri()) return false;
  return invoke<boolean>("start_backend");
}

/**
 * Fire a native OS toast via the Tauri shell (ADR-027). Used by the reminder
 * scheduler to surface workout/check-in reminders even when the window is hidden
 * to the tray. No-op outside Tauri (browser dev shows reminders in-app only).
 */
export async function notify(title: string, body: string): Promise<void> {
  if (!inTauri()) return;
  await invoke("notify", { title, body });
}
