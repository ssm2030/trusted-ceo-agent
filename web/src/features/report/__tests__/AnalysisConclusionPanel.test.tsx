import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnalysisConclusionPanel } from "@/features/report/AnalysisConclusionPanel";
import { makeClientReportPayload } from "@/features/report/__tests__/report-fixture";

describe("AnalysisConclusionPanel", () => {
  it("현재 문제의 정본 분석만 표시한다", () => {
    const { report } = makeClientReportPayload();
    const issue = structuredClone(report.final_result.issues[0]);
    issue.secondary_flags = ["margin_watch"];
    issue.cause_hypotheses = [
      {
        claim_code: "고정비 증가가 수익성 저하를 설명할 수 있습니다.",
      },
    ];
    issue.counter_hypotheses = [
      {
        claim_code: "일시적인 매출 인식 시점 차이일 수 있습니다.",
      },
    ];
    issue.unresolved_conflicts = [
      "원가 배부 기준의 일관성이 확인되지 않았습니다.",
    ];
    issue.conditional_response_refs = ["response_margin"];
    report.final_result.conditional_responses = [
      {
        response_id: "response_margin",
        condition_template: "원가 배부 오류가 확인되면",
        direction_template: "수익성 지표를 재계산합니다.",
      },
      {
        response_id: "response_collection",
        condition_template: "회수 예정일이 승인 범위를 벗어나면",
        direction_template: "현금 보전 대응안을 다시 확인합니다.",
      },
    ];

    render(<AnalysisConclusionPanel activeIssue={issue} report={report} />);

    expect(screen.getByText(issue.primary_grade)).toBeInTheDocument();
    expect(screen.getByText(issue.title_template)).toBeInTheDocument();
    expect(screen.getByText(issue.why_it_matters_template)).toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: "원인 가설" })).getByText(
        "고정비 증가가 수익성 저하를 설명할 수 있습니다.",
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: "반대 가설" })).getByText(
        "일시적인 매출 인식 시점 차이일 수 있습니다.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("원가 배부 기준의 일관성이 확인되지 않았습니다."),
    ).toBeInTheDocument();
    expect(screen.getByText("원가 배부 오류가 확인되면")).toBeInTheDocument();
    expect(screen.getByText("수익성 지표를 재계산합니다.")).toBeInTheDocument();
    expect(
      screen.queryByText("회수 예정일이 승인 범위를 벗어나면"),
    ).not.toBeInTheDocument();
  });

  it("없는 가설을 생성하지 않고 명시적 빈 상태를 표시한다", () => {
    const { report } = makeClientReportPayload();
    const issue = structuredClone(report.final_result.issues[0]);
    issue.cause_hypotheses = [];
    issue.counter_hypotheses = [];

    render(<AnalysisConclusionPanel activeIssue={issue} report={report} />);

    expect(screen.getByText("등록된 원인 가설 없음")).toBeInTheDocument();
    expect(screen.getByText("등록된 반대 가설 없음")).toBeInTheDocument();
  });
});
