import type {
  SourcePreviewV1,
  WebReportBundleV1,
} from "../../../../contracts/web-report/v1/generated/types";

const PREVIEW_REF_PATTERN =
  /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;

type PreviewCell = string | number | boolean | null;

export type SourcePreviewResponse =
  | Readonly<{
      preview_ref: string;
      source_ref: string;
      access_policy: "permitted";
      column_labels: string[];
      rows: PreviewCell[][];
      locator_summary: string;
      truncated: boolean;
      masking_status: "none" | "truncated";
    }>
  | Readonly<{
      preview_ref: string;
      source_ref: string;
      access_policy: "restricted";
      truncated: boolean;
      masking_status: "restricted" | "truncated";
      message: string;
    }>
  | Readonly<{
      preview_ref: string;
      source_ref: string;
      access_policy: "prohibited";
      message: "이 출처의 내용은 표시할 수 없습니다.";
    }>;

export class SourcePreviewError extends Error {
  constructor(
    message: string,
    readonly reason: "invalid_ref" | "not_found" | "invalid_bundle",
  ) {
    super(message);
    this.name = "SourcePreviewError";
  }
}

function locatorSummary(preview: SourcePreviewV1): string {
  const locator = preview.locator;
  if (locator.locator_type === "csv_records") {
    return `CSV 레코드 ${locator.record_indices.join(", ")}`;
  }
  if (locator.locator_type === "json_pointer") {
    return `JSON 위치 ${locator.json_pointer ?? ""}`;
  }
  const sheet = locator.sheet === null ? "" : `시트 ${locator.sheet}`;
  const cells =
    locator.cell_range === null ? "" : `셀 ${locator.cell_range}`;
  return [sheet, cells].filter(Boolean).join(", ");
}

export class SourcePreviewRepository {
  private readonly previews = new Map<string, SourcePreviewV1>();

  constructor(report: Pick<WebReportBundleV1, "source_previews">) {
    for (const preview of report.source_previews) {
      if (this.previews.has(preview.preview_ref)) {
        throw new SourcePreviewError(
          "중복된 미리보기 참조입니다.",
          "invalid_bundle",
        );
      }
      this.previews.set(preview.preview_ref, preview);
    }
  }

  get(previewRef: string): SourcePreviewResponse {
    if (!PREVIEW_REF_PATTERN.test(previewRef)) {
      throw new SourcePreviewError(
        "잘못된 미리보기 참조입니다.",
        "invalid_ref",
      );
    }
    const preview = this.previews.get(previewRef);
    if (preview === undefined) {
      throw new SourcePreviewError(
        "미리보기를 찾을 수 없습니다.",
        "not_found",
      );
    }
    if (preview.access_policy === "prohibited") {
      return Object.freeze({
        preview_ref: preview.preview_ref,
        source_ref: preview.source_ref,
        access_policy: "prohibited" as const,
        message: "이 출처의 내용은 표시할 수 없습니다." as const,
      });
    }
    if (preview.access_policy === "restricted") {
      return Object.freeze({
        preview_ref: preview.preview_ref,
        source_ref: preview.source_ref,
        access_policy: "restricted" as const,
        truncated: preview.truncated,
        masking_status:
          preview.masking_status === "truncated"
            ? "truncated"
            : ("restricted" as const),
        message: "이 출처는 메타데이터만 표시할 수 있습니다.",
      });
    }
    return Object.freeze({
      preview_ref: preview.preview_ref,
      source_ref: preview.source_ref,
      access_policy: "permitted" as const,
      column_labels: [...preview.column_labels],
      rows: preview.rows.map((row) => [...row]),
      locator_summary: locatorSummary(preview),
      truncated: preview.truncated,
      masking_status:
        preview.masking_status === "truncated"
          ? "truncated"
          : ("none" as const),
    });
  }
}
