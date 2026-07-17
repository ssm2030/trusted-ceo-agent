import { lookup } from "node:dns/promises";
import type { LookupAddress } from "node:dns";
import { isIP } from "node:net";

import type { OfficialUrlPolicy } from "../../../../contracts/web-report/v1/generated/types";

import {
  OfficialUrlPolicyError,
  assertOfficialUrl,
} from "@/lib/server/official-url-policy";

const REDIRECT_STATUSES = new Set([301, 302, 303, 307, 308]);
const MAX_REDIRECTS = 5;
const REQUEST_TIMEOUT_MS = 5_000;

export type OfficialLinkResolverOptions = Readonly<{
  fetcher?: typeof fetch;
  assertPublicDestination?: (url: URL) => Promise<void>;
}>;

function isPublicIpv4(address: string): boolean {
  const octets = address.split(".").map(Number);
  if (
    octets.length !== 4 ||
    octets.some(
      (octet) =>
        !Number.isInteger(octet) || octet < 0 || octet > 255,
    )
  ) {
    return false;
  }
  const [a, b, c] = octets;
  return !(
    a === 0 ||
    a === 10 ||
    a === 127 ||
    a >= 224 ||
    (a === 100 && b >= 64 && b <= 127) ||
    (a === 169 && b === 254) ||
    (a === 172 && b >= 16 && b <= 31) ||
    (a === 192 && b === 0 && c === 0) ||
    (a === 192 && b === 0 && c === 2) ||
    (a === 192 && b === 168) ||
    (a === 198 && (b === 18 || b === 19)) ||
    (a === 198 && b === 51 && c === 100) ||
    (a === 203 && b === 0 && c === 113)
  );
}

function isPublicIpv6(address: string): boolean {
  const normalized = address.toLowerCase();
  if (normalized.startsWith("::ffff:")) {
    return isPublicIpv4(normalized.slice("::ffff:".length));
  }
  return !(
    normalized === "::" ||
    normalized === "::1" ||
    normalized.startsWith("fc") ||
    normalized.startsWith("fd") ||
    /^fe[89ab]/.test(normalized) ||
    normalized.startsWith("ff") ||
    normalized.startsWith("2001:db8:")
  );
}

function isPublicAddress(address: string): boolean {
  const family = isIP(address);
  return (
    (family === 4 && isPublicIpv4(address)) ||
    (family === 6 && isPublicIpv6(address))
  );
}

export async function assertPublicOfficialDestination(
  url: URL,
): Promise<void> {
  const host = url.hostname.toLowerCase();
  if (
    host === "localhost" ||
    host.endsWith(".localhost") ||
    host.endsWith(".local") ||
    host.endsWith(".internal")
  ) {
    throw new OfficialUrlPolicyError();
  }
  if (isIP(host) !== 0) {
    if (!isPublicAddress(host)) {
      throw new OfficialUrlPolicyError();
    }
    return;
  }
  let addresses: LookupAddress[];
  try {
    addresses = await lookup(host, { all: true, verbatim: true });
  } catch {
    throw new OfficialUrlPolicyError();
  }
  if (
    addresses.length === 0 ||
    addresses.some((entry) => !isPublicAddress(entry.address))
  ) {
    throw new OfficialUrlPolicyError();
  }
}

async function requestHeaders(
  url: URL,
  fetcher: typeof fetch,
): Promise<Response> {
  const options: RequestInit = {
    method: "HEAD",
    redirect: "manual",
    cache: "no-store",
    credentials: "omit",
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  };
  let response: Response;
  try {
    response = await fetcher(url, options);
    if (response.status === 405 || response.status === 501) {
      await response.body?.cancel();
      response = await fetcher(url, {
        ...options,
        method: "GET",
        headers: { Range: "bytes=0-0" },
      });
    }
  } catch {
    throw new OfficialUrlPolicyError();
  }
  return response;
}

export async function resolveOfficialUrl(
  initialUrl: string,
  policy: OfficialUrlPolicy,
  options: OfficialLinkResolverOptions = {},
): Promise<string> {
  const fetcher = options.fetcher ?? fetch;
  const assertPublic =
    options.assertPublicDestination ??
    assertPublicOfficialDestination;
  const initial = assertOfficialUrl(initialUrl, initialUrl, policy);
  let current = initial;

  for (let redirectCount = 0; ; redirectCount += 1) {
    if (redirectCount > MAX_REDIRECTS) {
      throw new OfficialUrlPolicyError();
    }
    assertOfficialUrl(initial.href, current.href, policy);
    await assertPublic(current);
    const response = await requestHeaders(current, fetcher);
    if (!REDIRECT_STATUSES.has(response.status)) {
      await response.body?.cancel();
      if (!response.ok) {
        throw new OfficialUrlPolicyError();
      }
      return current.href;
    }
    await response.body?.cancel();
    if (!policy.allow_redirects) {
      throw new OfficialUrlPolicyError();
    }
    const location = response.headers.get("location");
    if (location === null) {
      throw new OfficialUrlPolicyError();
    }
    let target: URL;
    try {
      target = new URL(location, current);
    } catch {
      throw new OfficialUrlPolicyError();
    }
    current = assertOfficialUrl(initial.href, target.href, policy);
  }
}
