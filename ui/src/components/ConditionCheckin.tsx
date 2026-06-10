// 세션 시작 전 자가보고 컨디션 체크인 (ADR-023). 피로도·근육통 5단계 + 선택 메모.
// 선택형(건너뛰기 가능) — 입력하면 POST 후, 건너뛰거나 실패해도 onDone 으로 세션을 시작한다.
// 강도 조절은 코치가 제안→확인으로만 하며, 체크인 자체가 운동을 바꾸지 않는다.

import { useState } from "react";
import { submitCheckin } from "@/api/client";

interface Level {
  value: number;
  label: string;
}

// 피로도는 1–10 척도라 5단계를 짝수값에 매핑(2/4/6/8/10), 근육통은 ADR-023 의 1–5 그대로.
const FATIGUE_LEVELS: readonly Level[] = [
  { value: 2, label: "가뿐" },
  { value: 4, label: "좋음" },
  { value: 6, label: "보통" },
  { value: 8, label: "피곤" },
  { value: 10, label: "매우 피곤" },
];

const SORENESS_LEVELS: readonly Level[] = [
  { value: 1, label: "없음" },
  { value: 2, label: "약간" },
  { value: 3, label: "보통" },
  { value: 4, label: "꽤" },
  { value: 5, label: "심함" },
];

function LevelRow({
  title,
  levels,
  selected,
  onSelect,
}: {
  title: string;
  levels: readonly Level[];
  selected: number | null;
  onSelect: (value: number) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-sm font-semibold text-slate-300">{title}</span>
      <div className="flex gap-1" role="group" aria-label={title}>
        {levels.map((lv) => (
          <button
            key={lv.value}
            type="button"
            aria-label={`${title} ${lv.label}`}
            aria-pressed={selected === lv.value}
            onClick={() => onSelect(lv.value)}
            className={`flex-1 rounded-lg px-2 py-2 text-xs font-semibold ${
              selected === lv.value ? "bg-sky-600 text-white" : "bg-slate-800 text-slate-300"
            }`}
          >
            {lv.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function ConditionCheckin({ onDone }: { onDone: () => void }) {
  const [fatigue, setFatigue] = useState<number | null>(null);
  const [soreness, setSoreness] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    // 아무것도 입력 안 했으면 저장할 의미가 없으니 건너뛰기와 동일하게 처리.
    if (fatigue === null && soreness === null && !note.trim()) {
      onDone();
      return;
    }
    setSubmitting(true);
    try {
      await submitCheckin({
        fatigue: fatigue ?? undefined,
        soreness: soreness ?? undefined,
        note: note.trim() || undefined,
      });
    } catch (err) {
      // 선택형이라 체크인 실패가 세션 시작을 막지 않는다 (ADR-023).
      console.warn("컨디션 체크인 저장 실패", err);
    } finally {
      setSubmitting(false);
      onDone();
    }
  };

  return (
    <div
      className="fixed inset-0 z-20 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="컨디션 체크인"
    >
      <div className="flex w-full max-w-sm flex-col gap-4 rounded-2xl bg-slate-900 p-5">
        <div className="flex flex-col gap-1">
          <h2 className="text-lg font-bold text-slate-100">오늘 컨디션은 어때요?</h2>
          <p className="text-xs text-slate-400">
            건너뛰어도 됩니다. 알려주시면 강도 제안에 참고할게요.
          </p>
        </div>

        <LevelRow title="피로도" levels={FATIGUE_LEVELS} selected={fatigue} onSelect={setFatigue} />
        <LevelRow title="근육통" levels={SORENESS_LEVELS} selected={soreness} onSelect={setSoreness} />

        <label className="flex flex-col gap-1 text-sm font-semibold text-slate-300">
          메모 (선택)
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            placeholder="예: 어제 잠을 잘 못 잤어요"
            className="resize-none rounded-lg bg-slate-800 px-3 py-2 text-sm font-normal text-slate-100"
          />
        </label>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={onDone}
            className="flex-1 rounded-xl bg-slate-700 px-4 py-3 font-semibold text-slate-200"
          >
            건너뛰기
          </button>
          <button
            type="button"
            disabled={submitting}
            onClick={() => void submit()}
            className="flex-1 rounded-xl bg-emerald-600 px-4 py-3 font-semibold text-white disabled:opacity-40"
          >
            시작
          </button>
        </div>
      </div>
    </div>
  );
}
