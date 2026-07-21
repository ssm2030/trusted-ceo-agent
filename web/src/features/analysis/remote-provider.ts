import type {
  AnalysisProvider,
  HitlDecision,
  PendingAction,
  ProviderErrorCode,
  ProviderSnapshot,
} from "@/features/analysis/analysis-provider";
import type {
  AnalysisUpload,
  UploadedFileSummary,
} from '@/features/analysis/analysis-model';
import { isSafeUploadLogicalPath } from '@/lib/analysis-upload-path';

type FetchLike = (input: string | URL | Request, init?: RequestInit) => Promise<Response>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

const SOURCE_ID = /^source_[0-9a-f]{24}$/u;
const CONTROL = /[\u0000-\u001F\u007F]/u;

function parseUploadedFiles(value: unknown): UploadedFileSummary[] | null {
  if (!Array.isArray(value) || value.length > 64) return null;
  const seen = new Set<string>();
  const summaries: UploadedFileSummary[] = [];
  for (const item of value) {
    if (!isRecord(item) || typeof item.source_id !== 'string' || !SOURCE_ID.test(item.source_id) ||
        typeof item.logical_path !== 'string' || !isSafeUploadLogicalPath(item.logical_path) ||
        typeof item.display_name !== 'string' ||
        item.display_name !== item.logical_path.split('/').at(-1) ||
        typeof item.media_type !== 'string' || item.media_type.length < 1 || item.media_type.length > 128 ||
        !Number.isInteger(item.size_bytes) || (item.size_bytes as number) < 0 ||
        typeof item.collection_label !== 'string' || item.collection_label.length < 1 ||
        item.collection_label.length > 512 || CONTROL.test(item.collection_label)) {
      return null;
    }
    const expectedCollection = item.logical_path.includes('/')
      ? item.logical_path.split('/', 1)[0]
      : '\uac1c\ubcc4 \ud30c\uc77c';
    if (item.collection_label !== expectedCollection || seen.has(item.logical_path)) return null;
    seen.add(item.logical_path);
    summaries.push(item as UploadedFileSummary);
  }
  return summaries;
}

function parseSnapshot(value: unknown): ProviderSnapshot {
  const uploadedFiles = isRecord(value) ? parseUploadedFiles(value.uploaded_files) : null;
  if (!isRecord(value) || value.provider_kind !== "service" ||
      value.display_badge !== "실시간 AI 분석" || typeof value.run_id !== "string" ||
      !Number.isInteger(value.revision) || typeof value.workflow_status !== "string" ||
      !Number.isInteger(value.ui_phase) || typeof value.pending_action !== "string" ||
      !Array.isArray(value.allowed_actions) || typeof value.latest_event !== "string" ||
      !Number.isInteger(value.progress) ||
      !(value.result_ref === null || typeof value.result_ref === "string") ||
      !(value.pending_approval_request_id === null || typeof value.pending_approval_request_id === "string") ||
      uploadedFiles === null) {
    throw new RemoteProviderError("CONTRACT_FAILURE", "분석 서비스 응답 형식이 올바르지 않습니다.", 502);
  }
  return { ...value, uploaded_files: uploadedFiles } as unknown as ProviderSnapshot;
}

function errorBody(value: unknown): { code: ProviderErrorCode; message: string } {
  if (!isRecord(value) || typeof value.code !== "string" || typeof value.message !== "string") {
    return { code: "ENGINE_FAILURE", message: "분석 서비스를 사용할 수 없습니다." };
  }
  return { code: value.code as ProviderErrorCode, message: value.message };
}

function mutationKey(prefix: string): string {
  const uuid = globalThis.crypto.randomUUID().replaceAll("-", "_");
  return `web_${prefix}_${uuid}`;
}

export class RemoteProviderError extends Error {
  constructor(
    readonly code: ProviderErrorCode,
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "RemoteProviderError";
  }
}

export class RemoteAnalysisProvider implements AnalysisProvider {
  private readonly fetchImpl: FetchLike;
  private csrfToken: string | null = null;

