// Settings: backend/adapter health (ADR-014 /health) + default mode preset
// (PRD 2-2: 환경별 프리셋). The preset is a client-side default for new sessions.
// 2026-06-07: 운동 기록 초기화 기능 추가 (신규 사용자 시나리오 검증용).

import { useEffect, useState } from "react";
import {
  type GcalProposedEvent,
  type GcalStatus,
  gcalConnect,
  gcalDisconnect,
  getGcalStatus,
  getHealth,
  getNotificationSettings,
  previewPlanEvents,
  registerPlanEvents,
  updateNotificationSettings,
  type NotificationSettings,
} from "@/api/client";
import type { HealthResponse, SessionMode } from "@/api/types";

const DEFAULT_MODE_KEY = "localfit.defaultMode";

// 콜드스타트(사이드카+모델 ≈30s) 동안 첫 fetch 가 빗나가도 그대로 에러로 굳지 않게
// 잠시 재시도한다 — 이전에는 mount 시 1회만 호출해, 부팅 전 실패가 영구 에러로 남았다.
const COLD_START_RETRIES = 8;
const COLD_START_DELAY_MS = 2500;

function loadWithRetry<T>(
  fn: () => Promise<T>,
  onOk: (v: T) => void,
  onFail: () => void,
): () => void {
  let cancelled = false;
  let attempts = 0;
  const tick = () => {
    fn()
      .then((v) => {
        if (!cancelled) onOk(v);
      })
      .catch(() => {
        if (cancelled) return;
        attempts += 1;
        if (attempts < COLD_START_RETRIES) window.setTimeout(tick, COLD_START_DELAY_MS);
        else onFail();
      });
  };
  tick();
  return () => {
    cancelled = true;
  };
}

const MODE_LABELS: Record<SessionMode, string> = {
  c2c: "채팅·채팅 (조용히)",
  c2s: "채팅·음성 (헬스장)",
  s2s: "음성·음성 (집)",
};

const ADAPTER_LABELS: Record<"llm" | "stt" | "tts", string> = {
  llm: "LLM (코칭)",
  stt: "STT (음성 인식)",
  tts: "TTS (음성 합성)",
};

export function readDefaultMode(): SessionMode {
  const saved = localStorage.getItem(DEFAULT_MODE_KEY);
  // ADR-021: s2c 제거 — 과거에 저장된 "s2c"는 더 이상 유효하지 않으므로 기본값으로.
  if (saved === "c2c" || saved === "c2s" || saved === "s2s") return saved;
  return "c2c";
}

type ResetStatus =
  | { kind: "idle" }
  | { kind: "running"; scope: "history" | "all" }
  | { kind: "done"; scope: "history" | "all"; cleared: Record<string, number> }
  | { kind: "error"; message: string };

async function resetRecords(scope: "history" | "all"): Promise<Record<string, number>> {
  const res = await fetch(`/admin/reset?scope=${scope}`, { method: "POST" });
  if (!res.ok) throw new Error(`초기화 실패 (${res.status})`);
  const body = (await res.json()) as { cleared: Record<string, number>; scope: string };
  return body.cleared;
}

