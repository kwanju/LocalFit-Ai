// CalendarSection 테스트 (ADR-022 / phase v4-9b): 상태별 UI + 등록 확답 게이트.
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("@/api/client", () => ({
  getGcalStatus: vi.fn(),
  gcalConnect: vi.fn(),
  gcalDisconnect: vi.fn(),
  previewPlanEvents: vi.fn(),
  registerPlanEvents: vi.fn(),
}));

import {
  gcalConnect,
  getGcalStatus,
  previewPlanEvents,
  registerPlanEvents,
} from "@/api/client";
import { CalendarSection } from "./Settings";

const m = {
  status: vi.mocked(getGcalStatus),
  connect: vi.mocked(gcalConnect),
  preview: vi.mocked(previewPlanEvents),
  register: vi.mocked(registerPlanEvents),
};

afterEach(() => vi.clearAllMocks());

describe("CalendarSection", () => {
  it("미연동이면 '연동하기' 버튼을 노출하고, 클릭 시 connect→connected 반영", async () => {
    m.status.mockResolvedValue({ enabled: true, connected: false });
    m.connect.mockResolvedValue({ enabled: true, connected: true });
    render(<CalendarSection />);

    const btn = await screen.findByRole("button", { name: /연동하기/ });
    fireEvent.click(btn);

    expect(m.connect).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.getByText(/연동됨/)).toBeInTheDocument());
  });

  it("연동됨: 등록은 미리보기→확인 2단계(확답 게이트)", async () => {
    m.status.mockResolvedValue({ enabled: true, connected: true });
    m.preview.mockResolvedValue([
      { exercise: "푸시업", start: "2026-06-18T18:00:00", end: "2026-06-18T18:30:00", summary: "운동" },
    ]);
    m.register.mockResolvedValue({ created: 1, skipped: 0, events: [] });
    render(<CalendarSection />);

    fireEvent.click(await screen.findByText(/이번 주 운동 캘린더에 등록/));
    // 미리보기 단계: 아직 register 호출 안 됨(자동 등록 금지).
    await screen.findByText(/푸시업/);
    expect(m.register).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText(/1건 등록/));
    await waitFor(() => expect(m.register).toHaveBeenCalledTimes(1));
    await screen.findByText(/1건을 캘린더에 등록/);
  });

  it("config 비활성이면 버튼 대신 안내만", async () => {
    m.status.mockResolvedValue({ enabled: false, connected: false });
    render(<CalendarSection />);
    expect(await screen.findByText(/비활성화/)).toBeInTheDocument();
    expect(screen.queryByText(/연동하기/)).not.toBeInTheDocument();
  });
});
