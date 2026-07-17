import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { RevisionViewV1 } from "../../../../../contracts/web-report/v1/generated/types";

import { RevisionChanges } from "@/features/report/RevisionChanges";

const UNAVAILABLE_REVISION: RevisionViewV1 = {
  available: false,
  unavailable_reason: "NO_PRIOR_FINAL_RESULT",
  base_revision: null,
  compare_revision: 3,
  change_categories: [],
  added_refs: [],
  changed_refs: [],
  removed_refs: [],
  invalidated_approval_refs: [],
  previous_semantic_fingerprint: null,
  current_semantic_fingerprint:
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  display_message_ko: "이전 최종 결과가 없어 변경 정보를 제공할 수 없습니다.",
};

describe("RevisionChanges", () => {
  it("does not synthesize a semantic diff when the plugin supplied none", () => {
    render(
      <RevisionChanges
        activeIssueTitle="수익성 점검 필요"
        revisionView={UNAVAILABLE_REVISION}
      />,
    );

    expect(screen.getByText("변경 정보 사용 불가")).toBeInTheDocument();
    expect(
      screen.getByText(
        "이전 최종 결과가 없어 변경 정보를 제공할 수 없습니다.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("추정 변경")).not.toBeInTheDocument();
  });
});
