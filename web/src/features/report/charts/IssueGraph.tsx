"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";

import type { IssueGraph as IssueGraphContract } from "../../../../../contracts/web-report/v1/generated/types";

import styles from "@/features/report/ReportWorkspace.module.css";

const EChartCanvas = dynamic(
  () =>
    import("@/features/report/charts/EChartCanvas").then(
      (module) => module.EChartCanvas,
    ),
  {
    loading: () => (
      <div className={styles.chartLoading}>문제 구조를 준비하고 있습니다.</div>
    ),
    ssr: false,
  },
);

type IssueGraphProps = {
  activeIssueRef: string;
  graph: IssueGraphContract;
  onIssueSelect: (issueRef: string) => void;
};

export function IssueGraph({
  activeIssueRef,
  graph,
  onIssueSelect,
}: IssueGraphProps) {
  const option = useMemo(
    () => ({
      animationDuration: 280,
      series: [
        {
          data: graph.nodes.map((node) => ({
            id: node.issue_ref,
            name: node.label_ko,
            symbolSize: node.issue_ref === activeIssueRef ? 72 : 58,
            value: node.grade,
          })),
          edgeLabel: {
            formatter: "{c}",
            show: true,
          },
          edges: graph.edges.map((edge) => ({
            id: edge.relation_id,
            name: edge.relation_type,
            source: edge.from_issue_ref,
            target: edge.to_issue_ref,
            value: edge.relation_type,
          })),
          emphasis: { focus: "adjacency" },
          label: { show: true },
          layout: "force",
          roam: false,
          type: "graph",
        },
      ],
      tooltip: { trigger: "item" },
    }),
    [activeIssueRef, graph],
  );

  return (
    <EChartCanvas
      ariaLabel="플러그인이 제공한 전체 문제 구조"
      bindings={graph.nodes.map((node, dataIndex) => ({
        dataIndex,
        ref: node.issue_ref,
      }))}
      onBindingSelect={onIssueSelect}
      option={option}
    />
  );
}
