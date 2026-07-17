import type {
  AnalysisProvider,
  PendingAction,
  ProviderSnapshot,
} from "@/features/analysis/analysis-provider";
import {
  createInitialReplaySnapshot,
  REPLAY_PHASE_EVENTS,
} from "@/features/analysis/replay-scenario";

type FileLike = Pick<File, "name" | "size" | "type">;

type FileValidation =
  | { accepted: true }
  | { accepted: false; message: string };

const ALLOWED_ANALYSIS_EXTENSIONS = new Set(["csv", "json", "xlsx"]);
const FILE_POLICY_MESSAGE =
  "분석 자료는 CSV, JSON, XLSX 파일만 선택할 수 있습니다.";

function copySnapshot(snapshot: ProviderSnapshot): ProviderSnapshot {
  return {
    ...snapshot,
    allowed_actions: [...snapshot.allowed_actions],
    error: snapshot.error ? { ...snapshot.error } : null,
  };
}

export function validateReplayFile(file: FileLike): FileValidation {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!ALLOWED_ANALYSIS_EXTENSIONS.has(extension)) {
    return { accepted: false, message: FILE_POLICY_MESSAGE };
  }

  return { accepted: true };
}

export class ReplayAnalysisProvider implements AnalysisProvider {
  private current: ProviderSnapshot;

  constructor(snapshot: ProviderSnapshot = createInitialReplaySnapshot()) {
    this.current = copySnapshot(snapshot);
  }

  peekSnapshot(): ProviderSnapshot {
    return copySnapshot(this.current);
  }

  restoreSnapshot(snapshot: ProviderSnapshot): ProviderSnapshot {
    if (snapshot.provider_kind !== "replay") {
      return this.withError(
        "CONTRACT_FAILURE",
        "저장된 시연 흐름 상태만 복원할 수 있습니다.",
      );
    }
    this.current = copySnapshot(snapshot);
    return this.peekSnapshot();
  }

  async createRun(): Promise<ProviderSnapshot> {
    this.current = createInitialReplaySnapshot();
    return this.peekSnapshot();
  }

  async attachData(
    runId: string,
    expectedRevision: number,
    files: File[],
  ): Promise<ProviderSnapshot> {
    const boundaryError = this.checkMutation(runId, expectedRevision);
    if (boundaryError) {
      return boundaryError;
    }

    const invalid = files
      .map((file) => validateReplayFile(file))
      .find((result) => !result.accepted);
    if (invalid && !invalid.accepted) {
      return this.withError("CONTRACT_FAILURE", invalid.message);
    }

    if (files.length === 0) {
      return this.withError(
        "CONTRACT_FAILURE",
        "분석 자료를 하나 이상 선택해 주세요.",
      );
    }

    return this.update({
      revision: this.current.revision + 1,
      latest_event:
        "선택한 자료의 파일명·형식·크기만 저장된 시연 흐름에 연결했습니다.",
      error: null,
    });
  }

  async submitHumanResponse(
    runId: string,
    expectedRevision: number,
    response: string,
  ): Promise<ProviderSnapshot> {
    const boundaryError = this.checkMutation(runId, expectedRevision);
    if (boundaryError) {
      return boundaryError;
    }

    if (this.current.pending_action !== "human_response" || !response.trim()) {
      return this.withError(
        "HUMAN_RESPONSE_REQUIRED",
        "사람 확인 답변을 작성한 뒤 제출해 주세요.",
      );
    }

    return this.update({
      revision: this.current.revision + 1,
      workflow_status: "context_ready",
      ui_phase: 1,
      pending_action: "provider_work",
      pending_approval_request_id: null,
      allowed_actions: ["attach_data", "start_or_continue"],
      latest_event: "사람 확인 답변을 저장된 다음 장면에 반영했습니다.",
      progress: 18,
      error: null,
    });
  }

  async requestChanges(
    runId: string,
    expectedRevision: number,
  ): Promise<ProviderSnapshot> {
    const boundaryError = this.checkMutation(runId, expectedRevision);
    if (boundaryError) {
      return boundaryError;
    }

    return this.update({
      revision: this.current.revision + 1,
      workflow_status: "context_confirmation_required",
      ui_phase: 1,
      pending_action: "human_response",
      pending_approval_request_id: null,
      allowed_actions: ["submit_human_response"],
      latest_event: REPLAY_PHASE_EVENTS.changes,
      progress: 12,
      error: null,
    });
  }