export function Settings() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [defaultMode, setDefaultMode] = useState<SessionMode>(readDefaultMode);
  const [reset, setReset] = useState<ResetStatus>({ kind: "idle" });

  useEffect(
    () =>
      loadWithRetry(
        getHealth,
        (v) => {
          setHealth(v);
          setHealthError(false);
        },
        () => setHealthError(true),
      ),
    [],
  );

  const runReset = async (scope: "history" | "all") => {
    const prompt =
      scope === "all"
        ? "온보딩 프로필·루틴까지 모두 삭제합니다. 초기 화면으로 돌아가요. 진행할까요?"
        : "운동 기록(세션·세트·컨디션·대화)을 모두 삭제합니다. 진행할까요?";
    if (!window.confirm(prompt)) return;
    setReset({ kind: "running", scope });
    try {
      const cleared = await resetRecords(scope);
      setReset({ kind: "done", scope, cleared });
      if (scope === "all") {
        // 온보딩까지 지웠으니 onboarding 화면으로 리로드.
        window.setTimeout(() => {
          window.location.href = "/";
        }, 800);
      }
    } catch (err) {
      setReset({
        kind: "error",
        message: err instanceof Error ? err.message : "초기화 중 알 수 없는 오류가 발생했습니다.",
      });
    }
  };

  const onModeChange = (mode: SessionMode) => {
    setDefaultMode(mode);
    localStorage.setItem(DEFAULT_MODE_KEY, mode);
  };

  return (
    <div className="mx-auto flex h-full max-w-md flex-col gap-6 overflow-y-auto p-5">
      <h1 className="text-2xl font-bold">설정</h1>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">기본 모드</h2>
        <select
          value={defaultMode}
          onChange={(e) => onModeChange(e.target.value as SessionMode)}
          className="rounded-lg bg-slate-800 px-3 py-2 outline-none focus:ring-2 focus:ring-sky-500"
        >
          {(Object.keys(MODE_LABELS) as SessionMode[]).map((m) => (
            <option key={m} value={m}>
              {MODE_LABELS[m]}
            </option>
          ))}
        </select>
      </section>

      <NotificationSection />

      <CalendarSection />

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">서버 상태</h2>
        {healthError && <p className="text-sm text-rose-400">서버에 연결할 수 없습니다.</p>}
        {health && (
          <div className="flex flex-col gap-2 rounded-lg bg-slate-800 p-3">
            <StatusRow label="백엔드" ok={health.backend} />
            {(Object.keys(ADAPTER_LABELS) as ("llm" | "stt" | "tts")[]).map((key) => (
              <StatusRow
                key={key}
                label={ADAPTER_LABELS[key]}
                ok={health.adapters[key]}
                // ADR-030: idle 엔 모델이 안 떠 있는 게 정상 — 빨강 "사용 불가" 대신
                // "대기 중"으로 표기해 오해를 막는다. 세션 시작 시 로드된다.
                idle={!health.models_loaded}
              />
            ))}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">데이터 관리</h2>
        <p className="text-xs text-slate-500">
          테스트하면서 쌓인 세션/세트 기록을 비울 수 있어요. 신규 사용자 시나리오 검증에 사용.
        </p>
        <div className="flex flex-col gap-2 rounded-lg bg-slate-800 p-3">
          <button
            type="button"
            disabled={reset.kind === "running"}
            onClick={() => void runReset("history")}
            className="rounded-lg bg-amber-700 px-4 py-2 text-sm font-semibold disabled:opacity-50"
          >
            운동 기록만 초기화
          </button>
          <button
            type="button"
            disabled={reset.kind === "running"}
            onClick={() => void runReset("all")}
            className="rounded-lg bg-rose-700 px-4 py-2 text-sm font-semibold disabled:opacity-50"
          >
            전체 초기화 (프로필·루틴 포함)
          </button>
          {reset.kind === "running" && (
            <p className="text-xs text-slate-400">초기화 중…</p>
          )}
          {reset.kind === "done" && (
            <p className="text-xs text-emerald-400">
              완료: {Object.entries(reset.cleared)
                .filter(([, n]) => n > 0)
                .map(([k, n]) => `${k} ${n}`)
                .join(", ") || "(삭제할 데이터 없음)"}
            </p>
          )}
          {reset.kind === "error" && (
            <p className="text-xs text-rose-400">{reset.message}</p>
          )}
        </div>
      </section>

      {/* 단일 사용자 앱(ADR-002)이라 면책 고지는 능동 노출 없이 옵션으로만 둔다. */}
      <details className="mt-auto text-xs text-slate-500">
        <summary className="cursor-pointer select-none">면책 고지</summary>
        <p className="mt-2 leading-relaxed">
          LocalFit AI는 피트니스 가이던스 앱이며, 의료 기기나 의료 전문가를 대체하지 않습니다. 통증,
          부상, 또는 건강 이상이 있다면 운동을 중단하고 의료 전문가와 상담하세요.
        </p>
      </details>
    </div>
  );
}

// 능동 알림 설정 (ADR-027). 단일 행 DB 설정(/schedule/settings)을 읽어 수정.
// poll_interval/catchup 은 읽기 전용(config) 이라 노출하지 않는다.
const MUTE_DEFAULT = { start: "22:00", end: "07:00" };

function NotificationSection() {
  const [s, setS] = useState<NotificationSettings | null>(null);
  const [error, setError] = useState(false);

  const load = () =>
    loadWithRetry(
      getNotificationSettings,
      (v) => {
        setS(v);
        setError(false);
      },
      () => setError(true),
    );

  useEffect(() => load(), []);

  const patch = async (
    p: Partial<Omit<NotificationSettings, "poll_interval_sec" | "catchup_minutes">>,
  ) => {
    if (!s) return;
    setS({ ...s, ...p }); // optimistic
    try {
      setS(await updateNotificationSettings(p));
    } catch {
      setError(true);
    }
  };

  if (error && !s) {
    return (
      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">알림</h2>
        <p className="text-sm text-rose-400">알림 설정을 불러올 수 없습니다.</p>
        <button
          type="button"
          onClick={() => {
            setError(false);
            load();
          }}
          className="self-start rounded bg-slate-700 px-3 py-1 text-sm"
        >
          다시 시도
        </button>
      </section>
    );
  }
  if (!s) {
    return (
      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">알림</h2>
        <p className="text-sm text-slate-400">불러오는 중…</p>
      </section>
    );
  }

  // 음소거 사용 여부 = start/end 가 설정되어 있고 서로 다를 때(같으면 빈 구간 = 음소거 없음).
  const muteOn = s.mute_start != null && s.mute_end != null && s.mute_start !== s.mute_end;

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold">알림</h2>
      <p className="text-xs text-slate-500">
        운동 시간이 되면 알려드려요. 앱을 켜지 않아도 트레이에서 동작합니다.
      </p>
      <div className="flex flex-col gap-3 rounded-lg bg-slate-800 p-3">
        <label className="flex items-center justify-between">
          <span>능동 알림 켜기</span>
          <input
            type="checkbox"
            checked={s.enabled}
            onChange={(e) => void patch({ enabled: e.target.checked })}
            className="h-4 w-4 accent-sky-500"
          />
        </label>

        <fieldset disabled={!s.enabled} className="flex flex-col gap-3 disabled:opacity-40">
          <label className="flex items-center justify-between">
            <span>운동 시간</span>
            <input
              type="time"
              value={s.workout_time}
              onChange={(e) => void patch({ workout_time: e.target.value })}
              className="rounded bg-slate-700 px-2 py-1"
            />
          </label>
          <label className="flex items-center justify-between">
            <span>몇 분 전 알림</span>
            <input
              type="number"
              min={0}
              max={120}
              value={s.lead_minutes}
              onChange={(e) => void patch({ lead_minutes: Number(e.target.value) })}
              className="w-20 rounded bg-slate-700 px-2 py-1"
            />
          </label>

          <label className="flex items-center justify-between">
            <span>컨디션 체크인 알림</span>
            <input
              type="checkbox"
              checked={s.checkin_enabled}
              onChange={(e) => void patch({ checkin_enabled: e.target.checked })}
              className="h-4 w-4 accent-sky-500"
            />
          </label>
          {s.checkin_enabled && (
            <label className="flex items-center justify-between pl-3">
              <span className="text-sm text-slate-400">체크인 시간</span>
              <input
                type="time"
                value={s.checkin_time}
                onChange={(e) => void patch({ checkin_time: e.target.value })}
                className="rounded bg-slate-700 px-2 py-1"
              />
            </label>
          )}

          <MuteRow
            muteOn={muteOn}
            start={s.mute_start ?? MUTE_DEFAULT.start}
            end={s.mute_end ?? MUTE_DEFAULT.end}
            onPatch={patch}
          />
        </fieldset>
        {error && <p className="text-xs text-rose-400">설정 저장 중 오류가 발생했습니다.</p>}
      </div>
    </section>
  );
}

