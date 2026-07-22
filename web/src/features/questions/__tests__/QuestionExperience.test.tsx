import {
  act,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ResultAnswerV1 } from "../../../../../contracts/web-report/v1/generated/types";

import {
  QuestionExperience,
  type QuestionReferenceKind,
} from "@/features/questions/QuestionExperience";
import type {
  ConversationRecord,
  QuestionApi,
  QuestionRequestSnapshot,
  SubmitQuestionResponse,
} from "@/features/questions/question-api";
import { requestStatus } from "@/features/questions/question-experience-model";
import { useQuestionExperience } from "@/features/questions/useQuestionExperience";
import { QuestionDraftCache } from "@/features/questions/model/draft-cache";
import type { ReportScope } from "@/features/report/report-model";

const SCOPE: ReportScope = {
  activeRef: "evidence_main",
  issueId: "issue_main",
  scopeInstanceId: "evidence_main",
  scopeKind: "evidence",
};

const SECOND_SCOPE: ReportScope = {
  activeRef: "claim_secondary",
  issueId: "issue_secondary",
  scopeInstanceId: "claim_secondary",
  scopeKind: "claim",
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => {
    resolve = next;
  });
  return { promise, resolve };
}

const ANSWER: ResultAnswerV1 = {
  answer_version: "1.0.0",
  job_id: "job_main",
  run_id: "run_main",
  revision: 3,
  scope: {
    scope_kind: "evidence",
    scope_instance_id: "evidence_main",
    start_refs: ["evidence_main"],
    issue_id: "issue_main",
  },
  validation: {
    schema_valid: true,
    references_valid: true,
    values_valid: true,
    semantic_entailment_verified: false,
    label_ko: "스키마·참조 검증 통과",
  },
  answer_blocks: [
    {
      block_id: "answer_1",
      support_status: "supported",
      text: "검증된 근거에 따르면 관찰값을 확인할 수 있습니다.",
      resolved_values: [
        { value_ref: "fact_main", display_text: "100" },
      ],
      claim_refs: ["claim_main"],
      evidence_link_ids: ["evidence_main"],
      source_refs: ["source_main"],
    },
  ],
};

function completedRequest(): QuestionRequestSnapshot {
  return {
    answer: ANSWER,
    clientRequestId: "client_main",
    errorCode: null,
    queuePosition: null,
    requestId: "request_main",
    scopeSuggestions: [],
    state: "completed",
  };
}

function queuedRequest(
  requestId = "request_main",
  clientRequestId = "client_main",
): QuestionRequestSnapshot {
  return {
    ...completedRequest(),
    answer: null,
    clientRequestId,
    requestId,
    state: "queued",
  };
}

function createApi(overrides: Partial<QuestionApi> = {}): QuestionApi {
  return {
    cancelRequest: vi.fn().mockResolvedValue({ cancelled: true }),
    getCapability: vi.fn().mockResolvedValue({
      capability: {
        companyDataEnabled: false,
        disclosureVersion: "qa-remote-processing-v1",
        modeLabelKo: "POC 제한 모드",
        pocOnly: true,
        reasonCode: "POC_ONLY",
        textQuestionEnabled: true,
      },
      disclosuresKo: [
        "질문용 근거 묶음이 로그인된 Codex를 통해 OpenAI 서비스로 전송됩니다.",
        "답변은 플러그인 검증을 통과한 뒤에만 표시됩니다.",
      ],
    }),
    getConversation: vi.fn().mockResolvedValue({
      key: {
        revision: 3,
        runId: "run_main",
        scopeInstanceId: "evidence_main",
        scopeKind: "evidence",
      },
      records: [],
    }),
    getRequest: vi.fn().mockResolvedValue(completedRequest()),
    submitQuestion: vi.fn().mockResolvedValue({
      request: {
        ...completedRequest(),
        answer: null,
        state: "queued",
      },
    }),
    ...overrides,
  };
}

function makeCache(): QuestionDraftCache {
  return new QuestionDraftCache({
    digest: async (value) => `test:${value}`,
    storage: sessionStorage,
  });
}

function renderQuestionExperienceHook(api: QuestionApi) {
  const draftCache = makeCache();
  return renderHook(
    ({ scope }: { scope: ReportScope }) =>
      useQuestionExperience({
        api,
        csrfToken: "csrf_test",
        draftCache,
        enabled: true,
        previousRevision: 2,
        revision: 3,
        runId: "run_main",
        scope,
      }),
    { initialProps: { scope: SCOPE } },
  );
}

