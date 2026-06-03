import { BrowserRouter, Navigate, NavLink, Route, Routes } from "react-router-dom";
import { SessionProvider } from "@/state/session";
import { Onboarding } from "@/screens/Onboarding";
import { SessionLive } from "@/screens/SessionLive";
import { Settings, readDefaultMode } from "@/screens/Settings";
import { Calendar } from "@/screens/Calendar";

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
            <Route
              path="/session"
              element={
                <SessionProvider initialMode={readDefaultMode()}>
                  <SessionLive />
                </SessionProvider>
              }
            />
            <Route path="/calendar" element={<Calendar />} />
            <Route path="/settings" element={<Settings />} />
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
