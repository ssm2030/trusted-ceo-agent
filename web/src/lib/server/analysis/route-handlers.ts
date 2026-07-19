import { createHash } from "node:crypto";

import {
  AnalysisBackendError,
} from "@/lib/server/analysis/backend-client";
import type {
  AnalysisBackend,
  BackendHitlDecision,
  BackendMutation,
  BackendRunSnapshot,
} from "@/lib/server/analysis/types";
import { isRecord } from "@/lib/server/analysis/types";
import {
  CSRF_HEADER_NAME,
  LocalRequestSecurityError,
  assertLocalMutation,
  assertLocalSession,
  type LocalSecurityConfig,
} from "@/lib/server/local-request-security";

const JSON_LIMIT = 64 * 1024;
const MAX_FILES = 64;
const MAX_FILE_BYTES = 25 * 1024 * 1024;
const MAX_TOTAL_BYTES = 250 * 1024 * 1024;
const IDEMPOTENCY_KEY = /^[A-Za-z0-9_-]{16,128}$/u;
const SAFE_HEADERS = {
  "Cache-Control": "no-store",
  "Content-Security-Policy": "default-src 'none'; base-uri 'none'; frame-ancestors 'none'",
  "Content-Type": "application/json; charset=utf-8",
  "X-Content-Type-Options": "nosniff",
} as const;

export type AnalysisRouteDependencies = Readonly<{
  backend: AnalysisBackend;
  security: LocalSecurityConfig;
}>;

class AnalysisRequestError extends Error {
  constructor(message: string, readonly status: 400 | 413 | 415 | 422) {
    super(message);
  }
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: SAFE_HEADERS });
}

function safeError(error: unknown): Response {
  if (error instanceof LocalRequestSecurityError) {
    return jsonResponse({ message: error.message }, error.status);
  }
  if (error instanceof AnalysisRequestError) {
    return jsonResponse({ code: "INPUT_POLICY_FAILURE", message: error.message, retryable: false }, error.status);
  }
  if (error instanceof AnalysisBackendError) {
    return jsonResponse({ code: error.code, message: error.message, retryable: error.retryable }, error.status);
  }
  return jsonResponse({ code: "ENGINE_FAILURE", message: "분석 요청을 처리할 수 없습니다.", retryable: true }, 500);
}

