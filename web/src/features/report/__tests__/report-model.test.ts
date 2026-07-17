import { describe, expect, it } from "vitest";

import validTrusted from "../../../../../contracts/web-report/v1/fixtures/valid-trusted.json";
import type { WebReportBundleV1 } from "../../../../../contracts/web-report/v1/generated/types";

import { sanitizeReportBundle } from "@/features/report/report-model";

describe("sanitizeReportBundle", () => {
  it("removes embedded preview values and snapshot locators from the browser payload", () => {
    const bundle = structuredClone(validTrusted) as unknown as WebReportBundleV1;

    const payload = sanitizeReportBundle(bundle, {
      mode: "trusted_final",
      label: "승인·검증된 실행본",
      trusted: true,
      questionsAllowed: true,
    });

    expect(payload.report).not.toHaveProperty("source_previews");
    expect(payload.report.source_view[0]).not.toHaveProperty("snapshot_locator");
    expect(payload.report.source_view[0]).toMatchObject({
      source_ref: "source_main",
      display_name_ko: "원장 자료",
      preview_refs: ["preview_main"],
    });
    expect(JSON.stringify(payload)).not.toContain("sources/blobs/");
  });
});
