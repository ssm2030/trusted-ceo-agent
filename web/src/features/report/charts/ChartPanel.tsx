"use client";

import dynamic from "next/dynamic";

import type { ChartSpecV1 } from "../../../../../contracts/web-report/v1/generated/types";

import { EvidenceFallbackTable } from "@/features/report/charts/EvidenceFallbackTable";
import { buildChartView } from "@/features/report/model/chart-option";
import styles from "@/features/report/ReportWorkspace.module.css";

const EChartCanvas = dynamic(
  () =>
    import("@/features/report/charts/EChartCanvas").then(
      (module) => module.EChartCanvas,
    ),
  {
    loading: () => (
      <div className={styles.chartLoading}>차트를 준비하고 있습니다.</div>
    ),
    ssr: false,
  },
);

type ChartPanelProps = {
  onEvidenceSelect: (evidenceLinkId: string, issueRef: string) => void;
  spec: ChartSpecV1;
};

export function ChartPanel({
  onEvidenceSelect,
  spec,
}: ChartPanelProps) {
  const chartView = buildChartView(spec);
  const issueRef = spec.issue_refs[0];
  const selectEvidence = (evidenceLinkId: string) => {
    onEvidenceSelect(evidenceLinkId, issueRef);
  };

  return (
    <article className={styles.chartPanel}>
      <header className={styles.chartHeader}>
        <div>
          <h3>{spec.title_ko}</h3>
          <p className={styles.chartDescription}>{spec.description_ko}</p>
        </div>
        {spec.unit_code === null ? null : (
          <span className={styles.metricMeta}>단위: {spec.unit_code}</span>
        )}
      </header>

      {chartView.kind === "table" ? (
        <EvidenceFallbackTable
          onEvidenceSelect={selectEvidence}
          reason={chartView.reason}
          rows={chartView.rows}
        />
      ) : (
        <>
          <EChartCanvas
            ariaLabel={`${spec.title_ko} 차트`}
            bindings={chartView.pointBindings.map((binding) => ({
              dataIndex: binding.dataIndex,
              ref: binding.evidenceLinkId,
            }))}
            onBindingSelect={selectEvidence}
            option={chartView.option}
          />
          <ul className={styles.pointList} aria-label="차트 근거 이동">
            {chartView.rows.map((row) => (
              <li key={`${row.factId}:${row.label}`}>
                <button
                  className={styles.pointButton}
                  onClick={() => selectEvidence(row.evidenceLinkId)}
                  type="button"
                >
                  {row.label} 근거 보기
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </article>
  );
}
