// In-app reminder surface (ADR-027). Doubles as the fallback for "OS 알림 꺼짐"
// and "스케줄러 사망 → 앱 복귀 시 누락 표시": /schedule/pending is computed from the
// schedule independent of whether a toast actually fired, so opening the app always
// shows reminders whose time has passed and aren't yet handled.
//
// Click→session (8-3, tray/app-open routing): "지금 시작" enters the session-start
// flow (/session) where 세션 시작 + the condition check-in live; that's also where the
// ADR-030 model prewarm/cold-start UX kicks in.

import { useNavigate } from "react-router-dom";
import type { Reminder } from "@/api/client";

export function ReminderBanner({
  pending,
  onAck,
}: {
  pending: Reminder[];
  onAck: (key?: string) => void;
}) {
  const navigate = useNavigate();
  if (pending.length === 0) return null;

  // 운동 리마인드를 우선 노출(체크인보다 행동 유발). 나머지는 "외 N건"으로 요약.
  // pending.length > 0 (guarded above), so pending[0] is defined.
  const primary = pending.find((r) => r.kind === "workout") ?? pending[0]!;
  const others = pending.length - 1;
  const icon = primary.kind === "workout" ? "🏋️" : "📝";

  const start = () => {
    onAck(primary.key);
    navigate("/session");
  };

  return (
    <div
      role="status"
      className="flex items-center justify-between gap-2 bg-emerald-900 px-3 py-2 text-sm text-emerald-100"
    >
      <span className="min-w-0 flex-1 truncate">
        <span aria-hidden="true" className="mr-1">
          {icon}
        </span>
        {primary.title} — {primary.body}
        {others > 0 && <span className="text-emerald-300"> (외 {others}건)</span>}
      </span>
      <div className="flex shrink-0 gap-2">
        <button
          type="button"
          onClick={start}
          className="rounded bg-emerald-600 px-3 py-1 font-semibold text-white"
        >
          지금 시작
        </button>
        <button
          type="button"
          onClick={() => onAck(primary.key)}
          className="rounded bg-emerald-800 px-3 py-1"
        >
          나중에
        </button>
      </div>
    </div>
  );
}
