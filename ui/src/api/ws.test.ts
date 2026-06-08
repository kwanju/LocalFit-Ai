// CoachSocket 생명주기 단위 테스트 (Vitest).
// 2026-06-08: 세션 종료가 WS를 안 닫아 백엔드 정리/`session_ended`가 안 오던 버그를
// 박제. 이 계층(WS 생명주기)은 Python 테스트로 못 잡혀 사용자가 매번 먼저 발견하던 곳.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CoachSocket, type SocketStatus } from "./ws";

class MockWS {
  static instances: MockWS[] = [];
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  url: string;
  readyState = MockWS.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  closeCalled = 0;

  constructor(url: string) {
    this.url = url;
    MockWS.instances.push(this);
  }
  send(data: string): void {
    this.sent.push(data);
  }
  close(): void {
    this.closeCalled += 1;
    this.readyState = MockWS.CLOSED;
  }
  // -- test helpers --
  fireOpen(): void {
    this.readyState = MockWS.OPEN;
    this.onopen?.();
  }
  fireClose(): void {
    this.readyState = MockWS.CLOSED;
    this.onclose?.();
  }
}

function makeSocket() {
  const statuses: SocketStatus[] = [];
  const messages: unknown[] = [];
  const sock = new CoachSocket({
    onMessage: (m) => messages.push(m),
    onStatus: (s) => statuses.push(s),
  });
  return { sock, statuses, messages };
}

beforeEach(() => {
  MockWS.instances = [];
  vi.stubGlobal("WebSocket", MockWS as unknown as typeof WebSocket);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("CoachSocket.end()", () => {
  it("closes the socket, reports closed, and does not auto-reconnect", () => {
    const { sock, statuses } = makeSocket();
    sock.connect("c2c");
    const ws = MockWS.instances.at(-1)!;
    ws.fireOpen();
    expect(sock.isOpen).toBe(true);

    sock.end();

    // The fix: end() must actually close the underlying socket so the backend
    // on_client_disconnected cleanup runs.
    expect(ws.closeCalled).toBe(1);
    expect(statuses.at(-1)).toBe("closed");
    // Best-effort {type:"end"} is sent before closing.
    expect(ws.sent.map((s) => JSON.parse(s).type)).toContain("end");

    // A late onclose must NOT spin up a reconnect (intentionalClose).
    ws.fireClose();
    vi.runAllTimers();
    expect(MockWS.instances.length).toBe(1);
  });

  it("allows reconnect via start() after end()", () => {
    const { sock } = makeSocket();
    sock.connect("c2c");
    MockWS.instances.at(-1)!.fireOpen();
    sock.end();

    sock.start("c2c");
    expect(MockWS.instances.length).toBe(2); // a fresh socket was opened
  });
});

describe("CoachSocket.isActive (탭 이동 중 중복 연결 방지)", () => {
  it("tracks socket existence across the lifecycle", () => {
    const { sock } = makeSocket();
    expect(sock.isActive).toBe(false); // 연결 전

    sock.connect("c2c");
    expect(sock.isActive).toBe(true); // connecting 중에도 active (중복 connect 차단)

    MockWS.instances.at(-1)!.fireOpen();
    expect(sock.isActive).toBe(true);

    sock.end();
    expect(sock.isActive).toBe(false); // 종료 후 재연결 허용
  });
});

describe("CoachSocket outbox", () => {
  it("queues messages sent before open and flushes them on open", () => {
    const { sock } = makeSocket();
    sock.connect("c2c");
    const ws = MockWS.instances.at(-1)!;

    sock.sendText("안녕"); // not open yet → queued
    expect(ws.sent.length).toBe(0);

    ws.fireOpen();
    expect(ws.sent.length).toBe(1);
    expect(JSON.parse(ws.sent[0]!)).toEqual({ type: "text", text: "안녕" });
  });
});
