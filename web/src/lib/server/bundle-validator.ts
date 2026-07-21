import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import type {
  ViewerEligibilityDecisionV1,
  WebReportBundleV1,
} from "../../../../contracts/web-report/v1/generated/types";
import type { AnySchema } from "ajv";
import Ajv2020, { type ValidateFunction } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

import {
  MAX_REPORT_ARRAY_ITEMS,
  MAX_REPORT_JSON_DEPTH,
  WebReportValidationError,
  assertBoundedJson,
} from "@/lib/server/bundle-document-policy";
import { validateBundleSemantics } from "@/lib/server/bundle-semantics";
import { MAX_REPORT_IMPORT_BYTES } from "@/lib/server/import-policy";

export { MAX_REPORT_IMPORT_BYTES };
export {
  MAX_REPORT_ARRAY_ITEMS,
  MAX_REPORT_JSON_DEPTH,
  WebReportValidationError,
};

type ContractValidators = Readonly<{
  bundle: ValidateFunction;
  decision: ValidateFunction;
}>;

let validatorsPromise: Promise<ContractValidators> | undefined;


function contractRoot(): string {
  const moduleDirectory = path.dirname(fileURLToPath(import.meta.url));
  const candidates = [
    path.resolve(process.cwd(), "contracts/web-report/v1"),
    path.resolve(process.cwd(), "../contracts/web-report/v1"),
    path.resolve(moduleDirectory, "../../../../contracts/web-report/v1"),
  ];
  return candidates[0] === candidates[1]
    ? candidates[0]
    : candidates.find((candidate) =>
        path.isAbsolute(candidate),
      ) ?? candidates[0];
}

async function readSchema(name: string): Promise<AnySchema> {
  const candidates = [
    path.resolve(process.cwd(), "contracts/web-report/v1", name),
    path.resolve(process.cwd(), "../contracts/web-report/v1", name),
    path.resolve(
      path.dirname(fileURLToPath(import.meta.url)),
      "../../../../contracts/web-report/v1",
      name,
    ),
  ];
  let lastError: unknown;
  for (const candidate of candidates) {
    try {
      return JSON.parse(await readFile(candidate, "utf8")) as AnySchema;
    } catch (error) {
      lastError = error;
    }
  }
  throw new WebReportValidationError(
    `web report contract schema is unavailable under ${contractRoot()}: ${String(lastError)}`,
  );
}

async function contractValidators(): Promise<ContractValidators> {
  validatorsPromise ??= (async () => {
    const ajv = new Ajv2020({
      allErrors: true,
      allowUnionTypes: true,
      strict: true,
    });
    addFormats(ajv);
    const [bundleSchema, decisionSchema, presentationSchema] = await Promise.all([
      readSchema("web-report-bundle.schema.json"),
      readSchema("viewer-eligibility-decision.schema.json"),
      readSchema("presentation-manifest.schema.json"),
    ]);
    ajv.addSchema(presentationSchema);
    const bundle = ajv.compile(bundleSchema);
    const decision = ajv.compile(decisionSchema);
    return Object.freeze({ bundle, decision });
  })();
  return validatorsPromise;
}


export async function validateBundleBytes(
  bytes: Uint8Array,
): Promise<WebReportBundleV1> {
  if (bytes.byteLength > MAX_REPORT_IMPORT_BYTES) {
    throw new WebReportValidationError(
      "web report bundle exceeds 52,428,800 bytes",
    );
  }
  let document: unknown;
  try {
    const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    document = JSON.parse(text) as unknown;
  } catch {
    throw new WebReportValidationError("web report bundle JSON is invalid");
  }
  assertBoundedJson(document);
  const validators = await contractValidators();
  if (!validators.bundle(document)) {
    throw new WebReportValidationError(
      `web report bundle schema is invalid: ${validators.bundle.errors?.[0]?.instancePath ?? "/"}`,
    );
  }
  const bundle = document as WebReportBundleV1;
  validateBundleSemantics(bundle);
  return bundle;
}

const DECISION_BADGES = {
  trusted_final: "승인·검증된 실행본",
  poc_fixture: "검증된 POC 시연 실행본",
  unverified_import: "출처 미확인 묶음",
  rejected: "열 수 없는 묶음",
} as const;

export async function validateEligibilityDecision(
  value: unknown,
): Promise<ViewerEligibilityDecisionV1> {
  const validators = await contractValidators();
  if (!validators.decision(value)) {
    throw new WebReportValidationError(
      "viewer eligibility decision schema is invalid",
    );
  }
  const decision = value as ViewerEligibilityDecisionV1;
  if (decision.badge_label_ko !== DECISION_BADGES[decision.viewer_mode]) {
    throw new WebReportValidationError(
      "viewer eligibility badge label mismatch",
    );
  }
  if (
    (decision.viewer_mode === "rejected" &&
      (decision.eligible ||
        decision.failure_code === null ||
        decision.failure_message === null)) ||
    (decision.viewer_mode !== "rejected" &&
      (!decision.eligible ||
        decision.failure_code !== null ||
        decision.failure_message !== null))
  ) {
    throw new WebReportValidationError(
      "viewer eligibility decision is inconsistent",
    );
  }
  return decision;
}
