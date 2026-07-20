import { createHash, randomUUID } from "node:crypto";

import type { QuestionCapability } from "@/lib/server/questions/capability";
import type {
  ConversationRecord,
} from "@/lib/server/questions/conversation-store";
import {
  QuestionCoordinatorError,
  type QuestionRequestSnapshot,
  type SubmitQuestionInput,
} from "@/lib/server/questions/question-coordinator";
import type {
  ConversationKey,
  QuestionRunContext,
  ScopeKind,
} from "@/lib/server/questions/types";
import { SCOPE_KINDS } from "@/lib/server/questions/types";
import {
  LocalRequestSecurityError,
  type LocalSecurityConfig,
  assertLocalMutation,
  assertLocalSession,
} from "@/lib/server/local-request-security";

const MAX_QUESTION_REQUEST_BYTES = 16 * 1024;
const CONSENT_VERSION = "qa-remote-processing-v1";
const REQUEST_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;
const REF_PATTERN = /^[A-Za-z0-9][A-Za-z0-9:_-]{0,255}$/;
const BODY_KEYS = [
  "clientRequestId",
  "consentVersion",
  "issueId",
  "question",
  "revision",
  "runId",
  "scopeInstanceId",
  "scopeKind",
] as const;
const QUERY_KEYS = [
  "revision",
  "runId",
  "scopeInstanceId",
  "scopeKind",
] as const;

const SAFE_JSON_HEADERS = {
  "Cache-Control": "no-store",
  "Content-Security-Policy":
    "default-src 'none'; base-uri 'none'; frame-ancestors 'none'",
  "Content-Type": "application/json; charset=utf-8",
  "X-Content-Type-Options": "nosniff",
} as const;

export const QUESTION_DISCLOSURES_KO = [
  "질문과 선택한 근거 범위는 로컬 Python AI 서비스를 통해 OpenAI API로 전송됩니다.",
  "AI에는 검증된 근거 Job만 전달되며 내부 서비스 토큰이나 로컬 파일 경로는 전달되지 않습니다.",
  "응답은 스키마, 참조, 값 검증을 통과한 뒤에만 화면에 표시됩니다.",
  "회사 제한 데이터 질문은 OpenAI 원격 처리 동의가 있어야 전송됩니다.",
] as const;

type CoordinatorPort = Readonly<{
  submit(
    input: SubmitQuestionInput,
  ): Promise<QuestionRequestSnapshot>;
  get(requestId: string): QuestionRequestSnapshot | null;
  cancel(requestId: string): boolean;
}>;

type ConversationPort = Readonly<{
  append(record: ConversationRecord): Promise<void>;
  read(key: ConversationKey): Promise<ConversationRecord[]>;
  deleteAll(): Promise<void>;
}>;

export type QuestionRouteDependencies = Readonly<{
  security: LocalSecurityConfig;
  currentContext: () => QuestionRunContext | null;
  capability: (
    context: QuestionRunContext | null,
  ) => Promise<QuestionCapability>;
  coordinator: CoordinatorPort;
  conversations: ConversationPort;
}>;

type SubmitQuestionBody = {
  clientRequestId: string;
  runId: string;
  revision: number;
  scopeKind: ScopeKind;
  scopeInstanceId: string;
  issueId: string | null;
  question: string;
  consentVersion: typeof CONSENT_VERSION;
};

function response(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: SAFE_JSON_HEADERS,
  });
}

function errorResponse(error: unknown): Response {
  if (error instanceof LocalRequestSecurityError) {
    return response({ message: error.message }, error.status);
  }
  if (error instanceof QuestionCoordinatorError) {
    const status =
      error.code === "QUESTION_RATE_LIMITED" ? 429 : 503;
    return response(
      {
        message:
          error.code === "QUESTION_RATE_LIMITED"
            ? "질문 요청 한도를 초과했습니다."
            : "질문 대기열이 가득 찼습니다.",
        errorCode: error.code,
      },
      status,
    );
  }
  if (
    error instanceof TypeError ||
    error instanceof SyntaxError ||
    error instanceof URIError
  ) {
    return response(
      { message: "질문 요청 형식이 올바르지 않습니다." },
      400,
    );
  }
  return response(
    { message: "질문 요청을 처리할 수 없습니다." },
    500,
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  );
}

