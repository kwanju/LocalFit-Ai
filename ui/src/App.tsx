import { BrowserRouter, Navigate, NavLink, Outlet, Route, Routes } from "react-router-dom";
import { SessionProvider } from "@/state/session";
import { Onboarding } from "@/screens/Onboarding";
import { SessionLive } from "@/screens/SessionLive";
import { Settings, readDefaultMode } from "@/screens/Settings";
import { Calendar } from "@/screens/Calendar";

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
  return (
    <BrowserRouter>
      <div className="flex h-full flex-col">
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
