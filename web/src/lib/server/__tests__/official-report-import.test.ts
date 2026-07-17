// @vitest-environment node
import { createHash } from "node:crypto";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { canonicalize } from "json-canonicalize";
import { describe, expect, it } from "vitest";

import type { WebReportBundleV1 } from "../../../../../contracts/web-report/v1/generated/types";
import { REPORT_FILE_NAME_HEADER } from "@/lib/server/import-policy";
import {
  CSRF_HEADER_NAME,
  SESSION_COOKIE_NAME,
  createLocalSecurityConfig,
  issueLocalSession,
} from "@/lib/server/local-request-security";
import { handleReportImport } from "@/lib/server/report-route-handlers";
import { ReportStore } from "@/lib/server/report-store";

const fixturePath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../../../contracts/web-report/v1/fixtures/valid-unverified-import.json",
);

describe("official report import", () => {
  it("accepts a hash-valid bundle with an allowlisted official URL", async () => {
    const bundle = JSON.parse(
      await readFile(fixturePath, "utf8"),
    ) as WebReportBundleV1;
    bundle.source_view[0].official_url =
      "https://official.example/start";
    bundle.official_url_policy.allowed_origins = [
      "https://official.example",
    ];
    bundle.official_url_policy.allow_redirects = true;
    const copy = structuredClone(bundle) as Partial<WebReportBundleV1>;
    delete copy.bundle_hash;
    bundle.bundle_hash = createHash("sha256")
      .update(canonicalize(copy), "utf8")
      .digest("hex");
    const bytes = Buffer.from(canonicalize(bundle));
    const security = createLocalSecurityConfig({
      port: 3000,
      sessionSecret: new Uint8Array(32).fill(9),
    });
    const session = issueLocalSession(security);
    const response = await handleReportImport(
      new Request(`${security.origin}/api/report/import`, {
        method: "POST",
        headers: {
          host: security.host,
          origin: security.origin,
          cookie: `${SESSION_COOKIE_NAME}=${session.cookieValue}`,
          [CSRF_HEADER_NAME]: session.csrfToken,
          [REPORT_FILE_NAME_HEADER]: "web-report-bundle.json",
          "content-type": "application/json",
          "content-length": String(bytes.byteLength),
        },
        body: bytes,
      }),
      {
        security,
        store: new ReportStore(
          await mkdtemp(
            path.join(tmpdir(), "trusted-ceo-official-import-"),
          ),
        ),
      },
    );
    const body = await response.json();
    expect({ status: response.status, body }).toMatchObject({
      status: 201,
      body: { imported: true },
    });
  });
});
