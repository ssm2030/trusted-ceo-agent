// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import {
  AnalysisBackendClient,
  AnalysisBackendError,
  createAnalysisBackendConfig,
} from "@/lib/server/analysis/backend-client";

const TOKEN = "t".repeat(43);

describe("AnalysisBackendClient", () => {
  it("accepts only an exact IPv4-loopback base URL and a private token", () => {
    expect(() => createAnalysisBackendConfig({
      baseUrl: "http://127.0.0.1:8765",
      internalToken: TOKEN,
      timeoutMs: 2_000,
    })).not.toThrow();
    for (const baseUrl of [
      "http://localhost:8765",
      "http://0.0.0.0:8765",
      "https://127.0.0.1:8765",
      "http://127.0.0.1:8765/path",
    ]) {
      expect(() => createAnalysisBackendConfig({
        baseUrl,
        internalToken: TOKEN,
        timeoutMs: 2_000,
      })).toThrow();
    }
  });

  it("adds the internal token only on the server hop and validates snapshots", async () => {
    const fetchImpl = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
      expect(new Headers(init?.headers).get("X-Trusted-Ceo-Internal-Token")).toBe(TOKEN);
      return Response.json({
        provider_kind: "service",
        display_badge: "실시간 AI 분석",
        run_id: "run_20260719T000000Z_0123456789abcdef",
        revision: 1,
        workflow_status: "context_confirmation_required",
        ui_phase: 1,
        pending_action: "provider_work",
        allowed_actions: ["continue"],
        latest_event: "분석 목표 확인을 기다리고 있습니다.",
        progress: 10,
        result_ref: null,
        hitl_card: null,
        error: null,
      }, { headers: { "Cache-Control": "no-store" } });
    });
    const client = new AnalysisBackendClient(createAnalysisBackendConfig({
      baseUrl: "http://127.0.0.1:8765",
      internalToken: TOKEN,
      timeoutMs: 2_000,
    }), { fetchImpl });

    const snapshot = await client.createRun({
      expected_revision: 0,
      idempotency_key: "create_backend_test_0001",
    });

    expect(snapshot.provider_kind).toBe("service");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("posts questions and deserializes the actual Python snapshot contract", async () => {
    const runId = "run_20260719T000000Z_0123456789abcdef";
    const pythonSnapshot = {
      request_id: "questionrequest_" + "a".repeat(24),
      run_id: runId,
      revision: 2,
      generation: 0,
      state: "queued",
      scope_kind: "issue",
      scope_instance_id: "issue_main",
      answer: null,
      scope_suggestions: [],
      error_code: null,
      retryable: false,
    };
    const fetchImpl = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      expect(new Headers(init?.headers).get("X-Trusted-Ceo-Internal-Token")).toBe(TOKEN);
      expect(String(url)).toContain(`/v1/runs/${runId}/questions`);
      if (init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual({
          expected_revision: 2,
          idempotency_key: "question_backend_test_0001",
          question: "What is supported?",
          scope_kind: "issue",
          scope_instance_id: "issue_main",
          privacy_classification: "poc_deidentified",
        });
      }
      return Response.json(pythonSnapshot);
    });
    const client = new AnalysisBackendClient(createAnalysisBackendConfig({
      baseUrl: "http://127.0.0.1:8765",
      internalToken: TOKEN,
      timeoutMs: 2_000,
    }), { fetchImpl });

    const started = await client.startQuestion(runId, {
      expected_revision: 2,
      idempotency_key: "question_backend_test_0001",
      question: "What is supported?",
      scope_kind: "issue",
      scope_instance_id: "issue_main",
      privacy_classification: "poc_deidentified",
    });
    const loaded = await client.getQuestion(runId, pythonSnapshot.request_id);

    expect(started).toEqual(pythonSnapshot);
    expect(loaded).toEqual(pythonSnapshot);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });
  it("rejects non-JSON, oversized, malformed and secret-bearing failures", async () => {
    const responses = [
      new Response("html", { status: 502, headers: { "content-type": "text/html" } }),
      Response.json({ provider_kind: "plugin" }),
      Response.json({
        code: "AI_AUTH_FAILURE",
        message: `SDK failed with ${TOKEN}`,
        retryable: false,
      }, { status: 503 }),
    ];
    const client = new AnalysisBackendClient(createAnalysisBackendConfig({
      baseUrl: "http://127.0.0.1:8765",
      internalToken: TOKEN,
      timeoutMs: 2_000,
    }), { fetchImpl: vi.fn(async () => responses.shift()!) });

    await expect(client.getRun("run_20260719T000000Z_0123456789abcdef"))
      .rejects.toBeInstanceOf(AnalysisBackendError);
    await expect(client.getRun("run_20260719T000000Z_0123456789abcdef"))
      .rejects.toMatchObject({ code: "ENGINE_FAILURE" });
    try {
      await client.getRun("run_20260719T000000Z_0123456789abcdef");
      throw new Error("expected backend failure");
    } catch (error) {
      expect(error).toBeInstanceOf(AnalysisBackendError);
      expect(String(error)).not.toContain(TOKEN);
    }
  });
});
