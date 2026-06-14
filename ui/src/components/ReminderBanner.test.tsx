// ReminderBanner 테스트 (ADR-027): pending 우선순위·요약·지금시작/나중에 동작.
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { Reminder } from "@/api/client";
import { ReminderBanner } from "./ReminderBanner";

const workout: Reminder = {
  key: "workout|2026-06-14|18:00",
  kind: "workout",
  title: "운동할 시간이에요 💪",
  body: "오늘 계획한 운동을 시작해볼까요?",
  scheduled_for: "2026-06-14T18:00:00",
};
const checkin: Reminder = {
  key: "checkin|2026-06-14|09:00",
  kind: "checkin",
  title: "컨디션 체크인",
  body: "오늘 컨디션을 기록해요.",
  scheduled_for: "2026-06-14T09:00:00",
};

function renderBanner(pending: Reminder[], onAck = vi.fn()) {
  render(
    <MemoryRouter>
      <ReminderBanner pending={pending} onAck={onAck} />
    </MemoryRouter>,
  );
  return onAck;
}

describe("ReminderBanner", () => {
  it("pending 이 비면 아무것도 렌더하지 않는다", () => {
    const { container } = render(
      <MemoryRouter>
        <ReminderBanner pending={[]} onAck={vi.fn()} />
      </MemoryRouter>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("운동 리마인드를 체크인보다 우선 노출하고 나머지는 '외 N건'으로 요약한다", () => {
    renderBanner([checkin, workout]);
    expect(screen.getByText(/운동할 시간이에요/)).toBeInTheDocument();
    expect(screen.getByText(/외 1건/)).toBeInTheDocument();
  });

  it("'나중에'는 primary 키로 ack 한다", () => {
    const onAck = renderBanner([workout]);
    fireEvent.click(screen.getByRole("button", { name: "나중에" }));
    expect(onAck).toHaveBeenCalledWith(workout.key);
  });

  it("'지금 시작'은 ack 후 동작한다", () => {
    const onAck = renderBanner([workout]);
    fireEvent.click(screen.getByRole("button", { name: "지금 시작" }));
    expect(onAck).toHaveBeenCalledWith(workout.key);
  });
});
