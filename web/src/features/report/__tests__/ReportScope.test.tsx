import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { makeClientReportPayload } from "@/features/report/__tests__/report-fixture";
import { ReportWorkspace } from "@/features/report/ReportWorkspace";

vi.mock("@/features/report/charts/EChartCanvas", () => ({
  EChartCanvas: () => <div data-testid="echart-svg-canvas" />,
}));

describe("ReportWorkspace scope contract", () => {
  it("keeps evidence and source start refs in separate scope kinds", async () => {
    const user = userEvent.setup();
    const onScopeChange = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          preview_ref: "preview_main",
          source_ref: "source_main",
          access_policy: "permitted",
          truncated: false,
          masking_status: "none",
          column_labels: ["항목", "값"],
          rows: [["관찰값", "100"]],
          locator_summary: "원장 자료 1행",
        }),
      }),
    );

    render(
      <ReportWorkspace
        onScopeChange={onScopeChange}
        payload={makeClientReportPayload()}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "2026년 5월 근거 보기" }),
    );
    const consultantTabs = screen.getByRole("tablist", {
      name: "컨설턴트 분석 보기",
    });
    expect(
      within(consultantTabs).getByRole("tab", { name: "근거·출처" }),
    ).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("뒷받침 · 관찰")).toBeInTheDocument();

    await waitFor(() =>
      expect(onScopeChange).toHaveBeenLastCalledWith(
        expect.objectContaining({
          activeRef: "evidence_main",
          scopeInstanceId: "evidence_main",
          scopeKind: "evidence",
        }),
      ),
    );

    await user.click(
      screen.getByRole("button", { name: "출처 미리보기" }),
    );
    await waitFor(() =>
      expect(onScopeChange).toHaveBeenLastCalledWith(
        expect.objectContaining({
          activeRef: "source_main",
          scopeInstanceId: "source_main",
          scopeKind: "source",
        }),
      ),
    );

    vi.unstubAllGlobals();
  });

  it("does not change the question scope when only the consultant subview changes", async () => {
    const user = userEvent.setup();
    const onScopeChange = vi.fn();
    render(
      <ReportWorkspace
        onScopeChange={onScopeChange}
        payload={makeClientReportPayload()}
      />,
    );
    const navigation = screen.getByRole("navigation", {
      name: "결과 리포트 화면",
    });

    await user.click(
      within(navigation).getByRole("button", {
        name: "컨설턴트 근거 분석",
      }),
    );
    const consultantTabs = screen.getByRole("tablist", {
      name: "컨설턴트 분석 보기",
    });
    const scopeCallCount = onScopeChange.mock.calls.length;

    await user.click(
      within(consultantTabs).getByRole("tab", { name: "검증 계획" }),
    );

    expect(onScopeChange).toHaveBeenCalledTimes(scopeCallCount);
  });

  it("uses the supplied packet and revision as distinct scope instances", async () => {
    const user = userEvent.setup();
    const onScopeChange = vi.fn();
    render(
      <ReportWorkspace
        onScopeChange={onScopeChange}
        payload={makeClientReportPayload()}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "전문가 검토 패킷 1" }),
    );
    await waitFor(() =>
      expect(onScopeChange).toHaveBeenLastCalledWith(
        expect.objectContaining({
          activeRef: "packet_legal_main",
          scopeInstanceId: "packet_legal_main",
          scopeKind: "expert_packet",
        }),
      ),
    );

    await user.click(screen.getByRole("button", { name: "변경 이력" }));
    await waitFor(() =>
      expect(onScopeChange).toHaveBeenLastCalledWith(
        expect.objectContaining({
          scopeInstanceId: "section:revision_changes:issue_main",
          scopeKind: "section",
        }),
      ),
    );
  });
});
