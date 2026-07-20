import type { EChartsCoreOption } from "echarts/core";

import type { ChartSpecV1 } from "../../../../../contracts/web-report/v1/generated/types";

export type ChartPointBinding = {
  dataIndex: number;
  evidenceLinkId: string;
  factId: string;
  valueRef: string;
};

export type EvidenceTableRow = {
  evidenceLinkId: string;
  factId: string;
  formattedValue: string;
  label: string;
};

export type ChartView =
  | {
      kind: "chart";
      numericValues: number[];
      option: EChartsCoreOption;
      pointBindings: ChartPointBinding[];
      rows: EvidenceTableRow[];
    }
  | {
      kind: "table";
      reason: string;
      rows: EvidenceTableRow[];
    };

const DECIMAL_LITERAL = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$/;

function parseSafeDisplayValue(value: string): number | null {
  if (!DECIMAL_LITERAL.test(value)) {
    return null;
  }

  const numberValue = Number(value);
  if (!Number.isFinite(numberValue)) {
    return null;
  }

  if (!value.includes(".") && !/[eE]/.test(value) && !Number.isSafeInteger(numberValue)) {
    return null;
  }

  return numberValue;
}

function evidenceRows(spec: ChartSpecV1): EvidenceTableRow[] {
  return spec.points.map((point) => ({
    evidenceLinkId: point.evidence_link_ids[0],
    factId: point.fact_id,
    formattedValue: point.display_value,
    label: point.x_label,
  }));
}

function table(
  spec: ChartSpecV1,
  reason: string,
): ChartView {
  return {
    kind: "table",
    reason,
    rows: evidenceRows(spec),
  };
}

export function buildChartView(spec: ChartSpecV1): ChartView {
  if (!spec.float_safe) {
    return table(
      spec,
      "수치를 안전하게 그래프로 변환할 수 없어 근거 표로 표시합니다.",
    );
  }

  if (spec.chart_kind === "graph") {
    return table(
      spec,
      "문제 관계는 검증 엔진이 게시한 관계 그래프에서 확인할 수 있습니다.",
    );
  }

  if (spec.points.length === 0) {
    return table(spec, "표시할 관찰값이 없어 근거 표로 표시합니다.");
  }

  if (
    spec.chart_kind === "line" &&
    spec.points.some((point) => point.period_sort_key === null)
  ) {
    return table(spec, "기간 정렬 정보가 없어 근거 표로 표시합니다.");
  }

  const numericValues = spec.points.map((point) =>
    parseSafeDisplayValue(point.display_value),
  );
  if (numericValues.some((value) => value === null)) {
    return table(
      spec,
      "수치를 안전하게 그래프로 변환할 수 없어 근거 표로 표시합니다.",
    );
  }

  const safeValues = numericValues as number[];
  return {
    kind: "chart",
    numericValues: safeValues,
    option: {
      animationDuration: 320,
      grid: {
        bottom: 54,
        left: 24,
        right: 22,
        top: 28,
      },
      tooltip: {
        trigger: "axis",
      },
      xAxis: {
        data: spec.points.map((point) => point.x_label),
        name: spec.x_axis_label_ko ?? undefined,
        type: "category",
      },
      yAxis: {
        name: spec.y_axis_label_ko ?? undefined,
        type: "value",
      },
      series: [
        {
          data: safeValues,
          name: spec.title_ko,
          showSymbol: true,
          type: spec.chart_kind,
        },
      ],
    },
    pointBindings: spec.points.map((point, dataIndex) => ({
      dataIndex,
      evidenceLinkId: point.evidence_link_ids[0],
      factId: point.fact_id,
      valueRef: point.value_ref,
    })),
    rows: evidenceRows(spec),
  };
}
