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
  const isResting = counting.restRemainingSec !== null;
  const bigValue = isResting
    ? counting.restRemainingSec
    : isTimer
      ? Math.floor(counting.elapsedSec)
      : counting.rep;
  const unit = isResting ? "초 휴식" : isTimer ? "초" : "회";
  const valueClass = isResting ? "text-amber-400" : "text-sky-400";

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4">
      {counting.totalSets > 0 && (
        <span className="rounded-full bg-slate-800 px-4 py-1 text-sm font-semibold text-slate-300">
          세트 {Math.min(counting.setNumber, counting.totalSets)}/{counting.totalSets}
        </span>
      )}
      <div className="flex items-baseline gap-3">
        <span className={`text-count font-black tabular-nums ${valueClass}`}>{bigValue}</span>
        <span className="text-3xl text-slate-400">{unit}</span>
      </div>
      {!isResting && !isTimer && counting.phase && (
        <span className="rounded-full bg-slate-800 px-6 py-2 text-2xl font-semibold text-slate-200">
          {PHASE_LABEL[counting.phase]}
        </span>
      )}
      {!isResting && isTimer && (
        <span className="text-xl text-slate-400">{counting.elapsedSec.toFixed(1)}초 경과</span>
      )}
      {isResting && (
        <span className="text-base text-slate-400">다음 세트까지 잠시 휴식</span>
      )}
    </div>
  );
}
