// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import {
  answerResultQuestionThroughService,
} from "@/lib/server/questions/service-question-bridge";
import {
  ScopeRequiredError,
} from "@/lib/server/questions/question-coordinator";
import type {
  QuestionRunContext,
  ResultAnswer,
} from "@/lib/server/questions/types";
import type {
  BackendQuestionSnapshot,
} from "@/lib/server/analysis/types";

const context: QuestionRunContext = {
  registrationId: "service:run:2",
  artifactRoot: "C:\\service-context",
  runId: "run_20260717T010203Z_0123456789abcdef",
  revision: 2,
  viewerMode: "trusted_final",
  privacyClassification: "poc_deidentified",
  bundleHash: "a".repeat(64),
};
const answer = {
  answer_version: "1.0.0",
  job_id: "job_01",
  run_id: context.runId,
  revision: context.revision,
  scope: {
    scope_kind: "issue",
    scope_instance_id: "issue_01",
    start_refs: ["issue_01"],
    issue_id: "issue_01",
  },
  validation: {
    schema_valid: true,
    references_valid: true,
    values_valid: true,
    semantic_entailment_verified: false,
    label_ko: "스키마·참조 검증 통과",
  },
  answer_blocks: [],
} as ResultAnswer;

function snapshot(
  state: BackendQuestionSnapshot["state"],
  overrides: Partial<BackendQuestionSnapshot> = {},
): BackendQuestionSnapshot {
  return {
    request_id: "questionrequest_" + "a".repeat(24),
    run_id: context.runId,
    revision: context.revision,
    generation: 0,
    state,
    scope_kind: "issue",
    scope_instance_id: "issue_01",
    answer: null,
    scope_suggestions: [],
    error_code: null,
    retryable: false,
    ...overrides,
  };
}

const input = {
  clientRequestId: "browser-request-01",
  context,
  question: "What is supported?",
  scope: {
    kind: "issue" as const,
    instanceId: "issue_01",
    issueId: "issue_01",
  },
  signal: new AbortController().signal,
};

describe("answerResultQuestionThroughService", () => {
  it("uses stable idempotency, mirrors service progress, and returns only the canonical answer", async () => {
    const states = [
      snapshot("asking"),
      snapshot("validating"),
      snapshot("completed", { answer }),
    ];
    const backend = {
      startQuestion: vi.fn(async () => snapshot("queued")),
      getQuestion: vi.fn(async () => states.shift()!),
    };
    const setState = vi.fn();

    const result = await answerResultQuestionThroughService(
      { ...input, setState },
      {
        backend,
        currentContext: () => context,
        wait: async () => undefined,
      },
    );

    expect(result).toEqual(answer);
    expect(backend.startQuestion).toHaveBeenCalledWith(
      context.runId,
      expect.objectContaining({
        expected_revision: context.revision,
        idempotency_key: expect.stringMatching(/^[0-9a-f]{64}$/u),
        question: input.question,
        scope_kind: "issue",
        scope_instance_id: "issue_01",
        privacy_classification: "poc_deidentified",
      }),
    );
    expect(setState.mock.calls.map(([state]) => state)).toEqual([
      "preparing",
      "asking",
      "validating",
    ]);
  });

  it("maps scope-required snapshots without publishing an answer", async () => {
    const backend = {
      startQuestion: vi.fn(async () => snapshot("scope_required", {
        scope_suggestions: [{
          scope_kind: "evidence",
          scope_instance_id: "evidence_01",
        }],
        error_code: "SCOPE_REQUIRED",
      })),
      getQuestion: vi.fn(),
    };

    await expect(answerResultQuestionThroughService(input, {
      backend,
      currentContext: () => context,
      wait: async () => undefined,
    })).rejects.toEqual(new ScopeRequiredError([
      { kind: "evidence", instanceId: "evidence_01" },
    ]));
    expect(backend.getQuestion).not.toHaveBeenCalled();
  });
});