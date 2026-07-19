import { describe, expect, it, vi } from "vitest";

import { RemoteAnalysisProvider } from "@/features/analysis/remote-provider";

function snapshot(revision = 1) {
  return {
    provider_kind: "service",
    display_badge: "실시간 AI 분석",
    run_id: "run_20260719T000000Z_0123456789abcdef",
    revision,
    workflow_status: "context_confirmation_required",
    ui_phase: 1,
    pending_action: "provider_work",
    pending_approval_request_id: null,
    allowed_actions: ["continue"],
    latest_event: "분석 목표 확인을 기다리고 있습니다.",
    progress: 10,
    result_ref: null,
    hitl_card: null,
    error: null,
  };
}

describe("RemoteAnalysisProvider", () => {
  it("bootstraps CSRF, never sends backend secrets, and reuses a mutation key on network retry", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    let createAttempts = 0;
    const fetchImpl = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      calls.push({ url, init });
      if (url === "/api/report/session") {
        return Response.json({ csrfToken: "csrf_test_only" });
      }
      createAttempts += 1;
      if (createAttempts === 1) {
        throw new TypeError("network reset");
      }
      return Response.json(snapshot());
    });
    const provider = new RemoteAnalysisProvider({ fetchImpl });

    const created = await provider.createRun();

    expect(created.provider_kind).toBe("service");
    const mutations = calls.filter((call) => call.url === "/api/analysis/runs");
    expect(mutations).toHaveLength(2);
    expect(mutations[0].init?.body).toBe(mutations[1].init?.body);
    for (const call of calls) {
      const headers = new Headers(call.init?.headers);
      expect(headers.has("X-Trusted-Ceo-Internal-Token")).toBe(false);
      expect(headers.has("OPENAI_API_KEY")).toBe(false);
    }
  });

  it("refreshes the canonical snapshot after a stale revision response", async () => {
    const fetchImpl = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url === "/api/report/session") {
        return Response.json({ csrfToken: "csrf_test_only" });
      }
      if (url.endsWith("/actions/continue")) {
        return Response.json({
          code: "STALE_REVISION",
          message: "request revision is stale",
          retryable: false,
        }, { status: 409 });
      }
      return Response.json(snapshot(4));
    });
    const provider = new RemoteAnalysisProvider({ fetchImpl });

    const refreshed = await provider.startOrContinue(
      "run_20260719T000000Z_0123456789abcdef",
      1,
    );

    expect(refreshed.revision).toBe(4);
    expect(refreshed.error?.code).toBe("STALE_REVISION");
  });
});
