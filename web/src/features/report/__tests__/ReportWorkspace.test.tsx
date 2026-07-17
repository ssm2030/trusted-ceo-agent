import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ReportWorkspace } from "@/features/report/ReportWorkspace";
import { makeClientReportPayload } from "@/features/report/__tests__/report-fixture";

vi.mock("@/features/report/charts/EChartCanvas", () => ({
  EChartCanvas: () => <div data-testid="echart-svg-canvas" />,
}));

describe("ReportWorkspace", () => {
  it("renders five Korean screens and keeps one active issue scope", async () => {
    const user = userEvent.setup();
    render(<ReportWorkspace payload={makeClientReportPayload()} />);

    const navigation = screen.getByRole("navigation", {
      name: "결과 리포트 화면",
    });
    for (const label of [
      "최고경영자 의사결정 요약",
      "컨설턴트 근거 분석",
      "실행·신뢰 기록",
      "전문가 검토 패킷 1",
      "변경 이력",
    ]) {
      expect(
        within(navigation).getByRole("button", { name: label }),
      ).toBeInTheDocument();
    }

    await user.click(
      screen.getByRole("button", { name: "현금 회수 지연 선택" }),
    );
    await user.click(
      within(navigation).getByRole("button", {
        name: "컨설턴트 근거 분석",
      }),
    );

    expect(
      screen.getByRole("heading", { name: "현금 회수 지연 근거 분석" }),
    ).toBeInTheDocument();

    await user.click(
      within(navigation).getByRole("button", { name: "실행·신뢰 기록" }),
    );
    expect(screen.getByText("현재 범위: 현금 회수 지연")).toBeInTheDocument();
  });

  it("renders only the plugin-selected summary issues and supplied relations", async () => {
    const user = userEvent.setup();
    const payload = makeClientReportPayload();
    render(<ReportWorkspace payload={payload} />);

    expect(screen.getAllByTestId("ceo-summary-issue")).toHaveLength(
      payload.report.presentation_manifest.ceo_summary_issue_refs.length,
    );
    expect(screen.getAllByTestId("ceo-summary-issue").length).toBeLessThanOrEqual(
      3,
    );

    await user.click(
      screen.getByRole("button", { name: "전체 문제 구조 보기" }),
    );
    expect(screen.getByText("observed_together")).toBeInTheDocument();
    expect(screen.getAllByTestId("issue-structure-node")).toHaveLength(2);
  });

  it("keeps expert review strictly one-way", async () => {
    const user = userEvent.setup();
    render(<ReportWorkspace payload={makeClientReportPayload()} />);

    await user.click(
      screen.getByRole("button", { name: "전문가 검토 패킷 1" }),
    );

    expect(
      screen.getByRole("link", { name: "Markdown 내려받기" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "인쇄 보기" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(
      screen.queryByText(/검토 완료|답변 업로드|결과 반영/),
    ).not.toBeInTheDocument();
  });

  it("shows contract enums only through approved Korean labels", async () => {
    const user = userEvent.setup();
    render(<ReportWorkspace payload={makeClientReportPayload()} />);
    const navigation = screen.getByRole("navigation", {
      name: "결과 리포트 화면",
    });

    await user.click(
      within(navigation).getByRole("button", { name: "컨설턴트 근거 분석" }),
    );
    expect(screen.getByText("뒷받침 · 관찰")).toBeInTheDocument();
    expect(screen.getByText("허용")).toBeInTheDocument();
    expect(
      screen.queryByText(/supports|observation|permitted/),
    ).not.toBeInTheDocument();

    await user.click(
      within(navigation).getByRole("button", { name: "실행·신뢰 기록" }),
    );
    expect(screen.getByText("최종 확정")).toBeInTheDocument();
    expect(screen.getByText("최종 승인")).toBeInTheDocument();
    expect(
      screen.getByText("현재 유효 · 터미널 직접 입력"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("터미널 결정 · 리비전 2 · 사람"),
    ).toBeInTheDocument();
    for (const rawValue of [
      "finalized",
      "final",
      "current",
      "interactive_tty",
      "decide-interactive",
      "human",
    ]) {
      expect(
        screen.queryByText(rawValue, { exact: true }),
      ).not.toBeInTheDocument();
    }
  });
});
