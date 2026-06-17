// MySchedulePanel 테스트 (ADR-034 / phase v4-9c): 미연동 안내 + 목록/추가/삭제.
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("@/api/client", () => ({
  getGcalStatus: vi.fn(),
  listGcalEvents: vi.fn(),
  createGcalEvent: vi.fn(),
  deleteGcalEvent: vi.fn(),
  getGcalGaps: vi.fn().mockResolvedValue({ connected: true, hint: null }),
}));

import {
  createGcalEvent,
  deleteGcalEvent,
  getGcalStatus,
  listGcalEvents,
} from "@/api/client";
import { MySchedulePanel } from "./MySchedulePanel";

const m = {
  status: vi.mocked(getGcalStatus),
  list: vi.mocked(listGcalEvents),
  create: vi.mocked(createGcalEvent),
  del: vi.mocked(deleteGcalEvent),
};

function renderPanel() {
  return render(
    <MemoryRouter>
      <MySchedulePanel />
    </MemoryRouter>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("MySchedulePanel", () => {
  it("미연동이면 연동 안내와 설정 링크를 보여준다", async () => {
    m.status.mockResolvedValue({ enabled: true, connected: false });
    renderPanel();

    expect(await screen.findByText(/설정에서 캘린더를 연동하면/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /설정으로 가기/ })).toBeInTheDocument();
    expect(m.list).not.toHaveBeenCalled();
  });

  it("연동됨: 일정 목록을 제목+시간으로 렌더한다", async () => {
    m.status.mockResolvedValue({ enabled: true, connected: true });
    m.list.mockResolvedValue({
      connected: true,
      events: [
        {
          id: "a",
          summary: "헬스장 가기",
          start: "2026-06-18T18:00:00",
          end: "2026-06-18T19:00:00",
          all_day: false,
        },
      ],
    });
    renderPanel();

    expect(await screen.findByText("헬스장 가기")).toBeInTheDocument();
    expect(screen.getByText(/오후 6:00/)).toBeInTheDocument();
  });

  it("일정 추가 폼 제출 시 createGcalEvent 를 호출한다", async () => {
    m.status.mockResolvedValue({ enabled: true, connected: true });
    m.list.mockResolvedValue({ connected: true, events: [] });
    m.create.mockResolvedValue({
      id: "n",
      summary: "러닝",
      start: "2026-06-19T07:00:00",
      end: "2026-06-19T07:30:00",
      all_day: false,
    });
    renderPanel();

    fireEvent.change(await screen.findByLabelText("일정 제목"), {
      target: { value: "러닝" },
    });
    fireEvent.change(screen.getByLabelText("날짜"), { target: { value: "2026-06-19" } });
    fireEvent.change(screen.getByLabelText("시각"), { target: { value: "07:00" } });
    fireEvent.click(screen.getByRole("button", { name: "추가" }));

    await waitFor(() => expect(m.create).toHaveBeenCalledTimes(1));
    expect(m.create).toHaveBeenCalledWith({
      summary: "러닝",
      start: "2026-06-19T07:00:00",
      duration_min: 30,
    });
  });

  it("제목이 비면 추가하지 않고 안내한다", async () => {
    m.status.mockResolvedValue({ enabled: true, connected: true });
    m.list.mockResolvedValue({ connected: true, events: [] });
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "추가" }));
    expect(await screen.findByText(/제목을 입력해 주세요/)).toBeInTheDocument();
    expect(m.create).not.toHaveBeenCalled();
  });

  it("삭제 버튼 클릭 시 deleteGcalEvent 를 호출하고 목록에서 제거한다", async () => {
    m.status.mockResolvedValue({ enabled: true, connected: true });
    m.list.mockResolvedValue({
      connected: true,
      events: [
        {
          id: "a",
          summary: "헬스장 가기",
          start: "2026-06-18T18:00:00",
          end: "2026-06-18T19:00:00",
          all_day: false,
        },
      ],
    });
    m.del.mockResolvedValue(undefined);
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: /헬스장 가기 삭제/ }));
    await waitFor(() => expect(m.del).toHaveBeenCalledWith("a"));
    await waitFor(() =>
      expect(screen.queryByText("헬스장 가기")).not.toBeInTheDocument(),
    );
  });
});
