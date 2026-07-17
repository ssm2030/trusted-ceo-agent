import {
  chmod,
  mkdtemp,
  open,
  rm,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import type { QuestionCapability } from "@/lib/server/questions/capability";
import {
  buildCodexCommand,
  type CodexCommand,
} from "@/lib/server/questions/codex-command";
import {
  runCodexQuestion,
  type CodexRunResult,
} from "@/lib/server/questions/codex-runner";
import {
  buildSeatbeltProfile,
  wrapCodexWithSeatbelt,
} from "@/lib/server/questions/macos-seatbelt";
import {
  runPluginCli,
  type PluginCliRunOptions,
} from "@/lib/server/questions/plugin-cli";
import {
  QuestionExecutionError,
  ScopeRequiredError,
} from "@/lib/server/questions/question-coordinator";
import {
  getCurrentQuestionRunContext,
} from "@/lib/server/questions/run-context";
import type {
  PluginCliResult,
  QuestionRunContext,
  QuestionScope,
  ResultAnswer,
  ResultQuestionJob,
} from "@/lib/server/questions/types";
import {
  createQuestionWorkspace,
  type QuestionWorkspace,
} from "@/lib/server/questions/workspace";

type PluginRunner = (
  args: readonly string[],
  options?: PluginCliRunOptions,
) => Promise<PluginCliResult<unknown>>;

export type QuestionBridgeDependencies = Readonly<{
  pluginCli: PluginRunner;
  createWorkspace: (
    job: ResultQuestionJob,
  ) => Promise<QuestionWorkspace>;
  buildCommand: typeof buildCodexCommand;
  secureCommand: (
    command: CodexCommand,
    workspace: QuestionWorkspace,
    sandbox: "seatbelt_verified" | "poc_explicit",
  ) => Promise<CodexCommand>;
  runCodex: (input: {
    command: CodexCommand;
    outputPath: string;
    sandbox: "seatbelt_verified" | "poc_explicit";
    signal: AbortSignal;
  }) => Promise<CodexRunResult>;
  currentContext: () => QuestionRunContext | null;
  codexExecutable: string;
  codexHome: string;
}>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  );
}

async function writePrivateText(
  filePath: string,
  value: string,
): Promise<void> {
  const handle = await open(filePath, "wx", 0o600);
  try {
    if (process.platform !== "win32") {
      await handle.chmod(0o600);
    }
    await handle.writeFile(value, "utf8");
    await handle.sync();
  } finally {
    await handle.close();
  }
}

async function defaultSecureCommand(
  command: CodexCommand,
  workspace: QuestionWorkspace,
  sandbox: "seatbelt_verified" | "poc_explicit",
): Promise<CodexCommand> {
  if (sandbox === "poc_explicit") {
    return command;
  }
  if (process.platform !== "darwin") {
    throw new QuestionExecutionError(
      "MACOS_STRONG_ISOLATION_REQUIRED",
    );
  }
  const outputRoot = path.dirname(workspace.outputPath);
  const profilePath = path.join(outputRoot, "question.sb");
  const profile = buildSeatbeltProfile({
    codexExecutable: command.executable,
    questionRoot: workspace.root,
    outputRoot,
    temporaryRoot: outputRoot,
  });
  await writePrivateText(profilePath, profile);
  return wrapCodexWithSeatbelt({ profilePath, command });
}

function defaultDependencies(): QuestionBridgeDependencies {
  const codexExecutable =
    process.env.TRUSTED_CEO_CODEX_EXECUTABLE;
  const codexHome = process.env.TRUSTED_CEO_CODEX_HOME;
  if (
    codexExecutable === undefined ||
    codexHome === undefined ||
    !path.isAbsolute(codexExecutable) ||
    !path.isAbsolute(codexHome)
  ) {
    throw new QuestionExecutionError("CODEX_UNAVAILABLE");
  }
  return {
    pluginCli: runPluginCli as PluginRunner,
    createWorkspace: createQuestionWorkspace,
    buildCommand: buildCodexCommand,
    secureCommand: defaultSecureCommand,
    runCodex: runCodexQuestion,
    currentContext: getCurrentQuestionRunContext,
    codexExecutable,
    codexHome,
  };
}

function assertContextStillCurrent(
  expected: QuestionRunContext,
  currentContext: () => QuestionRunContext | null,
): void {
  const current = currentContext();
  if (
    current === null ||
    current.registrationId !== expected.registrationId ||
    current.runId !== expected.runId ||
    current.revision !== expected.revision ||
    current.bundleHash !== expected.bundleHash ||
    current.artifactRoot !== expected.artifactRoot
  ) {
    throw new QuestionExecutionError("QUESTION_REVISION_CHANGED");
  }
}

function preparedJob(
  response: PluginCliResult<unknown>,
  context: QuestionRunContext,
): ResultQuestionJob {
  if (
    !response.ok ||
    response.code !== 0 ||
    response.command !== "prepare-result-question" ||
    response.run_id !== context.runId ||
    response.revision !== context.revision ||
    !isRecord(response.data) ||
    !isRecord(response.data.job)
  ) {
    throw new QuestionExecutionError(
      "QUESTION_PREPARE_REJECTED",
    );
  }
  const job = response.data.job;
  if (
    job.job_version !== "1.0.0" ||
    typeof job.job_id !== "string" ||
    job.run_id !== context.runId ||
    job.revision !== context.revision ||
    job.privacy_classification !==
      context.privacyClassification
  ) {
    throw new QuestionExecutionError(
      "QUESTION_JOB_MISMATCH",
    );
  }
  return job as unknown as ResultQuestionJob;
}

