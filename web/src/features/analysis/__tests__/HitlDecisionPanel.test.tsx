import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { HitlDecisionPanel } from "@/features/analysis/HitlDecisionPanel";
import type { ProviderHitlCard } from "@/features/analysis/analysis-provider";

function card(kind: ProviderHitlCard["hitl_kind"]): ProviderHitlCard {
  return {
    hitl_kind: kind,
    request_id: `approval_${kind}`,
    base_revision: 7,
    title: kind === "context_data"
      ? "분석 목표와 범위를 확인해 주세요"
      : "진단 결과와 검증 범위를 확인해 주세요",
    summary: "검증된 항목만 표시합니다.",
    target_refs: ["issue_main", "evidence_main"],
    allowed_decisions: [
      "approve",
      "approve_with_edits",
      "reanalyze",
      "stop",
    ],
    editable_fields: ["delivery_scope.package"],
    sections: [{
      kind: "verification",
      title: "검증 계획",
      items: ["근거 연결을 다시 확인합니다."],
      target_refs: ["evidence_main"],
    }],
  };
}

describe("HitlDecisionPanel", () => {
  it.each(["context_data", "diagnostic_final"] as const)(
    "renders %s evidence targets and the bound revision",
    (kind) => {
      render(<HitlDecisionPanel
        busy={false}
        card={card(kind)}
        onDecision={vi.fn()}
      />);

      expect(screen.getByText(card(kind).title)).toBeVisible();
      expect(screen.getByText("revision 7")).toBeVisible();
      expect(screen.getAllByText("evidence_main").length).toBeGreaterThan(0);
      expect(screen.getByText("검증 계획")).toBeVisible();
    },
  );

  it("submits approve, structured edits, reanalysis, and stop without duplicate clicks", async () => {
    const user = userEvent.setup();
    const onDecision = vi.fn(async () => undefined);
    const { rerender } = render(<HitlDecisionPanel
      busy={false}
      card={card("diagnostic_final")}
      onDecision={onDecision}
    />);

    await user.click(screen.getByRole("button", { name: "승인" }));
    expect(onDecision).toHaveBeenLastCalledWith("approve", {}, null);

    await user.type(
      screen.getByLabelText("delivery_scope.package 수정값"),
      "ceo_brief",
    );
    await user.click(screen.getByRole("button", { name: "수정 후 승인" }));
    expect(onDecision).toHaveBeenLastCalledWith(
      "approve_with_edits",
      { delivery_scope: { package: "ceo_brief" } },
      null,
    );

    await user.type(screen.getByLabelText("결정 근거"), "근거 범위를 다시 확인해 주세요.");
    await user.click(screen.getByRole("button", { name: "재분석" }));
    expect(onDecision).toHaveBeenLastCalledWith(
      "reanalyze",
      {},
      "근거 범위를 다시 확인해 주세요.",
    );
    await user.click(screen.getByRole("button", { name: "중단" }));
    expect(onDecision).toHaveBeenLastCalledWith(
      "stop",
      {},
      "근거 범위를 다시 확인해 주세요.",
    );

    rerender(<HitlDecisionPanel
      busy
      card={card("diagnostic_final")}
      onDecision={onDecision}
    />);
    expect(screen.getByRole("button", { name: "승인" })).toBeDisabled();
  });
});