async function boundedJson(request: Request): Promise<unknown> {
  if (request.headers.get("content-type") !== "application/json") {
    throw new TypeError("invalid content type");
  }
  const length = request.headers.get("content-length");
  if (length === null || !/^[0-9]+$/.test(length)) {
    throw new TypeError("invalid content length");
  }
  const expected = Number(length);
  if (
    !Number.isSafeInteger(expected) ||
    expected <= 0 ||
    expected > MAX_QUESTION_REQUEST_BYTES
  ) {
    throw new TypeError("invalid content length");
  }
  const bytes = new Uint8Array(await request.arrayBuffer());
  if (
    bytes.byteLength !== expected ||
    bytes.byteLength > MAX_QUESTION_REQUEST_BYTES
  ) {
    throw new TypeError("invalid content length");
  }
  return JSON.parse(
    new TextDecoder("utf-8", { fatal: true }).decode(bytes),
  ) as unknown;
}

function sortedKeysEqual(
  value: Record<string, unknown>,
  expected: readonly string[],
): boolean {
  const keys = Object.keys(value).sort();
  return (
    keys.length === expected.length &&
    keys.every((key, index) => key === expected[index])
  );
}

function parseSubmitBody(
  value: Record<string, unknown>,
): SubmitQuestionBody | null {
  if (
    !sortedKeysEqual(value, BODY_KEYS) ||
    typeof value.clientRequestId !== "string" ||
    !REQUEST_ID_PATTERN.test(value.clientRequestId) ||
    typeof value.runId !== "string" ||
    !REF_PATTERN.test(value.runId) ||
    !Number.isInteger(value.revision) ||
    typeof value.scopeKind !== "string" ||
    !SCOPE_KINDS.includes(
      value.scopeKind as (typeof SCOPE_KINDS)[number],
    ) ||
    typeof value.scopeInstanceId !== "string" ||
    !REF_PATTERN.test(value.scopeInstanceId) ||
    (value.issueId !== null &&
      (typeof value.issueId !== "string" ||
        !REF_PATTERN.test(value.issueId))) ||
    typeof value.question !== "string" ||
    value.question.normalize("NFC").trim().length === 0 ||
    Array.from(value.question.normalize("NFC").trim()).length >
      2_000 ||
    value.consentVersion !== CONSENT_VERSION
  ) {
    return null;
  }
  return value as SubmitQuestionBody;
}

function rateKey(headers: Headers): string {
  const cookie = headers.get("cookie") ?? "";
  return createHash("sha256")
    .update(cookie, "utf8")
    .digest("hex");
}

export async function handleQuestionCapability(
  request: Request,
  dependencies: QuestionRouteDependencies,
): Promise<Response> {
  try {
    assertLocalSession(request.headers, dependencies.security);
    const context = dependencies.currentContext();
    const capability = await dependencies.capability(context);
    return response(
      {
        capability,
        disclosuresKo: QUESTION_DISCLOSURES_KO,
      },
      200,
    );
  } catch (error) {
    return errorResponse(error);
  }
}

export async function handleQuestionSubmit(
  request: Request,
  dependencies: QuestionRouteDependencies,
): Promise<Response> {
  try {
    assertLocalMutation(request.headers, dependencies.security);
    const document = await boundedJson(request);
    if (!isRecord(document)) {
      return response(
        { message: "질문 요청 형식이 올바르지 않습니다." },
        400,
      );
    }
    if (document.consentVersion !== CONSENT_VERSION) {
      return response(
        {
          message: "원격 처리 동의가 필요합니다.",
          errorCode: "REMOTE_PROCESSING_CONSENT_REQUIRED",
        },
        412,
      );
    }
    const body = parseSubmitBody(document);
    if (body === null) {
      return response(
        { message: "질문 요청 형식이 올바르지 않습니다." },
        400,
      );
    }
    const context = dependencies.currentContext();
    if (context === null) {
      return response(
        {
          message: "검증된 등록 실행본에서만 질문할 수 있습니다.",
          errorCode: "REGISTERED_REPORT_REQUIRED",
        },
        403,
      );
    }
    if (
      body.runId !== context.runId ||
      body.revision !== context.revision
    ) {
      return response(
        {
          message: "현재 결과 revision과 질문 범위가 다릅니다.",
          errorCode: "QUESTION_REVISION_CHANGED",
        },
        409,
      );
    }
    const capability = await dependencies.capability(context);
    if (
      !capability.textQuestionEnabled ||
      (context.privacyClassification ===
        "company_restricted" &&
        !capability.companyDataEnabled)
    ) {
      return response(
        {
          message: "현재 격리 검증 상태에서는 질문할 수 없습니다.",
          errorCode: capability.reasonCode,
        },
        403,
      );
    }
    const input: SubmitQuestionInput = {
      clientRequestId: body.clientRequestId,
      context,
      question: body.question,
      scope: {
        kind: body.scopeKind,
        instanceId: body.scopeInstanceId,
        issueId: body.issueId,
      },
      rateKey: rateKey(request.headers),
    };
    const snapshot = await dependencies.coordinator.submit(input);
    try {
      await dependencies.conversations.append({
        recordVersion: "1.0.0",
        recordId: randomUUID(),
        type: "question_submitted",
        key: {
          runId: context.runId,
          revision: context.revision,
          scopeKind: body.scopeKind,
          scopeInstanceId: body.scopeInstanceId,
        },
        question: body.question.normalize("NFC").trim(),
        createdAt: new Date().toISOString(),
      });
    } catch (error) {
      dependencies.coordinator.cancel(snapshot.requestId);
      throw error;
    }
    return response({ request: snapshot }, 202);
  } catch (error) {
    return errorResponse(error);
  }
}

