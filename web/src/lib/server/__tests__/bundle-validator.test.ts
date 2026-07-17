// @vitest-environment node
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

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
});
