"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import type { ResultAnswerV1 } from "../../../../contracts/web-report/v1/generated/types";

import {
  AnswerBlocks,
  type QuestionReferenceKind,
} from "@/features/questions/AnswerBlocks";
import {
  browserQuestionDraftCache,
  QuestionDraftCache,
  serializeConversationKey,
  type ConversationKey,
  type QuestionDraftState,
} from "@/features/questions/model/draft-cache";
import {
  createQuestionApi,
  type CapabilityResponse,
  type ConversationRecord,
  type QuestionApi,
  type QuestionRequestSnapshot,
  type QuestionRequestState,
} from "@/features/questions/question-api";
import { QuestionComposer } from "@/features/questions/QuestionComposer";
import { QuestionConsentDialog } from "@/features/questions/QuestionConsentDialog";
import { QuestionDrawer } from "@/features/questions/QuestionDrawer";
import { QuestionLauncher } from "@/features/questions/QuestionLauncher";
import { createSpeechInputController } from "@/features/questions/web-speech";
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

type DraftEnvelope = {
  key: string;
  state: QuestionDraftState;
};

type ConversationEnvelope = {
  current: ConversationRecord[];
  key: string;
  previous: ConversationRecord[];
};

type RequestEnvelope = {
  key: string;
  snapshot: QuestionRequestSnapshot;
};

const EMPTY_DRAFT: QuestionDraftState = {
  drawerOpen: false,
  scrollTop: 0,
  text: "",
};

const TERMINAL_STATES = new Set<QuestionRequestState>([
  "cancelled",
  "completed",
  "failed",
  "scope_required",
]);

const SCOPE_LABELS: Record<ReportScope["scopeKind"], string> = {
  claim: "주장",
  evidence: "근거",
  expert_packet: "전문가 패킷",
  issue: "문제",
  revision_diff: "변경",
  run: "실행",
  section: "화면",
  source: "출처",
};

function requestStatus(snapshot: QuestionRequestSnapshot | null): string {
  if (snapshot === null) {
    return "질문 대기 중";
  }
  switch (snapshot.state) {
    case "queued":
      return "질문 대기 중";
    case "preparing":
      return "근거 범위 준비 중";
    case "asking":
      return "AI 서비스가 근거를 검토 중";
    case "validating":
      return "로컬 검증 엔진이 답변 검증 중";
    case "scope_required":
      return "질문 범위를 더 좁혀 주세요";
    case "failed":
      return "질문을 완료하지 못했습니다";
    case "cancelled":
      return "질문이 취소되었습니다";
    case "completed":
      return "검증된 답변 준비 완료";
  }
}

