// @vitest-environment node
import { describe, expect, it } from "vitest";

import {
  SESSION_COOKIE_NAME,
  assertExactLocalRequest,
  assertLocalMutation,
  createLocalSecurityConfig,
  issueLocalSession,
  serializeSessionCookie,
} from "@/lib/server/local-request-security";

function localHeaders(overrides: Record<string, string> = {}): Headers {
  return new Headers({
    host: "127.0.0.1:3000",
    origin: "http://127.0.0.1:3000",
    ...overrides,
  });
}

describe("localhost request security", () => {
  const security = createLocalSecurityConfig({
    port: 3000,
    sessionSecret: new Uint8Array(32).fill(7),
  });

  it("accepts only the configured numeric localhost Host and Origin", () => {
    expect(() =>
      assertExactLocalRequest(localHeaders(), security, {
        requireOrigin: true,
      }),
    ).not.toThrow();

    expect(() =>
      assertExactLocalRequest(
        localHeaders({ host: "localhost:3000" }),
        security,
        { requireOrigin: true },
      ),
    ).toThrow("허용되지 않은 로컬 요청입니다.");
    expect(() =>
      assertExactLocalRequest(
        localHeaders({ origin: "http://127.0.0.1:3001" }),
        security,
        { requireOrigin: true },
      ),
    ).toThrow("허용되지 않은 로컬 요청입니다.");
  });

  it("requires a signed session and matching CSRF token for mutations", () => {
    const session = issueLocalSession(security);
    const headers = localHeaders({
      cookie: `${SESSION_COOKIE_NAME}=${session.cookieValue}`,
      "x-csrf-token": session.csrfToken,
    });

    expect(() => assertLocalMutation(headers, security)).not.toThrow();
    headers.set("x-csrf-token", `${session.csrfToken}x`);
    expect(() => assertLocalMutation(headers, security)).toThrow(
      "요청 보안 토큰을 확인할 수 없습니다.",
    );
  });

  it("serializes a host-only HttpOnly SameSite=Strict cookie", () => {
    const session = issueLocalSession(security);
    const cookie = serializeSessionCookie(session.cookieValue);

    expect(cookie).toContain(`${SESSION_COOKIE_NAME}=`);
    expect(cookie).toContain("HttpOnly");
    expect(cookie).toContain("SameSite=Strict");
    expect(cookie).toContain("Path=/");
    expect(cookie).not.toContain("Domain=");
    expect(SESSION_COOKIE_NAME).not.toMatch(/^__Host-/);
    expect(cookie).not.toContain(Buffer.from(security.sessionSecret).toString("hex"));
  });
});
