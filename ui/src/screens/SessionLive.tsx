// Live coaching screen — the 4-mode hub (phase-5B C2C, phase-5C voice/C2S).
// Composes counting display, chat, quick buttons, mic, and session controls
// over the session store + audio/wakelock hooks.

import { useEffect, useState } from "react";
import { useSession } from "@/state/session";
import { useAudio } from "@/hooks/useAudio";
import { useWakeLock } from "@/hooks/useWakeLock";
import { ChatPanel } from "@/components/ChatPanel";
import { CountingDisplay } from "@/components/CountingDisplay";
import { QuickButtons } from "@/components/QuickButtons";
import { ModeSwitch } from "@/components/ModeSwitch";
import type { ExerciseMode, SessionMode } from "@/api/types";
import type { SocketStatus } from "@/api/ws";

const VOICE_INPUT: ReadonlySet<SessionMode> = new Set<SessionMode>(["s2s", "s2c"]);
const VOICE_OUTPUT: ReadonlySet<SessionMode> = new Set<SessionMode>(["s2s", "c2s"]);

const STATUS_LABEL: Record<SocketStatus, string> = {
  connecting: "연결 중…",
  open: "연결됨",
  reconnecting: "재연결 중…",
  closed: "연결 끊김",
};

interface ExerciseOption {
  name: string;
  mode: ExerciseMode;
  target?: number;
}

const EXERCISES: readonly ExerciseOption[] = [
  { name: "풀업", mode: "metronome" },
  { name: "푸시업", mode: "metronome" },
  { name: "스쿼트", mode: "metronome" },
  { name: "플랭크", mode: "timer", target: 30 },
];

type MicMode = "hold" | "toggle";

const MIC_MODES: readonly { mode: MicMode; label: string }[] = [
  { mode: "hold", label: "길게 누르기" },
  { mode: "toggle", label: "탭 전환" },
];

export function SessionLive() {
  const { status, mode, started, serverState, messages, counting, lastAudio, actions } =
    useSession();
  const audio = useAudio();
  const wakeLock = useWakeLock();
  const [earphoneHint, setEarphoneHint] = useState(false);
  const [micMode, setMicMode] = useState<MicMode>("hold");

  const isVoiceInput = VOICE_INPUT.has(mode);
  const isVoiceOutput = VOICE_OUTPUT.has(mode);

  // Play the coach's voice when one arrives (voice-output modes only send it).
  // audio.playWav / actions are stable callbacks, so we key only on lastAudio.
  useEffect(() => {
    if (lastAudio) {
      void audio.playWav(lastAudio.b64);
      actions.consumeAudio(lastAudio.seq);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastAudio]);

  // Keep the screen awake while counting (plank can run minutes). request/release
  // are stable; keying on wakeLock would re-request on every render (sentinel leak).
  useEffect(() => {
    if (counting.active) void wakeLock.request();
    else void wakeLock.release();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [counting.active]);

  // Best-effort earphone hint (PRD 2-2: 알림만, 자동 전환 X).
  useEffect(() => {
    const md = navigator.mediaDevices;
    if (!md?.addEventListener) return;
    const onChange = async () => {
      try {
        const devices = await md.enumerateDevices();
        const outputs = devices.filter((d) => d.kind === "audiooutput");
        if (outputs.length > 1 && !isVoiceOutput) setEarphoneHint(true);
      } catch (err) {
        console.warn("Device enumeration failed", err);
      }
    };
    md.addEventListener("devicechange", onChange);
    return () => md.removeEventListener("devicechange", onChange);
  }, [isVoiceOutput]);

  const handleModeSelect = (next: SessionMode) => {
    if (next === mode) return;
    if (started) actions.switchMode(next);
    else actions.setMode(next);
    setEarphoneHint(false);
  };

  const tapInterrupt = () => {
    if (audio.playing) {
      actions.interrupt();
      audio.stopPlayback();
    }
  };

  const startMic = () => {
    if (started) void audio.startRecording();
  };
  const stopMic = async () => {
    if (!audio.recording) return;
    const recorded = await audio.stopRecording();
    if (recorded) actions.sendAudio(recorded.audioB64, recorded.sampleRate);
  };

  const disabled = !started;

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between gap-2 border-b border-slate-800 px-3 py-2">
        <ModeSwitch current={mode} onSelect={handleModeSelect} />
        <div className="flex items-center gap-2 text-xs">
          <span className={status === "open" ? "text-emerald-400" : "text-amber-400"}>
            {STATUS_LABEL[status]}
          </span>
          {serverState && <span className="text-slate-500">· {serverState}</span>}
        </div>
      </header>

      {earphoneHint && (
        <div className="flex items-center justify-between gap-2 bg-slate-800 px-3 py-2 text-sm">
          <span>이어폰이 연결된 것 같아요. 음성 출력으로 바꿀까요?</span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => handleModeSelect("c2s")}
              className="rounded bg-sky-600 px-3 py-1 font-semibold text-white"
            >
              C2S로 전환
            </button>
            <button
              type="button"
              onClick={() => setEarphoneHint(false)}
              className="rounded bg-slate-700 px-3 py-1"
            >
              닫기
            </button>
          </div>
        </div>
      )}

      <div
        role="button"
        tabIndex={0}
        onClick={tapInterrupt}
        onKeyDown={(e) => e.key === "Enter" && tapInterrupt()}
        className="flex flex-1 flex-col"
        aria-label="화면을 탭하면 코치 음성을 멈춰요"
      >
        <CountingDisplay counting={counting} />
        {audio.playing && (
          <p className="pb-2 text-center text-sm text-sky-400">코치 응답 중… (탭하면 멈춤)</p>
        )}
      </div>

      <section className="border-t border-slate-800">
        <CountingControls
          active={counting.active}
          disabled={disabled}
          onStart={(opt) => actions.startCounting(opt.mode, opt.target)}
          onStop={() => actions.stopCounting()}
        />
      </section>

      <section className="flex min-h-0 flex-1 flex-col" style={{ maxHeight: "45vh" }}>
        {mode === "c2s" && (
          <QuickButtons onSelect={(t) => actions.sendText(t)} disabled={disabled} />
        )}
        {isVoiceInput && (
          <MicControl
            disabled={disabled}
            recording={audio.recording}
            micError={audio.micError}
            micMode={micMode}
            onMicModeChange={setMicMode}
            onStart={startMic}
            onStop={() => void stopMic()}
          />
        )}
        <div className="min-h-0 flex-1 overflow-hidden">
          <ChatPanel messages={messages} onSend={(t) => actions.sendText(t)} disabled={disabled} />
        </div>
      </section>

      <footer className="flex flex-wrap gap-2 border-t border-slate-800 p-3">
        {!started ? (
          <button
            type="button"
            onClick={() => actions.startSession()}
            disabled={status !== "open"}
            className="rounded-xl bg-emerald-600 px-5 py-3 font-semibold text-white disabled:opacity-40"
          >
            세션 시작
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={() => actions.pause()}
              className="rounded-xl bg-slate-700 px-4 py-3 font-semibold"
            >
              일시정지
            </button>
            <button
              type="button"
              onClick={() => actions.resume()}
              className="rounded-xl bg-slate-700 px-4 py-3 font-semibold"
            >
              재개
            </button>
            <button
              type="button"
              onClick={() => {
                actions.interrupt();
                audio.stopPlayback();
              }}
              className="rounded-xl bg-amber-600 px-4 py-3 font-semibold text-white"
            >
              코치 멈춤
            </button>
            <button
              type="button"
              onClick={() => actions.endSession()}
              className="ml-auto rounded-xl bg-rose-600 px-4 py-3 font-semibold text-white"
            >
              세션 종료
            </button>
          </>
        )}
      </footer>
    </div>
  );
}

