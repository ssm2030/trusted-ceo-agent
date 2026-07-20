import { randomUUID } from "node:crypto";
import { tmpdir } from "node:os";
import path from "node:path";

import { getAnalysisServices } from "@/lib/server/analysis/services";
import {
  serviceCapabilityFor,
  type QuestionCapability,
} from "@/lib/server/questions/capability";
import {
  ConversationStore,
} from "@/lib/server/questions/conversation-store";
import {
  QuestionCoordinator,
} from "@/lib/server/questions/question-coordinator";
import type {
  QuestionRouteDependencies,
} from "@/lib/server/questions/question-route-handlers";
import {
  getCurrentQuestionRunContext,
  onQuestionRunContextChanged,
} from "@/lib/server/questions/run-context";
import {
  answerResultQuestionThroughService,
} from "@/lib/server/questions/service-question-bridge";
import type {
  ConversationKey,
  QuestionRunContext,
} from "@/lib/server/questions/types";
import {
  getReportRuntime,
} from "@/lib/server/report-runtime";

function webRuntimeRoot(): string {
  return (
    process.env.TRUSTED_CEO_WEB_RUNTIME_ROOT ??
    path.join(tmpdir(), "trusted-ceo-agent-web-runtime")
  );
}

export async function currentQuestionCapability(
  context: QuestionRunContext | null,
): Promise<QuestionCapability> {
  if (context === null) {
    return serviceCapabilityFor({
      contextPresent: false,
      serviceAvailable: true,
      aiReady: false,
    });
  }
  try {
    const health = await getAnalysisServices().backend.getHealth();
    return serviceCapabilityFor({
      contextPresent: true,
      serviceAvailable: true,
      aiReady: health.ai_ready,
    });
  } catch {
    return serviceCapabilityFor({
      contextPresent: true,
      serviceAvailable: false,
      aiReady: false,
    });
  }
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
  const analysis = getAnalysisServices();
  const conversations = new ConversationStore(
    path.join(runtimeRoot, "conversations"),
  );
  void conversations.prune().catch(() => undefined);
  const coordinator = new QuestionCoordinator({
    lockRoot: path.join(runtimeRoot, "questions"),
    answer: async ({
      clientRequestId,
      context,
      question,
      scope,
      signal,
      setState,
    }) => answerResultQuestionThroughService({
      clientRequestId,
      context,
      question,
      scope,
      signal,
      setState,
    }, {
      backend: analysis.backend,
      currentContext: getCurrentQuestionRunContext,
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