export async function handleQuestionRead(
  request: Request,
  requestId: string,
  dependencies: QuestionRouteDependencies,
): Promise<Response> {
  try {
    assertLocalSession(request.headers, dependencies.security);
    if (!REQUEST_ID_PATTERN.test(requestId)) {
      return response(
        { message: "질문 요청 ID가 올바르지 않습니다." },
        400,
      );
    }
    const snapshot = dependencies.coordinator.get(requestId);
    return snapshot === null
      ? response({ message: "질문 요청을 찾을 수 없습니다." }, 404)
      : response({ request: snapshot }, 200);
  } catch (error) {
    return errorResponse(error);
  }
}

export async function handleQuestionCancel(
  request: Request,
  requestId: string,
  dependencies: QuestionRouteDependencies,
): Promise<Response> {
  try {
    assertLocalMutation(request.headers, dependencies.security);
    if (!REQUEST_ID_PATTERN.test(requestId)) {
      return response(
        { message: "질문 요청 ID가 올바르지 않습니다." },
        400,
      );
    }
    return response(
      { cancelled: dependencies.coordinator.cancel(requestId) },
      200,
    );
  } catch (error) {
    return errorResponse(error);
  }
}

function conversationKeyFromUrl(
  request: Request,
): ConversationKey | null {
  const parameters = new URL(request.url).searchParams;
  const keys = [...new Set(parameters.keys())].sort();
  if (
    keys.length !== QUERY_KEYS.length ||
    keys.some((key, index) => key !== QUERY_KEYS[index])
  ) {
    return null;
  }
  const runId = parameters.get("runId");
  const revisionValue = parameters.get("revision");
  const scopeKind = parameters.get("scopeKind");
  const scopeInstanceId = parameters.get("scopeInstanceId");
  if (
    runId === null ||
    !REF_PATTERN.test(runId) ||
    revisionValue === null ||
    !/^[1-9][0-9]*$/.test(revisionValue) ||
    scopeKind === null ||
    !SCOPE_KINDS.includes(
      scopeKind as (typeof SCOPE_KINDS)[number],
    ) ||
    scopeInstanceId === null ||
    !REF_PATTERN.test(scopeInstanceId)
  ) {
    return null;
  }
  const revision = Number(revisionValue);
  if (!Number.isSafeInteger(revision)) {
    return null;
  }
  return {
    runId,
    revision,
    scopeKind: scopeKind as ScopeKind,
    scopeInstanceId,
  };
}

export async function handleConversationRead(
  request: Request,
  dependencies: QuestionRouteDependencies,
): Promise<Response> {
  try {
    assertLocalSession(request.headers, dependencies.security);
    const key = conversationKeyFromUrl(request);
    if (key === null) {
      return response(
        { message: "대화 범위가 올바르지 않습니다." },
        400,
      );
    }
    const records = await dependencies.conversations.read(key);
    return response({ key, records }, 200);
  } catch (error) {
    return errorResponse(error);
  }
}

export async function handleConversationDelete(
  request: Request,
  dependencies: QuestionRouteDependencies,
): Promise<Response> {
  try {
    assertLocalMutation(request.headers, dependencies.security);
    await dependencies.conversations.deleteAll();
    return response({ deleted: true }, 200);
  } catch (error) {
    return errorResponse(error);
  }
}
