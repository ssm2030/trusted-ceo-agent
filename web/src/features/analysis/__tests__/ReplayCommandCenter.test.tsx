import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { ReplayCommandCenter } from "@/features/analysis/ReplayCommandCenter";

describe("ReplayCommandCenter", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("states that uploaded bytes are not analyzed and accepts metadata-only files", async () => {
    const user = userEvent.setup();
    render(<ReplayCommandCenter />);

    expect(
      screen.getByText(
        "저장된 시연 흐름 — 이 화면은 준비된 작업 과정을 재현하며 선택한 파일 내용을 새로 분석하지 않습니다.",
      ),
    ).toBeInTheDocument();

    const input = screen.getByLabelText("분석 자료 선택");
    await user.upload(
      input,
      new File(["private-content"], "현금흐름.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }),
    );

    expect(screen.getByText("현금흐름.xlsx")).toBeInTheDocument();
    expect(screen.queryByText("private-content")).not.toBeInTheDocument();
  });

  it("offers a human response step after continuing the replay", async () => {
    const user = userEvent.setup();
    render(<ReplayCommandCenter />);

    await user.click(screen.getByRole("button", { name: "시연 흐름 시작" }));

    expect(
      screen.getByRole("textbox", { name: "사람 확인 답변" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "답변 제출" }),
    ).toBeInTheDocument();
  });

  it('keeps two separately selected folders in cumulative groups', async () => {
    const user = userEvent.setup();
    render(<ReplayCommandCenter />);
    const input = screen.getByLabelText('분석 폴더 선택');
    const first = new File(['# A'], 'a.md', { type: 'text/markdown' });
    Object.defineProperty(first, 'webkitRelativePath', { value: 'folder-a/a.md' });
    await user.upload(input, first);
    expect(await screen.findByText('folder-a/a.md')).toBeVisible();

    const second = new File(['x,y\n1,2\n'], 'b.csv', { type: 'text/csv' });
    Object.defineProperty(second, 'webkitRelativePath', { value: 'folder-b/b.csv' });
    await user.upload(input, second);

    expect(await screen.findByText('folder-b/b.csv')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'folder-a' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'folder-b' })).toBeVisible();
  });
});