async function readJson(request: Request): Promise<Record<string, unknown>> {
  if (!(request.headers.get("content-type") ?? "").toLowerCase().startsWith("application/json")) {
    throw new AnalysisRequestError("JSON 요청만 허용됩니다.", 415);
  }
  const declared = Number(request.headers.get("content-length") ?? "0");
  if (Number.isFinite(declared) && declared > JSON_LIMIT) {
    throw new AnalysisRequestError("요청 본문이 너무 큽니다.", 413);
  }
  const bytes = new Uint8Array(await request.arrayBuffer());
  if (bytes.byteLength > JSON_LIMIT) throw new AnalysisRequestError("요청 본문이 너무 큽니다.", 413);
  let value: unknown;
  try {
    value = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch {
    throw new AnalysisRequestError("요청 본문이 올바른 JSON이 아닙니다.", 400);
  }
  if (!isRecord(value)) throw new AnalysisRequestError("요청 본문은 객체여야 합니다.", 422);
  return value;
}

function mutation(value: Record<string, unknown>): BackendMutation {
  if (!Number.isInteger(value.expected_revision) || (value.expected_revision as number) < 0 ||
      typeof value.idempotency_key !== "string" || !IDEMPOTENCY_KEY.test(value.idempotency_key)) {
    throw new AnalysisRequestError("revision 또는 멱등 키가 올바르지 않습니다.", 422);
  }
  return {
    expected_revision: value.expected_revision as number,
    idempotency_key: value.idempotency_key,
  };
}

function browserSnapshot(value: BackendRunSnapshot): Record<string, unknown> {
  return {
    ...value,
    pending_approval_request_id: value.hitl_card?.request_id ?? null,
  };
}

export async function handleAnalysisHealth(
  request: Request,
  dependencies: AnalysisRouteDependencies,
): Promise<Response> {
  try {
    assertLocalSession(request.headers, dependencies.security);
    return jsonResponse(await dependencies.backend.getHealth());
  } catch (error) { return safeError(error); }
}

export async function handleAnalysisCreate(
  request: Request,
  dependencies: AnalysisRouteDependencies,
): Promise<Response> {
  try {
    assertLocalMutation(request.headers, dependencies.security);
    const value = await readJson(request);
    const input = mutation(value);
    const mission = value.mission;
    if (mission !== undefined && !isRecord(mission)) throw new AnalysisRequestError("mission이 올바르지 않습니다.", 422);
    const result = await dependencies.backend.createRun({ ...input, ...(mission === undefined ? {} : { mission }) });
    return jsonResponse(browserSnapshot(result));
  } catch (error) { return safeError(error); }
}

export async function handleAnalysisStatus(
  request: Request,
  runId: string,
  dependencies: AnalysisRouteDependencies,
): Promise<Response> {
  try {
    assertLocalSession(request.headers, dependencies.security);
    return jsonResponse(browserSnapshot(await dependencies.backend.getRun(runId)));
  } catch (error) { return safeError(error); }
}

export async function handleAnalysisFiles(
  request: Request,
  runId: string,
  dependencies: AnalysisRouteDependencies,
): Promise<Response> {
  try {
    assertLocalMutation(request.headers, dependencies.security);
    const declared = Number(request.headers.get("content-length") ?? "0");
    if (Number.isFinite(declared) && declared > MAX_TOTAL_BYTES + 1024 * 1024) {
      throw new AnalysisRequestError("업로드 전체 크기를 초과했습니다.", 413);
    }
    const form = await request.formData();
    const expected = form.get("expected_revision");
    const key = form.get("idempotency_key");
    if (typeof expected !== "string" || !/^[0-9]+$/u.test(expected) ||
        typeof key !== "string" || !IDEMPOTENCY_KEY.test(key)) {
      throw new AnalysisRequestError("업로드 revision 또는 멱등 키가 올바르지 않습니다.", 422);
    }
    const files = form.getAll("files");
    if (files.length < 1 || files.length > MAX_FILES || files.some((file) => !(file instanceof File))) {
      throw new AnalysisRequestError("업로드 파일 수가 올바르지 않습니다.", 422);
    }
    let total = 0;
    for (const file of files as File[]) {
      if (file.size < 1 || file.size > MAX_FILE_BYTES) throw new AnalysisRequestError("파일 크기 제한을 초과했습니다.", 413);
      total += file.size;
    }
    if (total > MAX_TOTAL_BYTES) throw new AnalysisRequestError("업로드 전체 크기를 초과했습니다.", 413);
    const backendForm = new FormData();
    backendForm.set("expected_revision", expected);
    backendForm.set("idempotency_key", key);
    for (const file of files as File[]) backendForm.append("files", file, file.name);
    return jsonResponse(browserSnapshot(await dependencies.backend.uploadFiles(runId, backendForm)));
  } catch (error) { return safeError(error); }
}

export async function handleAnalysisAction(
  request: Request,
  runId: string,
  action: string,
  dependencies: AnalysisRouteDependencies,
): Promise<Response> {
  try {
    assertLocalMutation(request.headers, dependencies.security);
    const input = mutation(await readJson(request));
    const handlers = {
      continue: dependencies.backend.continueRun.bind(dependencies.backend),
      retry: dependencies.backend.retry.bind(dependencies.backend),
      resume: dependencies.backend.resume.bind(dependencies.backend),
      stop: dependencies.backend.stop.bind(dependencies.backend),
      cancel: dependencies.backend.cancel.bind(dependencies.backend),
    } as const;
    const handler = handlers[action as keyof typeof handlers];
    if (handler === undefined) throw new AnalysisRequestError("지원하지 않는 실행 동작입니다.", 422);
    return jsonResponse(browserSnapshot(await handler(runId, input)));
  } catch (error) { return safeError(error); }
}

export async function handleAnalysisHumanResponse(
  request: Request,
  runId: string,
  dependencies: AnalysisRouteDependencies,
): Promise<Response> {
  try {
    assertLocalMutation(request.headers, dependencies.security);
    const value = await readJson(request);
    const base = mutation(value);
    if (!["approve", "approve_with_edits", "reanalyze", "stop"].includes(String(value.decision)) ||
        !isRecord(value.edits) || !(value.rationale === null || typeof value.rationale === "string")) {
      throw new AnalysisRequestError("웹 승인 응답이 올바르지 않습니다.", 422);
    }
    const csrf = request.headers.get(CSRF_HEADER_NAME);
    if (csrf === null) throw new AnalysisRequestError("웹 세션 지문을 만들 수 없습니다.", 422);
    const fingerprint = createHash("sha256").update(csrf, "utf8").digest("hex");
    const input: BackendHitlDecision = {
      ...base,
      decision: value.decision as BackendHitlDecision["decision"],
      edits: value.edits,
      rationale: value.rationale as string | null,
    };
    return jsonResponse(browserSnapshot(await dependencies.backend.submitHitl(runId, input, fingerprint)));
  } catch (error) { return safeError(error); }
}

export async function handleAnalysisReport(
  request: Request,
  runId: string,
  dependencies: AnalysisRouteDependencies,
): Promise<Response> {
  try {
    assertLocalSession(request.headers, dependencies.security);
    return jsonResponse(await dependencies.backend.getReport(runId));
  } catch (error) { return safeError(error); }
}

export async function handleAnalysisDelete(
  request: Request,
  runId: string,
  dependencies: AnalysisRouteDependencies,
): Promise<Response> {
  try {
    assertLocalMutation(request.headers, dependencies.security);
    const value = await readJson(request);
    const input = mutation(value);
    if (value.confirmed !== true) throw new AnalysisRequestError("삭제 확인이 필요합니다.", 422);
    await dependencies.backend.deleteRun(runId, { ...input, confirmed: true });
    return new Response(null, { status: 204, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } });
  } catch (error) { return safeError(error); }
}