// Google Calendar 연동 (ADR-022, phase v4-9b). ADR-020 로컬 히트맵과 무관.
// 최초 OAuth 연동은 음성으로 못 하므로 여기 버튼이 유일한 진입점이다. 등록은 미리보기→
// 확인 2단계(확답 게이트, 자동 등록 금지). 미연동/오프라인이면 코칭엔 영향 없음(degrade).
function _fmtEvent(e: GcalProposedEvent): string {
  const d = new Date(e.start);
  const when = d.toLocaleString("ko-KR", {
    month: "numeric", day: "numeric", weekday: "short", hour: "numeric", minute: "2-digit",
  });
  return `${when} · ${e.exercise}`;
}

export function CalendarSection() {
  const [status, setStatus] = useState<GcalStatus | null>(null);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState<null | "connect" | "disconnect" | "preview" | "register">(null);
  const [preview, setPreview] = useState<GcalProposedEvent[] | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = () =>
    loadWithRetry(
      getGcalStatus,
      (v) => {
        setStatus(v);
        setError(false);
      },
      () => setError(true),
    );
  useEffect(() => load(), []);

  const connect = async () => {
    setBusy("connect");
    setMsg(null);
    try {
      setStatus(await gcalConnect());
    } catch {
      setMsg("연동에 실패했어요. 자격증명(google_client_secret.json)과 브라우저 동의를 확인해 주세요.");
    } finally {
      setBusy(null);
    }
  };

  const disconnect = async () => {
    setBusy("disconnect");
    setPreview(null);
    setMsg(null);
    try {
      setStatus(await gcalDisconnect());
    } catch {
      /* 무시 — 상태는 다음 로드로 보정 */
    } finally {
      setBusy(null);
    }
  };

  const doPreview = async () => {
    setBusy("preview");
    setMsg(null);
    try {
      setPreview(await previewPlanEvents());
    } catch {
      setMsg("미리보기를 불러오지 못했어요.");
    } finally {
      setBusy(null);
    }
  };

  const doRegister = async () => {
    setBusy("register");
    try {
      const r = await registerPlanEvents();
      setMsg(r.created > 0 ? `${r.created}건을 캘린더에 등록했어요.` : "등록할 항목이 없었어요.");
      setPreview(null);
    } catch {
      setMsg("등록에 실패했어요.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold">캘린더</h2>
      <p className="text-xs text-slate-500">
        Google Calendar에 운동 일정을 등록하고, 다른 일정을 읽어 빈 시간을 추천받아요. 연동 안 해도
        코칭은 정상 동작합니다.
      </p>

      {error && !status ? (
        <div className="flex flex-col gap-2 rounded-lg bg-slate-800 p-3">
          <p className="text-sm text-rose-400">연동 상태를 불러올 수 없습니다.</p>
          <button
            type="button"
            onClick={() => {
              setError(false);
              load();
            }}
            className="self-start rounded bg-slate-700 px-3 py-1 text-sm"
          >
            다시 시도
          </button>
        </div>
      ) : !status ? (
        <p className="text-sm text-slate-400">불러오는 중…</p>
      ) : !status.enabled ? (
        <p className="text-sm text-slate-400">캘린더 연동이 설정(config)에서 비활성화되어 있어요.</p>
      ) : (
        <div className="flex flex-col gap-3 rounded-lg bg-slate-800 p-3">
          {!status.connected ? (
            <>
              <span className="text-sm text-slate-300">연동되지 않음</span>
              <button
                type="button"
                onClick={() => void connect()}
                disabled={busy === "connect"}
                className="self-start rounded bg-sky-600 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
              >
                {busy === "connect" ? "브라우저에서 동의해 주세요…" : "Google Calendar 연동하기"}
              </button>
            </>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <span className="text-sm text-emerald-400">연동됨 ✅</span>
                <button
                  type="button"
                  onClick={() => void disconnect()}
                  disabled={busy === "disconnect"}
                  className="rounded bg-slate-700 px-3 py-1 text-xs disabled:opacity-50"
                >
                  연동 해제
                </button>
              </div>

              {preview === null ? (
                <button
                  type="button"
                  onClick={() => void doPreview()}
                  disabled={busy === "preview"}
                  className="self-start rounded bg-slate-700 px-3 py-1.5 text-sm disabled:opacity-50"
                >
                  {busy === "preview" ? "불러오는 중…" : "이번 주 운동 캘린더에 등록"}
                </button>
              ) : preview.length === 0 ? (
                <p className="text-sm text-slate-400">등록할 주간 플랜이 없어요. 먼저 목표를 정해보세요.</p>
              ) : (
                <div className="flex flex-col gap-2">
                  <ul className="flex flex-col gap-1 text-sm text-slate-300">
                    {preview.map((e, i) => (
                      <li key={i}>• {_fmtEvent(e)}</li>
                    ))}
                  </ul>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => void doRegister()}
                      disabled={busy === "register"}
                      className="rounded bg-sky-600 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
                    >
                      {busy === "register" ? "등록 중…" : `${preview.length}건 등록`}
                    </button>
                    <button
                      type="button"
                      onClick={() => setPreview(null)}
                      className="rounded bg-slate-700 px-3 py-1.5 text-sm"
                    >
                      취소
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
          {msg && <p className="text-xs text-slate-400">{msg}</p>}
        </div>
      )}
    </section>
  );
}

// 야간 음소거 토글 + 시간 구간. 해제는 start==end 빈 구간으로 표현(서버가 같은 값=음소거
// 없음 처리) — null 을 PUT 으로 보낼 수 없는 제약(update 가 None 스킵)을 우회.
function MuteRow({
  muteOn,
  start,
  end,
  onPatch,
}: {
  muteOn: boolean;
  start: string;
  end: string;
  onPatch: (p: { mute_start?: string; mute_end?: string }) => void;
}) {
  return (
    <>
      <label className="flex items-center justify-between">
        <span>야간 음소거</span>
        <input
          type="checkbox"
          checked={muteOn}
          onChange={(e) =>
            onPatch(
              e.target.checked
                ? { mute_start: MUTE_DEFAULT.start, mute_end: MUTE_DEFAULT.end }
                : { mute_start: "00:00", mute_end: "00:00" },
            )
          }
          className="h-4 w-4 accent-sky-500"
        />
      </label>
      {muteOn && (
        <div className="flex items-center justify-between gap-2 pl-3">
          <span className="text-sm text-slate-400">조용히</span>
          <div className="flex items-center gap-1">
            <input
              type="time"
              value={start}
              onChange={(e) => onPatch({ mute_start: e.target.value })}
              className="rounded bg-slate-700 px-2 py-1"
            />
            <span className="text-slate-500">~</span>
            <input
              type="time"
              value={end}
              onChange={(e) => onPatch({ mute_end: e.target.value })}
              className="rounded bg-slate-700 px-2 py-1"
            />
          </div>
        </div>
      )}
    </>
  );
}

function StatusRow({ label, ok, idle = false }: { label: string; ok: boolean; idle?: boolean }) {
  // idle(세션 전, 모델 미로드)은 오류가 아니라 정상 대기 상태 — 노랑/회색으로 구분.
  const { cls, text } = ok
    ? { cls: "text-emerald-400", text: "정상" }
    : idle
      ? { cls: "text-amber-400", text: "대기 중 (세션 시작 시 로드)" }
      : { cls: "text-rose-400", text: "사용 불가" };
  return (
    <div className="flex items-center justify-between">
      <span>{label}</span>
      <span className={cls}>{text}</span>
    </div>
  );
}
