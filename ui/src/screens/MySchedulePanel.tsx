// "내 일정" 패널 — 기록 탭 위쪽 (ADR-034, phase v4-9c).
//
// ⚠️ 아래 히트맵(ADR-020, 로컬 운동 통계)과는 **다른 데이터**다: 이건 외부 Google
// Calendar 의 실제 일정(보기/추가/삭제). 라벨로 구분하고 client.ts 경유로만 접근한다.

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  createGcalEvent,
  deleteGcalEvent,
  getGcalGaps,
  getGcalStatus,
  listGcalEvents,
  type GcalEvent,
} from "@/api/client";

type PanelState = "loading" | "disconnected" | "ready" | "error";

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"] as const;

function localISO(d: Date): string {
  // 타임존 오프셋을 더해 로컬 wall-clock 을 보존(toISOString 은 UTC 라 날짜가 밀림).
  const off = d.getTimezoneOffset() * 60_000;
  return new Date(d.getTime() - off).toISOString().slice(0, 19);
}

function dayLabel(d: Date): string {
  return `${d.getMonth() + 1}월 ${d.getDate()}일 (${WEEKDAYS[d.getDay()]})`;
}

function timeLabel(ev: GcalEvent): string {
  if (ev.all_day) return "종일";
  const d = new Date(ev.start);
  const h = d.getHours();
  const m = d.getMinutes();
  const ampm = h < 12 ? "오전" : "오후";
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${ampm} ${h12}:${String(m).padStart(2, "0")}`;
}

function groupByDay(events: GcalEvent[]): Array<{ label: string; events: GcalEvent[] }> {
  const groups = new Map<string, { label: string; events: GcalEvent[] }>();
  for (const ev of events) {
    const d = new Date(ev.start);
    const key = localISO(d).slice(0, 10);
    if (!groups.has(key)) groups.set(key, { label: dayLabel(d), events: [] });
    groups.get(key)!.events.push(ev);
  }
  return Array.from(groups.values());
}

function AddEventForm({ onAdded }: { onAdded: () => void }) {
  const now = new Date();
  const defaultDate = localISO(now).slice(0, 10);
  const [summary, setSummary] = useState("");
  const [date, setDate] = useState(defaultDate);
  const [time, setTime] = useState("18:00");
  const [duration, setDuration] = useState(30);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    const title = summary.trim();
    if (!title) {
      setError("일정 제목을 입력해 주세요.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await createGcalEvent({ summary: title, start: `${date}T${time}:00`, duration_min: duration });
      setSummary("");
      onAdded();
    } catch {
      setError("일정을 추가하지 못했어요. 연동 상태를 확인해 주세요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2 rounded-lg bg-slate-800 p-3">
      <p className="text-sm font-semibold text-slate-200">일정 추가</p>
      <input
        aria-label="일정 제목"
        placeholder="예: 헬스장 가기"
        value={summary}
        onChange={(e) => setSummary(e.target.value)}
        className="rounded bg-slate-700 px-2 py-1 text-sm outline-none focus:ring-2 focus:ring-sky-500"
      />
      <div className="flex flex-wrap gap-2">
        <input
          aria-label="날짜"
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="rounded bg-slate-700 px-2 py-1 text-sm"
        />
        <input
          aria-label="시각"
          type="time"
          value={time}
          onChange={(e) => setTime(e.target.value)}
          className="rounded bg-slate-700 px-2 py-1 text-sm"
        />
        <select
          aria-label="길이"
          value={duration}
          onChange={(e) => setDuration(Number(e.target.value))}
          className="rounded bg-slate-700 px-2 py-1 text-sm"
        >
          <option value={30}>30분</option>
          <option value={45}>45분</option>
          <option value={60}>1시간</option>
          <option value={90}>1시간 30분</option>
        </select>
      </div>
      {error && <p className="text-xs text-rose-400">{error}</p>}
      <button
        type="button"
        onClick={submit}
        disabled={busy}
        className="self-start rounded-lg bg-sky-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-sky-500 disabled:opacity-50"
      >
        {busy ? "추가 중…" : "추가"}
      </button>
    </div>
  );
}

export function MySchedulePanel() {
  const [state, setState] = useState<PanelState>("loading");
  const [events, setEvents] = useState<GcalEvent[]>([]);
  const [gapHint, setGapHint] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const status = await getGcalStatus();
      if (!status.connected) {
        setState("disconnected");
        return;
      }
      const now = new Date();
      const from = localISO(new Date(now.getFullYear(), now.getMonth(), now.getDate()));
      const to = localISO(new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000));
      const result = await listGcalEvents(from, to);
      if (!result.connected) {
        setState("disconnected");
        return;
      }
      setEvents(result.events);
      setState("ready");
      // 빈 시간 힌트는 부가 정보 — 실패해도 패널은 정상.
      getGcalGaps()
        .then((g) => setGapHint(g.hint))
        .catch(() => setGapHint(null));
    } catch {
      setState("error");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function remove(id: string) {
    try {
      await deleteGcalEvent(id);
      setEvents((prev) => prev.filter((e) => e.id !== id));
    } catch {
      // 삭제 실패 시 목록을 다시 불러 실제 상태로 복구.
      void load();
    }
  }

  return (
    <section className="mb-8 flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-bold text-white">내 일정</h2>
        <span className="text-xs text-slate-500">Google Calendar</span>
      </div>

      {state === "loading" && <p className="text-sm text-slate-400">불러오는 중…</p>}

      {state === "error" && (
        <p className="text-sm text-rose-400">일정을 불러오지 못했어요.</p>
      )}

      {state === "disconnected" && (
        <div className="flex flex-col items-start gap-2 rounded-lg bg-slate-800 p-4">
          <p className="text-sm text-slate-300">
            설정에서 캘린더를 연동하면 일정이 여기에 보여요.
          </p>
          <Link
            to="/settings"
            className="rounded-lg bg-sky-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-sky-500"
          >
            설정으로 가기
          </Link>
        </div>
      )}

      {state === "ready" && (
        <>
          {gapHint && (
            <p className="rounded-lg bg-slate-900 px-3 py-2 text-sm text-emerald-300">
              ⏳ {gapHint}
            </p>
          )}

          {events.length === 0 ? (
            <p className="text-sm text-slate-400">앞으로 7일간 잡힌 일정이 없어요.</p>
          ) : (
            <div className="flex flex-col gap-3">
              {groupByDay(events).map((group) => (
                <div key={group.label} className="flex flex-col gap-1">
                  <p className="text-xs font-semibold text-slate-400">{group.label}</p>
                  {group.events.map((ev) => (
                    <div
                      key={ev.id}
                      className="flex items-center justify-between rounded-lg bg-slate-800 px-3 py-2"
                    >
                      <div className="flex min-w-0 items-center gap-3">
                        <span className="w-16 shrink-0 text-xs text-slate-400">
                          {timeLabel(ev)}
                        </span>
                        <span className="truncate text-sm text-slate-100">{ev.summary}</span>
                      </div>
                      <button
                        type="button"
                        aria-label={`${ev.summary} 삭제`}
                        onClick={() => remove(ev.id)}
                        className="ml-2 shrink-0 rounded px-2 py-1 text-xs text-rose-400 hover:bg-slate-700"
                      >
                        삭제
                      </button>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}

          <AddEventForm onAdded={load} />
        </>
      )}
    </section>
  );
}
