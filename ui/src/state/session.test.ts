// session reducer 단위 테스트 (Vitest).
// 세션 생명주기 상태 전이를 박제 — 특히 세션 종료 시 started/counting 리셋
// (2026-06-08: 종료가 안 풀리던 버그의 UI 상태 측면).

import { describe, expect, it } from "vitest";
import { initialStore, reducer } from "./session";

describe("session reducer — lifecycle", () => {
  it("session_started marks the session started", () => {
    const s = reducer(initialStore, {
      kind: "server",
      msg: { type: "session_started", session_id: 7, mode: "c2c" },
    });
    expect(s.started).toBe(true);
    expect(s.sessionId).toBe(7);
  });

  it("session_ended resets started and clears counting", () => {
    const started = reducer(initialStore, {
      kind: "server",
      msg: { type: "session_started", session_id: 7, mode: "c2c" },
    });
    const counting = {
      ...started,
      counting: { ...started.counting, active: true, rep: 5, setNumber: 1, totalSets: 3 },
    };

    const ended = reducer(counting, { kind: "server", msg: { type: "session_ended" } });

    expect(ended.started).toBe(false);
    expect(ended.counting.active).toBe(false);
    expect(ended.counting.rep).toBe(0);
  });

  it("queues an arbitrary number of rapid audio chunks without dropping", () => {
    // 카운트 숫자 누락의 근본: 빠르게 도착한 audio가 단일 슬롯을 덮어써 사라지던 문제.
    // 실제 세션은 청크가 수십~수백 개(10회 N세트 × 카운트/격려/휴식). 개수 무관하게
    // 전부 보존돼야 하므로 반복문으로 N개 검증.
    const N = 50;
    let s = initialStore;
    for (let i = 0; i < N; i += 1) {
      s = reducer(s, {
        kind: "server",
        msg: { type: "audio", data: `chunk-${i}`, sample_rate: 24000 },
      });
    }

    expect(s.audioQueue).toHaveLength(N);
    expect(s.audioQueue.map((c) => c.data)).toEqual(
      Array.from({ length: N }, (_, i) => `chunk-${i}`),
    );
    // seq는 1..N 으로 단조 증가 (중복/누락 없음).
    expect(s.audioQueue.map((c) => c.seq)).toEqual(
      Array.from({ length: N }, (_, i) => i + 1),
    );
  });

  it("drain_audio removes played chunks but keeps ones that arrived after", () => {
    let s = reducer(initialStore, {
      kind: "server",
      msg: { type: "audio", data: "AAA", sample_rate: 24000 },
    });
    s = reducer(s, { kind: "server", msg: { type: "audio", data: "BBB", sample_rate: 24000 } });
    // 재생에 넘긴 건 seq<=2. 그 사이 도착한 새 청크는 보존돼야.
    s = reducer(s, { kind: "server", msg: { type: "audio", data: "CCC", sample_rate: 24000 } });
    s = reducer(s, { kind: "drain_audio", upToSeq: 2 });

    expect(s.audioQueue.map((c) => c.data)).toEqual(["CCC"]);
  });

  it("counting_stopped clears the counting state", () => {
    const counting = {
      ...initialStore,
      counting: { ...initialStore.counting, active: true, rep: 3 },
    };
    const stopped = reducer(counting, { kind: "counting_stopped" });
    expect(stopped.counting.active).toBe(false);
    expect(stopped.counting.rep).toBe(0);
  });
});
