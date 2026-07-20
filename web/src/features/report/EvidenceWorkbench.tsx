import type {
  EvidenceLink,
  Issue,
} from "../../../../contracts/web-report/v1/generated/types";

import type { ClientReportBundle } from "@/features/report/report-model";
import styles from "@/features/report/ReportWorkspace.module.css";

export type PreviewRequest = {
  previewRef: string;
  sourceRef: string;
  sourceName: string;
  trigger: HTMLButtonElement;
};

type EvidenceWorkbenchProps = {
  activeEvidenceRef: string | null;
  activeIssue: Issue;
  onPreviewRequest: (request: PreviewRequest) => void;
  report: ClientReportBundle;
};

const EVIDENCE_POLARITY_LABELS = {
  contradicts: "반박",
  supports: "뒷받침",
} satisfies Record<EvidenceLink["polarity"], string>;

const EVIDENCE_ROLE_LABELS = {
  boundary: "적용 경계",
  corroboration: "교차 확인",
  counter_evidence: "반대 근거",
  mechanism: "작동 원리",
  observation: "관찰",
} satisfies Record<EvidenceLink["role"], string>;

const EVIDENCE_KIND_LABELS = {
  fact: "사실",
  signal: "신호",
} satisfies Record<EvidenceLink["evidence_kind"], string>;

const SOURCE_ACCESS_POLICY_LABELS = {
  permitted: "허용",
  prohibited: "금지",
  restricted: "제한",
} as const;

function EvidenceCard({
  active,
  evidence,
}: {
  active: boolean;
  evidence: EvidenceLink;
}) {
  return (
    <article
      className={`${styles.evidenceCard} ${
        active ? styles.evidenceCardActive : ""
      }`}
      aria-current={active ? "true" : undefined}
      id={`evidence-${evidence.evidence_link_id}`}
    >
      <p className={styles.sectionKicker}>
        {EVIDENCE_POLARITY_LABELS[evidence.polarity]} ·{" "}
        {EVIDENCE_ROLE_LABELS[evidence.role]}
      </p>
      <h3 className={styles.evidenceHeading}>{evidence.evidence_link_id}</h3>
      <p className={styles.issueReason}>{evidence.rationale_template}</p>
      <dl className={styles.dataList}>
        <div className={styles.dataRow}>
          <dt>근거 종류</dt>
          <dd>{EVIDENCE_KIND_LABELS[evidence.evidence_kind]}</dd>
        </div>
        <div className={styles.dataRow}>
          <dt>근거 참조</dt>
          <dd className={styles.hash}>{evidence.evidence_ref}</dd>
        </div>
        <div className={styles.dataRow}>
          <dt>독립성 그룹</dt>
          <dd className={styles.hash}>{evidence.independence_group_id}</dd>
        </div>
      </dl>
    </article>
  );
}

export function EvidenceWorkbench({
  activeEvidenceRef,
  activeIssue,
  onPreviewRequest,
  report,
}: EvidenceWorkbenchProps) {
  const closure = report.evidence_view.issue_claim_closure.find(
    (candidate) => candidate.issue_ref === activeIssue.issue_id,
  );
  const evidenceIds = closure?.evidence_link_ids ?? [];
  const evidenceLinks = report.evidence_view.evidence_links.filter((link) =>
    evidenceIds.includes(link.evidence_link_id),
  );
  const factIds = closure?.fact_refs ?? [];
  const facts = report.evidence_view.facts.filter((fact) =>
    factIds.includes(fact.fact_id),
  );
  const sourceIds = closure?.source_refs ?? [];
  const sources = report.source_view.filter((source) =>
    sourceIds.includes(source.source_ref),
  );

  return (
    <div className={styles.evidenceGrid}>
        <div className={styles.evidenceMain}>
          {evidenceLinks.length === 0 ? (
            <p className={styles.empty}>표시할 근거 연결이 없습니다.</p>
          ) : (
            evidenceLinks.map((evidence) => (
              <EvidenceCard
                active={activeEvidenceRef === evidence.evidence_link_id}
                evidence={evidence}
                key={evidence.evidence_link_id}
              />
            ))
          )}

          {facts.map((fact) => (
            <article className={styles.evidenceCard} key={fact.fact_id}>
              <p className={styles.sectionKicker}>제공된 사실</p>
              <h3 className={styles.evidenceHeading}>{fact.fact_code}</h3>
              <dl className={styles.dataList}>
                <div className={styles.dataRow}>
                  <dt>검증된 값</dt>
                  <dd>{String(fact.value.canonical_value)}</dd>
                </div>
                <div className={styles.dataRow}>
                  <dt>단위</dt>
                  <dd>{fact.value.unit_code ?? "제공되지 않음"}</dd>
                </div>
                <div className={styles.dataRow}>
                  <dt>품질 표식</dt>
                  <dd>
                    {fact.quality.length === 0
                      ? "없음"
                      : fact.quality.join(", ")}
                  </dd>
                </div>
              </dl>
            </article>
          ))}
        </div>

        <aside aria-label="출처" className={styles.evidenceAside}>
          <h3>출처</h3>
          <ul className={styles.sourceList}>
            {sources.map((source) => (
                <li
                  className={styles.sourceCard}
                  id={`source-${source.source_ref}`}
                  key={source.source_ref}
                >
                <strong>{source.display_name_ko}</strong>
                <p className={styles.metricMeta}>
                  {SOURCE_ACCESS_POLICY_LABELS[source.access_policy]}
                </p>
                <ul className={styles.trustList}>
                  {source.locator_summaries.map((locator) => (
                    <li key={locator.extraction_hash}>
                      {locator.display_locator}
                    </li>
                  ))}
                </ul>
                <div className={styles.sourceActions}>
                  {source.preview_refs.map((previewRef) => (
                    <button
                      className={styles.actionButton}
                      key={previewRef}
                      onClick={(event) =>
                        onPreviewRequest({
                          previewRef,
                          sourceRef: source.source_ref,
                          sourceName: source.display_name_ko,
                          trigger: event.currentTarget,
                        })
                      }
                      type="button"
                    >
                      출처 미리보기
                    </button>
                  ))}
                  {source.official_link_available ? (
                    <a
                      className={styles.actionLink}
                      href={`/api/report/official-links/${encodeURIComponent(
                        source.source_ref,
                      )}`}
                      rel="noreferrer"
                      target="_blank"
                    >
                      공식 링크 열기
                    </a>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </aside>
    </div>
  );
}
