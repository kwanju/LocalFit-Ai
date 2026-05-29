// C2S one-touch quick replies (phase-5C, PRD 미결 #2). Gym scenario: faster than
// typing. Each button sends its label as a coach message. ~14 phrases (10~15 range).

const QUICK_REPLIES: readonly string[] = [
  "세트 완료",
  "한 세트 더",
  "휴식 30초 추가",
  "휴식 끝, 시작할게요",
  "다음 운동",
  "이 운동 건너뛰기",
  "좀 더 천천히",
  "좀 더 빠르게",
  "너무 힘들어요",
  "폼 봐주세요",
  "무게 올릴게요",
  "무게 내릴게요",
  "5분만 쉴게요",
  "오늘은 여기까지",
];

interface QuickButtonsProps {
  onSelect: (text: string) => void;
  disabled?: boolean;
}

export function QuickButtons({ onSelect, disabled = false }: QuickButtonsProps) {
  return (
    <div className="grid grid-cols-2 gap-2 p-3 sm:grid-cols-3">
      {QUICK_REPLIES.map((reply) => (
        <button
          key={reply}
          type="button"
          onClick={() => onSelect(reply)}
          disabled={disabled}
          className="rounded-xl bg-slate-800 px-3 py-4 text-center font-semibold text-slate-100 active:bg-sky-600 disabled:opacity-40"
        >
          {reply}
        </button>
      ))}
    </div>
  );
}
