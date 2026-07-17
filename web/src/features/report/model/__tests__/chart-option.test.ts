import { describe, expect, it } from "vitest";

import type { ChartSpecV1 } from "../../../../../../contracts/web-report/v1/generated/types";

import { buildChartView } from "@/features/report/model/chart-option";

function makeChartSpec(
  overrides: Partial<ChartSpecV1> = {},
): ChartSpecV1 {
  return {
    chart_id: "chart_test",
    title_ko: "승인된 관찰값",
    description_ko: "플러그인이 제공한 값입니다.",
    chart_kind: "line",
    issue_refs: ["issue_main"],
    fact_refs: ["fact_a", "fact_b"],
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
        x_label: "1월",
        period_sort_key: "2026-01",
        value_ref: "fact_a",
        fact_id: "fact_a",
        display_value: "10",
        evidence_link_ids: ["evidence_a"],
      },
      {
        point_id: "point_b",
        x_label: "2월",
        period_sort_key: "2026-02",
        value_ref: "fact_b",
        fact_id: "fact_b",
        display_value: "12",
        evidence_link_ids: ["evidence_b"],
      },
    ],
    ...overrides,
  };
}

describe("buildChartView", () => {
  it("maps supplied values and evidence bindings without calculating a metric", () => {
    const view = buildChartView(makeChartSpec());

    expect(view.kind).toBe("chart");
    if (view.kind === "chart") {
      expect(view.numericValues).toEqual([10, 12]);
      expect(view.pointBindings).toEqual([
        {
          dataIndex: 0,
          evidenceLinkId: "evidence_a",
          factId: "fact_a",
          valueRef: "fact_a",
        },
        {
          dataIndex: 1,
          evidenceLinkId: "evidence_b",
          factId: "fact_b",
          valueRef: "fact_b",
        },
      ]);
      expect(view.rows.map((row) => row.formattedValue)).toEqual(["10", "12"]);
    }
  });

  it("uses a table when number conversion is unsafe", () => {
    expect(buildChartView(makeChartSpec({ float_safe: false }))).toMatchObject({
      kind: "table",
      reason:
        "수치를 안전하게 그래프로 변환할 수 없어 근거 표로 표시합니다.",
    });
  });

  it("uses a table when a line chart lacks a period sort key", () => {
    const spec = makeChartSpec();
    spec.points[0].period_sort_key = null;

    expect(buildChartView(spec)).toMatchObject({
      kind: "table",
      reason: "기간 정렬 정보가 없어 근거 표로 표시합니다.",
    });
  });
});
