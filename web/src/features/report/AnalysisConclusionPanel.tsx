import type { Issue } from "../../../../contracts/web-report/v1/generated/types";

import type { ClientReportBundle } from "@/features/report/report-model";
import styles from "@/features/report/ReportWorkspace.module.css";

type AnalysisConclusionPanelProps = {
  activeIssue: Issue;
  report: ClientReportBundle;
};

export function AnalysisConclusionPanel({
  activeIssue,
  report,
}: AnalysisConclusionPanelProps) {
  const responseById = new Map(
    report.final_result.conditional_responses.map((response) => [
      response.response_id,
      response,
    ]),
  );
  const responses = activeIssue.conditional_response_refs
    .map((reference) => responseById.get(reference))
    .filter((response) => response !== undefined);

  return (
    <div className={styles.analysisPanel}>
      <article className={styles.analysisSummary}>
        <span className={styles.grade}>{activeIssue.primary_grade}</span>
        <h3>{activeIssue.title_template}</h3>
        <p className={styles.issueReason}>
          {activeIssue.why_it_matters_template}
        </p>
        {activeIssue.secondary_flags.length > 0 ? (
          <ul className={styles.analysisTagList} aria-label="보조 플래그">
            {activeIssue.secondary_flags.map((flag) => (
              <li key={flag}>{flag}</li>
            ))}
          </ul>
        ) : null}
      </article>

      <div className={styles.hypothesisGrid}>
        <section aria-label="원인 가설" className={styles.hypothesisPanel}>
          <h3>원인 가설</h3>
          {activeIssue.cause_hypotheses.length > 0 ? (
            <ul className={styles.analysisList}>
              {activeIssue.cause_hypotheses.map(({ claim_code: claimCode }) => (
                <li key={claimCode}>{claimCode}</li>
              ))}
            </ul>
          ) : (
            <p className={styles.empty}>등록된 원인 가설 없음</p>
          )}
        </section>

        <section aria-label="반대 가설" className={styles.hypothesisPanel}>
          <h3>반대 가설</h3>
          {activeIssue.counter_hypotheses.length > 0 ? (
            <ul className={styles.analysisList}>
              {activeIssue.counter_hypotheses.map(
                ({ claim_code: claimCode }) => (
                  <li key={claimCode}>{claimCode}</li>
                ),
              )}
            </ul>
          ) : (
            <p className={styles.empty}>등록된 반대 가설 없음</p>
          )}
        </section>
      </div>

      <section className={`${styles.analysisBlock} ${styles.conflictBlock}`}>
        <h3>미해결 사항</h3>
        {activeIssue.unresolved_conflicts.length > 0 ? (
          <ul className={styles.analysisList}>
            {activeIssue.unresolved_conflicts.map((conflict) => (
              <li key={conflict}>{conflict}</li>
            ))}
          </ul>
        ) : (
          <p className={styles.empty}>기록된 미해결 충돌 없음</p>
        )}
      </section>

      <section className={styles.analysisBlock}>
        <h3>조건부 대응</h3>
        {responses.length > 0 ? (
          <ul className={styles.responseList}>
            {responses.map((response) => (
              <li key={response.response_id}>
                <strong>{response.condition_template}</strong>
                <span>{response.direction_template}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.empty}>등록된 조건부 대응 없음</p>
        )}
      </section>
    </div>
  );
}
