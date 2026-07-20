import type {
  AnalysisBackend,
  BackendErrorCode,
  BackendHealth,
  BackendHitlDecision,
  BackendMutation,
  BackendQuestionRequest,
  BackendQuestionSnapshot,
  BackendReport,
  BackendRunSnapshot,
} from "@/lib/server/analysis/types";
import {
  isRecord,
  parseBackendHealth,
  parseBackendQuestionSnapshot,
  parseBackendReport,
  parseBackendRunSnapshot,
} from "@/lib/server/analysis/types";

const TOKEN_PATTERN = /^[A-Za-z0-9_-]{32,256}$/u;
const BASE_URL_PATTERN = /^http:\/\/127\.0\.0\.1:([1-9][0-9]{0,4})$/u;
const RUN_ID_PATTERN = /^run_[A-Za-z0-9_-]{8,200}$/u;
const QUESTION_REQUEST_ID_PATTERN = /^questionrequest_[0-9a-f]{24}$/u;
const MAX_RESPONSE_BYTES = 64 * 1024 * 1024;

export type AnalysisBackendConfig = Readonly<{
  baseUrl: `http://127.0.0.1:${number}`;
  internalToken: string;
  timeoutMs: number;
}>;

type FetchLike = (input: string | URL | Request, init?: RequestInit) => Promise<Response>;

export class AnalysisBackendError extends Error {
  constructor(
    readonly code: BackendErrorCode,
    readonly status: number,
    readonly retryable: boolean,
  ) {
    super(code === "AI_AUTH_FAILURE" ? "OpenAI API key is required" : "AI service request failed");
    this.name = "AnalysisBackendError";
  }
}

export function createAnalysisBackendConfig(input: {
  baseUrl: string;
  internalToken: string;
  timeoutMs: number;
}): AnalysisBackendConfig {
  const match = BASE_URL_PATTERN.exec(input.baseUrl);
  const port = match === null ? 0 : Number(match[1]);
  if (match === null || port < 1 || port > 65_535) {
    throw new Error("analysis backend must use exact IPv4 loopback");
  }
  if (!TOKEN_PATTERN.test(input.internalToken)) {
    throw new Error("analysis backend internal token is invalid");
  }
  if (!Number.isInteger(input.timeoutMs) || input.timeoutMs < 100 || input.timeoutMs > 120_000) {
    throw new Error("analysis backend timeout is invalid");
  }
  return Object.freeze({
    baseUrl: input.baseUrl as AnalysisBackendConfig["baseUrl"],
    internalToken: input.internalToken,
    timeoutMs: input.timeoutMs,
  });
}

function safeRunId(runId: string): string {
  if (!RUN_ID_PATTERN.test(runId)) throw new AnalysisBackendError("INPUT_POLICY_FAILURE", 422, false);
  return encodeURIComponent(runId);
}

function safeQuestionRequestId(requestId: string): string {
  if (!QUESTION_REQUEST_ID_PATTERN.test(requestId)) {
    throw new AnalysisBackendError("INPUT_POLICY_FAILURE", 422, false);
  }
  return encodeURIComponent(requestId);
}

function parsedError(value: unknown): { code: BackendErrorCode; retryable: boolean } {
  if (!isRecord(value) || typeof value.code !== "string" || typeof value.retryable !== "boolean") {
    return { code: "ENGINE_FAILURE", retryable: true };
  }
  return { code: value.code as BackendErrorCode, retryable: value.retryable };
}

export class AnalysisBackendClient implements AnalysisBackend {
  private readonly fetchImpl: FetchLike;