  constructor(dependencies: { fetchImpl?: FetchLike } = {}) {
    this.fetchImpl = dependencies.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  private async ensureSession(): Promise<string> {
    if (this.csrfToken !== null) return this.csrfToken;
    const response = await this.fetchImpl("/api/report/session", {
      method: "POST",
      cache: "no-store",
      credentials: "same-origin",
    });
    let value: unknown;
    try { value = await response.json(); } catch { value = null; }
    if (!response.ok || !isRecord(value) || typeof value.csrfToken !== "string" || value.csrfToken.length === 0) {
      throw new RemoteProviderError("ENGINE_FAILURE", "로컬 보안 세션을 시작할 수 없습니다.", response.status);
    }
    this.csrfToken = value.csrfToken;
    return this.csrfToken;
  }

  private async parseResponse(response: Response): Promise<ProviderSnapshot> {
    let value: unknown;
    try { value = await response.json(); } catch { value = null; }
    if (!response.ok) {
      const failure = errorBody(value);
      throw new RemoteProviderError(failure.code, failure.message, response.status);
    }
    return parseSnapshot(value);
  }

  private async mutation(
    url: string,
    body: string | FormData,
    runIdForStale?: string,
  ): Promise<ProviderSnapshot> {
    const csrf = await this.ensureSession();
    const headers = new Headers({ "x-csrf-token": csrf });
    if (typeof body === "string") headers.set("content-type", "application/json");
    let lastNetworkError: unknown;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const response = await this.fetchImpl(url, {
          method: "POST",
          headers,
          body,
          cache: "no-store",
          credentials: "same-origin",
        });
        if (response.status === 409 && runIdForStale !== undefined) {
          let failure: { code: ProviderErrorCode; message: string } = {
            code: "STALE_REVISION",
            message: "화면의 실행 정보가 오래되었습니다.",
          };
          try { failure = errorBody(await response.json()); } catch { /* safe default */ }
          const current = await this.getStatus(runIdForStale);
          return { ...current, error: { code: failure.code, message: failure.message } };
        }
        return await this.parseResponse(response);
      } catch (error) {
        if (error instanceof RemoteProviderError) throw error;
        lastNetworkError = error;
      }
    }
    void lastNetworkError;
    throw new RemoteProviderError("AI_TRANSIENT_FAILURE", "로컬 분석 서비스 연결이 일시적으로 끊겼습니다.", 503);
  }

  private async read(url: string): Promise<ProviderSnapshot> {
    await this.ensureSession();
    const response = await this.fetchImpl(url, {
      method: "GET",
      cache: "no-store",
      credentials: "same-origin",
    });
    return this.parseResponse(response);
  }

  async getHealth(): Promise<{
    status: "ok";
    aiReady: boolean;
    model: "gpt-5.6";
  }> {
    await this.ensureSession();
    const response = await this.fetchImpl("/api/analysis/health", {
      method: "GET",
      cache: "no-store",
      credentials: "same-origin",
    });
    let value: unknown;
    try { value = await response.json(); } catch { value = null; }
    if (
      !response.ok ||
      !isRecord(value) ||
      value.status !== "ok" ||
      typeof value.ai_ready !== "boolean" ||
      value.model !== "gpt-5.6"
    ) {
      const failure = errorBody(value);
      throw new RemoteProviderError(failure.code, failure.message, response.status);
    }
    return {
      status: "ok",
      aiReady: value.ai_ready,
      model: "gpt-5.6",
    };
  }
  async createRun(): Promise<ProviderSnapshot> {
    const body = JSON.stringify({
      expected_revision: 0,
      idempotency_key: mutationKey("create"),
    });
    return this.mutation("/api/analysis/runs", body);
  }

  async attachData(
    runId: string,
    expectedRevision: number,
    uploads: AnalysisUpload[],
  ): Promise<ProviderSnapshot> {
    const form = new FormData();
    form.set("expected_revision", String(expectedRevision));
    form.set("idempotency_key", mutationKey("upload"));
    for (const upload of uploads) {
      form.append('files', upload.file, upload.file.name);
      form.append('logical_paths', upload.logicalPath);
    }
    return this.mutation(`/api/analysis/runs/${encodeURIComponent(runId)}/files`, form, runId);
  }

  async submitDecision(
    runId: string,
    expectedRevision: number,
    decision: HitlDecision,
    edits: Readonly<Record<string, unknown>> = {},
    rationale: string | null = null,
  ): Promise<ProviderSnapshot> {
    if (decision === "stop") {
      return this.stop(runId, expectedRevision);
    }
    const body = JSON.stringify({
      expected_revision: expectedRevision,
      idempotency_key: mutationKey("hitl"),
      decision,
      edits,
      rationale,
    });
    return this.mutation(`/api/analysis/runs/${encodeURIComponent(runId)}/human-responses`, body, runId);
  }

  submitHumanResponse(runId: string, expectedRevision: number, response: string): Promise<ProviderSnapshot> {
    return this.submitDecision(runId, expectedRevision, "approve", {}, response.trim() || null);
  }

  requestChanges(runId: string, expectedRevision: number): Promise<ProviderSnapshot> {
    return this.submitDecision(runId, expectedRevision, "reanalyze", {}, "웹에서 재분석을 요청했습니다.");
  }

  startOrContinue(runId: string, expectedRevision: number): Promise<ProviderSnapshot> {
    return this.action(runId, expectedRevision, "continue");
  }

  prepareTerminalApprovalRequest(runId: string, expectedRevision: number): Promise<ProviderSnapshot> {
    return this.startOrContinue(runId, expectedRevision);
  }

  getStatus(runId: string): Promise<ProviderSnapshot> {
    return this.read(`/api/analysis/runs/${encodeURIComponent(runId)}`);
  }

  async getPendingAction(runId: string): Promise<PendingAction> {
    return (await this.getStatus(runId)).pending_action;
  }

  async getTerminalApprovalInstruction(runId: string): Promise<string | null> {
    void runId;
    return null;
  }

  private action(runId: string, expectedRevision: number, action: string): Promise<ProviderSnapshot> {
    const body = JSON.stringify({
      expected_revision: expectedRevision,
      idempotency_key: mutationKey(action),
    });
    return this.mutation(`/api/analysis/runs/${encodeURIComponent(runId)}/actions/${action}`, body, runId);
  }

  retry(runId: string, expectedRevision: number): Promise<ProviderSnapshot> {
    return this.action(runId, expectedRevision, "retry");
  }
  resume(runId: string, expectedRevision: number): Promise<ProviderSnapshot> {
    return this.action(runId, expectedRevision, "resume");
  }
  stop(runId: string, expectedRevision: number): Promise<ProviderSnapshot> {
    return this.action(runId, expectedRevision, "stop");
  }
  cancel(runId: string, expectedRevision: number): Promise<ProviderSnapshot> {
    return this.action(runId, expectedRevision, "cancel");
  }

  async deleteRun(runId: string, expectedRevision: number): Promise<void> {
    const csrf = await this.ensureSession();
    const body = JSON.stringify({
      expected_revision: expectedRevision,
      idempotency_key: mutationKey("delete"),
      confirmed: true,
    });
    const response = await this.fetchImpl(`/api/analysis/runs/${encodeURIComponent(runId)}`, {
      method: "DELETE",
      headers: { "content-type": "application/json", "x-csrf-token": csrf },
      body,
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) {
      let value: unknown;
      try { value = await response.json(); } catch { value = null; }
      const failure = errorBody(value);
      throw new RemoteProviderError(failure.code, failure.message, response.status);
    }
  }

  async openFinalizedReport(runId: string): Promise<string | null> {
    await this.ensureSession();
    const response = await this.fetchImpl(
      `/api/analysis/runs/${encodeURIComponent(runId)}/report`,
      {
        method: "GET",
        cache: "no-store",
        credentials: "same-origin",
      },
    );
    if (!response.ok) {
      let value: unknown;
      try { value = await response.json(); } catch { value = null; }
      const failure = errorBody(value);
      throw new RemoteProviderError(failure.code, failure.message, response.status);
    }
    return "/report";
  }
}
