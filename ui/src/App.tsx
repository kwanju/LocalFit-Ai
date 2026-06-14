import { useEffect } from "react";
import { BrowserRouter, Navigate, NavLink, Outlet, Route, Routes } from "react-router-dom";
import { SessionProvider } from "@/state/session";
import { Onboarding } from "@/screens/Onboarding";
import { SessionLive } from "@/screens/SessionLive";
import { Settings, readDefaultMode } from "@/screens/Settings";
import { Calendar } from "@/screens/Calendar";
import { BackendStatusBanner } from "@/components/BackendStatusBanner";
import { prewarmModels } from "@/api/client";
import { inTauri } from "@/api/tauri";

// ADR-030 (b): app-open prewarm. When the desktop app opens/refocuses (e.g.
// reopened from the tray) start loading models so 세션 시작 is fast. This is the
// only allowed preload trigger — user intent (app open), never a background
// scheduler (which would fight a running game for VRAM). Browser dev is exempt
// so casual page loads don't pin VRAM. Best-effort: ignore failures.
function usePrewarmOnOpen() {
  useEffect(() => {
    if (!inTauri()) return;
    const fire = () => void prewarmModels().catch(() => {});
    fire();
    window.addEventListener("focus", fire);
    return () => window.removeEventListener("focus", fire);
  }, []);
}

// Shell that keeps ONE SessionProvider mounted across the workout tabs
// (운동/기록/설정) so navigating between them never tears down the live session
// (2026-06-08). Onboarding ("/") is outside the shell — leaving to it ends the
// session, which is the expected "back to start" behavior.
function SessionShell() {
  return (
    <SessionProvider initialMode={readDefaultMode()}>
      <Outlet />
    </SessionProvider>
  );
}

const NAV = [
  { to: "/", label: "시작", end: true },
  { to: "/session", label: "운동", end: false },
  { to: "/calendar", label: "기록", end: false },
  { to: "/settings", label: "설정", end: false },
];

export default function App() {
  usePrewarmOnOpen();
  return (
    <BrowserRouter>
      <div className="flex h-full flex-col">
        <BackendStatusBanner />
        <main className="min-h-0 flex-1 overflow-hidden">
          <Routes>
            <Route path="/" element={<Onboarding />} />
            <Route element={<SessionShell />}>
              <Route path="/session" element={<SessionLive />} />
              <Route path="/calendar" element={<Calendar />} />
              <Route path="/settings" element={<Settings />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        <nav className="flex border-t border-slate-800">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex-1 py-3 text-center text-sm font-semibold ${
                  isActive ? "text-sky-400" : "text-slate-400"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </BrowserRouter>
  );
}
