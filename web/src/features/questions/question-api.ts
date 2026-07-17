import type { ResultAnswerV1 } from "../../../../contracts/web-report/v1/generated/types";

import type {
  ConversationKey,
} from "@/features/questions/model/draft-cache";
import type { ReportScopeKind } from "@/features/report/report-model";

export type QuestionCapability = {
  companyDataEnabled: boolean;
  disclosureVersion: "qa-remote-processing-v1";
  modeLabelKo: string;
  pocOnly: boolean;
  reasonCode: string;
  textQuestionEnabled: boolean;
};

export type CapabilityResponse = {
  capability: QuestionCapability;
  disclosuresKo: string[];
};

export type QuestionRequestState =
  | "queued"
  | "preparing"
  | "asking"
  | "validating"
  | "completed"
  | "scope_required"
  | "failed"
  | "cancelled";

export type ScopeSuggestion = {
  instanceId: string;
  kind: string;
};

export type QuestionRequestSnapshot = {
  answer: ResultAnswerV1 | null;
  clientRequestId: string;
  errorCode: string | null;
  queuePosition: number | null;
  requestId: string;
  scopeSuggestions: ScopeSuggestion[];
  state: QuestionRequestState;
};

type ConversationBase = {
  createdAt: string;
  key: ConversationKey;
  recordId: string;
  recordVersion: "1.0.0";
};

export type ConversationRecord =
  | (ConversationBase & {
      question: string;
      type: "question_submitted";
    })
  | (ConversationBase & {
      answer: ResultAnswerV1;
      requestId: string;
      type: "answer_verified";
    })
  | (ConversationBase & {
      errorCode: string;
      requestId: string;
      type: "question_failed";
    });

export type ConversationResponse = {
  key: ConversationKey;
  records: ConversationRecord[];
};

export type SubmitQuestionBody = {
  clientRequestId: string;
  consentVersion: "qa-remote-processing-v1";
  issueId: string | null;
  question: string;
  revision: number;
  runId: string;
  scopeInstanceId: string;
  scopeKind: ReportScopeKind;
};

export type SubmitQuestionResponse = {
  request: QuestionRequestSnapshot;
};

export interface QuestionApi {
  cancelRequest(requestId: string): Promise<{ cancelled: boolean }>;
  getCapability(): Promise<CapabilityResponse>;
  getConversation(key: ConversationKey): Promise<ConversationResponse>;
  getRequest(requestId: string): Promise<QuestionRequestSnapshot>;
  submitQuestion(body: SubmitQuestionBody): Promise<SubmitQuestionResponse>;
}

export class QuestionApiError extends Error {
  constructor(readonly status: number) {
    super("question request failed");
    this.name = "QuestionApiError";
  }
}

async function readJson<T>(
  input: string,
  init: RequestInit,
): Promise<T> {
  const response = await fetch(input, {
    cache: "no-store",
    ...init,
  });
  if (!response.ok) {
    throw new QuestionApiError(response.status);
  }
  return (await response.json()) as T;
}

export function createQuestionApi(csrfToken: string): QuestionApi {
  const mutationHeaders = {
    "Content-Type": "application/json",
    "x-csrf-token": csrfToken,
  };
  return {
    cancelRequest: (requestId) =>
      readJson(`/api/questions/${encodeURIComponent(requestId)}`, {
        headers: mutationHeaders,
        method: "DELETE",
      }),
    getCapability: () =>
      readJson("/api/questions/capability", { method: "GET" }),
    getConversation: (key) => {
      const query = new URLSearchParams({
        revision: String(key.revision),
        runId: key.runId,
        scopeInstanceId: key.scopeInstanceId,
        scopeKind: key.scopeKind,
      });
      return readJson(`/api/conversations?${query.toString()}`, {
        method: "GET",
      });
    },
    getRequest: (requestId) =>
      readJson<{ request: QuestionRequestSnapshot }>(
        `/api/questions/${encodeURIComponent(requestId)}`,
        { method: "GET" },
      ).then((response) => response.request),
    submitQuestion: (body) =>
      readJson("/api/questions", {
        body: JSON.stringify(body),
        headers: mutationHeaders,
        method: "POST",
      }),
  };
}
