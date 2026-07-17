import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SourcePreviewDialog } from "@/features/report/SourcePreviewDialog";
import type { SourcePreviewResponse } from "@/features/report/report-model";

describe("SourcePreviewDialog prohibited response", () => {
  it("accepts the stable-ref and message-only server shape", async () => {
    const response: SourcePreviewResponse = {
      preview_ref: "preview_prohibited",
      source_ref: "source_main",
      access_policy: "prohibited",
      message: "이 출처의 내용은 미리볼 수 없습니다.",
    };

    render(
      <SourcePreviewDialog
        loadPreview={vi.fn().mockResolvedValue(response)}
        onClose={vi.fn()}
        open
        previewRef="preview_prohibited"
        sourceName="보호된 출처"
      />,
    );

    expect(
      await screen.findByText("이 출처의 내용은 미리볼 수 없습니다."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
