// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import type { QuestionCapability } from "@/lib/server/questions/capability";
import type {
  ConversationRecord,
} from "@/lib/server/questions/conversation-store";
import type {
  QuestionRequestSnapshot,
} from "@/lib/server/questions/question-coordinator";
import {
  handleConversationDelete,
  handleConversationRead,
  handleQuestionCapability,
  handleQuestionCancel,
  handleQuestionRead,
  handleQuestionSubmit,
  type QuestionRouteDependencies,
} from "@/lib/server/questions/question-route-handlers";
import {
  conversationKeyFromUrl,
  parseSubmitBody,
  questionRateKey,
} from "@/lib/server/questions/question-request-policy";
import type { QuestionRunContext } from "@/lib/server/questions/types";
import {
  CSRF_HEADER_NAME,
  SESSION_COOKIE_NAME,
  createLocalSecurityConfig,
  issueLocalSession,
} from "@/lib/server/local-request-security";

const security = createLocalSecurityConfig({
  port: 3000,
  sessionSecret: new Uint8Array(32).fill(7),
});

describe("question request policy boundary", () => {
  it("exposes pure request parsing helpers", () => {
    expect(parseSubmitBody).toBeTypeOf("function");
    expect(questionRateKey).toBeTypeOf("function");
    expect(conversationKeyFromUrl).toBeTypeOf("function");
  });
});
const context: QuestionRunContext = {
  registrationId: "representative",
  artifactRoot: "C:\\runs\\representative",
  runId: "run_20260717T010203Z_0123456789abcdef",
  revision: 3,
  viewerMode: "trusted_final",
  privacyClassification: "company_restricted",
  bundleHash: "a".repeat(64),
};
const capability: QuestionCapability = {
  textQuestionEnabled: true,
  companyDataEnabled: true,
  pocOnly: false,
  reasonCode: "READY",
  disclosureVersion: "qa-remote-processing-v1",
  modeLabelKo: "강격리 검증 모드",
};
const requestSnapshot: QuestionRequestSnapshot = {
  requestId: "request-1",
  clientRequestId: "client-1",
  state: "queued",
  queuePosition: 1,
  answer: null,
  scopeSuggestions: [],
  errorCode: null,
};

function headers(mutation: boolean): Headers {
  const session = issueLocalSession(security);
  const value = new Headers({
    host: security.host,
    cookie: `${SESSION_COOKIE_NAME}=${session.cookieValue}`,
  });
  if (mutation) {
    value.set("origin", security.origin);
    value.set(CSRF_HEADER_NAME, session.csrfToken);
  }
  return value;
}

function dependencies(
  overrides: Partial<QuestionRouteDependencies> = {},
): QuestionRouteDependencies {
  return {
    security,
    currentContext: () => context,
    capability: async () => capability,
    coordinator: {
      submit: vi.fn(async () => requestSnapshot),
      get: vi.fn(() => requestSnapshot),
      cancel: vi.fn(() => true),
    },
    conversations: {
      append: vi.fn(async () => undefined),
      read: vi.fn(async () => []),
      deleteAll: vi.fn(async () => undefined),
    },
    ...overrides,
  };
}

function jsonRequest(
  pathname: string,
  body: unknown,
): Request {
  const serialized = JSON.stringify(body);
  const requestHeaders = headers(true);
  requestHeaders.set("content-type", "application/json");
  requestHeaders.set(
    "content-length",
    String(Buffer.byteLength(serialized)),
  );
  return new Request(`${security.origin}${pathname}`, {
    method: "POST",
    headers: requestHeaders,
    body: serialized,
  });
}

function validBody() {
  return {
    clientRequestId: "client-1",
    runId: context.runId,
    revision: context.revision,
    scopeKind: "evidence",
    scopeInstanceId: "evidence_link_main",
    issueId: "issue_main",
    question: "이 근거가 결론을 어떻게 뒷받침하나요?",
    consentVersion: "qa-remote-processing-v1",
  };
}

