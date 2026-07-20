import { tmpdir } from "node:os";
import path from "node:path";

import type {
  ViewerEligibilityDecisionV1,
  WebReportBundleV1,
} from "../../../../contracts/web-report/v1/generated/types";
import { canonicalize } from "json-canonicalize";

import type { BackendReport } from "@/lib/server/analysis/types";
import {
  WebReportValidationError,
  validateBundleBytes,
  validateEligibilityDecision,
} from "@/lib/server/bundle-validator";
import {
  setCurrentQuestionRunContext,
} from "@/lib/server/questions/run-context";
import type {
  QuestionRunContext,
} from "@/lib/server/questions/types";
import type { ReportStore } from "@/lib/server/report-store";

export type ServiceReportActivationDependencies = Readonly<{
  store: ReportStore;
  setContext?: (context: QuestionRunContext) => void;
}>;

function assertEligibleBinding(
  bundle: WebReportBundleV1,
  decision: ViewerEligibilityDecisionV1,
): void {
  const approval = bundle.viewer_eligibility_receipt.final_approval_summary;
  const trustedInput =
    approval.input_method === "web_hitl" ||
    approval.input_method === "interactive_tty";
  if (
    bundle.run.workflow_state !== "finalized" ||
    !decision.eligible ||
    decision.viewer_mode !== "trusted_final" ||
    decision.run_id !== bundle.run.run_id ||
    decision.revision !== bundle.run.revision ||
    decision.bundle_hash !== bundle.bundle_hash ||
    bundle.viewer_eligibility_receipt.claimed_viewer_mode !==
      "trusted_final" ||
    !trustedInput ||
    approval.fixture_only
  ) {
    throw new WebReportValidationError(
      "service report is not an eligible trusted final report",
    );
  }
}

export async function activateServiceReport(
  report: BackendReport,
  dependencies: ServiceReportActivationDependencies,
): Promise<ViewerEligibilityDecisionV1> {
  const bytes = new TextEncoder().encode(canonicalize(report.bundle));
  let validatedBundle: WebReportBundleV1 | null = null;
  const decision = await dependencies.store.replaceAfterValidation(
    bytes,
    async () => {
      const bundle = await validateBundleBytes(bytes);
      const eligibility = await validateEligibilityDecision(
        report.eligibility,
      );
      assertEligibleBinding(bundle, eligibility);
      validatedBundle = bundle;
      return eligibility;
    },
  );
  if (validatedBundle === null) {
    throw new WebReportValidationError(
      "service report validation did not produce a bundle",
    );
  }
  const bundle: WebReportBundleV1 = validatedBundle;
  const context: QuestionRunContext = {
    registrationId: `service:${bundle.run.run_id}:${bundle.run.revision}`,
    artifactRoot: path.join(
      tmpdir(),
      "trusted-ceo-agent-service-context",
    ),
    runId: bundle.run.run_id,
    revision: bundle.run.revision,
    viewerMode: "trusted_final",
    privacyClassification:
      bundle.trust_view.deidentification.poc_only
        ? "poc_deidentified"
        : "company_restricted",
    bundleHash: bundle.bundle_hash,
  };
  (dependencies.setContext ?? setCurrentQuestionRunContext)(context);
  return decision;
}