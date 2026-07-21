import { createHash } from "node:crypto";

import type {
  ConversationKey,
  ScopeKind,
} from "@/lib/server/questions/types";
import { SCOPE_KINDS } from "@/lib/server/questions/types";

const MAX_QUESTION_REQUEST_BYTES = 16 * 1024;
export const CONSENT_VERSION = "qa-remote-processing-v1";
export const REQUEST_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;
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


export type SubmitQuestionBody = {
  clientRequestId: string;
  runId: string;
  revision: number;
  scopeKind: ScopeKind;
  scopeInstanceId: string;
  issueId: string | null;
  question: string;
  consentVersion: typeof CONSENT_VERSION;
};


export function isRecord(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  );
}

export async function boundedJson(request: Request): Promise<unknown> {
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

export function parseSubmitBody(
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

export function questionRateKey(headers: Headers): string {
  const cookie = headers.get("cookie") ?? "";
  return createHash("sha256")
    .update(cookie, "utf8")
    .digest("hex");
}


export function conversationKeyFromUrl(
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
