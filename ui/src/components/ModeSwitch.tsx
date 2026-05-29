// 1-tap mode switch (phase-5C, PRD 2-2). Before a session starts this just sets
// the mode; mid-session it restarts the session (backend mode is fixed at start).

import type { SessionMode } from "@/api/types";

interface ModeMeta {
  mode: SessionMode;
  label: string;
  hint: string;
}

const MODES: readonly ModeMeta[] = [
  { mode: "c2c", label: "채팅·채팅", hint: "조용히" },
  { mode: "c2s", label: "채팅·음성", hint: "헬스장" },
  { mode: "s2s", label: "음성·음성", hint: "집" },
  { mode: "s2c", label: "음성·채팅", hint: "답만" },
];

interface ModeSwitchProps {
  current: SessionMode;
  onSelect: (mode: SessionMode) => void;
}

export function ModeSwitch({ current, onSelect }: ModeSwitchProps) {
  return (
    <div className="flex gap-1" role="group" aria-label="모드 전환">
      {MODES.map((m) => {
        const selected = m.mode === current;
        return (
          <button
            key={m.mode}
            type="button"
            onClick={() => onSelect(m.mode)}
            aria-pressed={selected}
            title={`${m.label} (${m.hint})`}
            className={`flex flex-col items-center rounded-lg px-3 py-1.5 text-xs font-semibold ${
              selected ? "bg-sky-600 text-white" : "bg-slate-800 text-slate-300"
            }`}
          >
            <span>{m.label}</span>
            <span className="text-[10px] opacity-70">{m.hint}</span>
          </button>
        );
      })}
    </div>
  );
}
