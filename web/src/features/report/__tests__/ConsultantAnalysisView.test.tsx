import { useState } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  ConsultantAnalysisView,
  type ConsultantAnalysisSection,
} from "@/features/report/ConsultantAnalysisView";
import { makeClientReportPayload } from "@/features/report/__tests__/report-fixture";

function ControlledConsultantAnalysisView() {
  const { report } = makeClientReportPayload();
  const [activeView, setActiveView] =
    useState<ConsultantAnalysisSection>("analysis");

  return (
    <ConsultantAnalysisView
      activeEvidenceRef={null}
      activeIssue={report.final_result.issues[0]}
      activeView={activeView}
      onPreviewRequest={vi.fn()}
      onViewSelect={setActiveView}
      report={report}
    />
  );
}

describe("ConsultantAnalysisView", () => {
  it("switches among three scoped analysis views without duplicating the common heading", async () => {
    const user = userEvent.setup();
    const { report } = makeClientReportPayload();
    const issueTitle = report.final_result.issues[0].title_template;
    const expectedHeading = `${issueTitle} 분석 검토`;
    render(<ControlledConsultantAnalysisView />);

    const tablist = screen.getByRole("tablist", {
      name: "컨설턴트 분석 보기",
    });
    const tabs = within(tablist).getAllByRole("tab");
    expect(tabs).toHaveLength(3);
    expect(
      within(tablist).getByRole("tab", { name: "분석 결론" }),
    ).toHaveAttribute("aria-selected", "true");
    expect(
      screen.getByRole("tabpanel", { name: "분석 결론" }),
    ).toBeInTheDocument();

    await user.click(
      within(tablist).getByRole("tab", { name: "근거·출처" }),
    );

    expect(
      screen.getByRole("tabpanel", { name: "근거·출처" }),
    ).toBeInTheDocument();
    expect(screen.getByText("뒷받침 · 관찰")).toBeInTheDocument();
    expect(
      screen.getAllByRole("heading", { name: expectedHeading }),
    ).toHaveLength(1);
    expect(screen.getAllByText(`현재 범위: ${issueTitle}`)).toHaveLength(1);
    expect(
      screen.queryByRole("heading", { name: `${issueTitle} 근거 분석` }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("근거 분석 작업대")).not.toBeInTheDocument();

    await user.keyboard("{ArrowRight}");

    const verificationTab = within(tablist).getByRole("tab", {
      name: "검증 계획",
    });
    expect(verificationTab).toHaveFocus();
    expect(verificationTab).toHaveAttribute("aria-selected", "true");
    expect(
      screen.getByRole("tabpanel", { name: "검증 계획" }),
    ).toBeInTheDocument();
  });

  it("supports Home, End, and wrapping arrow navigation with roving tab focus", async () => {
    const user = userEvent.setup();
    render(<ControlledConsultantAnalysisView />);
    const tablist = screen.getByRole("tablist", {
      name: "컨설턴트 분석 보기",
    });
    const analysisTab = within(tablist).getByRole("tab", {
      name: "분석 결론",
    });
    const evidenceTab = within(tablist).getByRole("tab", {
      name: "근거·출처",
    });
    const verificationTab = within(tablist).getByRole("tab", {
      name: "검증 계획",
    });

    analysisTab.focus();
    await user.keyboard("{End}");
    expect(verificationTab).toHaveFocus();
    expect(verificationTab).toHaveAttribute("tabindex", "0");
    expect(analysisTab).toHaveAttribute("tabindex", "-1");

    await user.keyboard("{ArrowRight}");
    expect(analysisTab).toHaveFocus();
    expect(analysisTab).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{ArrowLeft}");
    expect(verificationTab).toHaveFocus();

    await user.keyboard("{Home}");
    expect(analysisTab).toHaveFocus();
    expect(evidenceTab).toHaveAttribute("tabindex", "-1");
  });

  it("fails closed when the active issue has no evidence closure", () => {
    const { report } = makeClientReportPayload();
    report.evidence_view.issue_claim_closure = [];

    render(
      <ConsultantAnalysisView
        activeEvidenceRef="evidence_main"
        activeIssue={report.final_result.issues[0]}
        activeView="evidence"
        onPreviewRequest={vi.fn()}
        onViewSelect={vi.fn()}
        report={report}
      />,
    );

    expect(screen.getByText("표시할 근거 연결이 없습니다.")).toBeInTheDocument();
    expect(screen.queryByText("뒷받침 · 관찰")).not.toBeInTheDocument();
    expect(screen.queryByText("원장 자료")).not.toBeInTheDocument();
  });

  it("exposes the active panel and selected evidence to keyboard and assistive technology", () => {
    const { report } = makeClientReportPayload();
    render(
      <ConsultantAnalysisView
        activeEvidenceRef="evidence_main"
        activeIssue={report.final_result.issues[0]}
        activeView="evidence"
        onPreviewRequest={vi.fn()}
        onViewSelect={vi.fn()}
        report={report}
      />,
    );

    expect(screen.getByRole("tabpanel", { name: "근거·출처" })).toHaveAttribute("tabindex", "0");
    expect(document.getElementById("evidence-evidence_main")).toHaveAttribute("aria-current", "true");
  });
});
