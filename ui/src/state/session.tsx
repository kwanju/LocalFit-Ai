// Session store: a Context + useReducer that owns the CoachSocket and
// translates the Pipecat JSON frame protocol into UI state (phase-7).
// Components read state via useSession() and act via the returned actions.

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  type ReactNode,
} from "react";
import { CoachSocket, type SocketStatus } from "@/api/ws";
import type { BeatMetaMessage, ExerciseMode, ServerMessage, SessionMode } from "@/api/types";

export type ChatRole = "user" | "coach" | "system";

export interface ChatEntry {
  id: number;
  role: ChatRole;
  text: string;
  safety?: boolean;
  pending?: boolean;
}

export interface AudioChunk {
  seq: number;
  data: string;
  sampleRate: number;
  beatMeta?: BeatMetaMessage;
}

export interface CountingState {
  active: boolean;
  exerciseMode: ExerciseMode | null;
  rep: number;
  phase: "up" | "down" | "tick" | null;
  elapsedSec: number;
  // Multi-set 진행 상태 (2026-06-07).
  setNumber: number;     // 진행 중 또는 휴식 후 시작할 세트 번호 (1-indexed). 0이면 비활성.
  totalSets: number;
  // 휴식 카운트다운. null이면 휴식 아님.
  restRemainingSec: number | null;
}

export interface SessionStore {
  status: SocketStatus;
  mode: SessionMode;
  sessionId: number | null;
  started: boolean;
  messages: ChatEntry[];
  counting: CountingState;
  error: string | null;
  // FIFO queue of coach audio chunks awaiting playback. Was a single slot
  // (`lastAudio`) which silently dropped chunks when several `audio` messages
  // arrived in the same React batch — count numbers went missing (2026-06-08).
  // SessionLive drains the whole queue into the gapless WebAudio scheduler.
  // `beatMeta` carries the matched count/encouragement metadata so playPcm.onStart
  // can update the counter at the actual audio playback start time (sync 보장).
  audioQueue: AudioChunk[];
  // 2026-06-07: beat_meta 메시지는 항상 audio 보다 먼저 도착. 도착 순서대로 큐에 쌓고
  // audio msg 가 도착하면 FIFO로 짝지어서 lastAudio.beatMeta 에 실어 보낸다.
  pendingBeatMeta: BeatMetaMessage[];
  // Live S2S: true while the mic is actively listening (false once an utterance
  // ends and we're transcribing/responding).
  liveListening: boolean;
  // Legacy field for backward compat with SessionLive header display.
  serverState: string | null;
}

const INITIAL_COUNTING: CountingState = {
  active: false,
  exerciseMode: null,
  rep: 0,
  phase: null,
  elapsedSec: 0,
  setNumber: 0,
  totalSets: 0,
  restRemainingSec: null,
};

const initialStore: SessionStore = {
  status: "connecting",
  mode: "c2c",
  sessionId: null,
  started: false,
  messages: [],
  counting: INITIAL_COUNTING,
  error: null,
  audioQueue: [],
  pendingBeatMeta: [],
  liveListening: false,
  serverState: null,
};

type Action =
  | { kind: "status"; status: SocketStatus }
  | { kind: "set_mode"; mode: SessionMode }
  | { kind: "user_text"; text: string }
  | { kind: "counting_request"; mode: ExerciseMode }
  | { kind: "counting_stopped" }
  | { kind: "drain_audio"; upToSeq: number }
  // playPcm.onStart 가 audio 재생 시작 시점에 dispatch — 카운터·세트 표시 업데이트
  | { kind: "apply_beat_meta"; meta: BeatMetaMessage }
  | { kind: "server"; msg: ServerMessage }
  | { kind: "reset" };

let chatSeq = 0;
function nextId(): number {
  chatSeq += 1;
  return chatSeq;
}

function pushEntry(messages: ChatEntry[], entry: Omit<ChatEntry, "id">): ChatEntry[] {
  return [...messages, { id: nextId(), ...entry }];
}

