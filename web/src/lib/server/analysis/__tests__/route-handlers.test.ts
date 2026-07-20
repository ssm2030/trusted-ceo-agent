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
