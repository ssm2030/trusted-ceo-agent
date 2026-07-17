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

describe("ReportLoader expired session", () => {
  it("bootstraps once more and retries only the current-report GET", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ csrfToken: "csrf_initial" }),
      })
      .mockResolvedValueOnce({ ok: false, status: 401 })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ csrfToken: "csrf_renewed" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => makeClientReportPayload(),
      });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReportLoader />);

    expect(
      await screen.findByRole("navigation", { name: "결과 리포트 화면" }),
    ).toBeInTheDocument();
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/report/session",
      "/api/report/current",
      "/api/report/session",
      "/api/report/current",
    ]);
    expect(
      fetchMock.mock.calls.filter(([url]) => url === "/api/report/import"),
    ).toHaveLength(0);
  });
});
