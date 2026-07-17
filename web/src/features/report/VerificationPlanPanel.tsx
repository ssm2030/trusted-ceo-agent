import type { Issue } from "../../../../contracts/web-report/v1/generated/types";

import type { ClientReportBundle } from "@/features/report/report-model";
import styles from "@/features/report/ReportWorkspace.module.css";

type VerificationPlanPanelProps = {
  activeIssue: Issue;
  report: ClientReportBundle;
};

export function VerificationPlanPanel({
  activeIssue,
  report,
}: VerificationPlanPanelProps) {
  const closure = report.evidence_view.issue_claim_closure.find(
    (candidate) => candidate.issue_ref === activeIssue.issue_id,
  );
  const sourceRefs = new Set(closure?.source_refs ?? []);
  const qualityItems = report.evidence_view.data_quality.filter(
    (item) =>
      item.resolution_status === "open" &&
      item.source_ref !== null &&
      sourceRefs.has(item.source_ref),
  );
  const packets = activeIssue.expert_review_refs
    .map((packetRef) => {
      const expandedPacket = report.expert_packet_view.find(
        (packet) =>
          packet.expert_packet_id === packetRef &&
          packet.target_issue_ref === activeIssue.issue_id,
      );
      if (expandedPacket !== undefined) {
        return {
          expert_packet_id: expandedPacket.expert_packet_id,
          profession: expandedPacket.profession,
          review_question: expandedPacket.review_question,
          forbidden_conclusions: expandedPacket.forbidden_conclusions,
        };
      }

      const publicPacket = report.final_result.expert_review_packets.find(
        (packet) => packet.expert_packet_id === packetRef,
      );
      return publicPacket === undefined
        ? undefined
        : {
            expert_packet_id: publicPacket.expert_packet_id,
            profession: publicPacket.profession,
            review_question: publicPacket.question_template,
            forbidden_conclusions: publicPacket.forbidden_conclusions,
          };
    })
    .filter((packet) => packet !== undefined);

  return (
    <div className={styles.analysisPanel}>
      <section className={styles.verificationBlock}>
        <h3>다음 검증 단계</h3>
        {activeIssue.verification_next_steps.length > 0 ? (
          <ul className={styles.analysisList}>
            {activeIssue.verification_next_steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ul>
        ) : (
          <p className={styles.empty}>등록된 다음 검증 단계 없음</p>
        )}
      </section>

      <section className={styles.verificationBlock}>
        <h3>미해결 충돌</h3>
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

      <section className={styles.verificationBlock}>
        <h3>전문가 검토 경계</h3>
        {packets.length > 0 ? (
          <ul className={styles.analysisList}>
            {packets.map((packet) => (
              <li key={packet.expert_packet_id}>
                <strong>{packet.profession}</strong>
                <p>{packet.review_question}</p>
                {packet.forbidden_conclusions.length > 0 ? (
                  <p>
                    결론 제한: {packet.forbidden_conclusions.join(", ")}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.empty}>요청된 전문가 검토 없음</p>
        )}
      </section>

      <section className={styles.verificationBlock}>
        <h3>현재 자료 제한</h3>
        {qualityItems.length > 0 ? (
          <ul className={styles.analysisList}>
            {qualityItems.map((item) => (
              <li key={item.quality_issue_id}>
                <strong>{item.suggested_resolution}</strong>
                <dl className={styles.dataList}>
                  <div className={styles.dataRow}>
                    <dt>영향 필드</dt>
                    <dd>{item.affected_field ?? "미지정"}</dd>
                  </div>
                  <div className={styles.dataRow}>
                    <dt>사유 코드</dt>
                    <dd>{item.reason_code}</dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.empty}>
            현재 범위에 연결된 미해결 자료 제한 없음
          </p>
        )}
      </section>
    </div>
  );
}
