// @vitest-environment node
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { validateBundleBytes } from "@/lib/server/bundle-validator";
import {
  buildClientReportPayload,
  makeUnverifiedImportDecision,
} from "@/lib/server/report-presentation";

const fixturePath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../../../contracts/web-report/v1/fixtures/valid-trusted.json",
);

describe("report presentation boundary", () => {
  it("forces standalone imports to unverified with questions disabled", async () => {
    const bundle = await validateBundleBytes(await readFile(fixturePath));
    const decision = makeUnverifiedImportDecision(bundle);
    const payload = buildClientReportPayload(bundle, decision);

    expect(payload.eligibility).toEqual({
      mode: "unverified_import",
      label: "출처 미확인 묶음",
      trusted: false,
      questionsAllowed: false,
    });
  });

  it("strips embedded previews, locators, and raw official URLs from browser data", async () => {
    const bundle = await validateBundleBytes(await readFile(fixturePath));
    bundle.source_view[0].official_url =
      "https://official.example/report";
    const payload = buildClientReportPayload(
      bundle,
      makeUnverifiedImportDecision(bundle),
    );
    const serialized = JSON.stringify(payload);

    expect(serialized).not.toContain("source_previews");
    expect(serialized).not.toContain("snapshot_locator");
    expect(serialized).not.toContain("https://official.example/report");
    expect(payload.report.source_view[0].official_link_available).toBe(
      true,
    );
  });
});
