// @vitest-environment node
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { RunRegistry } from "@/lib/server/run-registry";

const RUN_ID = "run_20260717T000000Z_aaaaaaaaaaaaaaaa";

describe("RunRegistry", () => {
  it("resolves only a server-configured registration below the allowlist root", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "trusted-ceo-registry-"));
    const allowed = path.join(root, "runs");
    const artifactRoot = path.join(allowed, RUN_ID);
    await mkdir(artifactRoot, { recursive: true });
    const registryPath = path.join(root, "registry.json");
    await writeFile(
      registryPath,
      JSON.stringify({
        registrations: [
          {
            registration_id: "representative",
            canonical_artifact_root: artifactRoot,
            expected_run_id: RUN_ID,
            allowed_revision: 9,
            expected_bundle_hash: "a".repeat(64),
          },
        ],
      }),
    );

    const registration = await new RunRegistry(
      registryPath,
      allowed,
    ).get("representative");
    expect(registration.expected_run_id).toBe(RUN_ID);
    expect(registration.canonical_artifact_root).toBe(artifactRoot);
  });

  it("rejects an artifact root outside the startup allowlist", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "trusted-ceo-registry-"));
    const allowed = path.join(root, "runs");
    const outside = path.join(root, "outside");
    await Promise.all([
      mkdir(allowed, { recursive: true }),
      mkdir(outside, { recursive: true }),
    ]);
    const registryPath = path.join(root, "registry.json");
    await writeFile(
      registryPath,
      JSON.stringify({
        registrations: [
          {
            registration_id: "outside",
            canonical_artifact_root: outside,
            expected_run_id: RUN_ID,
            allowed_revision: 1,
            expected_bundle_hash: "b".repeat(64),
          },
        ],
      }),
    );

    await expect(
      new RunRegistry(registryPath, allowed).get("outside"),
    ).rejects.toThrow("허용된 실행 디렉터리");
  });
});
