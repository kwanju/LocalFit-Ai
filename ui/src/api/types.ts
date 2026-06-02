// Protocol types for the Pipecat JSON frame WebSocket transport (phase-7).
// Replaces v1 ws_coach.py custom protocol with JsonFrameSerializer messages.

export type SessionMode = "s2s" | "c2s" | "c2c" | "s2c";
export type ExerciseMode = "metronome" | "timer";

export type DangerLevel = "low" | "moderate" | "high" | "emergency";

export type FitnessLevel = "beginner" | "intermediate" | "advanced";

// -- WebSocket: client → server ------------------------------------------
// Sent as JSON text frames.

export type ClientMessage =
  | { type: "text"; text: string }
  // PCM16LE audio chunk (streaming S2S/S2C) — base64 encoded
  | { type: "audio"; data: string; sample_rate: number }
  | { type: "interrupt" }
  // Control messages — routed to UIControlProcessor via InputTransportMessageFrame
  | { type: "start_counting"; exercise: string; reps: number; mode?: ExerciseMode; target_duration_sec?: number }
  | { type: "stop_counting" }
  | { type: "pause" }
  | { type: "resume" }
  | { type: "end" };

// -- WebSocket: server → client ------------------------------------------
// All messages are JSON text frames from JsonFrameSerializer.

export interface SessionStartedMessage {
  type: "session_started";
  session_id: number;
  mode: SessionMode;
}

// Coach text response (TextFrame / SafetyResponseFrame)
export interface TextMessage {
  type: "text";
  text: string;
  safety?: boolean;
  safety_level?: DangerLevel | null;
}

// TTS audio (OutputAudioRawFrame) — PCM16LE base64
export interface AudioMessage {
  type: "audio";
  data: string;
  sample_rate: number;
}

// User speech transcription (TranscriptionFrame)
export interface TranscriptionMessage {
  type: "transcription";
  text: string;
  final: boolean;
}

// Interruption (InterruptionFrame)
export interface InterruptMessage {
  type: "interrupt";
}

// Counting beat (OutputTransportMessageFrame from CountingInjectProcessor)
export interface BeatMessage {
  type: "beat";
  rep: number;
  phase: "up" | "down" | "tick";
  elapsed_sec: number;
}

// VAD state (OutputTransportMessageFrame from ws_voice)
export interface VadMessage {
  type: "vad";
  event: "listening" | "speech_start" | "speech_end";
}

export interface SessionEndedMessage {
  type: "session_ended";
}

export interface ErrorMessage {
  type: "error";
  message: string;
}

export type ServerMessage =
  | SessionStartedMessage
  | TextMessage
  | AudioMessage
  | TranscriptionMessage
  | InterruptMessage
  | BeatMessage
  | VadMessage
  | SessionEndedMessage
  | ErrorMessage;

// -- REST -----------------------------------------------------------------

export interface HealthResponse {
  status: "ok" | "degraded";
  backend: boolean;
  adapters: Record<"llm" | "stt" | "tts", boolean>;
}

export interface UserProfile {
  id: number;
  name: string;
  fitness_level: FitnessLevel;
  goal: string | null;
  age: number | null;
  weight_kg: number | null;
  height_cm: number | null;
}

export interface OnboardingStatus {
  onboarded: boolean;
  profile: UserProfile | null;
}

export interface AssessmentInput {
  pullup_max?: number;
  pushup_max?: number;
  squat_max?: number;
  plank_max_sec?: number;
}

export interface OnboardingRequest {
  name: string;
  age?: number;
  weight_kg?: number;
  height_cm?: number;
  fitness_level: FitnessLevel;
  available_times?: string[];
  goal?: string;
  assessment?: AssessmentInput;
}

export interface Routine {
  id: number;
  name: string;
  description: string | null;
}
