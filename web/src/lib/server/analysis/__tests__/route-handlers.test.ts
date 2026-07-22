// @vitest-environment node
import { createHash } from "node:crypto";
import { describe, expect, it, vi } from "vitest";

import {
  CSRF_HEADER_NAME,
  SESSION_COOKIE_NAME,
  createLocalSecurityConfig,
  issueLocalSession,
} from "@/lib/server/local-request-security";
import {
  handleAnalysisCreate,
  handleAnalysisFiles,
  handleAnalysisHumanResponse,
  handleAnalysisReport,
} from "@/lib/server/analysis/route-handlers";
import type { AnalysisBackend } from "@/lib/server/analysis/types";

const security = createLocalSecurityConfig({
  port: 3000,
  sessionSecret: new Uint8Array(32).fill(7),
});

function mutationHeaders(): Headers {
  const session = issueLocalSession(security);
  return new Headers({
    host: security.host,
    origin: security.origin,
    cookie: `${SESSION_COOKIE_NAME}=${session.cookieValue}`,
    [CSRF_HEADER_NAME]: session.csrfToken,
    "content-type": "application/json",
  });
}

function snapshot() {
  return {
    provider_kind: "service" as const,
    display_badge: "실시간 AI 분석" as const,
    run_id: "run_20260719T000000Z_0123456789abcdef",
    revision: 1,
    workflow_status: "context_confirmation_required",
    ui_phase: 1 as const,
    pending_action: "provider_work" as const,
    allowed_actions: ["continue"],
    latest_event: "분석 목표 확인을 기다리고 있습니다.",
    progress: 10,
    result_ref: null,
    hitl_card: null,
    error: null,
    uploaded_files: [],
  };
}

function backend(): AnalysisBackend {
  return {
    cancel: vi.fn(),
    continueRun: vi.fn(),
    createRun: vi.fn(async () => snapshot()),
    deleteRun: vi.fn(),
    getHealth: vi.fn(),
    getQuestion: vi.fn(),
    getReport: vi.fn(),
    getRun: vi.fn(),
    resume: vi.fn(),
    retry: vi.fn(),
    stop: vi.fn(),
    startQuestion: vi.fn(),
    submitHitl: vi.fn(async () => snapshot()),
    uploadFiles: vi.fn(),
  };
}

