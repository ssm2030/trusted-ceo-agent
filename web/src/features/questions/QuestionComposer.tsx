"use client";

import type { KeyboardEvent } from "react";

import { VoiceControls } from "@/features/questions/VoiceControls";
import type { SpeechInputController } from "@/features/questions/web-speech";
import styles from "@/features/questions/QuestionExperience.module.css";

type QuestionComposerProps = {
  answerText: string;
  busy: boolean;
  disabled: boolean;
  draft: string;
  onDraftChange: (draft: string) => void;
  onSubmit: () => void;
  speechController: SpeechInputController;
};

export function QuestionComposer({
  answerText,
  busy,
  disabled,
  draft,
  onDraftChange,
  onSubmit,
  speechController,
}: QuestionComposerProps) {
  const appendTranscript = (transcript: string) => {
    const spacer = draft.trim().length === 0 ? "" : " ";
    onDraftChange(`${draft}${spacer}${transcript}`);
  };
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      onSubmit();
    }
  };

  return (
    <div className={styles.composer}>
      <label htmlFor="result-question">결과 질문</label>
      <textarea
        className={styles.textarea}
        disabled={disabled || busy}
        id="result-question"
        onChange={(event) => onDraftChange(event.currentTarget.value)}
        onKeyDown={handleKeyDown}
        placeholder="현재 범위의 근거에 대해 질문하세요."
        value={draft}
      />
      <VoiceControls
        answerText={answerText}
        controller={speechController}
        onTranscript={appendTranscript}
      />
      <div className={styles.composerActions}>
        <span className={styles.messageMeta}>
          음성 인식 결과도 초안으로만 입력됩니다.
        </span>
        <button
          className={styles.primaryButton}
          disabled={
            disabled ||
            busy ||
            draft.trim().length === 0
          }
          onClick={onSubmit}
          type="button"
        >
          {busy ? "질문 처리 중" : "질문 보내기"}
        </button>
      </div>
    </div>
  );
}
