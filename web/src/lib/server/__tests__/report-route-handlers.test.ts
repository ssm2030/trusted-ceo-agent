// @vitest-environment node
import { createHash } from "node:crypto";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { canonicalize } from "json-canonicalize";
import { describe, expect, it, vi } from "vitest";

import type { WebReportBundleV1 } from "../../../../../contracts/web-report/v1/generated/types";
import {
  REPORT_FILE_NAME_HEADER,
} from "@/lib/server/import-policy";
import {
  CSRF_HEADER_NAME,
  SESSION_COOKIE_NAME,
  createLocalSecurityConfig,
  issueLocalSession,
} from "@/lib/server/local-request-security";
import {
  handleCurrentReport,
  handleOfficialLink,
  handleReportImport,
  handleSessionBootstrap,
  handleSourcePreview,
} from "@/lib/server/report-route-handlers";
import { ReportStore } from "@/lib/server/report-store";

const fixtureRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../../../contracts/web-report/v1/fixtures",
);

function securityFixture() {
  return createLocalSecurityConfig({
    port: 3000,
    sessionSecret: new Uint8Array(32).fill(9),
  });
}

function authenticatedHeaders(
  mutation: boolean,
): { headers: Headers; security: ReturnType<typeof securityFixture> } {
  const security = securityFixture();
  const session = issueLocalSession(security);
  const headers = new Headers({
    host: security.host,
    cookie: `${SESSION_COOKIE_NAME}=${session.cookieValue}`,
  });
  if (mutation) {
    headers.set("origin", security.origin);
    headers.set(CSRF_HEADER_NAME, session.csrfToken);
  }
  return { headers, security };
}

function hashBundle(bundle: WebReportBundleV1): string {
  const copy = structuredClone(bundle) as WebReportBundleV1;
  delete (copy as Partial<WebReportBundleV1>).bundle_hash;
  return createHash("sha256")
    .update(canonicalize(copy), "utf8")
    .digest("hex");
}

