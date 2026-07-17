import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ChartSpecV1 } from "../../../../../../contracts/web-report/v1/generated/types";

import { ChartPanel } from "@/features/report/charts/ChartPanel";

vi.mock("@/features/report/charts/EChartCanvas", () => ({
  EChartCanvas: () => <div data-testid="echart-svg-canvas" />,
}));

const CHART_SPEC: ChartSpecV1 = {
  chart_id: "chart_test",
  title_ko: "승인된 관찰값",
  description_ko: "플러그인이 제공한 값만 표시합니다.",
  chart_kind: "bar",
  issue_refs: ["issue_main"],
  fact_refs: ["fact_main"],
  signal_refs: [],
  x_axis_label_ko: "기간",
  y_axis_label_ko: "관찰값",
  unit_code: "count",
  currency_code: null,
  scale: "1",
  display_format: "decimal",
  float_safe: true,
  points: [
    {
      point_id: "point_a",
      x_label: "6월",
      period_sort_key: "2026-06",
      value_ref: "fact_main",
      fact_id: "fact_main",
      display_value: "100",
      evidence_link_ids: ["evidence_main"],
    },
  ],
};

describe("ChartPanel", () => {
  it("provides a keyboard path from each supplied point to evidence", async () => {
    const user = userEvent.setup();
    const onEvidenceSelect = vi.fn();

    render(
      <ChartPanel
        onEvidenceSelect={onEvidenceSelect}
        spec={CHART_SPEC}
      />,
    );

    await user.click(screen.getByRole("button", { name: "6월 근거 보기" }));
    expect(onEvidenceSelect).toHaveBeenCalledWith(
      "evidence_main",
      "issue_main",
    );
  });

  it("renders the supplied values as a table when chart safety is false", () => {
    render(
      <ChartPanel
        onEvidenceSelect={vi.fn()}
        spec={{ ...CHART_SPEC, float_safe: false }}
      />,
    );

    expect(
      screen.getByText(
        "수치를 안전하게 그래프로 변환할 수 없어 근거 표로 표시합니다.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "100" })).toBeInTheDocument();
    expect(screen.queryByTestId("echart-svg-canvas")).not.toBeInTheDocument();
  });
});
