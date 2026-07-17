import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TerminalApprovalNotice } from "@/features/analysis/TerminalApprovalNotice";

describe("TerminalApprovalNotice", () => {
  it("never offers a web approval action", () => {
    render(
      <TerminalApprovalNotice instruction="터미널에서 기존 요청을 확인하세요." />,
    );

    expect(screen.getByText("터미널 승인 필요")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /승인|거절/ })).not.toBeInTheDocument();
  });

  it("labels the human gate only in Korean", () => {
    render(<TerminalApprovalNotice instruction="터미널에서 요청을 확인하세요." />);

    expect(screen.getByText("사람 확인 단계")).toBeInTheDocument();
    expect(screen.queryByText("HUMAN GATE")).not.toBeInTheDocument();
  });
});