  async startOrContinue(
    runId: string,
    expectedRevision: number,
  ): Promise<ProviderSnapshot> {
    const boundaryError = this.checkMutation(runId, expectedRevision);
    if (boundaryError) {
      return boundaryError;
    }

    if (this.current.workflow_status === "created") {
      return this.update({
        revision: this.current.revision + 1,
        workflow_status: "context_confirmation_required",
        ui_phase: 1,
        pending_action: "human_response",
        pending_approval_request_id: null,
        allowed_actions: ["submit_human_response"],
        latest_event: REPLAY_PHASE_EVENTS.context,
        progress: 12,
        error: null,
      });
    }

    if (this.current.pending_action === "terminal_approval") {
      return this.withError(
        "TERMINAL_APPROVAL_REQUIRED",
        "실제 결정은 터미널 TTY에서만 할 수 있습니다.",
      );
    }

    return this.update({
      revision: this.current.revision + 1,
      workflow_status: "lens_ready",
      ui_phase: 3,
      pending_action: "provider_work",
      pending_approval_request_id: null,
      allowed_actions: ["start_or_continue", "request_changes"],
      latest_event: "저장된 문제 탐색 장면으로 이동했습니다.",
      progress: 46,
      error: null,
    });
  }

  async prepareTerminalApprovalRequest(
    runId: string,
    expectedRevision: number,
  ): Promise<ProviderSnapshot> {
    const boundaryError = this.checkMutation(runId, expectedRevision);
    if (boundaryError) {
      return boundaryError;
    }

    const waitingStatus =
      this.current.workflow_status === "mapping_proposal_ready"
        ? "data_confirmation_required"
        : "context_confirmation_required";

    return this.update({
      workflow_status: waitingStatus,
      pending_action: "terminal_approval",
      pending_approval_request_id:
        this.current.pending_approval_request_id ?? "replay-request-001",
      allowed_actions: ["poll_terminal_approval"],
      latest_event: REPLAY_PHASE_EVENTS.terminal,
      error: null,
    });
  }

  async getStatus(runId: string): Promise<ProviderSnapshot> {
    if (runId !== this.current.run_id) {
      return this.withError(
        "CONTRACT_FAILURE",
        "요청한 저장 실행본을 찾을 수 없습니다.",
      );
    }
    return this.peekSnapshot();
  }

  async getPendingAction(runId: string): Promise<PendingAction> {
    const status = await this.getStatus(runId);
    return status.pending_action;
  }

  async getTerminalApprovalInstruction(runId: string): Promise<string | null> {
    const status = await this.getStatus(runId);
    if (!status.pending_approval_request_id) {
      return null;
    }
    return "플러그인 터미널에서 기존 승인 요청을 확인한 뒤 이 화면의 상태를 새로 확인하세요.";
  }

  async retry(
    runId: string,
    expectedRevision: number,
  ): Promise<ProviderSnapshot> {
    return this.startOrContinue(runId, expectedRevision);
  }

  async resume(
    runId: string,
    expectedRevision: number,
  ): Promise<ProviderSnapshot> {
    return this.startOrContinue(runId, expectedRevision);
  }

  async stop(
    runId: string,
    expectedRevision: number,
  ): Promise<ProviderSnapshot> {
    const boundaryError = this.checkMutation(runId, expectedRevision);
    if (boundaryError) {
      return boundaryError;
    }
    return this.update({
      workflow_status: "stopped_by_human",
      pending_action: "resume",
      allowed_actions: ["resume"],
      latest_event: "저장된 작업 흐름을 중지했습니다.",
      error: { code: "STOPPED", message: "작업 흐름이 중지되었습니다." },
    });
  }

  async cancel(
    runId: string,
    expectedRevision: number,
  ): Promise<ProviderSnapshot> {
    const boundaryError = this.checkMutation(runId, expectedRevision);
    if (boundaryError) {
      return boundaryError;
    }
    return this.update({
      workflow_status: "cancelled",
      pending_action: "terminal",
      allowed_actions: [],
      latest_event: "저장된 작업 흐름을 취소했습니다.",
      error: { code: "CANCELLED", message: "작업 흐름이 취소되었습니다." },
    });
  }

  async openFinalizedReport(runId: string): Promise<string | null> {
    const status = await this.getStatus(runId);
    return status.workflow_status === "finalized" ? status.result_ref : null;
  }

  private checkMutation(
    runId: string,
    expectedRevision: number,
  ): ProviderSnapshot | null {
    if (runId !== this.current.run_id) {
      return this.withError(
        "CONTRACT_FAILURE",
        "요청한 저장 실행본을 찾을 수 없습니다.",
      );
    }
    if (expectedRevision !== this.current.revision) {
      return this.withError(
        "STALE_REVISION",
        "화면의 실행 정보가 오래되었습니다. 최신 상태를 다시 확인해 주세요.",
      );
    }
    return null;
  }

  private withError(
    code: NonNullable<ProviderSnapshot["error"]>["code"],
    message: string,
  ): ProviderSnapshot {
    return { ...this.peekSnapshot(), error: { code, message } };
  }

  private update(
    patch: Partial<ProviderSnapshot>,
  ): ProviderSnapshot {
    this.current = {
      ...this.current,
      ...patch,
      provider_kind: "replay",
      display_badge: "저장된 시연 흐름",
    };
    return this.peekSnapshot();
  }
}
