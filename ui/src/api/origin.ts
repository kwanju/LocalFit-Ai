// Where the FastAPI sidecar lives, from the webview's point of view (ADR-031).
//  - Dev (plain browser, or `tauri dev` served at localhost): same-origin — the
//    Vite proxy forwards REST + /ws to 127.0.0.1:8000, so no base is needed.
//  - Prod (Tauri bundle, served from tauri.localhost): NOT same-origin and there
//    is no proxy, so talk to the local sidecar directly (ADR-002 127.0.0.1).
// VITE_API_BASE / VITE_WS_BASE override both (kept for flexible deploys); without
// them the bundle still works, so there is no hidden build-time env dependency.

const SIDECAR = "127.0.0.1:8000";

/** True when served from the Tauri production bundle origin (tauri.localhost). */
function isTauriBundleOrigin(): boolean {
  return typeof window !== "undefined" && window.location.hostname.endsWith("tauri.localhost");
}

/** Base for REST calls ("" = same-origin / dev proxy). */
export function restBase(): string {
  return import.meta.env.VITE_API_BASE ?? (isTauriBundleOrigin() ? `http://${SIDECAR}` : "");
}

/** WebSocket origin override, or null to use the page origin (dev proxy). */
export function wsBaseOverride(): string | null {
  return import.meta.env.VITE_WS_BASE ?? (isTauriBundleOrigin() ? `ws://${SIDECAR}` : null);
}