function CountingControls({
  active,
  disabled,
  onStart,
  onStop,
}: {
  active: boolean;
  disabled: boolean;
  onStart: (opt: ExerciseOption) => void;
  onStop: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 p-3">
      {EXERCISES.map((opt) => (
        <button
          key={opt.name}
          type="button"
          disabled={disabled || active}
          onClick={() => onStart(opt)}
          className="rounded-lg bg-slate-800 px-3 py-2 text-sm font-semibold text-slate-100 disabled:opacity-40"
        >
          {opt.name}
        </button>
      ))}
      <button
        type="button"
        disabled={!active}
        onClick={onStop}
        className="ml-auto rounded-lg bg-slate-700 px-3 py-2 text-sm font-semibold disabled:opacity-40"
      >
        카운팅 정지
      </button>
    </div>
  );
}

function MicControl({
  disabled,
  recording,
  micError,
  micMode,
  onMicModeChange,
  onStart,
  onStop,
}: {
  disabled: boolean;
  recording: boolean;
  micError: string | null;
  micMode: MicMode;
  onMicModeChange: (mode: MicMode) => void;
  onStart: () => void;
  onStop: () => void;
}) {
  const buttonClass = `w-full rounded-xl px-5 py-6 text-lg font-bold text-white disabled:opacity-40 ${
    recording ? "bg-rose-600" : "bg-sky-600"
  }`;

  return (
    <div className="flex flex-col items-center gap-2 p-3">
      <div className="flex gap-1 text-xs" role="group" aria-label="마이크 입력 방식">
        {MIC_MODES.map((m) => (
          <button
            key={m.mode}
            type="button"
            onClick={() => onMicModeChange(m.mode)}
            aria-pressed={micMode === m.mode}
            className={`rounded-lg px-3 py-1.5 font-semibold ${
              micMode === m.mode ? "bg-sky-600 text-white" : "bg-slate-800 text-slate-300"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>
      {micMode === "hold" ? (
        <button
          type="button"
          disabled={disabled}
          onPointerDown={onStart}
          onPointerUp={onStop}
          onPointerLeave={() => {
            if (recording) onStop();
          }}
          className={buttonClass}
        >
          {recording ? "녹음 중… (떼면 전송)" : "길게 눌러 말하기"}
        </button>
      ) : (
        <button
          type="button"
          disabled={disabled}
          onClick={() => (recording ? onStop() : onStart())}
          className={buttonClass}
        >
          {recording ? "탭하면 종료·전송" : "탭하여 말하기 시작"}
        </button>
      )}
      {micError && <p className="text-sm text-rose-400">{micError}</p>}
    </div>
  );
}
