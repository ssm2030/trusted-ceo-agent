export type BackendErrorCode =
  | "INPUT_POLICY_FAILURE"
  | "HUMAN_RESPONSE_REQUIRED"
  | "AI_AUTH_FAILURE"
  | "AI_TRANSIENT_FAILURE"
  | "AI_REFUSAL"
  | "AI_OUTPUT_INVALID"
  | "VALIDATION_FAILURE"
  | "STALE_REVISION"
  | "ENGINE_FAILURE"
  | "STOPPED"
  | "CANCELLED"
  | "IDEMPOTENCY_CONFLICT";

export type BackendMutation = Readonly<{
  expected_revision: number;
  idempotency_key: string;
}>;

export type BackendHitlDecision = BackendMutation & Readonly<{
  decision: "approve" | "approve_with_edits" | "reanalyze" | "stop";
  edits: Readonly<Record<string, unknown>>;
  rationale: string | null;
}>;

export type BackendHitlSection = Readonly<{
  kind: string;
  title: string;
  items: readonly string[];
  target_refs: readonly string[];
}>;

export type BackendHitlCard = Readonly<{
  hitl_kind: "context_data" | "diagnostic_final";
  request_id: string;
  base_revision: number;
  title: string;
  summary: string;
  target_refs: readonly string[];
  allowed_decisions: readonly BackendHitlDecision["decision"][];
  editable_fields: readonly string[];
  sections: readonly BackendHitlSection[];
}>;

export type BackendRunSnapshot = Readonly<{
  provider_kind: "service";
  display_badge: "실시간 AI 분석";
  run_id: string;
  revision: number;
  workflow_status: string;
  ui_phase: 1 | 2 | 3 | 4 | 5 | 6 | 7;
  pending_action: "human_response" | "provider_work" | "retry" | "resume" | "terminal";
  allowed_actions: readonly string[];
  latest_event: string;
  progress: number;
  result_ref: string | null;
  hitl_card: BackendHitlCard | null;
  error: null | Readonly<{
    code: BackendErrorCode;
    message: string;
    retryable: boolean;
  }>;
}>;

export type BackendHealth = Readonly<{
  status: "ok";
  ai_ready: boolean;
  model: "gpt-5.6";
}>;

export type BackendReport = Readonly<{
  bundle: Readonly<Record<string, unknown>>;
  eligibility: Readonly<Record<string, unknown>>;
}>;

export interface AnalysisBackend {
  getHealth(): Promise<BackendHealth>;
  createRun(input: BackendMutation & { mission?: Record<string, unknown> }): Promise<BackendRunSnapshot>;
  uploadFiles(runId: string, form: FormData): Promise<BackendRunSnapshot>;
  getRun(runId: string): Promise<BackendRunSnapshot>;
  continueRun(runId: string, input: BackendMutation): Promise<BackendRunSnapshot>;
  retry(runId: string, input: BackendMutation): Promise<BackendRunSnapshot>;
  resume(runId: string, input: BackendMutation): Promise<BackendRunSnapshot>;
  stop(runId: string, input: BackendMutation): Promise<BackendRunSnapshot>;
  cancel(runId: string, input: BackendMutation): Promise<BackendRunSnapshot>;
  submitHitl(
    runId: string,
    input: BackendHitlDecision,
    browserFingerprint: string,
  ): Promise<BackendRunSnapshot>;
  getReport(runId: string): Promise<BackendReport>;
  deleteRun(runId: string, input: BackendMutation & { confirmed: true }): Promise<void>;
}

const ERROR_CODES = new Set<BackendErrorCode>([
  "INPUT_POLICY_FAILURE", "HUMAN_RESPONSE_REQUIRED", "AI_AUTH_FAILURE",
  "AI_TRANSIENT_FAILURE", "AI_REFUSAL", "AI_OUTPUT_INVALID",
  "VALIDATION_FAILURE", "STALE_REVISION", "ENGINE_FAILURE", "STOPPED",
  "CANCELLED", "IDEMPOTENCY_CONFLICT",
]);
const PENDING_ACTIONS = new Set([
  "human_response", "provider_work", "retry", "resume", "terminal",
]);
const RUN_ID = /^run_[A-Za-z0-9_-]{8,200}$/u;