beforeEach(() => {
  sessionStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("QuestionExperience", () => {
  it("exposes the model and state hook as focused modules", () => {
    expect(requestStatus(null)).toBe("질문 대기 중");
    expect(useQuestionExperience).toBeTypeOf("function");
  });

  it("preserves an unsent draft and returns focus after close", async () => {
    const user = userEvent.setup();
    render(
      <QuestionExperience
        api={createApi()}
        csrfToken="csrf_test"
        draftCache={makeCache()}
        enabled
        onReferenceSelect={vi.fn()}
        previousRevision={2}
        revision={3}
        runId="run_main"
        scope={SCOPE}
      />,
    );

    const launcher = screen.getByRole("button", {
      name: "결과에 질문하기",
    });
    await user.click(launcher);
    const composer = await screen.findByLabelText("결과 질문");
    await user.type(composer, "회수 지연 근거는?");
    await user.click(screen.getByRole("button", { name: "질문 창 닫기" }));
    expect(launcher).toHaveFocus();

    await user.click(launcher);
    expect(await screen.findByLabelText("결과 질문")).toHaveValue(
      "회수 지연 근거는?",
    );
  });

  it("requires remote-processing consent and renders only canonical answers", async () => {
    const user = userEvent.setup();
    const api = createApi();
    const onReferenceSelect = vi.fn<
      (kind: QuestionReferenceKind, reference: string) => void
    >();
    render(
      <QuestionExperience
        api={api}
        csrfToken="csrf_test"
        draftCache={makeCache()}
        enabled
        onReferenceSelect={onReferenceSelect}
        previousRevision={2}
        revision={3}
        runId="run_main"
        scope={SCOPE}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "결과에 질문하기" }),
    );
    await user.type(
      await screen.findByLabelText("결과 질문"),
      "이 근거가 무엇을 뜻하나요?",
    );
    await user.click(screen.getByRole("button", { name: "질문 보내기" }));
    expect(api.submitQuestion).not.toHaveBeenCalled();
    expect(
      screen.getByRole("dialog", { name: "원격 처리 동의" }),
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("checkbox", {
        name: "원격 처리 안내를 확인하고 동의합니다",
      }),
    );
    await user.click(
      screen.getByRole("button", { name: "동의하고 질문 보내기" }),
    );

    await waitFor(() =>
      expect(api.submitQuestion).toHaveBeenCalledWith(
        expect.objectContaining({
          consentVersion: "qa-remote-processing-v1",
          question: "이 근거가 무엇을 뜻하나요?",
          scopeInstanceId: "evidence_main",
          scopeKind: "evidence",
        }),
      ),
    );
    expect(
      await screen.findByText(
        "검증된 근거에 따르면 관찰값을 확인할 수 있습니다.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("스키마·참조 검증 통과"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/modelDraft|stdout|stderr/)).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("button", {
        name: "근거 evidence_main으로 이동",
      }),
    );
    expect(onReferenceSelect).toHaveBeenCalledWith(
      "evidence",
      "evidence_main",
    );
  });

  it("loads a previous revision separately and labels its records", async () => {
    const user = userEvent.setup();
    const previousRecord: ConversationRecord = {
      createdAt: "2026-07-16T00:00:00.000Z",
      key: {
        revision: 2,
        runId: "run_main",
        scopeInstanceId: "evidence_main",
        scopeKind: "evidence",
      },
      question: "이전 질문",
      recordId: "record_previous",
      recordVersion: "1.0.0",
      type: "question_submitted",
    };
    const api = createApi({
      getConversation: vi.fn().mockImplementation(async (key) => ({
        key,
        records: key.revision === 2 ? [previousRecord] : [],
      })),
    });
    render(
      <QuestionExperience
        api={api}
        csrfToken="csrf_test"
        draftCache={makeCache()}
        enabled
        onReferenceSelect={vi.fn()}
        previousRevision={2}
        revision={3}
        runId="run_main"
        scope={SCOPE}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "결과에 질문하기" }),
    );
    expect(await screen.findByText("이전 질문")).toBeInTheDocument();
    expect(screen.getByText("이전 리비전 2")).toBeInTheDocument();
  });

  it("cancels the previous request and allows a new question after returning to its scope", async () => {
    const user = userEvent.setup();
    const pendingRequest = deferred<QuestionRequestSnapshot>();
    const returnedRequest = deferred<QuestionRequestSnapshot>();
    const cache = makeCache();
    const submitQuestion = vi
      .fn<QuestionApi["submitQuestion"]>()
      .mockResolvedValueOnce({
        request: {
          ...completedRequest(),
          answer: null,
          state: "queued",
        },
      })
      .mockResolvedValueOnce({
        request: {
          ...completedRequest(),
          answer: null,
          clientRequestId: "client_returned",
          requestId: "request_returned",
          state: "queued",
        },
      });
    const api = createApi({
      getConversation: vi.fn().mockImplementation(async (key) => ({
        key,
        records: [],
      })),
      getRequest: vi.fn().mockImplementation((requestId) =>
        requestId === "request_main"
          ? pendingRequest.promise
          : returnedRequest.promise,
      ),
      submitQuestion,
    });
    const { rerender } = render(
      <QuestionExperience
        api={api}
        csrfToken="csrf_test"
        draftCache={cache}
        enabled
        onReferenceSelect={vi.fn()}
        previousRevision={2}
        revision={3}
        runId="run_main"
        scope={SCOPE}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "결과에 질문하기" }),
    );
    await user.type(
      await screen.findByLabelText("결과 질문"),
      "이전 범위의 질문",
    );
    await user.click(screen.getByRole("button", { name: "질문 보내기" }));
    await user.click(
      screen.getByRole("checkbox", {
        name: "원격 처리 안내를 확인하고 동의합니다",
      }),
    );
    await user.click(
      screen.getByRole("button", { name: "동의하고 질문 보내기" }),
    );
    await waitFor(() =>
      expect(api.getRequest).toHaveBeenCalledWith("request_main"),
    );

    rerender(
      <QuestionExperience
        api={api}
        csrfToken="csrf_test"
        draftCache={cache}
        enabled
        onReferenceSelect={vi.fn()}
        previousRevision={2}
        revision={3}
        runId="run_main"
        scope={SECOND_SCOPE}
      />,
    );

    await waitFor(() =>
      expect(api.cancelRequest).toHaveBeenCalledWith("request_main"),
    );

    rerender(
      <QuestionExperience
        api={api}
        csrfToken="csrf_test"
        draftCache={cache}
        enabled
        onReferenceSelect={vi.fn()}
        previousRevision={2}
        revision={3}
        runId="run_main"
        scope={SCOPE}
      />,
    );

    expect(
      await screen.findByText("질문이 취소되었습니다"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        "검증된 근거에 따르면 관찰값을 확인할 수 있습니다.",
      ),
    ).not.toBeInTheDocument();
    const composer = await screen.findByLabelText("결과 질문");
    expect(composer).toBeEnabled();
    await user.clear(composer);
    await user.type(composer, "돌아온 범위의 새 질문");
    expect(
      screen.getByRole("button", { name: "질문 보내기" }),
    ).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "질문 보내기" }));

    await waitFor(() =>
      expect(submitQuestion).toHaveBeenLastCalledWith(
        expect.objectContaining({
          question: "돌아온 범위의 새 질문",
          scopeInstanceId: "evidence_main",
          scopeKind: "evidence",
        }),
      ),
    );
    await waitFor(() =>
      expect(api.getRequest).toHaveBeenCalledWith("request_returned"),
    );

    await act(async () => {
      pendingRequest.resolve(completedRequest());
      await pendingRequest.promise;
    });
    expect(
      screen.queryByText(
        "검증된 근거에 따르면 관찰값을 확인할 수 있습니다.",
      ),
    ).not.toBeInTheDocument();

    await act(async () => {
      returnedRequest.resolve({
        ...completedRequest(),
        answer: null,
        clientRequestId: "client_returned",
        requestId: "request_returned",
        state: "cancelled",
      });
      await returnedRequest.promise;
    });
  });

  it("cancels an accepted request that arrives after switching scopes", async () => {
    const pendingSubmit = deferred<SubmitQuestionResponse>();
    const getRequest = vi.fn<QuestionApi["getRequest"]>();
    const api = createApi({
      getRequest,
      submitQuestion: vi.fn().mockReturnValue(pendingSubmit.promise),
    });
    const { result, rerender } = renderQuestionExperienceHook(api);
    let submission!: Promise<void>;

    act(() => {
      submission = result.current.performSubmit("전환 전 질문");
    });
    expect(api.submitQuestion).toHaveBeenCalledOnce();

    rerender({ scope: SECOND_SCOPE });
    await act(async () => {
      pendingSubmit.resolve({ request: queuedRequest() });
      await submission;
    });

    expect(api.cancelRequest).toHaveBeenCalledWith("request_main");
    expect(getRequest).not.toHaveBeenCalled();
    rerender({ scope: SCOPE });
    expect(result.current.currentRequest).toBeNull();
  });

  it("cancels an accepted request that arrives after unmount", async () => {
    const pendingSubmit = deferred<SubmitQuestionResponse>();
    const getRequest = vi.fn<QuestionApi["getRequest"]>();
    const api = createApi({
      getRequest,
      submitQuestion: vi.fn().mockReturnValue(pendingSubmit.promise),
    });
    const { result, unmount } = renderQuestionExperienceHook(api);
    let submission!: Promise<void>;

    act(() => {
      submission = result.current.performSubmit("언마운트 전 질문");
    });
    unmount();
    await act(async () => {
      pendingSubmit.resolve({ request: queuedRequest() });
      await submission;
    });

    expect(api.cancelRequest).toHaveBeenCalledWith("request_main");
    expect(getRequest).not.toHaveBeenCalled();
  });

  it("does not restart polling when a pending poll resolves after unmount", async () => {
    vi.useFakeTimers();
    const pendingRequest = deferred<QuestionRequestSnapshot>();
    const getRequest = vi
      .fn<QuestionApi["getRequest"]>()
      .mockReturnValue(pendingRequest.promise);
    const api = createApi({ getRequest });
    const { result, unmount } = renderQuestionExperienceHook(api);
    let submission!: Promise<void>;

    await act(async () => {
      submission = result.current.performSubmit("폴링 중 질문");
      await Promise.resolve();
    });
    expect(getRequest).toHaveBeenCalledOnce();

    unmount();
    await act(async () => {
      pendingRequest.resolve({
        ...queuedRequest(),
        state: "asking",
      });
      await submission;
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(700);
    });

    expect(getRequest).toHaveBeenCalledOnce();
  });

  it("absorbs cancellation failures and keeps the original scope reusable", async () => {
    const pendingRequest = deferred<QuestionRequestSnapshot>();
    const submitQuestion = vi
      .fn<QuestionApi["submitQuestion"]>()
      .mockResolvedValueOnce({ request: queuedRequest() })
      .mockResolvedValueOnce({
        request: queuedRequest("request_returned", "client_returned"),
      });
    const getRequest = vi
      .fn<QuestionApi["getRequest"]>()
      .mockImplementation((requestId) =>
        requestId === "request_main"
          ? pendingRequest.promise
          : Promise.resolve({
              ...queuedRequest("request_returned", "client_returned"),
              state: "cancelled",
            }),
      );
    const cancellationFailure = Promise.reject(new Error("cancel failed"));
    void cancellationFailure.then(undefined, () => undefined);
    const cancellationCatch = vi.spyOn(cancellationFailure, "catch");
    const api = createApi({
      cancelRequest: vi.fn().mockReturnValue(cancellationFailure),
      getRequest,
      submitQuestion,
    });
    const { result, rerender } = renderQuestionExperienceHook(api);
    let initialSubmission!: Promise<void>;
    await act(async () => {
      initialSubmission = result.current.performSubmit("취소될 질문");
      await Promise.resolve();
    });
    expect(getRequest).toHaveBeenCalledWith("request_main");

    rerender({ scope: SECOND_SCOPE });
    await act(async () => {
      await Promise.resolve();
    });
    rerender({ scope: SCOPE });

    expect(cancellationCatch).toHaveBeenCalledOnce();
    expect(result.current.currentRequest?.state).toBe("cancelled");
    expect(result.current.submitting).toBe(false);
    await act(async () => {
      await result.current.performSubmit("돌아온 범위의 질문");
    });
    expect(submitQuestion).toHaveBeenLastCalledWith(
      expect.objectContaining({ question: "돌아온 범위의 질문" }),
    );

    await act(async () => {
      pendingRequest.resolve(completedRequest());
      await initialSubmission;
    });
  });

  it("keeps text input visible while new questions are disabled", async () => {
    const user = userEvent.setup();
    render(
      <QuestionExperience
        api={createApi()}
        csrfToken="csrf_test"
        draftCache={makeCache()}
        enabled={false}
        onReferenceSelect={vi.fn()}
        previousRevision={null}
        revision={3}
        runId="run_main"
        scope={SCOPE}
      />,
    );
    await user.click(
      screen.getByRole("button", { name: "결과에 질문하기" }),
    );

    expect(await screen.findByLabelText("결과 질문")).toBeDisabled();
    expect(
      screen.getByText("현재 환경에서는 새 질문을 사용할 수 없습니다"),
    ).toBeInTheDocument();
  });
});
