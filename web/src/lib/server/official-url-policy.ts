import type { OfficialUrlPolicy } from "../../../../contracts/web-report/v1/generated/types";

export class OfficialUrlPolicyError extends Error {
  constructor() {
    super("허용되지 않은 공식 자료 링크입니다.");
    this.name = "OfficialUrlPolicyError";
  }
}

function parseHttpUrl(value: string): URL {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new OfficialUrlPolicyError();
  }
  if (
    (parsed.protocol !== "https:" && parsed.protocol !== "http:") ||
    parsed.username !== "" ||
    parsed.password !== ""
  ) {
    throw new OfficialUrlPolicyError();
  }
  return parsed;
}

function exactAllowedOrigins(policy: OfficialUrlPolicy): Set<string> {
  const result = new Set<string>();
  for (const value of policy.allowed_origins) {
    const parsed = parseHttpUrl(value);
    if (
      value !== parsed.origin ||
      parsed.pathname !== "/" ||
      parsed.search !== "" ||
      parsed.hash !== ""
    ) {
      throw new OfficialUrlPolicyError();
    }
    result.add(value);
  }
  return result;
}

function assertAllowed(
  parsed: URL,
  schemes: ReadonlySet<string>,
  origins: ReadonlySet<string>,
): void {
  const scheme = parsed.protocol.slice(0, -1);
  if (!schemes.has(scheme) || !origins.has(parsed.origin)) {
    throw new OfficialUrlPolicyError();
  }
}

export function assertOfficialUrl(
  initialUrl: string,
  redirectFinalUrl: string,
  policy: OfficialUrlPolicy,
): URL {
  const schemes = new Set<string>(policy.allowed_schemes);
  const origins = exactAllowedOrigins(policy);
  const initial = parseHttpUrl(initialUrl);
  const final = parseHttpUrl(redirectFinalUrl);
  assertAllowed(initial, schemes, origins);
  assertAllowed(final, schemes, origins);
  if (!policy.allow_redirects && initial.href !== final.href) {
    throw new OfficialUrlPolicyError();
  }
  return final;
}
