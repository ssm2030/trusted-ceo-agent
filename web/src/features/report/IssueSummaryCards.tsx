import type { Issue } from "../../../../contracts/web-report/v1/generated/types";

import styles from "@/features/report/ReportWorkspace.module.css";

type IssueSummaryCardsProps = {
  activeIssueRef: string;
  issues: Issue[];
  onIssueSelect: (issueRef: string) => void;
};

export function IssueSummaryCards({
  activeIssueRef,
  issues,
  onIssueSelect,
}: IssueSummaryCardsProps) {
  return (
    <div className={styles.issueGrid}>
      {issues.map((issue) => (
        <article
          className={`${styles.issueCard} ${
            issue.issue_id === activeIssueRef ? styles.issueCardActive : ""
          }`}
          data-testid="ceo-summary-issue"
          key={issue.issue_id}
        >
          <button
            aria-label={`${issue.title_template} 선택`}
            aria-pressed={issue.issue_id === activeIssueRef}
            className={styles.issueButton}
            onClick={() => onIssueSelect(issue.issue_id)}
            type="button"
          >
            <span className={styles.grade}>{issue.primary_grade}</span>
            <h3 className={styles.issueTitle}>{issue.title_template}</h3>
            <p className={styles.issueReason}>
              {issue.why_it_matters_template}
            </p>
            <span className={styles.metricMeta}>
              {issue.title_template} 선택
            </span>
          </button>
        </article>
      ))}
    </div>
  );
}
