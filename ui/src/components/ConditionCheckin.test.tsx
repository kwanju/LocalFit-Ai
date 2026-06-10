// ConditionCheckin 컴포넌트 테스트 (ADR-023): 건너뛰기/제출 동작 + 선택형 보장.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("@/api/client", () => ({
  submitCheckin: vi.fn().mockResolvedValue({ id: 1, saved: true }),
}));

import { submitCheckin } from "@/api/client";
import { ConditionCheckin } from "./ConditionCheckin";

describe("ConditionCheckin", () => {
  beforeEach(() => vi.clearAllMocks());

  it("건너뛰기는 저장 없이 onDone 을 호출한다 (선택형)", () => {
    const onDone = vi.fn();
    render(<ConditionCheckin onDone={onDone} />);
    fireEvent.click(screen.getByRole("button", { name: "건너뛰기" }));
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(submitCheckin).not.toHaveBeenCalled();
  });

  it("입력 없이 시작하면 저장하지 않고 onDone 을 호출한다", () => {
    const onDone = vi.fn();
    render(<ConditionCheckin onDone={onDone} />);
    fireEvent.click(screen.getByRole("button", { name: "시작" }));
    expect(submitCheckin).not.toHaveBeenCalled();
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("피로도·근육통 선택 후 시작하면 매핑된 값으로 저장하고 onDone 을 호출한다", async () => {
    const onDone = vi.fn();
    render(<ConditionCheckin onDone={onDone} />);
    fireEvent.click(screen.getByRole("button", { name: "피로도 피곤" })); // → 8
    fireEvent.click(screen.getByRole("button", { name: "근육통 약간" })); // → 2
    fireEvent.click(screen.getByRole("button", { name: "시작" }));

    await waitFor(() => expect(submitCheckin).toHaveBeenCalledTimes(1));
    expect(submitCheckin).toHaveBeenCalledWith({ fatigue: 8, soreness: 2, note: undefined });
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
  });
});
