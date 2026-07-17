import type { ResultAnswerV1 } from "../../../../contracts/web-report/v1/generated/types";

import type { ConversationRecord } from "@/features/questions/question-api";
import styles from "@/features/questions/QuestionExperience.module.css";

export type QuestionReferenceKind =
  | "claim"
  | "evidence"
  | "source"
  | "expert_packet"
  | "revision_diff";

type AnswerBlocksProps = {
  currentRecords: ConversationRecord[];
  onReferenceSelect: (
    kind: QuestionReferenceKind,
    reference: string,
  ) => void;
  previousRecords: ConversationRecord[];
  previousRevision: number | null;
  transientAnswer: ResultAnswerV1 | null;
};

type CanonicalAnswerProps = {
  answer: ResultAnswerV1;
  onReferenceSelect: AnswerBlocksProps["onReferenceSelect"];
};

function CanonicalAnswer({
  answer,
  onReferenceSelect,
}: CanonicalAnswerProps) {
  return (
    <>
      {answer.answer_blocks.map((block) => (
        <div key={block.block_id}>
          <p className={styles.answerText}>{block.text}</p>
          {block.support_status === "supported" ? (
            <div className={styles.referenceList}>
              {block.claim_refs.map((reference) => (
                <button
                  aria-label={`주장 ${reference}으로 이동`}
                  className={styles.referenceButton}
                  key={`claim:${reference}`}
                  onClick={() => onReferenceSelect("claim", reference)}
                  type="button"
                >
                  주장 근거
                </button>
              ))}
              {block.evidence_link_ids.map((reference) => (
                <button
                  aria-label={`근거 ${reference}으로 이동`}
                  className={styles.referenceButton}
                  key={`evidence:${reference}`}
                  onClick={() => onReferenceSelect("evidence", reference)}
                  type="button"
                >
                  근거 보기
                </button>
              ))}
              {block.source_refs.map((reference) => (
                <button
                  aria-label={`출처 ${reference}으로 이동`}
                  className={styles.referenceButton}
                  key={`source:${reference}`}
                  onClick={() => onReferenceSelect("source", reference)}
                  type="button"
                >
                  출처 보기
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ))}
      <span className={styles.validation}>{answer.validation.label_ko}</span>
    </>
  );
}

function recordItem(
  record: ConversationRecord,
  previous: boolean,
  onReferenceSelect: AnswerBlocksProps["onReferenceSelect"],
) {
  const previousClass = previous ? styles.previousMessage : "";
  if (record.type === "question_submitted") {
    return (
      <li
        className={`${styles.message} ${styles.questionMessage} ${previousClass}`}
        key={record.recordId}
      >
        {previous ? (
          <span className={styles.previousLabel}>
            이전 리비전 {record.key.revision}
          </span>
        ) : null}
        <p className={styles.answerText}>{record.question}</p>
      </li>
    );
  }
  if (record.type === "answer_verified") {
    return (
      <li
        className={`${styles.message} ${styles.answerMessage} ${previousClass}`}
        key={record.recordId}
      >
        {previous ? (
          <span className={styles.previousLabel}>
            이전 리비전 {record.key.revision}
          </span>
        ) : null}
        <CanonicalAnswer
          answer={record.answer}
          onReferenceSelect={onReferenceSelect}
        />
      </li>
    );
  }
  return (
    <li
      className={`${styles.message} ${styles.answerMessage} ${previousClass}`}
      key={record.recordId}
    >
      {previous ? (
        <span className={styles.previousLabel}>
          이전 리비전 {record.key.revision}
        </span>
      ) : null}
      <p className={styles.answerText}>
        질문을 완료하지 못했습니다. 저장된 결과는 그대로 유지됩니다.
      </p>
    </li>
  );
}

export function AnswerBlocks({
  currentRecords,
  onReferenceSelect,
  previousRecords,
  previousRevision,
  transientAnswer,
}: AnswerBlocksProps) {
  const hasTransientDuplicate =
    transientAnswer !== null &&
    currentRecords.some(
      (record) =>
        record.type === "answer_verified" &&
        record.answer.job_id === transientAnswer.job_id,
    );
  const empty =
    previousRecords.length === 0 &&
    currentRecords.length === 0 &&
    transientAnswer === null;

  if (empty) {
    return (
      <p className={styles.empty}>
        현재 범위에 저장된 질문이 없습니다.
      </p>
    );
  }

  return (
    <ol className={styles.timeline}>
      {previousRevision === null
        ? null
        : previousRecords.map((record) =>
            recordItem(record, true, onReferenceSelect),
          )}
      {currentRecords.map((record) =>
        recordItem(record, false, onReferenceSelect),
      )}
      {transientAnswer === null || hasTransientDuplicate ? null : (
        <li
          className={`${styles.message} ${styles.answerMessage}`}
          key={`transient:${transientAnswer.job_id}`}
        >
          <CanonicalAnswer
            answer={transientAnswer}
            onReferenceSelect={onReferenceSelect}
          />
        </li>
      )}
    </ol>
  );
}
