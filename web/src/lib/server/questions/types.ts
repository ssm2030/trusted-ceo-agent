import type {
  ResultAnswerDraftV1,
  ResultAnswerV1,
  ResultQuestionJobV1,
} from "../../../../../contracts/web-report/v1/generated/types";

export type ResultQuestionJob = ResultQuestionJobV1;
export type ResultAnswerDraft = ResultAnswerDraftV1;
export type ResultAnswer = ResultAnswerV1;

export type PrivacyClassification =
  | "poc_deidentified"
  | "company_restricted";

export const SCOPE_KINDS = [
  "run",
  "issue",
  "section",
  "claim",
  "evidence",
  "source",
  "expert_packet",
  "revision_diff",
] as const;

export type ScopeKind = (typeof SCOPE_KINDS)[number];

export interface QuestionRunContext {
  registrationId: string;
  artifactRoot: string;
  runId: string;
  revision: number;
  viewerMode: "trusted_final" | "poc_fixture";
  privacyClassification: PrivacyClassification;
  bundleHash: string;
}

export interface QuestionScope {
  kind: ScopeKind;
  instanceId: string;
  issueId: string | null;
}

export interface ConversationKey {
  runId: string;
  revision: number;
  scopeKind: ScopeKind;
  scopeInstanceId: string;
}

export function serializeConversationKey(
  key: ConversationKey,
): string {
  return [
    key.runId,
    String(key.revision),
    key.scopeKind,
    key.scopeInstanceId,
  ].join("\u001f");
}

export interface PluginCliResult<T> {
  ok: boolean;
  code: number;
  command: string;
  run_id: string | null;
  revision: number | null;
  state: string | null;
  data: T;
}
