// @vitest-environment node
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import type { QuestionCapability } from "@/lib/server/questions/capability";
import type { CodexCommand } from "@/lib/server/questions/codex-command";
import type { CodexRunResult } from "@/lib/server/questions/codex-runner";
import {
  answerResultQuestion,
} from "@/lib/server/questions/question-bridge";
import {
  ScopeRequiredError,
} from "@/lib/server/questions/question-coordinator";
import type {
  PluginCliResult,
  QuestionRunContext,
  QuestionScope,
  ResultAnswer,
  ResultAnswerDraft,
  ResultQuestionJob,
} from "@/lib/server/questions/types";
import type { QuestionWorkspace } from "@/lib/server/questions/workspace";

const roots: string[] = [];
const context: QuestionRunContext = {
  registrationId: "representative",
  artifactRoot: "C:\\runs\\representative",
  runId: "run_20260717T010203Z_0123456789abcdef",
  revision: 3,
  viewerMode: "trusted_final",
  privacyClassification: "company_restricted",
  bundleHash: "a".repeat(64),
};
const scope: QuestionScope = {
  kind: "evidence",
  instanceId: "evidence_link_main",
  issueId: "issue_main",
};
const capability: QuestionCapability = {
  textQuestionEnabled: true,
  companyDataEnabled: true,
  pocOnly: false,
  reasonCode: "READY",
  disclosureVersion: "qa-remote-processing-v1",
  modeLabelKo: "강격리 검증 모드",
};
const job = {
  job_version: "1.0.0",
  job_id: "job_main",
  run_id: context.runId,
  revision: context.revision,
  privacy_classification: context.privacyClassification,
  scope: {
    scope_kind: scope.kind,
    scope_instance_id: scope.instanceId,
    issue_id: scope.issueId,
    start_refs: [scope.instanceId],
  },
} as ResultQuestionJob;
const draft = {
  draft_version: "1.0.0",
  job_id: job.job_id,
  run_id: context.runId,
  revision: context.revision,
  answer_blocks: [],
} as ResultAnswerDraft;
const answer = {
  answer_version: "1.0.0",
  job_id: job.job_id,
  run_id: context.runId,
  revision: context.revision,
  scope: job.scope,
  answer_blocks: [],
} as ResultAnswer;

afterEach(async () => {
  await Promise.all(
    roots.splice(0).map((root) =>
      rm(root, { recursive: true, force: true }),
    ),
  );
});

async function workspace(): Promise<QuestionWorkspace> {
  const root = await mkdtemp(
    path.join(tmpdir(), "trusted-ceo-bridge-test-"),
  );
  roots.push(root);
  return {
    root,
    jobPath: path.join(root, "question-job.json"),
    schemaPath: path.join(root, "schema.json"),
    outputPath: path.join(root, "draft.json"),
    temporaryParent: root,
    cleanup: vi.fn(async () => undefined),
  };
}

function envelope<T>(
  command: string,
  code: number,
  data: T,
): PluginCliResult<T> {
  return {
    ok: true,
    code,
    command,
    run_id: context.runId,
    revision: context.revision,
    state: "finalized",
    data,
  };
}

describe("answerResultQuestion", () => {
  it("prepares, asks once, validates, and returns only the canonical answer", async () => {
    const calls: string[] = [];
    const pluginCli = vi
      .fn()
      .mockImplementationOnce(async () => {
        calls.push("prepare");
        return envelope("prepare-result-question", 0, { job });
      })
      .mockImplementationOnce(async () => {
        calls.push("validate");
        return envelope("validate-result-answer", 0, {
          answer,
        });
      });
    const runCodex = vi.fn(async (): Promise<CodexRunResult> => {
      calls.push("codex");
      return {
        draft,
        progressEventCount: 1,
        durationMs: 10,
      };
    });
    const isolatedWorkspace = await workspace();
    const command: CodexCommand = {
      executable: "/usr/bin/sandbox-exec",
      args: ["-f", "/tmp/profile"],
      env: {},
    };

    const result = await answerResultQuestion(
      {
        context,
        question: "이 근거가 결론을 어떻게 뒷받침하나요?",
        scope,
        capability,
        signal: new AbortController().signal,
      },
      {
        pluginCli,
        createWorkspace: async () => isolatedWorkspace,
        buildCommand: () => command,
        secureCommand: async () => command,
        runCodex,
        currentContext: () => context,
        codexExecutable: "/Applications/Codex.app/Contents/MacOS/codex",
        codexHome: "/tmp/codex-home",
      },
    );

    expect(calls).toEqual(["prepare", "codex", "validate"]);
    expect(result).toEqual(answer);
    expect(result).not.toEqual(draft);
    expect(isolatedWorkspace.cleanup).toHaveBeenCalledTimes(1);
  });

  it("returns scope suggestions without calling Codex", async () => {
    const pluginCli = vi.fn(async () =>
      envelope("prepare-result-question", 2, {
        error_code: "SCOPE_REQUIRED",
        suggestions: [
          {
            scope_kind: "source",
            scope_instance_id: "source_main",
          },
        ],
      }),
    );
    const runCodex = vi.fn();
    await expect(
      answerResultQuestion(
        {
          context,
          question: "더 넓은 범위가 필요한가요?",
          scope,
          capability,
          signal: new AbortController().signal,
        },
        {
          pluginCli,
          createWorkspace: async () => workspace(),
          buildCommand: vi.fn(),
          secureCommand: vi.fn(),
          runCodex,
          currentContext: () => context,
          codexExecutable: "/usr/bin/codex",
          codexHome: "/tmp/codex-home",
        },
      ),
    ).rejects.toEqual(
      new ScopeRequiredError([
        { kind: "source", instanceId: "source_main" },
      ]),
    );
    expect(runCodex).not.toHaveBeenCalled();
  });

  it("rejects company data before preparing when strong isolation is unavailable", async () => {
    const pluginCli = vi.fn();
    await expect(
      answerResultQuestion(
        {
          context,
          question: "질문",
          scope,
          capability: {
            ...capability,
            textQuestionEnabled: false,
            companyDataEnabled: false,
            pocOnly: true,
            reasonCode: "OUTSIDE_READ_NOT_DENIED",
          },
          signal: new AbortController().signal,
        },
        {
          pluginCli,
          createWorkspace: async () => workspace(),
          buildCommand: vi.fn(),
          secureCommand: vi.fn(),
          runCodex: vi.fn(),
          currentContext: () => context,
          codexExecutable: "/usr/bin/codex",
          codexHome: "/tmp/codex-home",
        },
      ),
    ).rejects.toMatchObject({
      code: "QUESTION_CAPABILITY_DENIED",
    });
    expect(pluginCli).not.toHaveBeenCalled();
  });
});
