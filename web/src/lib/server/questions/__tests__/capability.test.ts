// @vitest-environment node
import { describe, expect, it } from "vitest";

import {
  capabilityFor,
  serviceCapabilityFor,
  signSandboxProbeReceipt,
  type SandboxProbeReceiptBody,
} from "@/lib/server/questions/capability";

function receiptBody(
  overrides: Partial<SandboxProbeReceiptBody> = {},
): SandboxProbeReceiptBody {
  return {
    receiptVersion: "1.0.0",
    platform: "darwin",
    codexVersion: "codex 1.0.0",
    requiredFlagsPresent: true,
    ignoreUserConfigVerified: true,
    localSkillOnlyVerified: true,
    connectorsUnavailableVerified: true,
    insideReadSucceeded: true,
    outsideReadDenied: true,
    outputWriteRestricted: true,
    authenticationSucceeded: true,
    authIsolationVerified: true,
    completedAt: "2026-07-17T01:02:03.000Z",
    ...overrides,
  };
}

describe("result question capability", () => {
  it("enables company data only after a complete strong macOS probe", () => {
    const receipt = signSandboxProbeReceipt(receiptBody());
    expect(
      capabilityFor({
        receipt,
        platform: "darwin",
        privacyClassification: "company_restricted",
      }),
    ).toMatchObject({
      textQuestionEnabled: true,
      companyDataEnabled: true,
      pocOnly: false,
      reasonCode: "READY",
    });
  });

  it("allows only explicit POC data when outside-read denial is unverified", () => {
    const receipt = signSandboxProbeReceipt(
      receiptBody({ outsideReadDenied: false }),
    );
    expect(
      capabilityFor({
        receipt,
        platform: "darwin",
        privacyClassification: "poc_deidentified",
      }),
    ).toMatchObject({
      textQuestionEnabled: true,
      companyDataEnabled: false,
      pocOnly: true,
      reasonCode: "POC_ONLY_OS_ISOLATION_UNVERIFIED",
    });
    expect(
      capabilityFor({
        receipt,
        platform: "darwin",
        privacyClassification: "company_restricted",
      }).textQuestionEnabled,
    ).toBe(false);
  });

  it("fails closed on Windows and on tampered receipts", () => {
    const receipt = signSandboxProbeReceipt(receiptBody());
    expect(
      capabilityFor({
        receipt,
        platform: "win32",
        privacyClassification: "company_restricted",
      }),
    ).toMatchObject({
      textQuestionEnabled: false,
      companyDataEnabled: false,
    });
    expect(
      capabilityFor({
        receipt: {
          ...receipt,
          authenticationSucceeded: false,
        },
        platform: "darwin",
        privacyClassification: "poc_deidentified",
      }).textQuestionEnabled,
    ).toBe(false);
  });

  it("uses only service readiness and validated report context for the active capability", () => {
    expect(serviceCapabilityFor({
      contextPresent: false,
      serviceAvailable: true,
      aiReady: true,
    }).reasonCode).toBe("REGISTERED_REPORT_REQUIRED");
    expect(serviceCapabilityFor({
      contextPresent: true,
      serviceAvailable: false,
      aiReady: false,
    }).reasonCode).toBe("AI_SERVICE_UNAVAILABLE");
    expect(serviceCapabilityFor({
      contextPresent: true,
      serviceAvailable: true,
      aiReady: false,
    }).reasonCode).toBe("AI_API_KEY_REQUIRED");
    expect(serviceCapabilityFor({
      contextPresent: true,
      serviceAvailable: true,
      aiReady: true,
    })).toMatchObject({
      textQuestionEnabled: true,
      companyDataEnabled: true,
      reasonCode: "READY",
    });
  });});