function handleServer(store: SessionStore, msg: ServerMessage): SessionStore {
  switch (msg.type) {
    case "session_started":
      return {
        ...store,
        started: true,
        sessionId: msg.session_id,
        mode: msg.mode,
        error: null,
        serverState: "active",
        messages: pushEntry(store.messages, { role: "system", text: "세션을 시작했어요." }),
      };

    case "text": {
      const baseMessages = store.messages.some((m) => m.role === "user" && m.pending)
        ? store.messages.map((m) => (m.role === "user" && m.pending ? { ...m, pending: false } : m))
        : store.messages;
      return {
        ...store,
        messages: pushEntry(baseMessages, {
          role: "coach",
          text: msg.text,
          safety: msg.safety ?? false,
        }),
      };
    }

    case "audio": {
      // 가장 오래된 pending meta 와 짝지어 큐에 append (덮어쓰지 않음 → 드롭 방지).
      const [meta, ...restMeta] = store.pendingBeatMeta;
      const lastSeq = store.audioQueue.at(-1)?.seq ?? 0;
      return {
        ...store,
        audioQueue: [
          ...store.audioQueue,
          { seq: lastSeq + 1, data: msg.data, sampleRate: msg.sample_rate, beatMeta: meta },
        ],
        pendingBeatMeta: meta ? restMeta : store.pendingBeatMeta,
      };
    }

    case "transcription":
      // Only show finalised transcriptions as user messages.
      if (!msg.final) return store;
      return {
        ...store,
        messages: pushEntry(store.messages, { role: "user", text: msg.text }),
      };

    case "interrupt":
      // 인터럽트 시 재생 중단 → 대기 audio·meta 모두 폐기 (stale 방지).
      return { ...store, pendingBeatMeta: [], audioQueue: [] };

    case "beat_meta":
      // audio 와 짝지을 수 있도록 큐에 저장만 한다. 카운터 업데이트는 audio 가 실제로
      // 재생 시작될 때 (apply_beat_meta) 일어남.
      return {
        ...store,
        pendingBeatMeta: [...store.pendingBeatMeta, msg],
      };

    case "rest":
      // remaining_sec === 0 → 휴식 종료(곧 새 세트). 그 외에는 카운트다운 표시.
      return {
        ...store,
        counting: {
          ...store.counting,
          active: true,
          restRemainingSec: msg.remaining_sec > 0 ? msg.remaining_sec : null,
          setNumber: msg.set_done + 1,    // 곧 시작할 세트 번호
          totalSets: msg.total_sets,
          // 카운터 리셋: 새 세트가 곧 시작될 거니까 rep 0 으로.
          rep: msg.remaining_sec > 0 ? 0 : store.counting.rep,
        },
      };

    case "vad":
      return { ...store, liveListening: msg.event !== "speech_end" };

    case "error":
      return {
        ...store,
        error: msg.message,
        messages: pushEntry(store.messages, { role: "system", text: msg.message }),
      };

    case "session_ended":
      return {
        ...store,
        started: false,
        serverState: null,
        counting: INITIAL_COUNTING,
        pendingBeatMeta: [],
        audioQueue: [],
        messages: pushEntry(store.messages, { role: "system", text: "세션을 종료했어요." }),
      };
  }
}

function applyBeatMeta(store: SessionStore, meta: BeatMetaMessage): SessionStore {
  // count: rep 카운터 + 세트 표시 업데이트
  // encouragement / tick: 격려나 timer 진행 — 카운터 자체는 안 만짐 (격려는 한 박자
  // 차지하지만 rep 증가가 아니므로 그대로). timer 는 phase=="tick" 이라 elapsed 만.
  if (meta.kind === "count") {
    return {
      ...store,
      counting: {
        ...store.counting,
        active: true,
        exerciseMode: "metronome",
        rep: meta.rep,
        phase: meta.phase,
        elapsedSec: meta.elapsed_sec,
        setNumber: meta.set_number,
        totalSets: meta.total_sets,
        restRemainingSec: null,
      },
    };
  }
  if (meta.kind === "tick") {
    return {
      ...store,
      counting: {
        ...store.counting,
        active: true,
        exerciseMode: "timer",
        phase: "tick",
        elapsedSec: meta.elapsed_sec,
        setNumber: meta.set_number,
        totalSets: meta.total_sets,
        restRemainingSec: null,
      },
    };
  }
  // encouragement: 표시 변화 없음 — 단지 메시지 카드를 채팅에 보태도 됨 (옵션).
  return store;
}

// Exported for unit tests (Vitest) — pure reducer + initial store.
export { initialStore };
export function reducer(store: SessionStore, action: Action): SessionStore {
  switch (action.kind) {
    case "status":
      return { ...store, status: action.status };
    case "set_mode":
      return store.started ? store : { ...store, mode: action.mode };
    case "user_text":
      return {
        ...store,
        messages: pushEntry(store.messages, { role: "user", text: action.text, pending: true }),
      };
    case "counting_request":
      return { ...store, counting: { ...INITIAL_COUNTING, active: true, exerciseMode: action.mode } };
    case "counting_stopped":
      return { ...store, counting: INITIAL_COUNTING, pendingBeatMeta: [], audioQueue: [] };
    case "drain_audio":
      // 재생에 넘긴 청크만 제거 — 그 사이 도착한 새 청크(더 큰 seq)는 보존.
      return { ...store, audioQueue: store.audioQueue.filter((c) => c.seq > action.upToSeq) };
    case "apply_beat_meta":
      return applyBeatMeta(store, action.meta);
    case "server":
      return handleServer(store, action.msg);
    case "reset":
      return { ...initialStore, status: store.status };
  }
}

