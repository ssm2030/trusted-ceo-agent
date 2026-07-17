import type { ProviderSnapshot } from "@/features/analysis/analysis-provider";

export const ANALYSIS_PHASES = [
  "목표와 자료 준비",
  "데이터 구조 확인",
  "문제 탐색",
  "사람 확인",
  "심층 분석",
  "보고서 작성",
  "완료",
] as const;

export type AnalysisPhase = (typeof ANALYSIS_PHASES)[number];

export type ReplayFileMetadata = {
  name: string;
  size: number;
  type: string;
};

export const WORKFLOW_STATUS_LABELS: Readonly<Record<string, string>> =
  Object.freeze({
    created: "준비",
    context_confirmation_required: "목표 확인 필요",
    context_ready: "목표 확인 완료",
    schema_mapping_job_ready: "데이터 구조 확인 준비",
    mapping_proposal_ready: "데이터 구조 제안 준비",
    data_confirmation_required: "데이터 확인 대기",
    evidence_ready: "근거 준비",
    scope_narrowing_required: "분석 범위 확인 필요",
    lens_jobs_ready: "문제 탐색 준비",
    lens_ready: "문제 탐색 완료",
    integrated_draft: "진단 초안 준비",
    diagnostic_approval_required: "진단 승인 대기",
    deep_dive_authorized: "심층 분석 허가",
    deep_dive_jobs_ready: "심층 분석 준비",
    deep_dive_ready: "심층 분석 완료",
    finalization_jobs_ready: "보고서 작성 준비",
    writer_ready: "보고서 초안 준비",
    final_approval_required: "최종 승인 대기",
    delivery_approved: "전달 승인 완료",
    finalized: "완료",
    stopped_by_human: "사용자 중지",
    cancelled: "취소",
  });

export function getWorkflowStatusLabel(snapshot: ProviderSnapshot): string {
  return WORKFLOW_STATUS_LABELS[snapshot.workflow_status] ?? "상태 확인 중";
}

export function formatFileSize(size: number): string {
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}
