export type PendingAction =
  | "human_response"
  | "terminal_approval"
  | "provider_work"
  | "retry"
  | "resume"
  | "request_changes"
  | "terminal";

export type ProviderErrorCode =
  | "STALE_REVISION"
  | "HUMAN_RESPONSE_REQUIRED"
  | "TERMINAL_APPROVAL_REQUIRED"
  | "RETRYABLE_PROVIDER_FAILURE"
  | "CONTRACT_FAILURE"
  | "INTEGRITY_FAILURE"
  | "STOPPED"
  | "CANCELLED";

export type ProviderSnapshot = {
  provider_kind: "replay" | "plugin";
  display_badge: "저장된 시연 흐름" | "실시간 플러그인";
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
  error: null | {
    code: ProviderErrorCode;
    message: string;
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
  openFinalizedReport(runId: string): Promise<string | null>;
}
