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
import type { ExerciseMode, ServerMessage, SessionMode } from "@/api/types";

export type ChatRole = "user" | "coach" | "system";

export interface ChatEntry {
  id: number;
  role: ChatRole;
  text: string;
  safety?: boolean;
  pending?: boolean;
}

export interface CountingState {
  active: boolean;
  exerciseMode: ExerciseMode | null;
  rep: number;
  phase: "up" | "down" | "tick" | null;
  elapsedSec: number;
}

export interface SessionStore {
  status: SocketStatus;
  mode: SessionMode;
  sessionId: number | null;
  started: boolean;
  messages: ChatEntry[];
  counting: CountingState;
  error: string | null;
  // Bumped each time the coach returns audio; SessionLive plays it then clears.
  lastAudio: { seq: number; data: string; sampleRate: number } | null;
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
};

const initialStore: SessionStore = {
  status: "connecting",
  mode: "c2c",
  sessionId: null,
  started: false,
  messages: [],
  counting: INITIAL_COUNTING,
  error: null,
  lastAudio: null,
  liveListening: false,
  serverState: null,
};

type Action =
  | { kind: "status"; status: SocketStatus }
  | { kind: "set_mode"; mode: SessionMode }
  | { kind: "user_text"; text: string }
  | { kind: "counting_request"; mode: ExerciseMode }
  | { kind: "counting_stopped" }
  | { kind: "audio_consumed"; seq: number }
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

    case "audio":
      return {
        ...store,
        lastAudio: {
          seq: (store.lastAudio?.seq ?? 0) + 1,
          data: msg.data,
          sampleRate: msg.sample_rate,
        },
      };

    case "transcription":
      // Only show finalised transcriptions as user messages.
      if (!msg.final) return store;
      return {
        ...store,
        messages: pushEntry(store.messages, { role: "user", text: msg.text }),
      };

    case "interrupt":
      return store;

    case "beat":
      return {
        ...store,
        counting: {
          active: true,
          exerciseMode: msg.phase === "tick" ? "timer" : "metronome",
          rep: msg.rep,
          phase: msg.phase,
          elapsedSec: msg.elapsed_sec,
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
        messages: pushEntry(store.messages, { role: "system", text: "세션을 종료했어요." }),
      };
  }
}

function reducer(store: SessionStore, action: Action): SessionStore {
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
      return { ...store, counting: INITIAL_COUNTING };
    case "audio_consumed":
      return store.lastAudio?.seq === action.seq ? { ...store, lastAudio: null } : store;
    case "server":
      return handleServer(store, action.msg);
    case "reset":
      return { ...initialStore, status: store.status };
  }
}

export interface SessionActions {
  setMode: (mode: SessionMode) => void;
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
  consumeAudio: (seq: number) => void;
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

  useEffect(() => {
    const socket = socketRef.current;
    socket?.connect(initialMode ?? "c2c");
    return () => socket?.close();
  }, []);

  const modeRef = useRef(store.mode);
  modeRef.current = store.mode;

  const actions = useMemo<SessionActions>(() => {
    const socket = socketRef.current as CoachSocket;
    return {
      setMode: (mode) => dispatch({ kind: "set_mode", mode }),

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

      endSession: () => socket.end(),
      consumeAudio: (seq) => dispatch({ kind: "audio_consumed", seq }),
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