export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function stringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function parseHitlCard(value: unknown): BackendHitlCard | null {
  if (value === null) return null;
  if (!isRecord(value) ||
      (value.hitl_kind !== "context_data" && value.hitl_kind !== "diagnostic_final") ||
      typeof value.request_id !== "string" ||
      !Number.isInteger(value.base_revision) ||
      typeof value.title !== "string" || typeof value.summary !== "string" ||
      !stringArray(value.target_refs) || !stringArray(value.allowed_decisions) ||
      !stringArray(value.editable_fields) || !Array.isArray(value.sections)) {
    throw new Error("invalid backend HITL card");
  }
  const decisions = value.allowed_decisions;
  if (!decisions.every((item) => ["approve", "approve_with_edits", "reanalyze", "stop"].includes(item))) {
    throw new Error("invalid backend HITL decisions");
  }
  const sections = value.sections.map((section) => {
    if (!isRecord(section) || typeof section.kind !== "string" ||
        typeof section.title !== "string" || !stringArray(section.items) ||
        !stringArray(section.target_refs)) {
      throw new Error("invalid backend HITL section");
    }
    return {
      kind: section.kind,
      title: section.title,
      items: section.items,
      target_refs: section.target_refs,
    };
  });
  return {
    hitl_kind: value.hitl_kind,
    request_id: value.request_id,
    base_revision: value.base_revision as number,
    title: value.title,
    summary: value.summary,
    target_refs: value.target_refs,
    allowed_decisions: decisions as BackendHitlCard["allowed_decisions"],
    editable_fields: value.editable_fields,
    sections,
  };
}

export function parseBackendRunSnapshot(value: unknown): BackendRunSnapshot {
  if (!isRecord(value) || value.provider_kind !== "service" ||
      value.display_badge !== "실시간 AI 분석" ||
      typeof value.run_id !== "string" || !RUN_ID.test(value.run_id) ||
      !Number.isInteger(value.revision) || (value.revision as number) < 0 ||
      typeof value.workflow_status !== "string" ||
      !Number.isInteger(value.ui_phase) || (value.ui_phase as number) < 1 || (value.ui_phase as number) > 7 ||
      typeof value.pending_action !== "string" || !PENDING_ACTIONS.has(value.pending_action) ||
      !stringArray(value.allowed_actions) || typeof value.latest_event !== "string" ||
      !Number.isInteger(value.progress) || (value.progress as number) < 0 || (value.progress as number) > 100 ||
      !(value.result_ref === null || typeof value.result_ref === "string")) {
    throw new Error("invalid backend run snapshot");
  }
  const card = parseHitlCard(value.hitl_card);
  let error: BackendRunSnapshot["error"] = null;
  if (value.error !== null) {
    if (!isRecord(value.error) || typeof value.error.code !== "string" ||
        !ERROR_CODES.has(value.error.code as BackendErrorCode) ||
        typeof value.error.message !== "string" || typeof value.error.retryable !== "boolean") {
      throw new Error("invalid backend run error");
    }
    error = {
      code: value.error.code as BackendErrorCode,
      message: value.error.message,
      retryable: value.error.retryable,
    };
  }
  if ((value.pending_action === "human_response") !== (card !== null)) {
    throw new Error("backend HITL state is inconsistent");
  }
  return {
    provider_kind: "service",
    display_badge: "실시간 AI 분석",
    run_id: value.run_id,
    revision: value.revision as number,
    workflow_status: value.workflow_status,
    ui_phase: value.ui_phase as BackendRunSnapshot["ui_phase"],
    pending_action: value.pending_action as BackendRunSnapshot["pending_action"],
    allowed_actions: value.allowed_actions,
    latest_event: value.latest_event,
    progress: value.progress as number,
    result_ref: value.result_ref as string | null,
    hitl_card: card,
    error,
  };
}

export function parseBackendHealth(value: unknown): BackendHealth {
  if (!isRecord(value) || value.status !== "ok" || typeof value.ai_ready !== "boolean" || value.model !== "gpt-5.6") {
    throw new Error("invalid backend health response");
  }
  return { status: "ok", ai_ready: value.ai_ready, model: "gpt-5.6" };
}

export function parseBackendReport(value: unknown): BackendReport {
  if (!isRecord(value) || !isRecord(value.bundle) || !isRecord(value.eligibility)) {
    throw new Error("invalid backend report response");
  }
  return { bundle: value.bundle, eligibility: value.eligibility };
}
