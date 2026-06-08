// Settings: backend/adapter health (ADR-014 /health) + default mode preset
// (PRD 2-2: 환경별 프리셋). The preset is a client-side default for new sessions.
// 2026-06-07: 운동 기록 초기화 기능 추가 (신규 사용자 시나리오 검증용).

import { useEffect, useState } from "react";
import { getHealth } from "@/api/client";
import type { HealthResponse, SessionMode } from "@/api/types";

const DEFAULT_MODE_KEY = "localfit.defaultMode";

const MODE_LABELS: Record<SessionMode, string> = {
  c2c: "채팅·채팅 (조용히)",
  c2s: "채팅·음성 (헬스장)",
  s2s: "음성·음성 (집)",
  s2c: "음성·채팅",
};

const ADAPTER_LABELS: Record<"llm" | "stt" | "tts", string> = {
  llm: "LLM (코칭)",
  stt: "STT (음성 인식)",
  tts: "TTS (음성 합성)",
};

export function readDefaultMode(): SessionMode {
  const saved = localStorage.getItem(DEFAULT_MODE_KEY);
  if (saved === "c2c" || saved === "c2s" || saved === "s2s" || saved === "s2c") return saved;
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

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealthError(true));
  }, []);

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

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">서버 상태</h2>
        {healthError && <p className="text-sm text-rose-400">서버에 연결할 수 없습니다.</p>}
        {health && (
          <div className="flex flex-col gap-2 rounded-lg bg-slate-800 p-3">
            <StatusRow label="백엔드" ok={health.backend} />
            {(Object.keys(ADAPTER_LABELS) as ("llm" | "stt" | "tts")[]).map((key) => (
              <StatusRow key={key} label={ADAPTER_LABELS[key]} ok={health.adapters[key]} />
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

function StatusRow({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span>{label}</span>
      <span className={ok ? "text-emerald-400" : "text-rose-400"}>{ok ? "정상" : "사용 불가"}</span>
    </div>
  );
}
