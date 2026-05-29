// Large on-screen counting (PRD 2-3: 화면 큰 숫자). Metronome shows the rep and
// the current phase; timer shows elapsed seconds. Vibrates on each rep so the
// cue lands even if the earphone slips out (PRD 2-3 휴식/진동 알림).

import { useEffect, useRef } from "react";
import type { CountingState } from "@/state/session";

const PHASE_LABEL: Record<NonNullable<CountingState["phase"]>, string> = {
  up: "올라가기",
  down: "내려가기",
  tick: "유지",
};

function vibrate(pattern: number | number[]): void {
  if (typeof navigator !== "undefined" && "vibrate" in navigator) {
    navigator.vibrate(pattern);
  }
}

export function CountingDisplay({ counting }: { counting: CountingState }) {
  const prevRep = useRef(0);

  useEffect(() => {
    if (counting.active && counting.rep !== prevRep.current) {
      vibrate(60);
    }
    prevRep.current = counting.rep;
  }, [counting.active, counting.rep]);

  if (!counting.active) {
    return (
      <div className="flex flex-1 items-center justify-center text-slate-500">
        <p>카운팅이 시작되면 여기에 큰 숫자가 표시돼요.</p>
      </div>
    );
  }

  const isTimer = counting.exerciseMode === "timer";
  const bigValue = isTimer ? Math.floor(counting.elapsedSec) : counting.rep;
  const unit = isTimer ? "초" : "회";

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4">
      <div className="flex items-baseline gap-3">
        <span className="text-count font-black tabular-nums text-sky-400">{bigValue}</span>
        <span className="text-3xl text-slate-400">{unit}</span>
      </div>
      {!isTimer && counting.phase && (
        <span className="rounded-full bg-slate-800 px-6 py-2 text-2xl font-semibold text-slate-200">
          {PHASE_LABEL[counting.phase]}
        </span>
      )}
      {isTimer && (
        <span className="text-xl text-slate-400">{counting.elapsedSec.toFixed(1)}초 경과</span>
      )}
    </div>
  );
}
