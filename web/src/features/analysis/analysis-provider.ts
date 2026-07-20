export type PendingAction =
  | "human_response"
  | "terminal_approval"
  | "provider_work"
  | "retry"
  | "resume"
  | "request_changes"
  | "terminal";

export type ProviderErrorCode =
  | "INPUT_POLICY_FAILURE"
  | "AI_AUTH_FAILURE"
  | "AI_TRANSIENT_FAILURE"
  | "AI_REFUSAL"
  | "AI_OUTPUT_INVALID"
  | "VALIDATION_FAILURE"
  | "ENGINE_FAILURE"
  | "IDEMPOTENCY_CONFLICT"
  | "STALE_REVISION"
  | "HUMAN_RESPONSE_REQUIRED"
  | "TERMINAL_APPROVAL_REQUIRED"
  | "RETRYABLE_PROVIDER_FAILURE"
  | "CONTRACT_FAILURE"
  | "INTEGRITY_FAILURE"
  | "STOPPED"
  | "CANCELLED";

export type HitlDecision = "approve" | "approve_with_edits" | "reanalyze" | "stop";

export type ProviderHitlCard = Readonly<{
  hitl_kind: "context_data" | "diagnostic_final";
  request_id: string;
  base_revision: number;
  title: string;
  summary: string;
  target_refs: readonly string[];
  allowed_decisions: readonly HitlDecision[];
  editable_fields: readonly string[];
  sections: readonly Readonly<{
    kind: string;
    title: string;
    items: readonly string[];
    target_refs: readonly string[];
  }>[];
}>;

export type ProviderSnapshot = {
  provider_kind: "replay" | "plugin" | "service";
  display_badge: "저장된 시연 흐름" | "실시간 플러그인" | "실시간 AI 분석";
  run_id: string;
  revision: number;
  workflow_status: string;
  ui_phase: 1 | 2 | 3 | 4 | 5 | 6 | 7;
  pending_action: PendingAction;
  pending_approval_request_id: string | null;
  allowed_actions: string[];
  latest_event: string;
  progress: number;
  result_ref: string | null;
  hitl_card?: ProviderHitlCard | null;
  error: null | {
    code: ProviderErrorCode;
    message: string;
    retryable?: boolean;
  };
};

export interface AnalysisProvider {
  createRun(): Promise<ProviderSnapshot>;
  attachData(
    runId: string,
    expectedRevision: number,
    files: File[],
  ): Promise<ProviderSnapshot>;
  submitHumanResponse(
    runId: string,
    expectedRevision: number,
    response: string,
  ): Promise<ProviderSnapshot>;
  submitDecision(
    runId: string,
    expectedRevision: number,
    decision: HitlDecision,
    edits?: Readonly<Record<string, unknown>>,
    rationale?: string | null,
  ): Promise<ProviderSnapshot>;
  requestChanges(
    runId: string,
    expectedRevision: number,
  ): Promise<ProviderSnapshot>;
  startOrContinue(
    runId: string,
    expectedRevision: number,
  ): Promise<ProviderSnapshot>;
  prepareTerminalApprovalRequest(
    runId: string,
    expectedRevision: number,
  ): Promise<ProviderSnapshot>;
  getStatus(runId: string): Promise<ProviderSnapshot>;
  getPendingAction(runId: string): Promise<PendingAction>;
  getTerminalApprovalInstruction(runId: string): Promise<string | null>;
  retry(runId: string, expectedRevision: number): Promise<ProviderSnapshot>;
  resume(runId: string, expectedRevision: number): Promise<ProviderSnapshot>;
  stop(runId: string, expectedRevision: number): Promise<ProviderSnapshot>;
  cancel(runId: string, expectedRevision: number): Promise<ProviderSnapshot>;
  deleteRun(runId: string, expectedRevision: number): Promise<void>;
  openFinalizedReport(runId: string): Promise<string | null>;
}
