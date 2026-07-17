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

describe("ReportLoader localhost session", () => {
  it("creates the localhost session before reading the current report", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ csrfToken: "csrf_test_only" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => makeClientReportPayload(),
      });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReportLoader />);

    expect(
      await screen.findByRole("navigation", { name: "결과 리포트 화면" }),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/report/session",
      expect.objectContaining({
        cache: "no-store",
        method: "POST",
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/report/current",
      expect.objectContaining({ cache: "no-store" }),
    );
  });
});
