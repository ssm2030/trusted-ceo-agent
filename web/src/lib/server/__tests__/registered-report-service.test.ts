// @vitest-environment node
import {
  mkdir,
  mkdtemp,
  readFile,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it, vi } from "vitest";

import type { ViewerEligibilityDecisionV1 } from "../../../../../contracts/web-report/v1/generated/types";
import { activateRegisteredReport } from "@/lib/server/registered-report-service";
import { ReportStore } from "@/lib/server/report-store";
import { RunRegistry } from "@/lib/server/run-registry";

const fixturePath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../../../contracts/web-report/v1/fixtures/valid-trusted.json",
);

describe("registered report activation", () => {
  it("cross-validates a registered bundle before atomically publishing it", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "trusted-ceo-registered-"));
    const runsRoot = path.join(root, "runs");
    const runId = "run_20260717T000000Z_aaaaaaaaaaaaaaaa";
    const artifactRoot = path.join(runsRoot, runId);
    await mkdir(artifactRoot, { recursive: true });
    const bytes = await readFile(fixturePath);
    const bundle = JSON.parse(bytes.toString("utf8"));
    await writeFile(
      path.join(artifactRoot, "web-report-bundle.json"),
      bytes,
    );
    const registryPath = path.join(root, "registry.json");
    await writeFile(
      registryPath,
      JSON.stringify({
        registrations: [
          {
            registration_id: "representative",
            canonical_artifact_root: artifactRoot,
            expected_run_id: runId,
            allowed_revision: 3,
            expected_bundle_hash: bundle.bundle_hash,
          },
        ],
      }),
    );
    const decision: ViewerEligibilityDecisionV1 = {
      decision_version: "1.0.0",
      eligible: true,
      viewer_mode: "trusted_final",
      badge_label_ko: "승인·검증된 실행본",
      run_id: runId,
      revision: 3,
      bundle_hash: bundle.bundle_hash,
      completed_checks: ["final_package"],
      failure_code: null,
      failure_message: null,
    };
    const validator = vi.fn().mockResolvedValue(decision);
    const store = new ReportStore(path.join(root, "runtime"));

    await activateRegisteredReport("representative", {
      registry: new RunRegistry(registryPath, runsRoot),
      store,
      validator,
    });

    expect(validator).toHaveBeenCalledWith(
      expect.objectContaining({
        artifactRoot,
        runId,
        revision: 3,
        expectedBundleHash: bundle.bundle_hash,
        bundlePath: expect.stringContaining("current-report.json"),
      }),
    );
    expect((await store.readCurrentPair())?.decision).toEqual(
      decision,
    );
  });

  it("keeps the existing current report when plugin validation fails", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "trusted-ceo-registered-"));
    const runsRoot = path.join(root, "runs");
    const runId = "run_20260717T000000Z_aaaaaaaaaaaaaaaa";
    const artifactRoot = path.join(runsRoot, runId);
    await mkdir(artifactRoot, { recursive: true });
    const bytes = await readFile(fixturePath);
    const bundle = JSON.parse(bytes.toString("utf8"));
    await writeFile(
      path.join(artifactRoot, "web-report-bundle.json"),
      bytes,
    );
    const registryPath = path.join(root, "registry.json");
    await writeFile(
      registryPath,
      JSON.stringify({
        registrations: [
          {
            registration_id: "representative",
            canonical_artifact_root: artifactRoot,
            expected_run_id: runId,
            allowed_revision: 3,
            expected_bundle_hash: bundle.bundle_hash,
          },
        ],
      }),
    );
    const store = new ReportStore(path.join(root, "runtime"));
    await store.publishVerified(Buffer.from('{"old":true}'), {
      bundle_hash: "old",
    });
    const before = await store.readCurrentPair();

    await expect(
      activateRegisteredReport("representative", {
        registry: new RunRegistry(registryPath, runsRoot),
        store,
        validator: async () => {
          throw new Error("plugin rejected");
        },
      }),
    ).rejects.toThrow("plugin rejected");
    expect((await store.readCurrentPair())?.generation).toBe(
      before?.generation,
    );
  });
});
