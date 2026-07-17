// @vitest-environment node
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { canonicalize } from "json-canonicalize";
import { describe, expect, it } from "vitest";

import type { WebReportBundleV1 } from "../../../../../contracts/web-report/v1/generated/types";
import {
  MAX_REPORT_IMPORT_BYTES,
  validateBundleBytes,
} from "@/lib/server/bundle-validator";

const fixtureRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../../../contracts/web-report/v1/fixtures",
);

describe("bundle validator", () => {
  it("accepts the frozen valid bundle fixture", async () => {
    const bundle = await validateBundleBytes(
      await readFile(path.join(fixtureRoot, "valid-poc.json")),
    );
    expect(bundle.bundle_version).toBe("1.0.0");
  });

  it.each([
    ["invalid-hash.json", "bundle hash"],
    ["invalid-reference.json", "Evidence Link"],
  ])("rejects %s with its semantic violation", async (name, expected) => {
    await expect(
      validateBundleBytes(await readFile(path.join(fixtureRoot, name))),
    ).rejects.toThrow(expected);
  });

  it("rejects oversized bytes before parsing JSON", async () => {
    await expect(
      validateBundleBytes(new Uint8Array(MAX_REPORT_IMPORT_BYTES + 1)),
    ).rejects.toThrow("52,428,800");
  });

  it.each([
    "/etc/passwd",
    "/var/lib/trusted-ceo/report.json",
    "/tmp/trusted-ceo/source.csv",
  ])("rejects POSIX absolute display locator %s", async (displayLocator) => {
    const bundle = JSON.parse(
      await readFile(path.join(fixtureRoot, "valid-poc.json"), "utf8"),
    ) as WebReportBundleV1;
    bundle.source_view[0].locator_summaries[0].display_locator = displayLocator;
    const hashBody = structuredClone(bundle) as Partial<WebReportBundleV1>;
    delete hashBody.bundle_hash;
    bundle.bundle_hash = createHash("sha256")
      .update(canonicalize(hashBody), "utf8")
      .digest("hex");

    await expect(
      validateBundleBytes(new TextEncoder().encode(JSON.stringify(bundle))),
    ).rejects.toThrow("absolute path");
  });

  it("allows an RFC 6901 JSON Pointer display locator", async () => {
    const bundle = JSON.parse(
      await readFile(path.join(fixtureRoot, "valid-poc.json"), "utf8"),
    ) as WebReportBundleV1;
    bundle.source_view[0].locator_summaries[0].locator_type = "json_pointer";
    bundle.source_view[0].locator_summaries[0].display_locator = "/records/0";
    const hashBody = structuredClone(bundle) as Partial<WebReportBundleV1>;
    delete hashBody.bundle_hash;
    bundle.bundle_hash = createHash("sha256")
      .update(canonicalize(hashBody), "utf8")
      .digest("hex");

    await expect(
      validateBundleBytes(new TextEncoder().encode(JSON.stringify(bundle))),
    ).resolves.toMatchObject({ bundle_hash: bundle.bundle_hash });
  });
});