describe("report route handlers", () => {
  it("bootstraps a session only for the exact local Host and Origin", async () => {
    const security = securityFixture();
    const response = await handleSessionBootstrap(
      new Request(`${security.origin}/api/report/session`, {
        method: "POST",
        headers: {
          host: security.host,
          origin: security.origin,
        },
      }),
      { security },
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("set-cookie")).toContain("HttpOnly");
    expect(response.headers.get("set-cookie")).toContain(
      "SameSite=Strict",
    );
    expect(response.headers.has("access-control-allow-origin")).toBe(
      false,
    );

    const rejected = await handleSessionBootstrap(
      new Request(`${security.origin}/api/report/session`, {
        method: "POST",
        headers: {
          host: "localhost:3000",
          origin: security.origin,
        },
      }),
      { security },
    );
    expect(rejected.status).toBe(403);
  });

  it("imports one valid JSON bundle as unverified and returns sanitized current data", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "trusted-ceo-route-"));
    const store = new ReportStore(root);
    const bytes = await readFile(
      path.join(fixtureRoot, "valid-trusted.json"),
    );
    const { headers, security } = authenticatedHeaders(true);
    headers.set(REPORT_FILE_NAME_HEADER, "web-report-bundle.json");
    headers.set("content-type", "application/json");
    headers.set("content-length", String(bytes.byteLength));

    const imported = await handleReportImport(
      new Request(`${security.origin}/api/report/import`, {
        method: "POST",
        headers,
        body: bytes,
      }),
      { security, store },
    );
    expect(imported.status).toBe(201);
    expect(
      (await store.readCurrentPair())?.decision,
    ).toMatchObject({
      viewer_mode: "unverified_import",
      badge_label_ko: "출처 미확인 묶음",
    });

    const readHeaders = authenticatedHeaders(false);
    const current = await handleCurrentReport(
      new Request(`${security.origin}/api/report/current`, {
        headers: readHeaders.headers,
      }),
      { security: readHeaders.security, store },
    );
    expect(current.status).toBe(200);
    const payload = await current.json();
    expect(payload.eligibility.questionsAllowed).toBe(false);
    const serialized = JSON.stringify(payload);
    expect(serialized).not.toContain("source_previews");
    expect(serialized).not.toContain("snapshot_locator");
    expect(current.headers.get("cache-control")).toBe("no-store");
  });

  it("preserves the current generation after an invalid import", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "trusted-ceo-route-"));
    const store = new ReportStore(root);
    const valid = await readFile(
      path.join(fixtureRoot, "valid-unverified-import.json"),
    );
    const invalid = await readFile(
      path.join(fixtureRoot, "invalid-hash.json"),
    );
    const { headers, security } = authenticatedHeaders(true);
    headers.set(REPORT_FILE_NAME_HEADER, "web-report-bundle.json");
    headers.set("content-type", "application/json");
    headers.set("content-length", String(valid.byteLength));
    await handleReportImport(
      new Request(`${security.origin}/api/report/import`, {
        method: "POST",
        headers,
        body: valid,
      }),
      { security, store },
    );
    const before = await store.readCurrentPair();

    headers.set("content-length", String(invalid.byteLength));
    const response = await handleReportImport(
      new Request(`${security.origin}/api/report/import`, {
        method: "POST",
        headers,
        body: invalid,
      }),
      { security, store },
    );
    expect(response.status).toBe(422);
    expect((await store.readCurrentPair())?.generation).toBe(
      before?.generation,
    );
  });

  it("serves permitted preview values only through a preview ref", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "trusted-ceo-route-"));
    const store = new ReportStore(root);
    const bytes = await readFile(
      path.join(fixtureRoot, "valid-unverified-import.json"),
    );
    const { headers: mutationHeaders, security } =
      authenticatedHeaders(true);
    mutationHeaders.set(
      REPORT_FILE_NAME_HEADER,
      "web-report-bundle.json",
    );
    mutationHeaders.set("content-type", "application/json");
    mutationHeaders.set("content-length", String(bytes.byteLength));
    await handleReportImport(
      new Request(`${security.origin}/api/report/import`, {
        method: "POST",
        headers: mutationHeaders,
        body: bytes,
      }),
      { security, store },
    );
    const { headers } = authenticatedHeaders(false);
    const response = await handleSourcePreview(
      new Request(
        `${security.origin}/api/report/source-previews/preview_main`,
        { headers },
      ),
      "preview_main",
      { security: securityFixture(), store },
    );
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      preview_ref: "preview_main",
      access_policy: "permitted",
      rows: expect.any(Array),
    });
  });

  it("resolves official links on the server and exposes only the final redirect", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "trusted-ceo-route-"));
    const store = new ReportStore(root);
    const bundle = JSON.parse(
      await readFile(
        path.join(fixtureRoot, "valid-unverified-import.json"),
        "utf8",
      ),
    ) as WebReportBundleV1;
    bundle.source_view[0].official_url =
      "https://official.example/start";
    bundle.official_url_policy.allowed_origins = [
      "https://official.example",
    ];
    bundle.official_url_policy.allow_redirects = true;
    bundle.bundle_hash = hashBundle(bundle);
    const bytes = Buffer.from(canonicalize(bundle));
    const { headers: mutationHeaders, security } =
      authenticatedHeaders(true);
    mutationHeaders.set(
      REPORT_FILE_NAME_HEADER,
      "web-report-bundle.json",
    );
    mutationHeaders.set("content-type", "application/json");
    mutationHeaders.set("content-length", String(bytes.byteLength));
    await handleReportImport(
      new Request(`${security.origin}/api/report/import`, {
        method: "POST",
        headers: mutationHeaders,
        body: bytes,
      }),
      { security, store },
    );
    const read = authenticatedHeaders(false);
    const resolver = vi
      .fn()
      .mockResolvedValue("https://official.example/final");
    const response = await handleOfficialLink(
      new Request(
        `${security.origin}/api/report/official-links/source_main`,
        { headers: read.headers },
      ),
      "source_main",
      {
        security: read.security,
        store,
        resolveOfficialUrl: resolver,
      },
    );
    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe(
      "https://official.example/final",
    );
    expect(resolver).toHaveBeenCalledWith(
      "https://official.example/start",
      bundle.official_url_policy,
    );
  });
});
