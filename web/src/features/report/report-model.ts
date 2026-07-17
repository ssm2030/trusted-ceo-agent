import type {
  SourceViewItem,
  ViewerEligibilityDecisionV1,
  WebReportBundleV1,
} from "../../../../contracts/web-report/v1/generated/types";

export type ReportViewerMode = Exclude<
  ViewerEligibilityDecisionV1["viewer_mode"],
  "rejected"
>;

export type ReportEligibility = {
  mode: ReportViewerMode;
  label: Exclude<
    ViewerEligibilityDecisionV1["badge_label_ko"],
    "열 수 없는 묶음"
  >;
  trusted: boolean;
  questionsAllowed: boolean;
};

export type ClientSourceViewItem = Omit<
  SourceViewItem,
  "snapshot_locator" | "official_url"
> & {
  official_link_available: boolean;
};

export type ClientReportBundle = Omit<
  WebReportBundleV1,
  "source_previews" | "source_view"
> & {
  source_view: ClientSourceViewItem[];
};

export type ReportClientPayload = {
  report: ClientReportBundle;
  eligibility: ReportEligibility;
};

export type ReportSection =
  | "decision"
  | "evidence"
  | "trust"
  | "expert_packets"
  | "revision_changes";

export type ReportScopeKind =
  | "run"
  | "issue"
  | "section"
  | "claim"
  | "evidence"
  | "source"
  | "expert_packet"
  | "revision_diff";

export type ReportScope = {
  scopeKind: ReportScopeKind;
  scopeInstanceId: string;
  issueId: string | null;
  activeRef: string | null;
};

type SourcePreviewBase = {
  preview_ref: string;
  source_ref: string;
};

export type SourcePreviewResponse =
  | (SourcePreviewBase & {
      access_policy: "permitted";
      truncated: boolean;
      masking_status: "none" | "truncated";
      column_labels: string[];
      rows: (string | number | boolean | null)[][];
      locator_summary: string;
      message?: never;
    })
  | (SourcePreviewBase & {
      access_policy: "restricted";
      message: string;
      truncated?: boolean;
      masking_status?: "restricted" | "truncated";
      column_labels?: never;
      rows?: never;
      locator_summary?: never;
    })
  | (SourcePreviewBase & {
      access_policy: "prohibited";
      message: string;
    });

export function sanitizeReportBundle(
  bundle: WebReportBundleV1,
  eligibility: ReportEligibility,
): ReportClientPayload {
  const {
    source_previews: embeddedSourcePreviews,
    source_view: sourceView,
    ...safeReport
  } = bundle;
  void embeddedSourcePreviews;

  return {
    report: {
      ...safeReport,
      source_view: sourceView.map(
        ({ snapshot_locator: snapshotLocator, official_url: officialUrl, ...source }) => {
          void snapshotLocator;
          return {
            ...source,
            official_link_available: officialUrl !== null,
          };
        },
      ),
    },
    eligibility,
  };
}
