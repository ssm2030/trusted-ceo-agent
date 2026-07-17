import { randomUUID } from "node:crypto";
import {
  lstat,
  readFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import {
  capabilityFor,
  type QuestionCapability,
  type SandboxProbeReceipt,
} from "@/lib/server/questions/capability";
import {
  ConversationStore,
} from "@/lib/server/questions/conversation-store";
import {
  answerResultQuestion,
} from "@/lib/server/questions/question-bridge";
import {
  QuestionCoordinator,
} from "@/lib/server/questions/question-coordinator";
import {
  getCurrentQuestionRunContext,
  onQuestionRunContextChanged,
} from "@/lib/server/questions/run-context";
import type {
  ConversationKey,
  QuestionRunContext,
} from "@/lib/server/questions/types";
import {
  getReportRuntime,
} from "@/lib/server/report-runtime";
import type {
  QuestionRouteDependencies,
} from "@/lib/server/questions/question-route-handlers";

const MAX_RECEIPT_BYTES = 64 * 1024;

function webRuntimeRoot(): string {
  return (
    process.env.TRUSTED_CEO_WEB_RUNTIME_ROOT ??
    path.join(tmpdir(), "trusted-ceo-agent-web-runtime")
  );
}

async function loadProbeReceipt(): Promise<SandboxProbeReceipt | null> {
  const receiptPath =
    process.env.TRUSTED_CEO_QUESTION_PROBE_RECEIPT;
  if (
    receiptPath === undefined ||
    !path.isAbsolute(receiptPath)
  ) {
    return null;
  }
  try {
    const details = await lstat(receiptPath);
    if (
      !details.isFile() ||
      details.isSymbolicLink() ||
      details.size <= 0 ||
      details.size > MAX_RECEIPT_BYTES
    ) {
      return null;
    }
    const serialized = await readFile(receiptPath, "utf8");
    const value = JSON.parse(serialized) as unknown;
    return typeof value === "object" &&
      value !== null &&
      !Array.isArray(value)
      ? (value as SandboxProbeReceipt)
      : null;
  } catch {
    return null;
  }
}

export async function currentQuestionCapability(
  context: QuestionRunContext | null,
): Promise<QuestionCapability> {
  if (context === null) {
    return capabilityFor({
      receipt: null,
      privacyClassification: "company_restricted",
    });
  }
  return capabilityFor({
    receipt: await loadProbeReceipt(),
    platform: process.platform,
    privacyClassification: context.privacyClassification,
    allowAutomatedFakeCodex:
      process.env.NODE_ENV === "test" &&
      process.env.TRUSTED_CEO_FAKE_CODEX === "1",
  });
}

function keyFor(
  input: Parameters<QuestionCoordinator["submit"]>[0],
): ConversationKey {
  return {
    runId: input.context.runId,
    revision: input.context.revision,
    scopeKind: input.scope.kind,
    scopeInstanceId: input.scope.instanceId,
  };
}

function createServices(): QuestionRouteDependencies {
  const runtimeRoot = webRuntimeRoot();
  const conversations = new ConversationStore(
    path.join(runtimeRoot, "conversations"),
  );
  void conversations.prune().catch(() => undefined);
  const coordinator = new QuestionCoordinator({
    lockRoot: path.join(runtimeRoot, "questions"),
    answer: async ({
      context,
      question,
      scope,
      signal,
      setState,
    }) =>
      answerResultQuestion({
        context,
        question,
        scope,
        capability: await currentQuestionCapability(context),
        signal,
        setState,
      }),
    onTerminal: async (input, snapshot) => {
      if (
        snapshot.state === "completed" &&
        snapshot.answer !== null
      ) {
        await conversations.append({
          recordVersion: "1.0.0",
          recordId: randomUUID(),
          type: "answer_verified",
          key: keyFor(input),
          requestId: snapshot.requestId,
          answer: snapshot.answer,
          createdAt: new Date().toISOString(),
        });
        return;
      }
      if (
        snapshot.state === "failed" ||
        snapshot.state === "cancelled" ||
        snapshot.state === "scope_required"
      ) {
        await conversations.append({
          recordVersion: "1.0.0",
          recordId: randomUUID(),
          type: "question_failed",
          key: keyFor(input),
          requestId: snapshot.requestId,
          errorCode: snapshot.errorCode ?? "QUESTION_FAILED",
          createdAt: new Date().toISOString(),
        });
      }
    },
  });
  let previous = getCurrentQuestionRunContext();
  onQuestionRunContextChanged((next) => {
    if (previous !== null) {
      coordinator.cancelForRunRevision(
        previous.runId,
        previous.revision,
      );
    }
    previous = next;
  });
  return {
    security: getReportRuntime().security,
    currentContext: getCurrentQuestionRunContext,
    capability: currentQuestionCapability,
    coordinator,
    conversations,
  };
}

let services: QuestionRouteDependencies | undefined;

export function getQuestionServices(): QuestionRouteDependencies {
  services ??= createServices();
  return services;
}
