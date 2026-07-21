"use client";

import {
  AnswerBlocks,
  type QuestionReferenceKind,
} from "@/features/questions/AnswerBlocks";
import {
  browserQuestionDraftCache,
  type QuestionDraftCache,
} from "@/features/questions/model/draft-cache";
import type { QuestionApi } from "@/features/questions/question-api";
import {
  SCOPE_LABELS,
  TERMINAL_STATES,
} from "@/features/questions/question-experience-model";
import { QuestionComposer } from "@/features/questions/QuestionComposer";
import { QuestionConsentDialog } from "@/features/questions/QuestionConsentDialog";
import { QuestionDrawer } from "@/features/questions/QuestionDrawer";
import { QuestionLauncher } from "@/features/questions/QuestionLauncher";
import { useQuestionExperience } from "@/features/questions/useQuestionExperience";
import type { ReportScope } from "@/features/report/report-model";
import styles from "@/features/questions/QuestionExperience.module.css";

export type { QuestionReferenceKind };

type QuestionExperienceProps = {
  api?: QuestionApi;
  csrfToken: string | null;
  draftCache?: QuestionDraftCache;
  enabled: boolean;
  onReferenceSelect: (
    kind: QuestionReferenceKind,
    reference: string,
  ) => void;
  previousRevision: number | null;
  revision: number;
  runId: string;
  scope: ReportScope;
};


export function QuestionExperience({
  api,
  csrfToken,
  draftCache = browserQuestionDraftCache,
  enabled,
  onReferenceSelect,
  previousRevision,
  revision,
  runId,
  scope,
}: QuestionExperienceProps) {
  const {
    answerText,
    canAsk,
    capability,
    closeDrawer,
    consentChecked,
    consentOpen,
    currentRecords,
    currentRequest,
    draft,
    launcherRef,
    modeLabel,
    pendingQuestion,
    performSubmit,
    previousRecords,
    requestSubmit,
    setConsentChecked,
    setConsentGranted,
    setConsentOpen,
    setPendingQuestion,
    speechController,
    status,
    submitting,
    transientAnswer,
    updateDraft,
  } = useQuestionExperience({
    api,
    csrfToken,
    draftCache,
    enabled,
    previousRevision,
    revision,
    runId,
    scope,
  });

  return (
    <>
      <QuestionLauncher
        buttonRef={launcherRef}
        onOpen={() => updateDraft({ drawerOpen: true })}
      />
      <QuestionDrawer
        composer={
          <QuestionComposer
            answerText={answerText}
            busy={submitting || (currentRequest !== null &&
              !TERMINAL_STATES.has(currentRequest.state))}
            disabled={!canAsk}
            draft={draft.text}
            onDraftChange={(text) => updateDraft({ text })}
            onSubmit={requestSubmit}
            speechController={speechController}
          />
        }
        modeLabel={modeLabel}
        onClose={closeDrawer}
        onScrollTopChange={(scrollTop) => updateDraft({ scrollTop })}
        open={draft.drawerOpen}
        scopeLabel={`현재 범위: ${SCOPE_LABELS[scope.scopeKind]} · ${scope.scopeInstanceId}`}
        scrollTop={draft.scrollTop}
      >
        <p className={styles.status} role="status">
          {status}
          {modeLabel === null ? null : (
            <span className={styles.mode}>{modeLabel}</span>
          )}
        </p>
        <AnswerBlocks
          currentRecords={currentRecords}
          onReferenceSelect={onReferenceSelect}
          previousRecords={previousRecords}
          previousRevision={previousRevision}
          transientAnswer={transientAnswer}
        />
      </QuestionDrawer>
      <QuestionConsentDialog
        accepted={consentChecked}
        disclosures={capability?.disclosuresKo ?? []}
        modeLabel={modeLabel ?? "질문 처리 모드"}
        onAcceptedChange={setConsentChecked}
        onCancel={() => {
          setConsentOpen(false);
          setConsentChecked(false);
          setPendingQuestion(null);
        }}
        onConfirm={() => {
          if (!consentChecked || pendingQuestion === null) {
            return;
          }
          const question = pendingQuestion;
          setConsentGranted(true);
          setConsentOpen(false);
          setPendingQuestion(null);
          void performSubmit(question);
        }}
        open={consentOpen}
      />
    </>
  );
}
