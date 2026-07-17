import type { IssueGraph as IssueGraphContract } from "../../../../contracts/web-report/v1/generated/types";

import { IssueGraph } from "@/features/report/charts/IssueGraph";
import styles from "@/features/report/ReportWorkspace.module.css";

type FullIssueStructureProps = {
  activeIssueRef: string;
  graph: IssueGraphContract;
  onClose: () => void;
  onIssueSelect: (issueRef: string) => void;
};

export function FullIssueStructure({
  activeIssueRef,
  graph,
  onClose,
  onIssueSelect,
}: FullIssueStructureProps) {
  const nodeNames = new Map(
    graph.nodes.map((node) => [node.issue_ref, node.label_ko]),
  );

  return (
    <section aria-labelledby="issue-structure-title" className={styles.structurePanel}>
      <header className={styles.structureHeader}>
        <div>
          <p className={styles.sectionKicker}>제공된 문제 관계</p>
          <h3 id="issue-structure-title">플러그인이 제공한 전체 문제 구조</h3>
        </div>
        <button className={styles.closeButton} onClick={onClose} type="button">
          구조 닫기
        </button>
      </header>

      <div className={styles.structureNodes}>
        {graph.nodes.map((node) => (
          <button
            aria-pressed={node.issue_ref === activeIssueRef}
            className={`${styles.structureNode} ${
              node.issue_ref === activeIssueRef
                ? styles.structureNodeActive
                : ""
            }`}
            data-testid="issue-structure-node"
            key={node.issue_ref}
            onClick={() => onIssueSelect(node.issue_ref)}
            type="button"
          >
            <strong>{node.label_ko}</strong>
            <span className={styles.metricMeta}>{node.grade}</span>
          </button>
        ))}
      </div>

      {graph.nodes.length === 0 ? null : (
        <IssueGraph
          activeIssueRef={activeIssueRef}
          graph={graph}
          onIssueSelect={onIssueSelect}
        />
      )}

      <ul className={styles.structureRelationList}>
        {graph.edges.map((edge) => (
          <li className={styles.structureRelation} key={edge.relation_id}>
            <span>{nodeNames.get(edge.from_issue_ref) ?? edge.from_issue_ref}</span>
            <strong>{edge.relation_type}</strong>
            <span>{nodeNames.get(edge.to_issue_ref) ?? edge.to_issue_ref}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
