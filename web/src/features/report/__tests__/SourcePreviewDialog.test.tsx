import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SourcePreviewDialog } from "@/features/report/SourcePreviewDialog";
import type { SourcePreviewResponse } from "@/features/report/report-model";

describe("SourcePreviewDialog", () => {
  it("loads a permitted preview by ref and returns focus on Escape", async () => {
    const trigger = document.createElement("button");
    trigger.textContent = "미리보기 열기";
    document.body.append(trigger);
    const triggerRef = { current: trigger };
    const onClose = vi.fn();
    const response: SourcePreviewResponse = {
      preview_ref: "preview_main",
      source_ref: "source_main",
      access_policy: "permitted",
      truncated: false,
      masking_status: "none",
      column_labels: ["항목", "값"],
      rows: [["관찰값", "100"]],
      locator_summary: "원장 자료 1행",
    };

    render(
      <SourcePreviewDialog
        loadPreview={vi.fn().mockResolvedValue(response)}
        onClose={onClose}
        open
        previewRef="preview_main"
        returnFocusRef={triggerRef}
        sourceName="원장 자료"
      />,
    );

    expect(await screen.findByRole("cell", { name: "100" })).toBeInTheDocument();
    expect(screen.queryByText(/sources\/blobs|[A-Z]:\\/)).not.toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
    expect(trigger).toHaveFocus();
    trigger.remove();
  });

  it("shows only the supplied policy message for restricted previews", async () => {
    const response: SourcePreviewResponse = {
      preview_ref: "preview_restricted",
      source_ref: "source_main",
      access_policy: "restricted",
      truncated: false,
      masking_status: "restricted",
      message: "이 출처는 메타데이터만 표시할 수 있습니다.",
    };

    render(
      <SourcePreviewDialog
        loadPreview={vi.fn().mockResolvedValue(response)}
        onClose={vi.fn()}
        open
        previewRef="preview_restricted"
        sourceName="제한 자료"
      />,
    );

    expect(
      await screen.findByText("이 출처는 메타데이터만 표시할 수 있습니다."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
