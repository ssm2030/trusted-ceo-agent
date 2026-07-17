"use client";

import styles from "@/features/questions/QuestionExperience.module.css";

type QuestionConsentDialogProps = {
  accepted: boolean;
  disclosures: string[];
  modeLabel: string;
  onAcceptedChange: (accepted: boolean) => void;
  onCancel: () => void;
  onConfirm: () => void;
  open: boolean;
};

export function QuestionConsentDialog({
  accepted,
  disclosures,
  modeLabel,
  onAcceptedChange,
  onCancel,
  onConfirm,
  open,
}: QuestionConsentDialogProps) {
  if (!open) {
    return null;
  }
  return (
    <div className={styles.consentBackdrop}>
      <section
        aria-label="원격 처리 동의"
        aria-modal="true"
        className={styles.consentDialog}
        role="dialog"
      >
        <p className={styles.eyebrow}>최초 질문 전 확인</p>
        <h2>원격 처리 동의</h2>
        <span className={styles.mode}>{modeLabel}</span>
        <ul className={styles.disclosureList}>
          {disclosures.map((disclosure) => (
            <li key={disclosure}>{disclosure}</li>
          ))}
        </ul>
        <label className={styles.checkLabel}>
          <input
            checked={accepted}
            onChange={(event) => onAcceptedChange(event.currentTarget.checked)}
            type="checkbox"
          />
          원격 처리 안내를 확인하고 동의합니다
        </label>
        <div className={styles.consentActions}>
          <button
            className={styles.secondaryButton}
            onClick={onCancel}
            type="button"
          >
            취소
          </button>
          <button
            className={styles.primaryButton}
            disabled={!accepted}
            onClick={onConfirm}
            type="button"
          >
            동의하고 질문 보내기
          </button>
        </div>
      </section>
    </div>
  );
}
