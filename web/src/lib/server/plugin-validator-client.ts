import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { promisify } from "node:util";

import type { ViewerEligibilityDecisionV1 } from "../../../../contracts/web-report/v1/generated/types";

import { validateEligibilityDecision } from "@/lib/server/bundle-validator";

const execFileAsync = promisify(execFile);
const MAX_PLUGIN_STDOUT_BYTES = 4 * 1024 * 1024;
const PLUGIN_TIMEOUT_MS = 60_000;
const HASH_PATTERN = /^[0-9a-f]{64}$/;
const RESPONSE_KEYS = [
  "code",
  "command",
  "contract_version",
  "data",
  "message",
  "ok",
  "revision",
  "run_id",
  "state",
] as const;

export type ValidateWebReportInput = Readonly<{
  artifactRoot: string;
  bundlePath: string;
  runId: string;
  revision: number;
  expectedBundleHash: string;
}>;

export type FixedCommand = Readonly<{
  file: "uv";
  args: string[];
}>;

export type ValidationExpectation = Readonly<{
  runId: string;
  revision: number;
  expectedBundleHash: string;
}>;

export class PluginValidatorClientError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PluginValidatorClientError";
  }
}

function isPlainObject(
  value: unknown,
): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    Object.getPrototypeOf(value) === Object.prototype
  );
}

export function buildValidateWebReportCommand(
  input: ValidateWebReportInput,
): FixedCommand {
  if (
    !Number.isInteger(input.revision) ||
    input.revision < 1 ||
    !HASH_PATTERN.test(input.expectedBundleHash)
  ) {
    throw new PluginValidatorClientError(
      "플러그인 검증 입력이 올바르지 않습니다.",
    );
  }
  return Object.freeze({
    file: "uv" as const,
    args: [
      "run",
      "--project",
      "plugin/trusted-ceo-agent",
      "--frozen",
      "--offline",
      "--no-sync",
      "python",
      "plugin/trusted-ceo-agent/scripts/trusted_ceo_agent.py",
      "validate-web-report",
      "--artifact-root",
      input.artifactRoot,
      "--run-id",
      input.runId,
      "--revision",
      String(input.revision),
      "--bundle",
      input.bundlePath,
    ],
  });
}

export async function parseValidateWebReportStdout(
  stdout: string,
  expected: ValidationExpectation,
): Promise<ViewerEligibilityDecisionV1> {
  if (
    Buffer.byteLength(stdout, "utf8") > MAX_PLUGIN_STDOUT_BYTES ||
    stdout.trim().length === 0
  ) {
    throw new PluginValidatorClientError(
      "플러그인 검증 출력은 단일 JSON이어야 합니다.",
    );
  }
  let envelope: unknown;
  try {
    envelope = JSON.parse(stdout.trim()) as unknown;
  } catch {
    throw new PluginValidatorClientError(
      "플러그인 검증 출력은 단일 JSON이어야 합니다.",
    );
  }
  if (!isPlainObject(envelope)) {
    throw new PluginValidatorClientError(
      "플러그인 검증 응답 형식이 올바르지 않습니다.",
    );
  }
  const keys = Object.keys(envelope).sort();
  if (
    keys.length !== RESPONSE_KEYS.length ||
    keys.some((key, index) => key !== RESPONSE_KEYS[index])
  ) {
    throw new PluginValidatorClientError(
      "플러그인 검증 응답 형식이 올바르지 않습니다.",
    );
  }
  if (
    envelope.contract_version !== "1.0.0" ||
    envelope.ok !== true ||
    envelope.code !== 0 ||
    envelope.command !== "validate-web-report" ||
    typeof envelope.message !== "string" ||
    envelope.run_id !== expected.runId ||
    envelope.revision !== expected.revision ||
    (envelope.state !== null &&
      typeof envelope.state !== "string")
  ) {
    throw new PluginValidatorClientError(
      "플러그인 검증 응답의 실행 정보가 일치하지 않습니다.",
    );
  }
  const decision = await validateEligibilityDecision(envelope.data);
  if (
    decision.viewer_mode === "rejected" ||
    decision.run_id !== expected.runId ||
    decision.revision !== expected.revision
  ) {
    throw new PluginValidatorClientError(
      "플러그인 검증 결정의 실행 정보가 일치하지 않습니다.",
    );
  }
  if (decision.bundle_hash !== expected.expectedBundleHash) {
    throw new PluginValidatorClientError(
      "plugin decision bundle hash mismatch",
    );
  }
  return decision;
}

function inferredRepositoryRoot(): string {
  const configured = process.env.TRUSTED_CEO_REPO_ROOT;
  if (configured !== undefined) {
    if (!path.isAbsolute(configured)) {
      throw new PluginValidatorClientError(
        "서버 repository root가 올바르지 않습니다.",
      );
    }
    return configured;
  }
  const candidates = [
    process.cwd(),
    path.resolve(process.cwd(), ".."),
  ];
  const root = candidates.find((candidate) =>
    existsSync(
      path.join(
        candidate,
        "plugin/trusted-ceo-agent/scripts/trusted_ceo_agent.py",
      ),
    ),
  );
  if (root === undefined) {
    throw new PluginValidatorClientError(
      "서버 repository root를 찾을 수 없습니다.",
    );
  }
  return root;
}

export function minimalPluginEnvironment(
  source: NodeJS.ProcessEnv = process.env,
): NodeJS.ProcessEnv {
  const result: NodeJS.ProcessEnv = {
    NODE_ENV: source.NODE_ENV ?? "production",
    PYTHONUTF8: "1",
    UV_NO_PROGRESS: "1",
    UV_OFFLINE: "1",
  };
  for (const key of [
    "PATH",
    "Path",
    "PATHEXT",
    "SystemRoot",
    "WINDIR",
    "HOME",
    "USERPROFILE",
    "TMPDIR",
    "TMP",
    "TEMP",
    "LOCALAPPDATA",
    "UV_CACHE_DIR",
  ]) {
    if (source[key] !== undefined) {
      result[key] = source[key];
    }
  }
  return result;
}

export async function validateRegisteredReport(
  input: ValidateWebReportInput,
  options: {
    repositoryRoot?: string;
    environment?: NodeJS.ProcessEnv;
  } = {},
): Promise<ViewerEligibilityDecisionV1> {
  const command = buildValidateWebReportCommand(input);
  const repositoryRoot =
    options.repositoryRoot ?? inferredRepositoryRoot();
  if (!path.isAbsolute(repositoryRoot)) {
    throw new PluginValidatorClientError(
      "서버 repository root가 올바르지 않습니다.",
    );
  }
  let stdout: string;
  try {
    const result = await execFileAsync(command.file, command.args, {
      cwd: repositoryRoot,
      env: minimalPluginEnvironment(options.environment),
      encoding: "utf8",
      maxBuffer: MAX_PLUGIN_STDOUT_BYTES,
      timeout: PLUGIN_TIMEOUT_MS,
      windowsHide: true,
      shell: false,
    });
    stdout = result.stdout;
  } catch {
    throw new PluginValidatorClientError(
      "플러그인 결과 검증에 실패했습니다.",
    );
  }
  return parseValidateWebReportStdout(stdout, {
    runId: input.runId,
    revision: input.revision,
    expectedBundleHash: input.expectedBundleHash,
  });
}
