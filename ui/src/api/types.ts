// Protocol types mirrored from the FastAPI backend. Keep in sync with
// app/core/orchestrator.py, app/core/state_machine.py, app/api/ws_coach.py.

export type SessionMode = "s2s" | "c2s" | "c2c" | "s2c";
export type ExerciseMode = "metronome" | "timer";

export type IntentType =
  | "body_state"
  | "schedule"
  | "feedback"
  | "goal"
  | "injury"
  | "general";

export type DangerLevel = "low" | "moderate" | "high" | "emergency";

export type SessionState =
  | "idle"
  | "condition_check"
  | "warmup"
  | "exercising"
  | "rest"
  | "cooldown"
  | "completed"
  | "paused"
  | "aborted"
  | "injury_alert"
  | "safety_check"
  | "emergency_stopped"
  | "recovered";

export type FitnessLevel = "beginner" | "intermediate" | "advanced";

// -- WebSocket: client → server ------------------------------------------

export type ClientMessage =
  | { type: "start"; mode: SessionMode; routine_id?: number }
  | { type: "text"; text: string }
  | { type: "audio"; audio_b64: string; sample_rate: number }
  | { type: "interrupt" }
  | { type: "pause" }
  | { type: "resume" }
  | { type: "start_counting"; mode: ExerciseMode; target_duration_sec?: number }
  | { type: "stop_counting" }
  | { type: "end" };

// -- WebSocket: server → client ------------------------------------------

export interface SessionStartedMessage {
  type: "session_started";
  session_id: number;
  mode: SessionMode;
  state: SessionState;
}

export interface ResponseMessage {
  type: "response";
  user_text: string;
  response_text: string;
  state: SessionState;
  intent: IntentType | null;
  safety_triggered: boolean;
  safety_level: DangerLevel | null;
  audio_b64: string | null;
}

export interface BeatMessage {
  type: "beat";
  rep: number;
  phase: "up" | "down" | "tick";
  elapsed_sec: number;
}

export interface StateMessage {
  type: "state";
  state: SessionState;
}

export interface ErrorMessage {
  type: "error";
  message: string;
}

export interface SessionEndedMessage {
  type: "session_ended";
  state: SessionState | null;
}

export type ServerMessage =
  | SessionStartedMessage
  | ResponseMessage
  | BeatMessage
  | StateMessage
  | ErrorMessage
  | SessionEndedMessage;

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
