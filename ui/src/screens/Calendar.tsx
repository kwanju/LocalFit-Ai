// Calendar screen — yearly workout heatmap (ADR-020).

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchCalendar, type DayStat } from "@/api/calendar";
import { CalendarHeatmap } from "@/components/CalendarHeatmap";

type LoadState = "loading" | "empty" | "ready" | "error";

const CURRENT_YEAR = new Date().getFullYear();
const YEARS = [CURRENT_YEAR, CURRENT_YEAR - 1, CURRENT_YEAR - 2].filter((y) => y >= 2024);

// 1-week strip view when there's data but it's all very recent
function hasOnlyRecentData(stats: DayStat[]): boolean {
  if (stats.length === 0) return false;
  const dates = stats.map((s) => new Date(s.date).getTime());
  const oldest = Math.min(...dates);
  const sevenDaysAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
  return oldest >= sevenDaysAgo;
}

function WeekStrip({ stats }: { stats: DayStat[] }) {
  const today = new Date();
  const days: Array<{ label: string; stat: DayStat | undefined }> = [];
  const byDate = new Map<string, DayStat>(stats.map((s) => [s.date, s]));

  for (let i = 6; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const iso = d.toISOString().slice(0, 10);
    const label = (["일", "월", "화", "수", "목", "금", "토"] as const)[d.getDay() as 0|1|2|3|4|5|6];
    days.push({ label, stat: byDate.get(iso) });
  }

  const levelBg = [
    "bg-slate-700",
    "bg-green-800",
    "bg-green-700",
    "bg-green-600",
    "bg-green-500",
  ] as const;

  return (
    <div className="flex justify-center gap-2 rounded-xl bg-slate-900 p-4">
      {days.map(({ label, stat }) => {
        const level = stat?.level ?? 0;
        return (
          <div key={label} className="flex flex-col items-center gap-1">
            <div className={`h-8 w-8 rounded ${levelBg[level]}`} />
            <span className="text-xs text-slate-400">{label}</span>
          </div>
        );
      })}
    </div>
  );
}

export function Calendar() {
  const [year, setYear] = useState(CURRENT_YEAR);
  const [stats, setStats] = useState<DayStat[]>([]);
  const [state, setState] = useState<LoadState>("loading");

  useEffect(() => {
    setState("loading");
    const from = `${year}-01-01`;
    const to = `${year}-12-31`;
    fetchCalendar(from, to)
      .then((data) => {
        setStats(data);
        setState(data.length === 0 ? "empty" : "ready");
      })
      .catch(() => setState("error"));
  }, [year]);

  const showStrip = state === "ready" && hasOnlyRecentData(stats);

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-slate-950 px-4 py-6">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">운동 기록</h1>
        {state === "ready" && !showStrip && (
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="rounded bg-slate-800 px-2 py-1 text-sm text-slate-200"
          >
            {YEARS.map((y) => (
              <option key={y} value={y}>
                {y}년
              </option>
            ))}
          </select>
        )}
      </div>

      {/* States */}
      {state === "loading" && (
        <p className="text-center text-slate-400">불러오는 중…</p>
      )}

      {state === "error" && (
        <p className="text-center text-red-400">
          기록을 불러오지 못했습니다. 서버가 실행 중인지 확인해 주세요.
        </p>
      )}

      {state === "empty" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
          <p className="text-2xl">🏋️</p>
          <p className="text-slate-300">아직 운동 기록이 없어요.</p>
          <p className="text-sm text-slate-500">첫 세션을 시작해보세요!</p>
          <Link
            to="/session"
            className="mt-2 rounded-lg bg-sky-600 px-6 py-2 text-sm font-semibold text-white hover:bg-sky-500"
          >
            세션 시작
          </Link>
        </div>
      )}

      {state === "ready" && showStrip && (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-slate-400 text-center">최근 7일</p>
          <WeekStrip stats={stats} />
          <p className="text-center text-xs text-slate-500 mt-2">
            운동을 계속하면 연간 히트맵이 채워져요!
          </p>
        </div>
      )}

      {state === "ready" && !showStrip && (
        <CalendarHeatmap data={stats} year={year} />
      )}
    </div>
  );
}