describe("analysis BFF route handlers", () => {
  it("requires the existing local session and CSRF before creating a run", async () => {
    const service = backend();
    const body = JSON.stringify({
      expected_revision: 0,
      idempotency_key: "create_route_test_0001",
    });
    const denied = await handleAnalysisCreate(new Request(
      "http://127.0.0.1:3000/api/analysis/runs",
      { method: "POST", headers: { "content-type": "application/json" }, body },
    ), { backend: service, security, activateReport: vi.fn() });
    expect(denied.status).toBe(403);
    expect(service.createRun).not.toHaveBeenCalled();

    const accepted = await handleAnalysisCreate(new Request(
      "http://127.0.0.1:3000/api/analysis/runs",
      { method: "POST", headers: mutationHeaders(), body },
    ), { backend: service, security, activateReport: vi.fn() });
    expect(accepted.status).toBe(200);
    expect(accepted.headers.get("cache-control")).toBe("no-store");
    expect(JSON.stringify(await accepted.json())).not.toContain("Internal-Token");
  });

  it("derives a lowercase SHA-256 browser fingerprint without forwarding session secrets", async () => {
    const service = backend();
    const headers = mutationHeaders();
    const csrf = headers.get(CSRF_HEADER_NAME)!;
    const response = await handleAnalysisHumanResponse(new Request(
      "http://127.0.0.1:3000/api/analysis/runs/run_20260719T000000Z_0123456789abcdef/human-responses",
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          expected_revision: 2,
          idempotency_key: "approve_route_test_0001",
          decision: "approve",
          edits: {},
          rationale: null,
        }),
      },
    ), "run_20260719T000000Z_0123456789abcdef", { backend: service, security, activateReport: vi.fn() });

    expect(response.status).toBe(200);
    expect(service.submitHitl).toHaveBeenCalledWith(
      "run_20260719T000000Z_0123456789abcdef",
      expect.any(Object),
      createHash("sha256").update(csrf, "utf8").digest("hex"),
    );
  });

  it('forwards files with aligned logical paths and rejects count mismatches', async () => {
    const service = backend();
    vi.mocked(service.uploadFiles).mockResolvedValue(snapshot());
    const form = new FormData();
    form.set('expected_revision', '1');
    form.set('idempotency_key', 'upload_route_test_0001');
    form.append('files', new File(['# A'], 'a.md', { type: 'text/markdown' }));
    form.append('logical_paths', 'folder-a/a.md');
    form.append('files', new File(['x,y\n1,2\n'], 'b.csv', { type: 'text/csv' }));
    form.append('logical_paths', 'folder-b/b.csv');
    const headers = mutationHeaders();
    headers.delete('content-type');

    const response = await handleAnalysisFiles(new Request(
      'http://127.0.0.1:3000/api/analysis/runs/run_20260719T000000Z_0123456789abcdef/files',
      { method: 'POST', headers, body: form },
    ), 'run_20260719T000000Z_0123456789abcdef', {
      backend: service,
      security,
      activateReport: vi.fn(),
    });

    expect(response.status).toBe(200);
    const forwarded = vi.mocked(service.uploadFiles).mock.calls[0][1];
    expect((forwarded.getAll('files') as File[]).map((file) => file.name)).toEqual(['a.md', 'b.csv']);
    expect(forwarded.getAll('logical_paths')).toEqual(['folder-a/a.md', 'folder-b/b.csv']);

    const mismatchForm = new FormData();
    mismatchForm.set('expected_revision', '1');
    mismatchForm.set('idempotency_key', 'upload_route_test_0002');
    mismatchForm.append('files', new File(['# A'], 'a.md', { type: 'text/markdown' }));
    mismatchForm.append('files', new File(['# B'], 'b.md', { type: 'text/markdown' }));
    mismatchForm.append('logical_paths', 'folder-a/a.md');
    const mismatchHeaders = mutationHeaders();
    mismatchHeaders.delete('content-type');
    const mismatch = await handleAnalysisFiles(new Request(
      'http://127.0.0.1:3000/api/analysis/runs/run_20260719T000000Z_0123456789abcdef/files',
      { method: 'POST', headers: mismatchHeaders, body: mismatchForm },
    ), 'run_20260719T000000Z_0123456789abcdef', {
      backend: service,
      security,
      activateReport: vi.fn(),
    });

    expect(mismatch.status).toBe(422);
    expect(vi.mocked(service.uploadFiles)).toHaveBeenCalledTimes(1);
  });

  it("normalizes Unicode upload paths before forwarding them", async () => {
    const service = backend();
    vi.mocked(service.uploadFiles).mockResolvedValue(snapshot());
    const form = new FormData();
    form.set("expected_revision", "1");
    form.set("idempotency_key", "upload_route_unicode_0001");
    form.append(
      "files",
      new File(["# Plan"], "\u00e9.md", { type: "text/markdown" }),
    );
    form.append("logical_paths", "strategy/e\u0301.md");
    const headers = mutationHeaders();
    headers.delete("content-type");

    const response = await handleAnalysisFiles(
      new Request(
        "http://127.0.0.1:3000/api/analysis/runs/run_20260719T000000Z_0123456789abcdef/files",
        { method: "POST", headers, body: form },
      ),
      "run_20260719T000000Z_0123456789abcdef",
      { backend: service, security, activateReport: vi.fn() },
    );

    expect(response.status).toBe(200);
    const forwarded = vi.mocked(service.uploadFiles).mock.calls[0][1];
    expect(forwarded.getAll("logical_paths")).toEqual([
      "strategy/\u00e9.md",
    ]);
  });

  it.each([
    "../plan.md",
    "/absolute/plan.md",
    "C:/private/plan.md",
    "folder\\plan.md",
  ])("rejects unsafe upload path %s before calling the backend", async (path) => {
    const service = backend();
    const form = new FormData();
    form.set("expected_revision", "1");
    form.set("idempotency_key", "upload_route_unsafe_0001");
    form.append(
      "files",
      new File(["# Plan"], "plan.md", { type: "text/markdown" }),
    );
    form.append("logical_paths", path);
    const headers = mutationHeaders();
    headers.delete("content-type");

    const response = await handleAnalysisFiles(
      new Request(
        "http://127.0.0.1:3000/api/analysis/runs/run_20260719T000000Z_0123456789abcdef/files",
        { method: "POST", headers, body: form },
      ),
      "run_20260719T000000Z_0123456789abcdef",
      { backend: service, security, activateReport: vi.fn() },
    );

    expect(response.status).toBe(422);
    expect(service.uploadFiles).not.toHaveBeenCalled();
  });

  it("activates a validated service report before returning it", async () => {
    const service = backend();
    const report = {
      bundle: { bundle_version: "1.0.0" },
      eligibility: { decision_version: "1.0.0" },
    };
    vi.mocked(service.getReport).mockResolvedValue(report);
    const activateReport = vi.fn(async () => undefined);

    const response = await handleAnalysisReport(new Request(
      "http://127.0.0.1:3000/api/analysis/runs/run_20260719T000000Z_0123456789abcdef/report",
      { method: "GET", headers: mutationHeaders() },
    ), "run_20260719T000000Z_0123456789abcdef", {
      backend: service,
      security,
      activateReport,
    });

    expect(response.status).toBe(200);
    expect(activateReport).toHaveBeenCalledWith(report);
    expect(await response.json()).toEqual(report);
  });
});
