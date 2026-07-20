"use client";

import { useState } from "react";

import type {
  ChartSpecV1,
  Issue,
  IssueGraph as IssueGraphContract,
  MetricCardV1,
} from "../../../../contracts/web-report/v1/generated/types";

import { ChartPanel } from "@/features/report/charts/ChartPanel";
import { FullIssueStructure } from "@/features/report/FullIssueStructure";
import { IssueSummaryCards } from "@/features/report/IssueSummaryCards";
import styles from "@/features/report/ReportWorkspace.module.css";

type DecisionBriefProps = {
  activeIssueRef: string;
  charts: ChartSpecV1[];
  graph: IssueGraphContract;
  issues: Issue[];
  metricCards: MetricCardV1[];
  onEvidenceSelect: (evidenceLinkId: string, issueRef: string) => void;
  onIssueSelect: (issueRef: string) => void;
};

export function DecisionBrief({
  activeIssueRef,
  charts,
  graph,
  issues,
  metricCards,
  onEvidenceSelect,
  onIssueSelect,
}: DecisionBriefProps) {
  const [structureOpen, setStructureOpen] = useState(false);
  const activeIssue =
    issues.find((issue) => issue.issue_id === activeIssueRef) ?? issues[0];
  const activeCards = metricCards.filter(
    (card) => card.issue_ref === activeIssueRef,
  );
  const activeCharts = charts.filter((chart) =>
    chart.issue_refs.includes(activeIssueRef),
  );

  return (
    <section aria-labelledby="decision-title" className={styles.section}>
      <header className={styles.sectionHeader}>
        <div>
          <p className={styles.sectionKicker}>최고경영자 의사결정 요약</p>
          <h2 className={styles.sectionTitle} id="decision-title">
            최고경영자 의사결정 요약
          </h2>
          <p className={styles.sectionDescription}>
            검증 엔진이 선택한 문제와 표시값만 보여 줍니다. 웹은 순위나 수치를
            새로 만들지 않습니다.
          </p>
        </div>
        <button
          className={styles.actionButton}
          onClick={() => setStructureOpen((current) => !current)}
          type="button"
        >
          전체 문제 구조 보기
        </button>
      </header>

      <IssueSummaryCards
        activeIssueRef={activeIssueRef}
        issues={issues}
        onIssueSelect={onIssueSelect}
      />

      {activeIssue === undefined ? null : (
        <div className={styles.scopeBand}>
          현재 범위: {activeIssue.title_template}
        </div>
      )}

      <div className={styles.metricGrid}>
        {activeCards.map((card) => (
          <article className={styles.metricCard} key={card.metric_card_id}>
            <span className={styles.metricLabel}>{card.label_ko}</span>
            <strong className={styles.metricValue}>{card.display_value}</strong>
            <span className={styles.metricMeta}>
              {[card.currency_code, card.unit_code].filter(Boolean).join(" · ")}
            </span>
          </article>
        ))}
      </div>

      {activeCharts.length === 0 ? (
        <p className={styles.empty}>
          이 문제 범위에 검증 엔진이 게시한 차트가 없습니다.
        </p>
      ) : (
        <div className={styles.chartGrid}>
          {activeCharts.map((chart) => (
            <ChartPanel
              key={chart.chart_id}
              onEvidenceSelect={onEvidenceSelect}
              spec={chart}
            />
          ))}
        </div>
      )}

      {structureOpen ? (
        <FullIssueStructure
          activeIssueRef={activeIssueRef}
          graph={graph}
          onClose={() => setStructureOpen(false)}
          onIssueSelect={onIssueSelect}
        />
      ) : null}
    </section>
  );
}
