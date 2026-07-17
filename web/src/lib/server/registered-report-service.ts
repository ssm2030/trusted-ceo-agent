import {
  readFile,
  realpath,
  stat,
} from "node:fs/promises";
import path from "node:path";

import type { ViewerEligibilityDecisionV1 } from "../../../../contracts/web-report/v1/generated/types";

import {
  WebReportValidationError,
  validateBundleBytes,
  validateEligibilityDecision,
} from "@/lib/server/bundle-validator";
import { MAX_REPORT_IMPORT_BYTES } from "@/lib/server/import-policy";
import {
  type ValidateWebReportInput,
  validateRegisteredReport,
} from "@/lib/server/plugin-validator-client";
import type { ReportStore } from "@/lib/server/report-store";
import type { RunRegistry } from "@/lib/server/run-registry";

export type RegisteredReportValidator = (
  input: ValidateWebReportInput,
) => Promise<ViewerEligibilityDecisionV1>;

export type RegisteredReportDependencies = Readonly<{
  registry: RunRegistry;
  store: ReportStore;
  validator?: RegisteredReportValidator;
}>;

async function stableBundleRead(bundlePath: string): Promise<Uint8Array> {
  const before = await stat(bundlePath);
  if (
    !before.isFile() ||
    before.size <= 0 ||
    before.size > MAX_REPORT_IMPORT_BYTES
  ) {
    throw new WebReportValidationError(
      "registered web report bundle size is invalid",
    );
  }
  const bytes = await readFile(bundlePath);
  const after = await stat(bundlePath);
  if (
    before.size !== after.size ||
    before.mtimeMs !== after.mtimeMs ||
    bytes.byteLength !== after.size
  ) {
    throw new WebReportValidationError(
      "registered web report bundle changed while reading",
    );
  }
  return new Uint8Array(bytes);
}

export async function activateRegisteredReport(
  registrationId: string,
  dependencies: RegisteredReportDependencies,
): Promise<ViewerEligibilityDecisionV1> {
  const registration =
    await dependencies.registry.get(registrationId);
  const expectedBundlePath = path.join(
    registration.canonical_artifact_root,
    "web-report-bundle.json",
  );
  const bundlePath = await realpath(expectedBundlePath);
  if (
    path.dirname(bundlePath) !==
    registration.canonical_artifact_root
  ) {
    throw new WebReportValidationError(
      "registered bundle is outside its artifact root",
    );
  }
  const bytes = await stableBundleRead(bundlePath);
  const bundle = await validateBundleBytes(bytes);
  if (
    bundle.run.workflow_state !== "finalized" ||
    bundle.run.run_id !== registration.expected_run_id ||
    bundle.run.revision !== registration.allowed_revision ||
    bundle.bundle_hash !== registration.expected_bundle_hash
  ) {
    throw new WebReportValidationError(
      "registered bundle does not match the run registry",
    );
  }
  const validator =
    dependencies.validator ?? validateRegisteredReport;
  return dependencies.store.replaceAfterValidation(
    bytes,
    async (candidatePath) => {
      const decision = await validator({
        artifactRoot: registration.canonical_artifact_root,
        bundlePath: candidatePath,
        runId: registration.expected_run_id,
        revision: registration.allowed_revision,
        expectedBundleHash: registration.expected_bundle_hash,
      });
      await validateEligibilityDecision(decision);
      if (
        !decision.eligible ||
        decision.viewer_mode === "rejected" ||
        decision.run_id !== registration.expected_run_id ||
        decision.revision !== registration.allowed_revision ||
        decision.bundle_hash !== registration.expected_bundle_hash
      ) {
        throw new WebReportValidationError(
          "plugin decision does not match the run registry",
        );
      }
      return decision;
    },
  );
}
