import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VerificationPlanPanel } from "@/features/report/VerificationPlanPanel";
import { makeClientReportPayload } from "@/features/report/__tests__/report-fixture";

function addScopedQualityCases(
  report: ReturnType<typeof makeClientReportPayload>["report"],
) {
  report.evidence_view.data_quality = [
    {
      quality_issue_id: "quality_current_open",
      source_ref: "source_main",
      issue_code: "ambiguous_unit",
      severity: "warning",
      affected_field: "amount",
      raw_value_hash: null,
      normalized_role: "amount",
      reason_code: "unit_requires_confirmation",
      suggested_resolution: "원본 통화와 금액 단위를 확인하세요.",
      resolution_status: "open",
    },
    {
      quality_issue_id: "quality_other_open",
      source_ref: "source_other",
      issue_code: "invalid_date",
      severity: "blocking",
      affected_field: "date",
      raw_value_hash: null,
      normalized_role: "transaction_date",
      reason_code: "date_requires_confirmation",
      suggested_resolution: "다른 이슈의 날짜를 확인하세요.",
      resolution_status: "open",
    },
    {
      quality_issue_id: "quality_current_resolved",
      source_ref: "source_main",
      issue_code: "duplicate_business_key",
      severity: "info",
      affected_field: "document_id",
      raw_value_hash: null,
      normalized_role: "document_id",
      reason_code: "duplicate_reviewed",
      suggested_resolution: "이미 해소된 중복입니다.",
      resolution_status: "resolved",
    },
  ];
}

describe("VerificationPlanPanel", () => {
  it("현재 문제에 연결된 검증 항목만 표시한다", () => {
    const { report } = makeClientReportPayload();
    const activeIssue = structuredClone(report.final_result.issues[0]);
    activeIssue.verification_next_steps = ["비용 구조의 승인 범위를 확인"];
    activeIssue.unresolved_conflicts = [
      "검증 대상 계약의 적용 범위가 확정되지 않았습니다.",
    ];
    activeIssue.expert_review_refs = ["packet_legal_main"];
    addScopedQualityCases(report);

    render(
      <VerificationPlanPanel activeIssue={activeIssue} report={report} />,
    );

    expect(screen.getByText("비용 구조의 승인 범위를 확인")).toBeInTheDocument();
    expect(screen.getByText("법률")).toBeInTheDocument();
    expect(screen.getByText(/현재 계약 조항/)).toBeInTheDocument();
    expect(
      screen.getByText("검증 대상 계약의 적용 범위가 확정되지 않았습니다."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("run_20260717T000000Z_aaaaaaaaaaaaaaaa"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(
        "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      ),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("document_contract_main")).not.toBeInTheDocument();
    expect(
      screen.getByText("원본 통화와 금액 단위를 확인하세요."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("다른 이슈의 날짜를 확인하세요."),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("이미 해소된 중복입니다."),
    ).not.toBeInTheDocument();
  });

  it("다른 문제 대상의 전문가 패킷을 현재 문제에 표시하지 않는다", () => {
    const { report } = makeClientReportPayload();
    const activeIssue = structuredClone(report.final_result.issues[0]);
    const foreignPacket = structuredClone(report.expert_packet_view[0]);
    foreignPacket.expert_packet_id = "packet_foreign";
    foreignPacket.target_issue_ref = "issue_secondary";
    foreignPacket.profession = "세무";
    foreignPacket.review_question = "다른 문제에 대한 세무 검토 질문";
    activeIssue.expert_review_refs = [foreignPacket.expert_packet_id];
    report.expert_packet_view.push(foreignPacket);

    render(
      <VerificationPlanPanel
        activeIssue={activeIssue}
        report={report}
      />,
    );

    expect(
      screen.queryByText("다른 문제에 대한 세무 검토 질문"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("세무")).not.toBeInTheDocument();
    expect(screen.getByText("요청된 전문가 검토 없음")).toBeInTheDocument();
  });

  it("uses the public expert packet when the expanded packet view is absent", () => {
    const { report } = makeClientReportPayload();
    const activeIssue = structuredClone(report.final_result.issues[0]);
    activeIssue.expert_review_refs = ["packet_legal_main"];
    report.expert_packet_view = [];

    render(
      <VerificationPlanPanel
        activeIssue={activeIssue}
        report={report}
      />,
    );

    expect(screen.getByText("법률")).toBeInTheDocument();
    expect(
      screen.getByText("현재 계약 조항이 승인된 관찰 사실에 어떤 제한을 두는지 검토해 주세요."),
    ).toBeInTheDocument();
    expect(screen.queryByText("요청된 전문가 검토 없음")).not.toBeInTheDocument();
  });

  it("자료가 없을 때 영역별 빈 상태를 유지한다", () => {
    const { report } = makeClientReportPayload();
    const activeIssue = structuredClone(report.final_result.issues[0]);
    activeIssue.verification_next_steps = [];
    activeIssue.unresolved_conflicts = [];
    activeIssue.expert_review_refs = [];
    report.evidence_view.data_quality = [];

    render(
      <VerificationPlanPanel activeIssue={activeIssue} report={report} />,
    );

    expect(
      screen.getByText("등록된 다음 검증 단계 없음"),
    ).toBeInTheDocument();
    expect(screen.getByText("기록된 미해결 충돌 없음")).toBeInTheDocument();
    expect(screen.getByText("요청된 전문가 검토 없음")).toBeInTheDocument();
    expect(
      screen.getByText("현재 범위에 연결된 미해결 자료 제한 없음"),
    ).toBeInTheDocument();
  });
});
