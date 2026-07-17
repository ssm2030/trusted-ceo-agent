import type {
  ViewerEligibilityDecisionV1,
  WebReportBundleV1,
} from "../../../../contracts/web-report/v1/generated/types";
import {
  sanitizeReportBundle,
  type ReportClientPayload,
  type ReportEligibility,
} from "@/features/report/report-model";

import { WebReportValidationError } from "@/lib/server/bundle-validator";

export function makeUnverifiedImportDecision(
  bundle: WebReportBundleV1,
): ViewerEligibilityDecisionV1 {
  return Object.freeze({
    decision_version: "1.0.0",
    eligible: true,
    viewer_mode: "unverified_import",
    badge_label_ko: "출처 미확인 묶음",
    run_id: bundle.run.run_id,
    revision: bundle.run.revision,
    bundle_hash: bundle.bundle_hash,
    completed_checks: [
      "bundle_hash",
      "bundle_schema",
      "reference_closure",
    ],
    failure_code: null,
    failure_message: null,
  });
}

export function eligibilityFromDecision(
  decision: ViewerEligibilityDecisionV1,
): ReportEligibility {
  if (!decision.eligible || decision.viewer_mode === "rejected") {
    throw new WebReportValidationError(
      "rejected report cannot be presented",
    );
  }
  if (decision.viewer_mode === "trusted_final") {
    return Object.freeze({
      mode: "trusted_final" as const,
      label: "승인·검증된 실행본" as const,
      trusted: true,
      questionsAllowed: true,
    });
  }
  if (decision.viewer_mode === "poc_fixture") {
    return Object.freeze({
      mode: "poc_fixture" as const,
      label: "검증된 POC 시연 실행본" as const,
      trusted: false,
      questionsAllowed: false,
    });
  }
  return Object.freeze({
    mode: "unverified_import" as const,
    label: "출처 미확인 묶음" as const,
    trusted: false,
    questionsAllowed: false,
  });
}

export function buildClientReportPayload(
  bundle: WebReportBundleV1,
  decision: ViewerEligibilityDecisionV1,
): ReportClientPayload {
  if (
    decision.run_id !== bundle.run.run_id ||
    decision.revision !== bundle.run.revision ||
    decision.bundle_hash !== bundle.bundle_hash
  ) {
    throw new WebReportValidationError(
      "report and eligibility decision do not match",
    );
  }
  return sanitizeReportBundle(
    bundle,
    eligibilityFromDecision(decision),
  );
}
