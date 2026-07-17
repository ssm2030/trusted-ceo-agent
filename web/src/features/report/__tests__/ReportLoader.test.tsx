import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeClientReportPayload } from "@/features/report/__tests__/report-fixture";
import { ReportLoader } from "@/features/report/ReportLoader";

vi.mock("@/features/report/charts/EChartCanvas", () => ({
  EChartCanvas: () => <div data-testid="echart-svg-canvas" />,
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ReportLoader", () => {
  it("renders a validated current report payload", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ csrfToken: "csrf_test_only" }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => makeClientReportPayload(),
        }),
    );

    render(<ReportLoader />);

    expect(
      await screen.findByRole("navigation", { name: "결과 리포트 화면" }),
    ).toBeInTheDocument();
  });

  it("does not expose raw fetch errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("Failed to fetch C:\\secret\\run")),
    );

    render(<ReportLoader />);

    expect(
      await screen.findByText(
        "웹 리포트 묶음이 필요합니다. 결과 리포트에서 web-report-bundle.json을 가져오세요.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Failed to fetch|C:\\secret/)).not.toBeInTheDocument();
  });
});
