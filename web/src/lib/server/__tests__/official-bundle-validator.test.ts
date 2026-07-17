// @vitest-environment node
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { canonicalize } from "json-canonicalize";
import { expect, it } from "vitest";

import type { WebReportBundleV1 } from "../../../../../contracts/web-report/v1/generated/types";
import { validateBundleBytes } from "@/lib/server/bundle-validator";

it("validates an official-link bundle after its root hash is renewed", async () => {
  const fixturePath = path.resolve(
    path.dirname(fileURLToPath(import.meta.url)),
    "../../../../../contracts/web-report/v1/fixtures/valid-unverified-import.json",
  );
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

  await expect(
    validateBundleBytes(Buffer.from(canonicalize(bundle))),
  ).resolves.toMatchObject({ bundle_hash: bundle.bundle_hash });
});
