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

  it("does NOT flip to 'down' on a single transient failure (debounce)", async () => {
    mockGetHealth.mockResolvedValueOnce(OK_HEALTH);
    const { result } = renderHook(() => useBackendHealth());
    await flush();
    expect(result.current.status).toBe("up");

    // 단발 실패(모델 로드 중 이벤트루프 정체로 1회 타임아웃 등)는 'up' 유지.
    mockGetHealth.mockRejectedValueOnce(new Error("blip"));
    await flush(5000);
    expect(result.current.status).toBe("up");
  });

  it("flips to 'down' only after FAILS_TO_DOWN consecutive failures", async () => {
    mockGetHealth.mockResolvedValueOnce(OK_HEALTH);
    const { result } = renderHook(() => useBackendHealth());
    await flush();
    expect(result.current.status).toBe("up");

    // 사이드카 강제 종료 → 연속 실패가 쌓여야 'down' (3회).
    mockGetHealth.mockRejectedValue(new Error("died"));
    await flush(5000); // 1회 실패
    expect(result.current.status).toBe("up");
    await flush(5000); // 2회
    expect(result.current.status).toBe("up");
    await flush(5000); // 3회 → down
    expect(result.current.status).toBe("down");

    // 복구되면 즉시 'up' + streak 리셋.
    mockGetHealth.mockResolvedValue(OK_HEALTH);
    await flush(5000);
    expect(result.current.status).toBe("up");
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
