import type { Issue } from "../../../../contracts/web-report/v1/generated/types";

import type {
  ClientReportBundle,
  ReportEligibility,
} from "@/features/report/report-model";
import styles from "@/features/report/ReportWorkspace.module.css";

type TrustManifestProps = {
  activeIssue: Issue;
  eligibility: ReportEligibility;
  report: ClientReportBundle;
};

const WORKFLOW_STATE_LABELS = {
  finalized: "최종 확정",
} as const;

const APPROVAL_GATE_LABELS: Readonly<Record<string, string>> = {
  context: "맥락 확인",
  data: "데이터 확인",
  diagnostic: "진단 검토",
  final: "최종 승인",
  scope_narrowing: "범위 조정",
};

const APPROVAL_STATUS_LABELS: Readonly<Record<string, string>> = {
  current: "현재 유효",
  invalidated: "무효화됨",
};

const INPUT_METHOD_LABELS: Readonly<Record<string, string>> = {
  interactive_tty: "터미널 직접 입력",
  test_fixture: "테스트용 입력",
};

const TRUST_COMMAND_LABELS: Readonly<Record<string, string>> = {
  "approval-request": "승인 요청",
  "approve-interactive": "터미널 승인",
  cancel: "취소",
  "decide-interactive": "터미널 결정",
  finalize: "최종 확정",
  "ingest-result": "결과 수집",
  "prepare-finalization": "최종화 준비",
  "prepare-jobs": "작업 준비",
  "reduce-stage": "단계 통합",
  resume: "재개",
  "run-components": "구성요소 실행",
  scan: "자료 점검",
  stop: "중단",
  "submit-human-response": "사람 응답 제출",
};

const ACTOR_KIND_LABELS = {
  human: "사람",
  runtime: "실행 엔진",
} as const;

function contractLabel(
  value: string | null,
  labels: Readonly<Record<string, string>>,
  missingLabel: string,
  unknownLabel: string,
) {
  if (value === null) {
    return missingLabel;
  }
  return labels[value] ?? unknownLabel;
}

export function TrustManifest({
  activeIssue,
  eligibility,
  report,
}: TrustManifestProps) {
  const badgeClass =
    eligibility.mode === "trusted_final"
      ? styles.statusTrusted
      : eligibility.mode === "poc_fixture"
        ? styles.statusPoc
        : styles.statusUnverified;

  return (
    <section aria-labelledby="trust-title" className={styles.section}>
      <header className={styles.sectionHeader}>
        <div>
          <p className={styles.sectionKicker}>신뢰 명세</p>
          <h2 className={styles.sectionTitle} id="trust-title">
            실행·신뢰 기록
          </h2>
          <p className={styles.sectionDescription}>
            로컬 검증 엔진이 제공한 실행, 승인, 검증 계보입니다.
          </p>
        </div>
        <span className={styles.scopeBand}>
          현재 범위: {activeIssue.title_template}
        </span>
      </header>

      <div className={styles.trustGrid}>
        <article className={styles.dossier}>
          <header className={styles.dossierHeader}>
            <p className={styles.sectionKicker}>실행 기록</p>
            <h3>{report.run.run_id}</h3>
          </header>
          <div className={styles.dossierBody}>
            <span className={`${styles.statusBadge} ${badgeClass}`}>
              {eligibility.label}
            </span>
            <dl className={styles.dataList}>
              <div className={styles.dataRow}>
                <dt>리비전</dt>
                <dd>{report.run.revision}</dd>
              </div>
              <div className={styles.dataRow}>
                <dt>실행 상태</dt>
                <dd>{WORKFLOW_STATE_LABELS[report.run.workflow_state]}</dd>
              </div>
              <div className={styles.dataRow}>
                <dt>검증기 버전</dt>
                <dd>{report.trust_view.validator_version}</dd>
              </div>
              <div className={styles.dataRow}>
                <dt>묶음 해시</dt>
                <dd className={styles.hash}>{report.bundle_hash}</dd>
              </div>
              <div className={styles.dataRow}>
                <dt>의미 지문</dt>
                <dd className={styles.hash}>
                  {report.run.semantic_fingerprint}
                </dd>
              </div>
            </dl>
          </div>
        </article>

        <article className={styles.dossier}>
          <header className={styles.dossierHeader}>
            <p className={styles.sectionKicker}>완료된 검증</p>
            <h3>검증 완료 항목</h3>
          </header>
          <div className={styles.dossierBody}>
            <ul className={styles.trustList}>
              {report.trust_view.completed_checks.map((check) => (
                <li key={check}>{check}</li>
              ))}
            </ul>
          </div>
        </article>
      </div>

      <div className={styles.trustGrid}>
        <article className={styles.revisionCard}>
          <h3>승인 계보</h3>
          <ul className={styles.trustList}>
            {report.trust_view.approval_summary.map((approval, index) => (
              <li key={`${approval.approval_id ?? "approval"}:${index}`}>
                <strong>
                  {contractLabel(
                    approval.gate,
                    APPROVAL_GATE_LABELS,
                    "승인 단계 미제공",
                    "기타 승인 단계",
                  )}
                </strong>
                <span className={styles.metricMeta}>
                  {contractLabel(
                    approval.status,
                    APPROVAL_STATUS_LABELS,
                    "상태 미제공",
                    "기타 승인 상태",
                  )}{" "}
                  ·{" "}
                  {contractLabel(
                    approval.input_method,
                    INPUT_METHOD_LABELS,
                    "입력 방식 미제공",
                    "기타 입력 방식",
                  )}
                </span>
              </li>
            ))}
          </ul>
        </article>

        <article className={styles.revisionCard}>
          <h3>제한과 비식별 고지</h3>
          <p>{report.trust_view.deidentification.notice_ko}</p>
          <ul className={styles.trustList}>
            {report.trust_view.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </article>
      </div>

      <article className={styles.revisionCard}>
        <h3>신뢰 이벤트</h3>
        <ol className={styles.eventList}>
          {report.trust_view.trust_events.map((event) => (
            <li className={styles.event} key={event.event_id}>
              <strong>#{event.sequence}</strong>
              <span>
                {contractLabel(
                  event.command,
                  TRUST_COMMAND_LABELS,
                  "명령 미제공",
                  "기타 실행 명령",
                )}{" "}
                · 리비전 {event.revision} ·{" "}
                {ACTOR_KIND_LABELS[event.actor_kind]}
              </span>
            </li>
          ))}
        </ol>
      </article>
    </section>
  );
}
