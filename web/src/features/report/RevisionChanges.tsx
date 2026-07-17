import type { RevisionViewV1 } from "../../../../contracts/web-report/v1/generated/types";

import styles from "@/features/report/ReportWorkspace.module.css";

type RevisionChangesProps = {
  activeIssueTitle: string;
  revisionView: RevisionViewV1;
};

type ReferenceCardProps = {
  emptyMessage: string;
  references: string[];
  title: string;
};

function ReferenceCard({
  emptyMessage,
  references,
  title,
}: ReferenceCardProps) {
  return (
    <article className={styles.revisionCard}>
      <h3>{title}</h3>
      {references.length === 0 ? (
        <p className={styles.empty}>{emptyMessage}</p>
      ) : (
        <ul className={styles.trustList}>
          {references.map((reference) => (
            <li className={styles.hash} key={reference}>
              {reference}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

export function RevisionChanges({
  activeIssueTitle,
  revisionView,
}: RevisionChangesProps) {
  if (!revisionView.available) {
    return (
      <section aria-labelledby="revision-title" className={styles.section}>
        <header className={styles.sectionHeader}>
          <div>
            <p className={styles.sectionKicker}>변경 기록</p>
            <h2 className={styles.sectionTitle} id="revision-title">
              변경 정보 사용 불가
            </h2>
            <p className={styles.sectionDescription}>
              {revisionView.display_message_ko}
            </p>
          </div>
          <span className={styles.scopeBand}>현재 범위: {activeIssueTitle}</span>
        </header>
        <p className={styles.notice}>
          플러그인이 변경 정보를 제공하지 않았으므로 웹에서 의미 차이를
          추정하지 않습니다.
        </p>
      </section>
    );
  }

  return (
    <section aria-labelledby="revision-title" className={styles.section}>
      <header className={styles.sectionHeader}>
        <div>
          <p className={styles.sectionKicker}>변경 기록</p>
          <h2 className={styles.sectionTitle} id="revision-title">
            변경 이력
          </h2>
          <p className={styles.sectionDescription}>
            {revisionView.display_message_ko}
          </p>
        </div>
        <span className={styles.scopeBand}>현재 범위: {activeIssueTitle}</span>
      </header>

      <dl className={styles.reportMeta}>
        <dt>기준 리비전</dt>
        <dd>{revisionView.base_revision ?? "제공되지 않음"}</dd>
        <dt>비교 리비전</dt>
        <dd>{revisionView.compare_revision ?? "제공되지 않음"}</dd>
        <dt>변경 범주</dt>
        <dd>
          {revisionView.change_categories.length === 0
            ? "제공되지 않음"
            : revisionView.change_categories.join(", ")}
        </dd>
      </dl>

      <div className={styles.revisionGrid}>
        <ReferenceCard
          emptyMessage="추가된 참조가 없습니다."
          references={revisionView.added_refs}
          title="추가된 참조"
        />
        <ReferenceCard
          emptyMessage="변경된 참조가 없습니다."
          references={revisionView.changed_refs}
          title="변경된 참조"
        />
        <ReferenceCard
          emptyMessage="제거된 참조가 없습니다."
          references={revisionView.removed_refs}
          title="제거된 참조"
        />
        <ReferenceCard
          emptyMessage="무효화된 승인 참조가 없습니다."
          references={revisionView.invalidated_approval_refs}
          title="무효화된 승인 참조"
        />
      </div>

      <div className={styles.revisionGrid}>
        <article className={styles.revisionCard}>
          <h3>이전 의미 지문</h3>
          <p className={styles.hash}>
            {revisionView.previous_semantic_fingerprint ?? "제공되지 않음"}
          </p>
        </article>
        <article className={styles.revisionCard}>
          <h3>현재 의미 지문</h3>
          <p className={styles.hash}>
            {revisionView.current_semantic_fingerprint}
          </p>
        </article>
      </div>
    </section>
  );
}
