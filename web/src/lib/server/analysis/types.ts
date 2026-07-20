import type {
  ResultAnswerV1,
} from "../../../../../contracts/web-report/v1/generated/types";
import {
  SCOPE_KINDS,
  type ScopeKind,
} from "@/lib/server/questions/types";
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

export type BackendQuestionState =
  | "queued"
  | "preparing"
  | "asking"
  | "validating"
  | "completed"
  | "scope_required"
  | "failed"
  | "cancelled";

export type BackendQuestionRequest = BackendMutation & Readonly<{
  question: string;
  scope_kind: ScopeKind;
  scope_instance_id: string;
  privacy_classification: "poc_deidentified" | "company_restricted";
}>;

export type BackendQuestionSnapshot = Readonly<{
  request_id: string;
  run_id: string;
  revision: number;
  generation: number;
  state: BackendQuestionState;
  scope_kind: ScopeKind;
  scope_instance_id: string;
  answer: ResultAnswerV1 | null;
  scope_suggestions: readonly Readonly<{
    scope_kind: ScopeKind;
    scope_instance_id: string;
  }>[];
  error_code: string | null;
  retryable: boolean;
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
  startQuestion(
    runId: string,
    input: BackendQuestionRequest,
  ): Promise<BackendQuestionSnapshot>;
  getQuestion(
    runId: string,
    requestId: string,
  ): Promise<BackendQuestionSnapshot>;
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

const QUESTION_STATES = new Set<BackendQuestionState>([
  "queued", "preparing", "asking", "validating", "completed",
  "scope_required", "failed", "cancelled",
]);
const QUESTION_REQUEST_ID = /^questionrequest_[0-9a-f]{24}$/u;
const QUESTION_KEYS = [
  "answer", "error_code", "generation", "request_id", "retryable",
  "revision", "run_id", "scope_instance_id", "scope_kind",
  "scope_suggestions", "state",
] as const;

function exactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
): boolean {
  const actual = Object.keys(value).sort();
  return actual.length === expected.length &&
    actual.every((key, index) => key === expected[index]);
}

function parseQuestionAnswer(
  value: unknown,
  runId: string,
  revision: number,
): ResultAnswerV1 | null {
  if (value === null) return null;
  if (!isRecord(value) || value.answer_version !== "1.0.0" ||
      typeof value.job_id !== "string" || value.run_id !== runId ||
      value.revision !== revision || !isRecord(value.scope) ||
      !isRecord(value.validation) || !Array.isArray(value.answer_blocks)) {
    throw new Error("invalid backend question answer");
  }
  return value as unknown as ResultAnswerV1;
}

export function parseBackendQuestionSnapshot(
  value: unknown,
): BackendQuestionSnapshot {
  if (!isRecord(value) || !exactKeys(value, QUESTION_KEYS) ||
      typeof value.request_id !== "string" ||
      !QUESTION_REQUEST_ID.test(value.request_id) ||
      typeof value.run_id !== "string" || !RUN_ID.test(value.run_id) ||
      !Number.isInteger(value.revision) || (value.revision as number) < 1 ||
      !Number.isInteger(value.generation) || (value.generation as number) < 0 ||
      typeof value.state !== "string" ||
      !QUESTION_STATES.has(value.state as BackendQuestionState) ||
      typeof value.scope_kind !== "string" ||
      !SCOPE_KINDS.includes(value.scope_kind as ScopeKind) ||
      typeof value.scope_instance_id !== "string" ||
      value.scope_instance_id.length < 1 || value.scope_instance_id.length > 500 ||
      !Array.isArray(value.scope_suggestions) ||
      !(value.error_code === null ||
        (typeof value.error_code === "string" && value.error_code.length <= 100)) ||
      typeof value.retryable !== "boolean") {
    throw new Error("invalid backend question snapshot");
  }
  const suggestions = value.scope_suggestions.map((item) => {
    if (!isRecord(item) ||
        !exactKeys(item, ["scope_instance_id", "scope_kind"]) ||
        typeof item.scope_kind !== "string" ||
        !SCOPE_KINDS.includes(item.scope_kind as ScopeKind) ||
        typeof item.scope_instance_id !== "string" ||
        item.scope_instance_id.length < 1 || item.scope_instance_id.length > 500) {
      throw new Error("invalid backend scope suggestion");
    }
    return Object.freeze({
      scope_kind: item.scope_kind as ScopeKind,
      scope_instance_id: item.scope_instance_id,
    });
  });
  const answer = parseQuestionAnswer(
    value.answer,
    value.run_id,
    value.revision as number,
  );
  const state = value.state as BackendQuestionState;
  const active = ["queued", "preparing", "asking", "validating"].includes(state);
  if ((active && (answer !== null || suggestions.length > 0 ||
        value.error_code !== null || value.retryable)) ||
      (state === "completed" && (answer === null || suggestions.length > 0 ||
        value.error_code !== null || value.retryable)) ||
      (state === "scope_required" && (answer !== null || suggestions.length === 0 ||
        value.error_code !== "SCOPE_REQUIRED" || value.retryable)) ||
      (["failed", "cancelled"].includes(state) &&
        (answer !== null || suggestions.length > 0 || value.error_code === null))) {
    throw new Error("inconsistent backend question snapshot");
  }
  return Object.freeze({
    request_id: value.request_id,
    run_id: value.run_id,
    revision: value.revision as number,
    generation: value.generation as number,
    state,
    scope_kind: value.scope_kind as ScopeKind,
    scope_instance_id: value.scope_instance_id,
    answer,
    scope_suggestions: Object.freeze(suggestions),
    error_code: value.error_code as string | null,
    retryable: value.retryable,
  });
}