function clientRequestId(): string {
  return globalThis.crypto?.randomUUID?.() ??
    `client-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function latestAnswerText(
  records: ConversationRecord[],
  transientAnswer: ResultAnswerV1 | null,
): string {
  const answer =
    transientAnswer ??
    records
      .filter(
        (
          record,
        ): record is Extract<
          ConversationRecord,
          { type: "answer_verified" }
        > => record.type === "answer_verified",
      )
      .at(-1)?.answer ??
    null;
  return answer?.answer_blocks.map((block) => block.text).join("\n\n") ?? "";
}

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
  const conversationKey = useMemo<ConversationKey>(
    () => ({
      revision,
      runId,
      scopeInstanceId: scope.scopeInstanceId,
      scopeKind: scope.scopeKind,
    }),
    [
      revision,
      runId,
      scope.scopeInstanceId,
      scope.scopeKind,
    ],
  );
  const serializedKey = serializeConversationKey(conversationKey);
  const resolvedApi = useMemo(
    () =>
      api ??
      (csrfToken === null ? null : createQuestionApi(csrfToken)),
    [api, csrfToken],
  );
  const speechController = useMemo(
    () => createSpeechInputController(),
    [],
  );
  const launcherRef = useRef<HTMLButtonElement>(null);
  const interactionVersion = useRef(0);
  const currentKeyRef = useRef(serializedKey);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const previousKeyRef = useRef(serializedKey);
  const activeRequestRef = useRef<RequestEnvelope | null>(null);
  useEffect(() => {
    currentKeyRef.current = serializedKey;
  }, [serializedKey]);

  const [draftEnvelope, setDraftEnvelope] = useState<DraftEnvelope>({
    key: serializedKey,
    state: EMPTY_DRAFT,
  });
  const [conversation, setConversation] =
    useState<ConversationEnvelope | null>(null);
  const [capability, setCapability] =
    useState<CapabilityResponse | null>(null);
  const [activeRequest, setActiveRequest] =
    useState<RequestEnvelope | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [consentOpen, setConsentOpen] = useState(false);
  const [consentChecked, setConsentChecked] = useState(false);
  const [consentGranted, setConsentGranted] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  const draft =
    draftEnvelope.key === serializedKey
      ? draftEnvelope.state
      : {
          ...EMPTY_DRAFT,
          drawerOpen: draftEnvelope.state.drawerOpen,
        };
  const currentRecords =
    conversation?.key === serializedKey ? conversation.current : [];
  const previousRecords =
    conversation?.key === serializedKey ? conversation.previous : [];
  const currentRequest =
    activeRequest?.key === serializedKey
      ? activeRequest.snapshot
      : null;

  const updateDraft = useCallback(
    (update: Partial<QuestionDraftState>) => {
      interactionVersion.current += 1;
      setDraftEnvelope((current) => ({
        key: serializedKey,
        state: {
          ...(current.key === serializedKey
            ? current.state
            : EMPTY_DRAFT),
          ...update,
        },
      }));
    },
    [serializedKey],
  );

  useEffect(() => {
    const loadVersion = interactionVersion.current;
    let active = true;
    void draftCache.load(conversationKey).then((cached) => {
      if (active && interactionVersion.current === loadVersion) {
        setDraftEnvelope({ key: serializedKey, state: cached });
      }
    });
    return () => {
      active = false;
    };
  }, [conversationKey, draftCache, serializedKey]);

  useEffect(() => {
    if (draftEnvelope.key === serializedKey) {
      void draftCache.save(conversationKey, draftEnvelope.state);
    }
  }, [
    conversationKey,
    draftCache,
    draftEnvelope,
    serializedKey,
  ]);

  useEffect(() => {
    if (
      !draft.drawerOpen ||
      !enabled ||
      resolvedApi === null
    ) {
      return;
    }
    let active = true;
    const previousKey =
      previousRevision === null || previousRevision === revision
        ? null
        : { ...conversationKey, revision: previousRevision };
    const previousPromise =
      previousKey === null
        ? Promise.resolve({ key: conversationKey, records: [] })
        : resolvedApi.getConversation(previousKey);

    void Promise.all([
      resolvedApi.getCapability(),
      resolvedApi.getConversation(conversationKey),
      previousPromise,
    ])
      .then(([nextCapability, current, previous]) => {
        if (!active) {
          return;
        }
        setCapability(nextCapability);
        setConversation({
          current: current.records,
          key: serializedKey,
          previous: previous.records,
        });
        setLoadFailed(false);
      })
      .catch(() => {
        if (active) {
          setLoadFailed(true);
        }
      });
    return () => {
      active = false;
    };
  }, [
    conversationKey,
    draft.drawerOpen,
    enabled,
    previousRevision,
    resolvedApi,
    revision,
    serializedKey,
  ]);

  useEffect(() => {
    if (previousKeyRef.current === serializedKey) {
      return;
    }
    const request = activeRequestRef.current;
    if (
      request !== null &&
      request.key !== serializedKey &&
      !TERMINAL_STATES.has(request.snapshot.state) &&
      resolvedApi !== null
    ) {
      void resolvedApi.cancelRequest(request.snapshot.requestId);
    }
    if (pollTimerRef.current !== null) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    previousKeyRef.current = serializedKey;
  }, [resolvedApi, serializedKey]);

  useEffect(
    () => () => {
      if (pollTimerRef.current !== null) {
        clearTimeout(pollTimerRef.current);
      }
    },
    [],
  );

  const setRequest = (envelope: RequestEnvelope) => {
    activeRequestRef.current = envelope;
    setActiveRequest(envelope);
  };

  const refreshConversation = async (key: string) => {
    if (resolvedApi === null || currentKeyRef.current !== key) {
      return;
    }
    try {
      const current = await resolvedApi.getConversation(conversationKey);
      if (currentKeyRef.current === key) {
        setConversation((existing) => ({
          current: current.records,
          key,
          previous:
            existing?.key === key ? existing.previous : [],
        }));
      }
    } catch {
      // A verified transient answer remains visible if refresh is delayed.
    }
  };

  const pollRequest = async (requestId: string, key: string) => {
    if (resolvedApi === null || currentKeyRef.current !== key) {
      return;
    }
    try {
      const snapshot = await resolvedApi.getRequest(requestId);
      if (currentKeyRef.current !== key) {
        return;
      }
      setRequest({ key, snapshot });
      if (TERMINAL_STATES.has(snapshot.state)) {
        if (snapshot.state === "completed") {
          await refreshConversation(key);
        }
        return;
      }
      pollTimerRef.current = setTimeout(
        () => void pollRequest(requestId, key),
        700,
      );
    } catch {
      setLoadFailed(true);
    }
  };

  const performSubmit = async (question: string) => {
    if (resolvedApi === null || submitting) {
      return;
    }
    const keyAtSubmit = serializedKey;
    setSubmitting(true);
    try {
      const accepted = await resolvedApi.submitQuestion({
        clientRequestId: clientRequestId(),
        consentVersion: "qa-remote-processing-v1",
        issueId: scope.issueId,
        question,
        revision,
        runId,
        scopeInstanceId: scope.scopeInstanceId,
        scopeKind: scope.scopeKind,
      });
      if (currentKeyRef.current !== keyAtSubmit) {
        return;
      }
      setRequest({ key: keyAtSubmit, snapshot: accepted.request });
      updateDraft({ text: "" });
      await pollRequest(accepted.request.requestId, keyAtSubmit);
    } catch {
      setLoadFailed(true);
    } finally {
      setSubmitting(false);
    }
  };

  const canAsk =
    enabled &&
    resolvedApi !== null &&
    capability?.capability.textQuestionEnabled === true &&
    capability.capability.disclosureVersion ===
      "qa-remote-processing-v1";
  const requestSubmit = () => {
    const question = draft.text.trim();
    if (!canAsk || question.length === 0) {
      return;
    }
    if (!consentGranted) {
      setPendingQuestion(question);
      setConsentOpen(true);
      return;
    }
    void performSubmit(question);
  };
  const closeDrawer = useCallback(() => {
    updateDraft({ drawerOpen: false });
    queueMicrotask(() => launcherRef.current?.focus());
  }, [updateDraft]);
  const transientAnswer = currentRequest?.answer ?? null;
  const status = !enabled
    ? "현재 환경에서는 새 질문을 사용할 수 없습니다"
    : loadFailed
      ? "현재 환경에서는 새 질문을 사용할 수 없습니다"
      : requestStatus(currentRequest);
  const answerText = latestAnswerText(
    currentRecords,
    transientAnswer,
  );
  const modeLabel =
    capability?.capability.modeLabelKo ??
    (!enabled ? "질문 비활성" : null);

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
