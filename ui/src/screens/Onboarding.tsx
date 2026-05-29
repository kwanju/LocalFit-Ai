// Onboarding (PRD 부록 A): profile + optional fitness assessment → first routine.
// Single-user (ADR-002): no user id is sent. Posts to /onboarding then routes to
// the live session.

import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { getOnboarding, submitOnboarding, ApiError } from "@/api/client";
import type { AssessmentInput, FitnessLevel, OnboardingRequest } from "@/api/types";

const LEVELS: { value: FitnessLevel; label: string }[] = [
  { value: "beginner", label: "초급" },
  { value: "intermediate", label: "중급" },
  { value: "advanced", label: "고급" },
];

function numberOrUndefined(raw: string): number | undefined {
  const n = Number(raw);
  return raw.trim() === "" || Number.isNaN(n) ? undefined : n;
}

export function Onboarding() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [level, setLevel] = useState<FitnessLevel>("beginner");
  const [goal, setGoal] = useState("");
  const [pullup, setPullup] = useState("");
  const [pushup, setPushup] = useState("");
  const [squat, setSquat] = useState("");
  const [plank, setPlank] = useState("");
  const [alreadyDone, setAlreadyDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getOnboarding()
      .then((status) => {
        if (status.onboarded) {
          setAlreadyDone(true);
          if (status.profile) setName(status.profile.name);
        }
      })
      .catch((err) => {
        // Best-effort prefill; real errors surface on submit. Don't block the form.
        console.warn("Onboarding status check failed", err);
      });
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const assessment: AssessmentInput = {};
    const pu = numberOrUndefined(pullup);
    const ph = numberOrUndefined(pushup);
    const sq = numberOrUndefined(squat);
    const pl = numberOrUndefined(plank);
    if (pu !== undefined) assessment.pullup_max = pu;
    if (ph !== undefined) assessment.pushup_max = ph;
    if (sq !== undefined) assessment.squat_max = sq;
    if (pl !== undefined) assessment.plank_max_sec = pl;

    const body: OnboardingRequest = {
      name: name.trim() || "사용자",
      fitness_level: level,
    };
    if (goal.trim()) body.goal = goal.trim();
    if (Object.keys(assessment).length > 0) body.assessment = assessment;

    try {
      await submitOnboarding(body);
      navigate("/session");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "온보딩에 실패했습니다.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto flex h-full max-w-md flex-col gap-4 overflow-y-auto p-5">
      <h1 className="text-2xl font-bold">시작하기</h1>
      {alreadyDone && (
        <p className="rounded-lg bg-slate-800 p-3 text-sm text-slate-300">
          이미 온보딩을 완료했어요. 다시 제출하면 프로필이 갱신돼요.
        </p>
      )}
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1">
          <span className="text-sm text-slate-400">이름</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="rounded-lg bg-slate-800 px-3 py-2 outline-none focus:ring-2 focus:ring-sky-500"
            placeholder="사용자"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-sm text-slate-400">체력 수준</span>
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value as FitnessLevel)}
            className="rounded-lg bg-slate-800 px-3 py-2 outline-none focus:ring-2 focus:ring-sky-500"
          >
            {LEVELS.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-sm text-slate-400">목표 (선택)</span>
          <input
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            className="rounded-lg bg-slate-800 px-3 py-2 outline-none focus:ring-2 focus:ring-sky-500"
            placeholder="예: 풀업 10개"
          />
        </label>

        <fieldset className="flex flex-col gap-3 rounded-lg border border-slate-800 p-3">
          <legend className="px-1 text-sm text-slate-400">체력 측정 (선택)</legend>
          <AssessmentField label="풀업 최대 (회)" value={pullup} onChange={setPullup} />
          <AssessmentField label="푸시업 최대 (회)" value={pushup} onChange={setPushup} />
          <AssessmentField label="스쿼트 최대 (회)" value={squat} onChange={setSquat} />
          <AssessmentField label="플랭크 최대 (초)" value={plank} onChange={setPlank} />
        </fieldset>

        {error && <p className="text-sm text-rose-400">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="rounded-xl bg-emerald-600 px-5 py-3 font-semibold text-white disabled:opacity-50"
        >
          {submitting ? "생성 중…" : "루틴 만들고 시작"}
        </button>
      </form>
    </div>
  );
}

function AssessmentField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-3">
      <span className="text-sm">{label}</span>
      <input
        type="number"
        min={0}
        inputMode="numeric"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-24 rounded-lg bg-slate-900 px-3 py-2 text-right outline-none focus:ring-2 focus:ring-sky-500"
      />
    </label>
  );
}
