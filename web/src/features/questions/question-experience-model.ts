import type { ResultAnswerV1 } from "../../../../contracts/web-report/v1/generated/types";

import type {
  ConversationKey,
  QuestionDraftState,
} from "@/features/questions/model/draft-cache";
import type {
  ConversationRecord,
  QuestionRequestSnapshot,
  QuestionRequestState,
} from "@/features/questions/question-api";
import type { ReportScope } from "@/features/report/report-model";


export type DraftEnvelope = {
  key: string;
  state: QuestionDraftState;
};

export type ConversationEnvelope = {
  current: ConversationRecord[];
  key: string;
  previous: ConversationRecord[];
};

export type RequestEnvelope = {
  key: string;
  snapshot: QuestionRequestSnapshot;
};

export const EMPTY_DRAFT: QuestionDraftState = {
  drawerOpen: false,
  scrollTop: 0,
  text: "",
};

export const TERMINAL_STATES = new Set<QuestionRequestState>([
  "cancelled",
  "completed",
  "failed",
  "scope_required",
]);

export const SCOPE_LABELS: Record<ReportScope["scopeKind"], string> = {
  claim: "주장",
  evidence: "근거",
  expert_packet: "전문가 패킷",
  issue: "문제",
  revision_diff: "변경",
  run: "실행",
  section: "화면",
  source: "출처",
};

export function requestStatus(
  snapshot: QuestionRequestSnapshot | null,
): string {
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

export function clientRequestId(): string {
  return globalThis.crypto?.randomUUID?.() ??
    `client-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function latestAnswerText(
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

export function conversationKeyFor(
  runId: string,
  revision: number,
  scope: ReportScope,
): ConversationKey {
  return {
    revision,
    runId,
    scopeInstanceId: scope.scopeInstanceId,
    scopeKind: scope.scopeKind,
  };
}