describe("question route handlers", () => {
  it("returns capability disclosures without server paths", async () => {
    const response = await handleQuestionCapability(
      new Request(`${security.origin}/api/questions/capability`, {
        headers: headers(false),
      }),
      dependencies(),
    );
    expect(response.status).toBe(200);
    const payload = await response.json();
    expect(payload.capability).toMatchObject({
      textQuestionEnabled: true,
      disclosureVersion: "qa-remote-processing-v1",
    });
    expect(payload.disclosuresKo).toHaveLength(4);
    expect(JSON.stringify(payload)).not.toContain(
      context.artifactRoot,
    );
  });

  it("requires consent, current revision, and company capability", async () => {
    expect(
      (
        await handleQuestionSubmit(
          jsonRequest("/api/questions", {
            ...validBody(),
            consentVersion: undefined,
          }),
          dependencies(),
        )
      ).status,
    ).toBe(412);
    expect(
      (
        await handleQuestionSubmit(
          jsonRequest("/api/questions", {
            ...validBody(),
            revision: 2,
          }),
          dependencies(),
        )
      ).status,
    ).toBe(409);
    expect(
      (
        await handleQuestionSubmit(
          jsonRequest("/api/questions", validBody()),
          dependencies({
            capability: async () => ({
              ...capability,
              textQuestionEnabled: false,
              companyDataEnabled: false,
              pocOnly: true,
              reasonCode: "OUTSIDE_READ_NOT_DENIED",
            }),
          }),
        )
      ).status,
    ).toBe(403);
  });

  it("accepts a bounded consented request and stores it after validation", async () => {
    const deps = dependencies();
    const response = await handleQuestionSubmit(
      jsonRequest("/api/questions", validBody()),
      deps,
    );
    expect(response.status).toBe(202);
    expect(await response.json()).toEqual({
      request: requestSnapshot,
    });
    expect(deps.coordinator.submit).toHaveBeenCalledWith(
      expect.objectContaining({
        clientRequestId: "client-1",
        context,
        question: validBody().question,
      }),
    );
    expect(deps.conversations.append).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "question_submitted",
        key: {
          runId: context.runId,
          revision: context.revision,
          scopeKind: "evidence",
          scopeInstanceId: "evidence_link_main",
        },
      }),
    );
  });

  it("reads and cancels asynchronous requests", async () => {
    const deps = dependencies();
    const read = await handleQuestionRead(
      new Request(
        `${security.origin}/api/questions/request-1`,
        { headers: headers(false) },
      ),
      "request-1",
      deps,
    );
    expect(read.status).toBe(200);
    expect(await read.json()).toEqual({
      request: requestSnapshot,
    });

    const cancel = await handleQuestionCancel(
      new Request(
        `${security.origin}/api/questions/request-1`,
        { method: "DELETE", headers: headers(true) },
      ),
      "request-1",
      deps,
    );
    expect(cancel.status).toBe(200);
    expect(await cancel.json()).toEqual({ cancelled: true });
  });

  it("uses all four conversation key fields and deletes interaction data only", async () => {
    const read = vi.fn(
      async (): Promise<ConversationRecord[]> =>
        [],
    );
    const deps = dependencies({
      conversations: {
        append: vi.fn(async () => undefined),
        read,
        deleteAll: vi.fn(async () => undefined),
      },
    });
    const query = new URLSearchParams({
      runId: context.runId,
      revision: "3",
      scopeKind: "evidence",
      scopeInstanceId: "evidence_link_main",
    });
    const response = await handleConversationRead(
      new Request(
        `${security.origin}/api/conversations?${query}`,
        { headers: headers(false) },
      ),
      deps,
    );
    expect(response.status).toBe(200);
    expect(read).toHaveBeenCalledWith({
      runId: context.runId,
      revision: 3,
      scopeKind: "evidence",
      scopeInstanceId: "evidence_link_main",
    });

    const deleted = await handleConversationDelete(
      new Request(`${security.origin}/api/conversations`, {
        method: "DELETE",
        headers: headers(true),
      }),
      deps,
    );
    expect(deleted.status).toBe(200);
    expect(deps.conversations.deleteAll).toHaveBeenCalledTimes(1);
  });

  it("checks local security before any business dependency", async () => {
    const getContext = vi.fn(() => context);
    const deps = dependencies({ currentContext: getContext });
    const body = JSON.stringify(validBody());
    const response = await handleQuestionSubmit(
      new Request(`${security.origin}/api/questions`, {
        method: "POST",
        headers: {
          host: "localhost:3000",
          origin: security.origin,
          "content-type": "application/json",
          "content-length": String(Buffer.byteLength(body)),
        },
        body,
      }),
      deps,
    );
    expect(response.status).toBe(403);
    expect(getContext).not.toHaveBeenCalled();
  });
});
