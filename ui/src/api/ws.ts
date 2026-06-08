// WebSocket client for the Pipecat /ws/voice endpoint (phase-7).
// Protocol: JSON text frames via JsonFrameSerializer (no protobuf).
// Mode is passed as a URL query param (?mode=C2C) so it is fixed per connection.
// Mode changes cause a disconnect + reconnect with the new mode URL.

import type { ClientMessage, ExerciseMode, ServerMessage, SessionMode } from "./types";

export type SocketStatus = "connecting" | "open" | "reconnecting" | "closed";

interface CoachSocketHandlers {
  onMessage: (msg: ServerMessage) => void;
  onStatus: (status: SocketStatus) => void;
}

const RECONNECT_BASE_MS = 500;
const RECONNECT_MAX_MS = 8000;

function resolveUrl(mode: SessionMode): string {
  const base = import.meta.env.VITE_WS_BASE;
  const modeParam = `mode=${mode.toUpperCase()}`;
  if (base) return `${base}/ws/voice?${modeParam}`;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/voice?${modeParam}`;
}

export class CoachSocket {
  private ws: WebSocket | null = null;
  private intentionalClose = false;
  private attempt = 0;
  private reconnectTimer: number | null = null;
  private _mode: SessionMode = "c2c";
  private readonly outbox: ClientMessage[] = [];

  constructor(private readonly handlers: CoachSocketHandlers) {}

  connect(mode?: SessionMode): void {
    if (mode) this._mode = mode;
    this.intentionalClose = false;
    this.open();
  }

  close(): void {
    this.intentionalClose = true;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.outbox.length = 0;
    this.ws?.close();
    this.ws = null;
    this.handlers.onStatus("closed");
  }

  get isOpen(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  /** True while a socket exists (connecting OR open) — guards against duplicate connects. */
  get isActive(): boolean {
    return this.ws !== null;
  }

  private open(): void {
    this.handlers.onStatus(this.attempt === 0 ? "connecting" : "reconnecting");
    const ws = new WebSocket(resolveUrl(this._mode));
    this.ws = ws;

    ws.onopen = () => {
      this.attempt = 0;
      this.handlers.onStatus("open");
      const pending = this.outbox.splice(0);
      for (const msg of pending) this.rawSend(msg);
    };

    ws.onmessage = (event: MessageEvent<string>) => {
      try {
        this.handlers.onMessage(JSON.parse(event.data) as ServerMessage);
      } catch (err) {
        console.error("Failed to parse server message", err);
      }
    };

    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.ws = null;
      if (this.intentionalClose) return;
      this.scheduleReconnect();
    };

    ws.onerror = () => {
      ws.close();
    };
  }

  private scheduleReconnect(): void {
    this.handlers.onStatus("reconnecting");
    const delay = Math.min(RECONNECT_BASE_MS * 2 ** this.attempt, RECONNECT_MAX_MS);
    this.attempt += 1;
    this.reconnectTimer = window.setTimeout(() => this.open(), delay);
  }

  private rawSend(msg: ClientMessage): void {
    this.ws?.send(JSON.stringify(msg));
  }

  send(msg: ClientMessage): void {
    if (this.isOpen) {
      this.rawSend(msg);
    } else {
      this.outbox.push(msg);
    }
  }

  // -- typed convenience senders ------------------------------------------

  /** Connect (or reconnect) with a given mode. Closes existing connection first. */
  start(mode: SessionMode): void {
    if (this._mode === mode && this.isOpen) return;
    this._mode = mode;
    // Close intentionally then reopen — intentionalClose prevents auto-reconnect
    // but open() resets it.
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
    this.attempt = 0;
    this.open();
  }

  sendText(text: string): void {
    this.send({ type: "text", text });
  }

  sendAudio(audioB64: string, sampleRate: number): void {
    // Full recorded audio (C2S hold/toggle mic modes) — PCM16LE base64.
    this.send({ type: "audio", data: audioB64, sample_rate: sampleRate });
  }

  // -- live S2S (streaming VAD) -------------------------------------------

  listenStart(): void {
    // No-op: in Pipecat, audio streaming starts automatically in S2S/S2C modes.
    // Kept for backward-compat with session.tsx action calls.
  }

  sendAudioChunk(pcmB64: string, sampleRate: number): void {
    // Realtime audio: drop if not open (flood prevention).
    if (!this.isOpen) return;
    this.rawSend({ type: "audio", data: pcmB64, sample_rate: sampleRate });
  }

  listenStop(): void {
    // No-op: backend VAD handles speech detection.
  }

  interrupt(): void {
    this.send({ type: "interrupt" });
  }

  pause(): void {
    this.send({ type: "pause" });
  }

  resume(): void {
    this.send({ type: "resume" });
  }

  startCounting(exercise: string, reps: number, mode: ExerciseMode = "metronome", targetDurationSec?: number): void {
    this.send(
      targetDurationSec === undefined
        ? { type: "start_counting", exercise, reps, mode }
        : { type: "start_counting", exercise, reps, mode, target_duration_sec: targetDurationSec },
    );
  }

  stopCounting(): void {
    this.send({ type: "stop_counting" });
  }

  end(): void {
    // Mark intentional so onclose doesn't trigger auto-reconnect.
    this.intentionalClose = true;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    // Best-effort notify, then CLOSE the socket. Closing is what triggers the
    // backend `on_client_disconnected` cleanup (stop counting, end DB session,
    // send session_ended). Without the close the pipeline lingered and the UI
    // never reset `started` → "세션 종료가 안 됨" (2026-06-08 fix).
    if (this.isOpen) this.rawSend({ type: "end" });
    this.ws?.close();
    this.ws = null;
    this.outbox.length = 0;
    this.handlers.onStatus("closed");
  }
}
