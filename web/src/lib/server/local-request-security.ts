import {
  createHmac,
  randomBytes,
  timingSafeEqual,
} from "node:crypto";

export const SESSION_COOKIE_NAME = "trusted_ceo_session";
export const CSRF_HEADER_NAME = "x-csrf-token";

const SESSION_ID_BYTES = 32;
const SIGNATURE_BYTES = 32;
const TOKEN_PATTERN = /^[A-Za-z0-9_-]+$/;

export type LocalSecurityConfig = Readonly<{
  host: string;
  origin: string;
  sessionSecret: Uint8Array;
}>;

export type IssuedLocalSession = Readonly<{
  cookieValue: string;
  csrfToken: string;
}>;

export class LocalRequestSecurityError extends Error {
  constructor(
    message: string,
    readonly status: 401 | 403 = 403,
  ) {
    super(message);
    this.name = "LocalRequestSecurityError";
  }
}

export function createLocalSecurityConfig(input: {
  port: number;
  sessionSecret?: Uint8Array;
}): LocalSecurityConfig {
  if (!Number.isInteger(input.port) || input.port < 1 || input.port > 65_535) {
    throw new Error("invalid localhost port");
  }
  const secret = input.sessionSecret ?? randomBytes(SIGNATURE_BYTES);
  if (secret.byteLength < SIGNATURE_BYTES) {
    throw new Error("session secret must contain at least 32 bytes");
  }
  const host = `127.0.0.1:${input.port}`;
  return Object.freeze({
    host,
    origin: `http://${host}`,
    sessionSecret: new Uint8Array(secret),
  });
}

export function assertExactLocalRequest(
  headers: Headers,
  security: LocalSecurityConfig,
  options: { requireOrigin: boolean },
): void {
  if (headers.get("host") !== security.host) {
    throw new LocalRequestSecurityError("허용되지 않은 로컬 요청입니다.");
  }
  const origin = headers.get("origin");
  if (
    (options.requireOrigin && origin === null) ||
    (origin !== null && origin !== security.origin)
  ) {
    throw new LocalRequestSecurityError("허용되지 않은 로컬 요청입니다.");
  }
}

function hmac(
  security: LocalSecurityConfig,
  purpose: "session" | "csrf",
  sessionId: string,
): Buffer {
  return createHmac("sha256", security.sessionSecret)
    .update(`${purpose}\0${sessionId}`, "utf8")
    .digest();
}

function equalBase64Url(candidate: string, expected: Buffer): boolean {
  if (!TOKEN_PATTERN.test(candidate)) {
    return false;
  }
  let actual: Buffer;
  try {
    actual = Buffer.from(candidate, "base64url");
  } catch {
    return false;
  }
  return (
    actual.byteLength === expected.byteLength &&
    timingSafeEqual(actual, expected)
  );
}

export function issueLocalSession(
  security: LocalSecurityConfig,
): IssuedLocalSession {
  const sessionId = randomBytes(SESSION_ID_BYTES).toString("base64url");
  const signature = hmac(security, "session", sessionId).toString("base64url");
  return Object.freeze({
    cookieValue: `${sessionId}.${signature}`,
    csrfToken: hmac(security, "csrf", sessionId).toString("base64url"),
  });
}

export function serializeSessionCookie(cookieValue: string): string {
  if (
    cookieValue.length > 256 ||
    !/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(cookieValue)
  ) {
    throw new Error("invalid session cookie value");
  }
  return `${SESSION_COOKIE_NAME}=${cookieValue}; Path=/; HttpOnly; SameSite=Strict`;
}

function readCookie(headers: Headers, name: string): string | null {
  const cookieHeader = headers.get("cookie");
  if (cookieHeader === null || cookieHeader.length > 8_192) {
    return null;
  }
  const matches = cookieHeader
    .split(";")
    .map((part) => part.trim())
    .filter((part) => part.startsWith(`${name}=`));
  if (matches.length !== 1) {
    return null;
  }
  return matches[0].slice(name.length + 1);
}

function verifiedSessionId(
  headers: Headers,
  security: LocalSecurityConfig,
): string {
  const cookieValue = readCookie(headers, SESSION_COOKIE_NAME);
  if (cookieValue === null) {
    throw new LocalRequestSecurityError(
      "로컬 세션을 확인할 수 없습니다.",
      401,
    );
  }
  const pieces = cookieValue.split(".");
  if (
    pieces.length !== 2 ||
    !TOKEN_PATTERN.test(pieces[0]) ||
    Buffer.from(pieces[0], "base64url").byteLength !== SESSION_ID_BYTES ||
    !equalBase64Url(pieces[1], hmac(security, "session", pieces[0]))
  ) {
    throw new LocalRequestSecurityError(
      "로컬 세션을 확인할 수 없습니다.",
      401,
    );
  }
  return pieces[0];
}

export function assertLocalSession(
  headers: Headers,
  security: LocalSecurityConfig,
): void {
  assertExactLocalRequest(headers, security, { requireOrigin: false });
  verifiedSessionId(headers, security);
}

export function assertLocalMutation(
  headers: Headers,
  security: LocalSecurityConfig,
): void {
  assertExactLocalRequest(headers, security, { requireOrigin: true });
  const sessionId = verifiedSessionId(headers, security);
  const csrfToken = headers.get(CSRF_HEADER_NAME);
  if (
    csrfToken === null ||
    !equalBase64Url(csrfToken, hmac(security, "csrf", sessionId))
  ) {
    throw new LocalRequestSecurityError(
      "요청 보안 토큰을 확인할 수 없습니다.",
    );
  }
}
