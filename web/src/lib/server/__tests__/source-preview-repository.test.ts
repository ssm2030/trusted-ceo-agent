// @vitest-environment node
import type { WebReportBundleV1 } from "../../../../../contracts/web-report/v1/generated/types";
import { describe, expect, it } from "vitest";

import { SourcePreviewRepository } from "@/lib/server/source-preview-repository";

function bundleWithPreview(
  accessPolicy: "permitted" | "restricted" | "prohibited",
): WebReportBundleV1 {
  return {
    source_previews: [
      {
        preview_ref: "preview_main",
        source_ref: "source_main",
        locator: {
          locator_type: "csv_records",
          record_indices: [1],
          json_pointer: null,
          sheet: null,
          cell_range: null,
        },
        column_labels: accessPolicy === "permitted" ? ["매출"] : [],
        rows: accessPolicy === "permitted" ? [[120]] : [],
        truncated: false,
        truncation_reason: null,
        masking_status:
          accessPolicy === "permitted" ? "none" : accessPolicy,
        access_policy: accessPolicy,
        preview_hash: "a".repeat(64),
      },
    ],
  } as WebReportBundleV1;
}

describe("SourcePreviewRepository", () => {
  it("returns values only for permitted previews", () => {
    const result = new SourcePreviewRepository(
      bundleWithPreview("permitted"),
    ).get("preview_main");
    expect(result).toMatchObject({
      preview_ref: "preview_main",
      access_policy: "permitted",
      column_labels: ["매출"],
      rows: [[120]],
    });
  });

  it("returns no values or locator for prohibited previews", () => {
    expect(
      new SourcePreviewRepository(bundleWithPreview("prohibited")).get(
        "preview_main",
      ),
    ).toEqual({
      preview_ref: "preview_main",
      source_ref: "source_main",
      access_policy: "prohibited",
      message: "이 출처의 내용은 표시할 수 없습니다.",
    });
  });

  it("rejects path-shaped refs before lookup", () => {
    expect(() =>
      new SourcePreviewRepository(bundleWithPreview("permitted")).get(
        "../source.csv",
      ),
    ).toThrow("잘못된 미리보기 참조입니다.");
  });
});
