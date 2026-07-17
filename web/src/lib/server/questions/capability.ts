import { createHash, timingSafeEqual } from "node:crypto";

import { canonicalize } from "json-canonicalize";

import type {
  PrivacyClassification,
} from "@/lib/server/questions/types";

export interface SandboxProbeReceiptBody {
  receiptVersion: "1.0.0";
  platform: string;
  codexVersion: string;
  requiredFlagsPresent: boolean;
  ignoreUserConfigVerified: boolean;
  localSkillOnlyVerified: boolean;
  connectorsUnavailableVerified: boolean;
  insideReadSucceeded: boolean;
  outsideReadDenied: boolean;
  outputWriteRestricted: boolean;
  authenticationSucceeded: boolean;
  authIsolationVerified: boolean;
  completedAt: string;
}

export interface SandboxProbeReceipt
  extends SandboxProbeReceiptBody {
  receiptHash: string;
}

export type QuestionCapabilityReason =
  | "READY"
  | "POC_ONLY_OS_ISOLATION_UNVERIFIED"
  | "CODEX_UNAVAILABLE"
  | "CODEX_LOGIN_REQUIRED"
  | "REQUIRED_FLAG_MISSING"
  | "OUTSIDE_READ_NOT_DENIED"
  | "AUTH_ISOLATION_UNVERIFIED";

export interface QuestionCapability {
  textQuestionEnabled: boolean;
  companyDataEnabled: boolean;
  pocOnly: boolean;
  reasonCode: QuestionCapabilityReason;
  disclosureVersion: "qa-remote-processing-v1";
  modeLabelKo: string;
}

function receiptDigest(body: SandboxProbeReceiptBody): string {
  return createHash("sha256")
    .update(canonicalize(body), "utf8")
    .digest("hex");
}

export function signSandboxProbeReceipt(
  body: SandboxProbeReceiptBody,
): SandboxProbeReceipt {
  return Object.freeze({
    ...body,
    receiptHash: receiptDigest(body),
  });
}

function validReceipt(
  receipt: SandboxProbeReceipt,
): boolean {
  const {
    receiptHash,
    ...body
  } = receipt;
  if (
    !/^[0-9a-f]{64}$/.test(receiptHash) ||
    body.receiptVersion !== "1.0.0" ||
    !Number.isFinite(Date.parse(body.completedAt))
  ) {
    return false;
  }
  const actual = Buffer.from(receiptHash, "hex");
  const expected = Buffer.from(
    receiptDigest(body as SandboxProbeReceiptBody),
    "hex",
  );
  return (
    actual.byteLength === expected.byteLength &&
    timingSafeEqual(actual, expected)
  );
}

function disabled(
  reasonCode: QuestionCapabilityReason,
  pocOnly = false,
): QuestionCapability {
  return Object.freeze({
    textQuestionEnabled: false,
    companyDataEnabled: false,
    pocOnly,
    reasonCode,
    disclosureVersion: "qa-remote-processing-v1",
    modeLabelKo: pocOnly
      ? "POC 제한 모드"
      : "질문 사용 불가",
  });
}

export function capabilityFor(input: {
  receipt: SandboxProbeReceipt | null;
  platform?: NodeJS.Platform;
  privacyClassification: PrivacyClassification;
  allowAutomatedFakeCodex?: boolean;
}): QuestionCapability {
  const platform = input.platform ?? process.platform;
  if (
    input.receipt === null ||
    !validReceipt(input.receipt)
  ) {
    return disabled("CODEX_UNAVAILABLE");
  }
  const receipt = input.receipt;
  if (!receipt.authenticationSucceeded) {
    return disabled("CODEX_LOGIN_REQUIRED");
  }
  if (
    !receipt.requiredFlagsPresent ||
    !receipt.ignoreUserConfigVerified ||
    !receipt.localSkillOnlyVerified ||
    !receipt.connectorsUnavailableVerified
  ) {
    return disabled("REQUIRED_FLAG_MISSING");
  }
  if (
    platform !== "darwin" &&
    !input.allowAutomatedFakeCodex
  ) {
    return disabled("OUTSIDE_READ_NOT_DENIED");
  }
  const isolationReason: QuestionCapabilityReason | null =
    !receipt.insideReadSucceeded ||
    !receipt.outsideReadDenied ||
    !receipt.outputWriteRestricted
      ? "OUTSIDE_READ_NOT_DENIED"
      : !receipt.authIsolationVerified
        ? "AUTH_ISOLATION_UNVERIFIED"
        : null;
  if (isolationReason === null && platform === "darwin") {
    return Object.freeze({
      textQuestionEnabled: true,
      companyDataEnabled: true,
      pocOnly: false,
      reasonCode: "READY",
      disclosureVersion: "qa-remote-processing-v1",
      modeLabelKo: "강격리 검증 모드",
    });
  }
  if (
    input.privacyClassification === "company_restricted"
  ) {
    return disabled(isolationReason ?? "OUTSIDE_READ_NOT_DENIED", true);
  }
  return Object.freeze({
    textQuestionEnabled: true,
    companyDataEnabled: false,
    pocOnly: true,
    reasonCode: "POC_ONLY_OS_ISOLATION_UNVERIFIED",
    disclosureVersion: "qa-remote-processing-v1",
    modeLabelKo: "POC 제한 모드",
  });
}