export interface SessionActions {
  setMode: (mode: SessionMode) => void;
  ensureConnected: () => void;
  startSession: (routineId?: number) => void;
  switchMode: (mode: SessionMode) => void;
  sendText: (text: string) => void;
  sendAudio: (audioB64: string, sampleRate: number) => void;
  listenStart: () => void;
  sendAudioChunk: (pcmB64: string, sampleRate: number) => void;
  listenStop: () => void;
  interrupt: () => void;
  pause: () => void;
  resume: () => void;
  startCounting: (exercise: string, reps: number, mode?: ExerciseMode, targetDurationSec?: number) => void;
  stopCounting: () => void;
  endSession: () => void;
  drainAudio: (upToSeq: number) => void;
  // playPcm.onStart 가 audio 재생 시작 시점에 호출 — 카운터·세트 표시 업데이트.
  applyBeatMeta: (meta: BeatMetaMessage) => void;
}

interface SessionContextValue extends SessionStore {
  actions: SessionActions;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({
  children,
  initialMode,
}: {
  children: ReactNode;
  initialMode?: SessionMode;
}) {
  const [store, dispatch] = useReducer(
    reducer,
    initialMode ? { ...initialStore, mode: initialMode } : initialStore,
  );
  const socketRef = useRef<CoachSocket | null>(null);

  if (socketRef.current === null) {
    socketRef.current = new CoachSocket({
      onMessage: (msg) => dispatch({ kind: "server", msg }),
      onStatus: (status) => dispatch({ kind: "status", status }),
    });
  }

  // The provider now lives at the app shell level (App.tsx) so it survives
  // tab navigation (운동↔기록↔설정) — leaving the workout screen must NOT end the
  // session (2026-06-08). Connection is therefore lazy: the SessionLive screen
  // calls ensureConnected() on mount. We only close on provider unmount (i.e.
  // leaving the shell entirely / app teardown).
  useEffect(() => {
    const socket = socketRef.current;
    return () => socket?.close();
  }, []);

  const modeRef = useRef(store.mode);
  modeRef.current = store.mode;

  const actions = useMemo<SessionActions>(() => {
    const socket = socketRef.current as CoachSocket;
    return {
      setMode: (mode) => dispatch({ kind: "set_mode", mode }),

      // Connect once when entering the workout screen; idempotent across tab
      // re-entry (no duplicate socket, no re-fired opener) since the provider
      // persists. After 세션 종료 (socket closed) this reconnects (2026-06-08).
      ensureConnected: () => {
        if (!socket.isActive) socket.connect(modeRef.current);
      },

      startSession: () => {
        // Phase-7: session begins when we connect.  Re-connect if not open.
        socket.start(modeRef.current);
      },

      switchMode: (mode) => {
        socket.end();
        dispatch({ kind: "set_mode", mode });
        modeRef.current = mode;
        socket.start(mode);
      },

      sendText: (text) => {
        dispatch({ kind: "user_text", text });
        socket.sendText(text);
      },

      sendAudio: (audioB64, sampleRate) => socket.sendAudio(audioB64, sampleRate),
      listenStart: () => socket.listenStart(),
      sendAudioChunk: (pcmB64, sampleRate) => socket.sendAudioChunk(pcmB64, sampleRate),
      listenStop: () => socket.listenStop(),
      interrupt: () => socket.interrupt(),
      pause: () => socket.pause(),
      resume: () => socket.resume(),

      startCounting: (exercise, reps, mode = "metronome", targetDurationSec) => {
        dispatch({ kind: "counting_request", mode });
        socket.startCounting(exercise, reps, mode, targetDurationSec);
      },

      stopCounting: () => {
        socket.stopCounting();
        dispatch({ kind: "counting_stopped" });
      },

      endSession: () => {
        socket.end();
        // Optimistic reset — don't depend on a session_ended round-trip that may
        // not arrive once the socket is closing (2026-06-08 fix).
        dispatch({ kind: "server", msg: { type: "session_ended" } });
      },
      drainAudio: (upToSeq) => dispatch({ kind: "drain_audio", upToSeq }),
      applyBeatMeta: (meta) => dispatch({ kind: "apply_beat_meta", meta }),
    };
  }, []);

  const value = useMemo<SessionContextValue>(() => ({ ...store, actions }), [store, actions]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (ctx === null) {
    throw new Error("useSession must be used within a SessionProvider");
  }
  return ctx;
}
