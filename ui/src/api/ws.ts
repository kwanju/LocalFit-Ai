// WebSocket coach client with auto-reconnect (ADR-009: standard browser API +
// hand-written reconnect). Owns the socket; callers send typed ClientMessages
// and subscribe to typed ServerMessages. No app/session logic lives here.

import type { ClientMessage, ExerciseMode, ServerMessage, SessionMode } from "./types";

export type SocketStatus = "connecting" | "open" | "reconnecting" | "closed";

interface CoachSocketHandlers {
  onMessage: (msg: ServerMessage) => void;
  onStatus: (status: SocketStatus) => void;
}

const RECONNECT_BASE_MS = 500;
const RECONNECT_MAX_MS = 8000;

function resolveUrl(): string {
  const base = import.meta.env.VITE_WS_BASE;
  if (base) return `${base}/ws/coach`;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/coach`;
}

export class CoachSocket {
  private ws: WebSocket | null = null;
  private intentionalClose = false;
  private attempt = 0;
  private reconnectTimer: number | null = null;
  private readonly outbox: ClientMessage[] = [];

  constructor(private readonly handlers: CoachSocketHandlers) {}

  connect(): void {
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

  private open(): void {
    this.handlers.onStatus(this.attempt === 0 ? "connecting" : "reconnecting");
    const ws = new WebSocket(resolveUrl());
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
        // A malformed frame must not kill the socket — log and keep listening.
        console.error("Failed to parse server message", err);
      }
    };

    ws.onclose = () => {
      if (this.ws !== ws) return; // superseded by a newer socket (e.g. StrictMode remount)
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

  // Queues until the socket is open, then flushes in order. Keeps the UI from
  // having to guard every call on connection state during a reconnect.
  send(msg: ClientMessage): void {
    if (this.isOpen) {
      this.rawSend(msg);
    } else {
      this.outbox.push(msg);
    }
  }

  // -- typed convenience senders ------------------------------------------

  start(mode: SessionMode, routineId?: number): void {
    this.send(
      routineId === undefined
        ? { type: "start", mode }
        : { type: "start", mode, routine_id: routineId },
    );
  }

  sendText(text: string): void {
    this.send({ type: "text", text });
  }

  sendAudio(audioB64: string, sampleRate: number): void {
    this.send({ type: "audio", audio_b64: audioB64, sample_rate: sampleRate });
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

  startCounting(mode: ExerciseMode, targetDurationSec?: number): void {
    this.send(
      targetDurationSec === undefined
        ? { type: "start_counting", mode }
        : { type: "start_counting", mode, target_duration_sec: targetDurationSec },
    );
  }

  stopCounting(): void {
    this.send({ type: "stop_counting" });
  }

  end(): void {
    this.send({ type: "end" });
  }
}
