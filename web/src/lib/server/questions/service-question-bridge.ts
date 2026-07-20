import { createHash } from "node:crypto";

import type {
  AnalysisBackend,
  BackendQuestionSnapshot,
} from "@/lib/server/analysis/types";
import {
  QuestionExecutionError,
  ScopeRequiredError,
} from "@/lib/server/questions/question-coordinator";
import type {
  QuestionRunContext,
  QuestionScope,
  ResultAnswer,
} from "@/lib/server/questions/types";

const DEFAULT_POLL_INTERVAL_MS = 250;

type ServiceQuestionBackend = Pick<
  AnalysisBackend,
  "startQuestion" | "getQuestion"
>;

export type ServiceQuestionBridgeDependencies = Readonly<{
  backend: ServiceQuestionBackend;
  currentContext: () => QuestionRunContext | null;
  wait?: (milliseconds: number, signal: AbortSignal) => Promise<void>;
}>;

type ServiceQuestionInput = Readonly<{
  clientRequestId: string;
  context: QuestionRunContext;
  question: string;
  scope: QuestionScope;
  signal: AbortSignal;
  setState?: (
    state: "preparing" | "asking" | "validating",
  ) => void;
}>;

function assertContextStillCurrent(
  expected: QuestionRunContext,
  currentContext: () => QuestionRunContext | null,
): void {
  const current = currentContext();
  if (
    current === null ||
    current.registrationId !== expected.registrationId ||
    current.runId !== expected.runId ||
    current.revision !== expected.revision ||
    current.bundleHash !== expected.bundleHash
  ) {
    throw new QuestionExecutionError("QUESTION_REVISION_CHANGED");
  }
}

function idempotencyKey(input: ServiceQuestionInput): string {
  return createHash("sha256")
    .update(input.context.runId, "utf8")
    .update("\0", "utf8")
    .update(String(input.context.revision), "utf8")
    .update("\0", "utf8")
    .update(input.clientRequestId, "utf8")
    .digest("hex");
}

function defaultWait(
  milliseconds: number,
  signal: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new QuestionExecutionError("QUESTION_CANCELLED"));
      return;
    }
    const timer = setTimeout(resolve, milliseconds);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(new QuestionExecutionError("QUESTION_CANCELLED"));
    }, { once: true });
  });
}

function assertSnapshotBinding(
  snapshot: BackendQuestionSnapshot,
  input: ServiceQuestionInput,
): void {
  if (
    snapshot.run_id !== input.context.runId ||
    snapshot.revision !== input.context.revision ||
    snapshot.scope_kind !== input.scope.kind ||
    snapshot.scope_instance_id !== input.scope.instanceId
  ) {
    throw new QuestionExecutionError("QUESTION_RESPONSE_MISMATCH");
  }
}

function terminalResult(
  snapshot: BackendQuestionSnapshot,
): ResultAnswer | null {
  if (snapshot.state === "completed") {
    if (snapshot.answer === null) {
      throw new QuestionExecutionError("ANSWER_VALIDATION_REJECTED");
    }
    return snapshot.answer;
  }
  if (snapshot.state === "scope_required") {
    throw new ScopeRequiredError(snapshot.scope_suggestions.map((item) => ({
      kind: item.scope_kind,
      instanceId: item.scope_instance_id,
    })));
  }
  if (snapshot.state === "failed") {
    throw new QuestionExecutionError(
      snapshot.error_code ?? "QUESTION_FAILED",
      snapshot.retryable,
    );
  }
  if (snapshot.state === "cancelled") {
    throw new QuestionExecutionError(
      snapshot.error_code ?? "QUESTION_CANCELLED",
    );
  }
  return null;
}

function publishState(
  snapshot: BackendQuestionSnapshot,
  setState: ServiceQuestionInput["setState"],
): void {
  if (snapshot.state === "queued" || snapshot.state === "preparing") {
    setState?.("preparing");
  } else if (snapshot.state === "asking") {
    setState?.("asking");
  } else if (snapshot.state === "validating") {
    setState?.("validating");
  }
}

export async function answerResultQuestionThroughService(
  input: ServiceQuestionInput,
  dependencies: ServiceQuestionBridgeDependencies,
): Promise<ResultAnswer> {
  if (input.signal.aborted) {
    throw new QuestionExecutionError("QUESTION_CANCELLED");
  }
  assertContextStillCurrent(input.context, dependencies.currentContext);
  let snapshot = await dependencies.backend.startQuestion(
    input.context.runId,
    {
      expected_revision: input.context.revision,
      idempotency_key: idempotencyKey(input),
      question: input.question,
      scope_kind: input.scope.kind,
      scope_instance_id: input.scope.instanceId,
      privacy_classification: input.context.privacyClassification,
    },
  );
  const wait = dependencies.wait ?? defaultWait;
  while (true) {
    assertContextStillCurrent(input.context, dependencies.currentContext);
    assertSnapshotBinding(snapshot, input);
    publishState(snapshot, input.setState);
    const result = terminalResult(snapshot);
    if (result !== null) return result;
    await wait(DEFAULT_POLL_INTERVAL_MS, input.signal);
    snapshot = await dependencies.backend.getQuestion(
      input.context.runId,
      snapshot.request_id,
    );
  }
}