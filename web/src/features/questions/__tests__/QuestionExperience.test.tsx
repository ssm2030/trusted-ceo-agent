import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ResultAnswerV1 } from "../../../../../contracts/web-report/v1/generated/types";

import {
  QuestionExperience,
  type QuestionReferenceKind,
} from "@/features/questions/QuestionExperience";
import type {
  ConversationRecord,
  QuestionApi,
  QuestionRequestSnapshot,
} from "@/features/questions/question-api";
import { QuestionDraftCache } from "@/features/questions/model/draft-cache";
import type { ReportScope } from "@/features/report/report-model";

const SCOPE: ReportScope = {
  activeRef: "evidence_main",
  issueId: "issue_main",
  scopeInstanceId: "evidence_main",
  scopeKind: "evidence",
};

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

beforeEach(() => {
  sessionStorage.clear();
});

describe("QuestionExperience", () => {
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