  constructor(
    private readonly config: AnalysisBackendConfig,
    dependencies: { fetchImpl?: FetchLike } = {},
  ) {
    this.fetchImpl = dependencies.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  private async request<T>(
    path: string,
    init: RequestInit,
    parse: (value: unknown) => T,
  ): Promise<T> {
    if (!path.startsWith("/") || path.includes("..") || path.includes("://")) {
      throw new AnalysisBackendError("INPUT_POLICY_FAILURE", 422, false);
    }
    const headers = new Headers(init.headers);
    headers.set("X-Trusted-Ceo-Internal-Token", this.config.internalToken);
    headers.set("accept", "application/json");
    try {
      const response = await this.fetchImpl(`${this.config.baseUrl}${path}`, {
        ...init,
        cache: "no-store",
        headers,
        signal: init.signal ?? AbortSignal.timeout(this.config.timeoutMs),
      });
      if (response.status === 204) return undefined as T;
      const contentType = response.headers.get("content-type") ?? "";
      const declared = Number(response.headers.get("content-length") ?? "0");
      if (!contentType.toLowerCase().startsWith("application/json") ||
          (Number.isFinite(declared) && declared > MAX_RESPONSE_BYTES)) {
        throw new AnalysisBackendError("ENGINE_FAILURE", 502, true);
      }
      const bytes = new Uint8Array(await response.arrayBuffer());
      if (bytes.byteLength > MAX_RESPONSE_BYTES) {
        throw new AnalysisBackendError("ENGINE_FAILURE", 502, true);
      }
      let value: unknown;
      try {
        value = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
      } catch {
        throw new AnalysisBackendError("ENGINE_FAILURE", 502, true);
      }
      if (!response.ok) {
        const failure = parsedError(value);
        throw new AnalysisBackendError(failure.code, response.status, failure.retryable);
      }
      try {
        return parse(value);
      } catch {
        throw new AnalysisBackendError("ENGINE_FAILURE", 502, true);
      }
    } catch (error) {
      if (error instanceof AnalysisBackendError) throw error;
      throw new AnalysisBackendError("AI_TRANSIENT_FAILURE", 503, true);
    }
  }

  private json<T>(path: string, method: string, body: unknown, parse: (value: unknown) => T): Promise<T> {
    return this.request(path, {
      method,
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }, parse);
  }

  getHealth(): Promise<BackendHealth> {
    return this.request("/health", { method: "GET" }, parseBackendHealth);
  }
  createRun(input: BackendMutation & { mission?: Record<string, unknown> }): Promise<BackendRunSnapshot> {
    return this.json("/v1/runs", "POST", input, parseBackendRunSnapshot);
  }
  uploadFiles(runId: string, form: FormData): Promise<BackendRunSnapshot> {
    return this.request(`/v1/runs/${safeRunId(runId)}/files`, { method: "POST", body: form }, parseBackendRunSnapshot);
  }
  getRun(runId: string): Promise<BackendRunSnapshot> {
    return this.request(`/v1/runs/${safeRunId(runId)}`, { method: "GET" }, parseBackendRunSnapshot);
  }
  continueRun(runId: string, input: BackendMutation): Promise<BackendRunSnapshot> {
    return this.json(`/v1/runs/${safeRunId(runId)}/actions/continue`, "POST", input, parseBackendRunSnapshot);
  }
  retry(runId: string, input: BackendMutation): Promise<BackendRunSnapshot> {
    return this.json(`/v1/runs/${safeRunId(runId)}/actions/retry`, "POST", input, parseBackendRunSnapshot);
  }
  resume(runId: string, input: BackendMutation): Promise<BackendRunSnapshot> {
    return this.json(`/v1/runs/${safeRunId(runId)}/actions/resume`, "POST", input, parseBackendRunSnapshot);
  }
  stop(runId: string, input: BackendMutation): Promise<BackendRunSnapshot> {
    return this.json(`/v1/runs/${safeRunId(runId)}/actions/stop`, "POST", input, parseBackendRunSnapshot);
  }
  cancel(runId: string, input: BackendMutation): Promise<BackendRunSnapshot> {
    return this.json(`/v1/runs/${safeRunId(runId)}/actions/cancel`, "POST", input, parseBackendRunSnapshot);
  }
  submitHitl(runId: string, input: BackendHitlDecision, browserFingerprint: string): Promise<BackendRunSnapshot> {
    return this.request(`/v1/runs/${safeRunId(runId)}/human-responses`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "X-Trusted-Ceo-Browser-Fingerprint": browserFingerprint,
      },
      body: JSON.stringify(input),
    }, parseBackendRunSnapshot);
  }
  getReport(runId: string): Promise<BackendReport> {
    return this.request(`/v1/runs/${safeRunId(runId)}/report`, { method: "GET" }, parseBackendReport);
  }
  startQuestion(
    runId: string,
    input: BackendQuestionRequest,
  ): Promise<BackendQuestionSnapshot> {
    return this.json(
      `/v1/runs/${safeRunId(runId)}/questions`,
      "POST",
      input,
      parseBackendQuestionSnapshot,
    );
  }
  getQuestion(runId: string, requestId: string): Promise<BackendQuestionSnapshot> {
    return this.request(
      `/v1/runs/${safeRunId(runId)}/questions/${safeQuestionRequestId(requestId)}`,
      { method: "GET" },
      parseBackendQuestionSnapshot,
    );
  }
  deleteRun(runId: string, input: BackendMutation & { confirmed: true }): Promise<void> {
    return this.request(`/v1/runs/${safeRunId(runId)}`, {
      method: "DELETE",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(input),
    }, () => undefined);
  }
}
