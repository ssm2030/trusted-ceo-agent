// @vitest-environment node
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  QuestionCoordinator,
  ScopeRequiredError,
} from "@/lib/server/questions/question-coordinator";
import type {
  QuestionRunContext,
  QuestionScope,
  ResultAnswer,
} from "@/lib/server/questions/types";

const roots: string[] = [];
const context: QuestionRunContext = {
  registrationId: "representative",
  artifactRoot: "C:\\runs\\representative",
  runId: "run_20260717T010203Z_0123456789abcdef",
  revision: 3,
  viewerMode: "trusted_final",
  privacyClassification: "company_restricted",
  bundleHash: "a".repeat(64),
};
const scope: QuestionScope = {
  kind: "issue",
  instanceId: "issue_main",
  issueId: "issue_main",
};
const answer = {
  answer_version: "1.0.0",
  answer_blocks: [],
} as unknown as ResultAnswer;

async function lockRoot(): Promise<string> {
  const root = await mkdtemp(
    path.join(tmpdir(), "trusted-ceo-coordinator-test-"),
  );
  roots.push(root);
  return root;
}

function submitted(
  clientRequestId: string,
  rateKey = "session-a",
) {
  return {
    clientRequestId,
    context,
    scope,
    question: "이 문제의 근거는 무엇인가요?",
    rateKey,
  };
}

async function waitFor(
  predicate: () => boolean,
  timeoutMs = 1000,
): Promise<void> {
  const started = Date.now();
  while (!predicate()) {
    if (Date.now() - started > timeoutMs) {
      throw new Error("condition was not reached");
    }
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
}

afterEach(async () => {
  await Promise.all(
    roots.splice(0).map((root) =>
      rm(root, { recursive: true, force: true }),
    ),
  );
});

describe("QuestionCoordinator", () => {
  it("passes the stable client request ID to the answer service", async () => {
    const answerQuestion = vi.fn(async () => answer);
    const coordinator = new QuestionCoordinator({
      lockRoot: await lockRoot(),
      answer: answerQuestion,
    });

    const request = await coordinator.submit(submitted("stable-client-id"));
    await waitFor(
      () => coordinator.get(request.requestId)?.state === "completed",
    );

    expect(answerQuestion).toHaveBeenCalledWith(
      expect.objectContaining({ clientRequestId: "stable-client-id" }),
    );
  });
  it("runs one request and bounds waiting positions to three", async () => {
    const releases: Array<() => void> = [];
    const coordinator = new QuestionCoordinator({
      lockRoot: await lockRoot(),
      answer: vi.fn(
        async () =>
          new Promise<ResultAnswer>((resolve) => {
            releases.push(() => resolve(answer));
          }),
      ),
    });
    const first = await coordinator.submit(submitted("client-1"));
    await waitFor(() => releases.length === 1);
    const second = await coordinator.submit(submitted("client-2"));
    const third = await coordinator.submit(submitted("client-3"));
    const fourth = await coordinator.submit(submitted("client-4"));
    expect([
      second.queuePosition,
      third.queuePosition,
      fourth.queuePosition,
    ]).toEqual([1, 2, 3]);
    await expect(
      coordinator.submit(submitted("client-5")),
    ).rejects.toMatchObject({
      code: "QUESTION_QUEUE_FULL",
    });

    releases.shift()?.();
    await waitFor(
      () => coordinator.get(first.requestId)?.state === "completed",
    );
    coordinator.cancel(second.requestId);
    coordinator.cancel(third.requestId);
    coordinator.cancel(fourth.requestId);
  });

  it("deduplicates client IDs, rate limits the seventh request, and cancels old revisions", async () => {
    const coordinator = new QuestionCoordinator({
      lockRoot: await lockRoot(),
      answer: async () => answer,
    });
    const first = await coordinator.submit(submitted("same"));
    expect(
      await coordinator.submit(submitted("same")),
    ).toEqual(first);
    await waitFor(
      () => coordinator.get(first.requestId)?.state === "completed",
    );
    for (let index = 2; index <= 6; index += 1) {
      const current = await coordinator.submit(
        submitted(`client-${index}`),
      );
      await waitFor(
        () =>
          coordinator.get(current.requestId)?.state ===
          "completed",
      );
    }
    await expect(
      coordinator.submit(submitted("client-7")),
    ).rejects.toMatchObject({
      code: "QUESTION_RATE_LIMITED",
    });

    const pending = new QuestionCoordinator({
      lockRoot: await lockRoot(),
      answer: async ({ signal }) =>
        new Promise<ResultAnswer>((_resolve, reject) => {
          signal.addEventListener(
            "abort",
            () => reject(new Error("cancelled")),
            { once: true },
          );
        }),
    });
    const request = await pending.submit(
      submitted("revision-cancel"),
    );
    pending.cancelForRunRevision(context.runId, context.revision);
    await waitFor(
      () =>
        pending.get(request.requestId)?.state === "cancelled",
    );
  });

  it("returns scope suggestions without retrying", async () => {
    const answerQuestion = vi.fn(async () => {
      throw new ScopeRequiredError([
        { kind: "evidence", instanceId: "evidence_link_main" },
      ]);
    });
    const coordinator = new QuestionCoordinator({
      lockRoot: await lockRoot(),
      answer: answerQuestion,
    });
    const request = await coordinator.submit(submitted("scope"));
    await waitFor(
      () =>
        coordinator.get(request.requestId)?.state ===
        "scope_required",
    );
    expect(coordinator.get(request.requestId)).toMatchObject({
      scopeSuggestions: [
        {
          kind: "evidence",
          instanceId: "evidence_link_main",
        },
      ],
    });
    expect(answerQuestion).toHaveBeenCalledTimes(1);
  });
});
