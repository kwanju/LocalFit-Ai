// Chat I/O (phase-5B). Renders the conversation log and a text composer.
// Presentational: state + send are passed in by SessionLive.

import { useEffect, useRef, useState, type FormEvent } from "react";
import type { ChatEntry } from "@/state/session";

const ROLE_STYLE: Record<ChatEntry["role"], string> = {
  user: "self-end bg-sky-600 text-white",
  coach: "self-start bg-slate-800 text-slate-100",
  system: "self-center bg-transparent text-slate-500 text-sm",
};

interface ChatPanelProps {
  messages: ChatEntry[];
  onSend: (text: string) => void;
  disabled?: boolean;
}

export function ChatPanel({ messages, onSend, disabled = false }: ChatPanelProps) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || disabled) return;
    onSend(text);
    setDraft("");
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-3">
        {messages.length === 0 && (
          <p className="m-auto text-slate-500">코치와 대화를 시작해 보세요.</p>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2 ${ROLE_STYLE[m.role]} ${
              m.safety ? "ring-2 ring-rose-500" : ""
            } ${m.pending ? "opacity-60" : ""}`}
          >
            {m.text}
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <form onSubmit={submit} className="flex gap-2 border-t border-slate-800 p-3">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={disabled}
          placeholder={disabled ? "세션을 시작하면 입력할 수 있어요" : "메시지를 입력하세요"}
          className="flex-1 rounded-xl bg-slate-800 px-4 py-3 text-slate-100 outline-none ring-sky-500 focus:ring-2 disabled:opacity-50"
          aria-label="채팅 입력"
        />
        <button
          type="submit"
          disabled={disabled || draft.trim().length === 0}
          className="rounded-xl bg-sky-600 px-5 py-3 font-semibold text-white disabled:opacity-40"
        >
          전송
        </button>
      </form>
    </div>
  );
}
