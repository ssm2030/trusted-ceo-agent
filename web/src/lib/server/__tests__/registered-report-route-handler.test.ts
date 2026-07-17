// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import {
  CSRF_HEADER_NAME,
  SESSION_COOKIE_NAME,
  createLocalSecurityConfig,
  issueLocalSession,
} from "@/lib/server/local-request-security";
import { handleRegisteredReportActivation } from "@/lib/server/registered-report-route-handler";

const decision = {
  decision_version: "1.0.0" as const,
  eligible: true,
  viewer_mode: "trusted_final" as const,
  badge_label_ko: "승인·검증된 실행본" as const,
  run_id: "run_20260717T000000Z_aaaaaaaaaaaaaaaa",
  revision: 3,
  bundle_hash: "a".repeat(64),
  completed_checks: ["final_package"],
  failure_code: null,
  failure_message: null,
};

function requestBody(body: unknown) {
  const security = createLocalSecurityConfig({
    port: 3000,
    sessionSecret: new Uint8Array(32).fill(4),
  });
  const session = issueLocalSession(security);
  const serialized = JSON.stringify(body);
  return {
    security,
    request: new Request(
      `${security.origin}/api/report/registered`,
      {
        method: "POST",
        headers: {
          host: security.host,
          origin: security.origin,
          cookie: `${SESSION_COOKIE_NAME}=${session.cookieValue}`,
          [CSRF_HEADER_NAME]: session.csrfToken,
          "content-type": "application/json",
          "content-length": String(
            Buffer.byteLength(serialized, "utf8"),
          ),
        },
        body: serialized,
      },
    ),
  };
}

describe("registered report activation route", () => {
  it("accepts only a registration_id and never exposes server paths", async () => {
    const { request, security } = requestBody({
      registration_id: "representative",
    });
    const activate = vi.fn().mockResolvedValue(decision);
    const response = await handleRegisteredReportActivation(request, {
      security,
      activate,
    });

    expect(response.status).toBe(201);
    expect(activate).toHaveBeenCalledWith("representative");
    const body = await response.json();
    expect(body).toEqual({
      activated: true,
      eligibility: {
        mode: "trusted_final",
        label: "승인·검증된 실행본",
        trusted: true,
        questionsAllowed: true,
      },
    });
    expect(JSON.stringify(body)).not.toContain("artifact");
  });

  it("rejects browser-supplied artifact paths and unknown fields", async () => {
    const { request, security } = requestBody({
      registration_id: "representative",
      artifact_root: "C:\\secret",
    });
    const activate = vi.fn().mockResolvedValue(decision);
    const response = await handleRegisteredReportActivation(request, {
      security,
      activate,
    });

    expect(response.status).toBe(400);
    expect(activate).not.toHaveBeenCalled();
  });
});
