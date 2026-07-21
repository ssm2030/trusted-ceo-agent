import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

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
  type QuestionApi,
} from "@/features/questions/question-api";
import {
  EMPTY_DRAFT,
  TERMINAL_STATES,
  clientRequestId,
  latestAnswerText,
  requestStatus,
  type ConversationEnvelope,
  type DraftEnvelope,
  type RequestEnvelope,
} from "@/features/questions/question-experience-model";
import { createSpeechInputController } from "@/features/questions/web-speech";
import type { ReportScope } from "@/features/report/report-model";


type UseQuestionExperienceOptions = {
  api?: QuestionApi;
  csrfToken: string | null;
  draftCache?: QuestionDraftCache;
  enabled: boolean;
  previousRevision: number | null;
  revision: number;
  runId: string;
  scope: ReportScope;
};


export function useQuestionExperience({
  api,
  csrfToken,
  draftCache = browserQuestionDraftCache,
  enabled,
  previousRevision,
  revision,
  runId,
  scope,
}: UseQuestionExperienceOptions) {
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
  return {
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
  };
}