function scopeRequired(
  response: PluginCliResult<unknown>,
): ScopeRequiredError | null {
  if (
    response.ok &&
    response.code === 2 &&
    response.command === "prepare-result-question" &&
    isRecord(response.data) &&
    response.data.error_code === "SCOPE_REQUIRED" &&
    Array.isArray(response.data.suggestions)
  ) {
    const suggestions = response.data.suggestions.map(
      (value) => {
        if (
          !isRecord(value) ||
          typeof value.scope_kind !== "string" ||
          typeof value.scope_instance_id !== "string"
        ) {
          throw new QuestionExecutionError(
            "QUESTION_SCOPE_RESPONSE_INVALID",
          );
        }
        return {
          kind: value.scope_kind,
          instanceId: value.scope_instance_id,
        };
      },
    );
    return new ScopeRequiredError(suggestions);
  }
  return null;
}

function canonicalAnswer(
  response: PluginCliResult<unknown>,
  context: QuestionRunContext,
  job: ResultQuestionJob,
): ResultAnswer {
  if (
    !response.ok ||
    response.code !== 0 ||
    response.command !== "validate-result-answer" ||
    response.run_id !== context.runId ||
    response.revision !== context.revision ||
    !isRecord(response.data) ||
    !isRecord(response.data.answer)
  ) {
    throw new QuestionExecutionError(
      "ANSWER_VALIDATION_REJECTED",
    );
  }
  const answer = response.data.answer;
  if (
    answer.answer_version !== "1.0.0" ||
    answer.job_id !== job.job_id ||
    answer.run_id !== context.runId ||
    answer.revision !== context.revision ||
    !Array.isArray(answer.answer_blocks)
  ) {
    throw new QuestionExecutionError(
      "ANSWER_BINDING_MISMATCH",
    );
  }
  return answer as unknown as ResultAnswer;
}

export async function answerResultQuestion(
  input: {
    context: QuestionRunContext;
    question: string;
    scope: QuestionScope;
    capability: QuestionCapability;
    signal: AbortSignal;
    setState?: (
      state: "preparing" | "asking" | "validating",
    ) => void;
  },
  dependencies: QuestionBridgeDependencies = defaultDependencies(),
): Promise<ResultAnswer> {
  if (
    !input.capability.textQuestionEnabled ||
    (input.context.privacyClassification ===
      "company_restricted" &&
      !input.capability.companyDataEnabled)
  ) {
    throw new QuestionExecutionError(
      "QUESTION_CAPABILITY_DENIED",
    );
  }
  assertContextStillCurrent(
    input.context,
    dependencies.currentContext,
  );
  input.setState?.("preparing");

  const requestRoot = await mkdtemp(
    path.join(tmpdir(), "trusted-ceo-question-request-"),
  );
  if (process.platform !== "win32") {
    await chmod(requestRoot, 0o700);
  }
  const questionPath = path.join(requestRoot, "question.txt");
  let workspace: QuestionWorkspace | null = null;
  try {
    await writePrivateText(questionPath, input.question);
    const prepared = await dependencies.pluginCli(
      [
        "prepare-result-question",
        "--artifact-root",
        input.context.artifactRoot,
        "--run-id",
        input.context.runId,
        "--revision",
        String(input.context.revision),
        "--question-file",
        questionPath,
        "--scope-kind",
        input.scope.kind,
        "--scope-instance-id",
        input.scope.instanceId,
        "--privacy-classification",
        input.context.privacyClassification,
      ],
      {
        signal: input.signal,
        redactions: [input.question],
      },
    );
    const required = scopeRequired(prepared);
    if (required !== null) {
      throw required;
    }
    const job = preparedJob(prepared, input.context);
    assertContextStillCurrent(
      input.context,
      dependencies.currentContext,
    );
    workspace = await dependencies.createWorkspace(job);
    const sandbox =
      input.context.privacyClassification ===
        "company_restricted" &&
      input.capability.companyDataEnabled
        ? "seatbelt_verified"
        : "poc_explicit";
    let command = dependencies.buildCommand({
      codexExecutable: dependencies.codexExecutable,
      codexHome: dependencies.codexHome,
      workspace,
    });
    command = await dependencies.secureCommand(
      command,
      workspace,
      sandbox,
    );
    input.setState?.("asking");
    let runResult: CodexRunResult;
    try {
      runResult = await dependencies.runCodex({
        command,
        outputPath: workspace.outputPath,
        sandbox,
        signal: input.signal,
      });
    } catch (error) {
      if (error instanceof QuestionExecutionError) {
        throw error;
      }
      throw new QuestionExecutionError(
        "CODEX_TRANSIENT_FAILURE",
        true,
      );
    }
    if (
      runResult.draft.job_id !== job.job_id ||
      runResult.draft.run_id !== input.context.runId ||
      runResult.draft.revision !== input.context.revision
    ) {
      throw new QuestionExecutionError(
        "ANSWER_DRAFT_BINDING_MISMATCH",
      );
    }
    assertContextStillCurrent(
      input.context,
      dependencies.currentContext,
    );
    input.setState?.("validating");
    const validated = await dependencies.pluginCli(
      [
        "validate-result-answer",
        "--artifact-root",
        input.context.artifactRoot,
        "--run-id",
        input.context.runId,
        "--revision",
        String(input.context.revision),
        "--job",
        workspace.jobPath,
        "--draft",
        workspace.outputPath,
      ],
      { signal: input.signal },
    );
    const answer = canonicalAnswer(
      validated,
      input.context,
      job,
    );
    assertContextStillCurrent(
      input.context,
      dependencies.currentContext,
    );
    return answer;
  } finally {
    await workspace?.cleanup();
    await rm(requestRoot, { recursive: true, force: true });
  }
}
