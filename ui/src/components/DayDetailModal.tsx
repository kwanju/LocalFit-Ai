// Day detail modal — shown when a calendar day is clicked (ADR-020).
// Tailwind dialog only, zero additional libraries.

import type { DayStat } from "@/api/calendar";

interface Props {
  stat: DayStat;
  onClose: () => void;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일`;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
}

const LEVEL_LABEL = ["휴식", "가벼움", "보통", "열심히", "최대"] as const;
const LEVEL_COLOR = [
  "text-slate-400",
  "text-green-600",
  "text-green-500",
  "text-green-400",
  "text-green-300",
] as const;

export function DayDetailModal({ stat, onClose }: Props) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-xl bg-slate-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="mb-4 flex items-start justify-between">
          <div>
            <p className="text-lg font-bold text-white">{formatDate(stat.date + "T00:00:00")}</p>
            <p className={`text-sm font-semibold ${LEVEL_COLOR[stat.level]}`}>
              {LEVEL_LABEL[stat.level]}
              {stat.volume > 0 && (
                <span className="ml-2 font-normal text-slate-400">
                  볼륨 {stat.volume.toFixed(0)}
                </span>
              )}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:text-white"
          >
            ✕
          </button>
        </div>

        {/* Exercises */}
        {stat.exercises.length > 0 && (
          <div className="mb-3">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
              운동
            </p>
            <div className="flex flex-wrap gap-1">
              {stat.exercises.map((ex) => (
                <span
                  key={ex}
                  className="rounded-full bg-slate-700 px-2 py-0.5 text-xs text-slate-200"
                >
                  {ex}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Sessions */}
        {stat.sessions.length > 0 && (
          <div className="mb-3">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
              세션
            </p>
            <ul className="space-y-1">
              {stat.sessions.map((s) => (
                <li key={s.id} className="text-sm text-slate-300">
                  {formatTime(s.started_at)} 시작
                  {s.duration_min != null && ` · ${s.duration_min}분`}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Condition */}
        {stat.condition_avg != null && (
          <div>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
              컨디션
            </p>
            <p className="text-sm text-slate-300">
              {stat.condition_avg.toFixed(1)} / 10
            </p>
          </div>
        )}

        {stat.exercises.length === 0 && stat.sessions.length === 0 && (
          <p className="text-sm text-slate-500">기록된 운동이 없습니다.</p>
        )}
      </div>
    </div>
  );
}
