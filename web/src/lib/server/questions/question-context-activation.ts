import {
  validateBundleBytes,
} from "@/lib/server/bundle-validator";
import {
  activateRegisteredReport,
  type RegisteredReportDependencies,
} from "@/lib/server/registered-report-service";
import {
  setCurrentQuestionRunContext,
} from "@/lib/server/questions/run-context";

export async function activateRegisteredReportForQuestions(
  registrationId: string,
  dependencies: RegisteredReportDependencies,
) {
  const registration =
    await dependencies.registry.get(registrationId);
  const decision = await activateRegisteredReport(
    registrationId,
    dependencies,
  );
  const current = await dependencies.store.readCurrentPair();
  if (current === null) {
    throw new Error("registered report publication is unavailable");
  }
  const bundle = await validateBundleBytes(current.bytes);
  if (
    !decision.eligible ||
    (decision.viewer_mode !== "trusted_final" &&
      decision.viewer_mode !== "poc_fixture") ||
    decision.run_id !== registration.expected_run_id ||
    decision.revision !== registration.allowed_revision ||
    decision.bundle_hash !== registration.expected_bundle_hash ||
    bundle.run.run_id !== registration.expected_run_id ||
    bundle.run.revision !== registration.allowed_revision ||
    bundle.bundle_hash !== registration.expected_bundle_hash
  ) {
    throw new Error(
      "registered report question context is inconsistent",
    );
  }
  setCurrentQuestionRunContext({
    registrationId,
    artifactRoot: registration.canonical_artifact_root,
    runId: registration.expected_run_id,
    revision: registration.allowed_revision,
    viewerMode: decision.viewer_mode,
    privacyClassification:
      decision.viewer_mode === "poc_fixture" ||
      bundle.trust_view.deidentification.poc_only
        ? "poc_deidentified"
        : "company_restricted",
    bundleHash: registration.expected_bundle_hash,
  });
  return decision;
}
