import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RunHeader } from "@/features/shell/RunHeader";

describe("RunHeader", () => {
  it("shows replay identity without claiming real-time analysis", () => {
    render(
      <RunHeader
        badge="저장된 시연 흐름"
        revision={0}
        runId="replay-demo"
        status="준비"
      />,
    );

    expect(screen.getByText("저장된 시연 흐름")).toBeInTheDocument();
    expect(screen.getByText("리비전 0")).toBeInTheDocument();
    expect(screen.queryByText("실시간 플러그인")).not.toBeInTheDocument();
  });
});
