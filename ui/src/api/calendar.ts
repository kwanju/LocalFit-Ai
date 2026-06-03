// Calendar API client (ADR-020). All fetch calls go through this module.

const BASE = import.meta.env.VITE_API_BASE ?? "";
const TIMEOUT_MS = 8000;

export interface SessionSummary {
  id: number;
  started_at: string;
  duration_min: number | null;
}

export interface DayStat {
  date: string; // YYYY-MM-DD
  level: number; // 0-4
  volume: number;
  sessions: SessionSummary[];
  exercises: string[];
  condition_avg: number | null;
}

export async function fetchCalendar(from?: string, to?: string): Promise<DayStat[]> {
  const params = new URLSearchParams();
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  const qs = params.size ? `?${params.toString()}` : "";

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${BASE}/api/calendar${qs}`, { signal: controller.signal });
    if (!res.ok) throw new Error(`캘린더 데이터 조회 실패 (${res.status})`);
    return (await res.json()) as DayStat[];
  } finally {
    clearTimeout(timer);
  }
}
