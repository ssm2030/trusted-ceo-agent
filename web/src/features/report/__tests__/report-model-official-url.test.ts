import { describe, expect, it } from "vitest";

import validTrusted from "../../../../../contracts/web-report/v1/fixtures/valid-trusted.json";
import type { WebReportBundleV1 } from "../../../../../contracts/web-report/v1/generated/types";

import { sanitizeReportBundle } from "@/features/report/report-model";

describe("sanitizeReportBundle official-link boundary", () => {
  it("keeps raw official URLs on the server side", () => {
    const bundle = structuredClone(validTrusted) as unknown as WebReportBundleV1;
    bundle.source_view[0].official_url = "https://official.example/source";

    const payload = sanitizeReportBundle(bundle, {
      mode: "trusted_final",
      label: "승인·검증된 실행본",
      trusted: true,
      questionsAllowed: true,
    });

    expect(payload.report.source_view[0]).not.toHaveProperty("official_url");
    expect(JSON.stringify(payload)).not.toContain("https://official.example");
  });
});
