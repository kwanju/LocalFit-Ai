// useBackendHealth 상태 머신 단위 테스트 (Vitest).
// phase v4-6 6-3: 사이드카(Python+모델) 사망 감지. 콜드스타트(≈30s)엔 'down'을
// 띄우면 안 되고(starting), 한 번이라도 떠 있다가 죽으면 'down'으로 넘어가야 한다.
// 이 경계 로직은 사람 E2E 없이 여기서 회귀 방어한다 (testing-strategy.md).

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getHealth } from "@/api/client";
import { useBackendHealth } from "./useBackendHealth";

vi.mock("@/api/client", () => ({ getHealth: vi.fn() }));
const mockGetHealth = vi.mocked(getHealth);

const OK_HEALTH = {
  status: "ok" as const,
  backend: true,
  adapters: { llm: true, stt: true, tts: true },
};

// fake timers 하에서 mock된 promise(microtask)를 함께 흘려보낸다.
async function flush(ms = 0): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  mockGetHealth.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useBackendHealth", () => {
  it("stays 'starting' while the sidecar is not yet reachable (cold start)", async () => {
    mockGetHealth.mockRejectedValue(new Error("not up yet"));
    const { result } = renderHook(() => useBackendHealth());
    await flush();
    // 한 번도 뜬 적 없으므로 'down'이 아니라 'starting' — 콜바신 배너를 안 띄운다.
    expect(result.current.status).toBe("starting");
  });

  it("reports 'up' once /health responds", async () => {
    mockGetHealth.mockResolvedValue(OK_HEALTH);
    const { result } = renderHook(() => useBackendHealth());
    await flush();
    expect(result.current.status).toBe("up");
  });

  it("flips to 'down' when the sidecar dies after being reachable", async () => {
    mockGetHealth.mockResolvedValueOnce(OK_HEALTH);
    const { result } = renderHook(() => useBackendHealth());
    await flush();
    expect(result.current.status).toBe("up");

    // 이후 폴링이 실패하면(사이드카 강제 종료) 'down'으로.
    mockGetHealth.mockRejectedValue(new Error("died"));
    await flush(5000);
    expect(result.current.status).toBe("down");
  });

  it("polls /health on an interval", async () => {
    mockGetHealth.mockResolvedValue(OK_HEALTH);
    renderHook(() => useBackendHealth());
    await flush();
    expect(mockGetHealth).toHaveBeenCalledTimes(1); // 즉시 1회
    await flush(5000);
    expect(mockGetHealth).toHaveBeenCalledTimes(2);
    await flush(5000);
    expect(mockGetHealth).toHaveBeenCalledTimes(3);
  });
});
