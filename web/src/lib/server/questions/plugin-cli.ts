import {
  spawn,
  type ChildProcessWithoutNullStreams,
} from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

import { minimalPluginEnvironment } from "@/lib/server/plugin-validator-client";
import type {
  PluginCliResult,
} from "@/lib/server/questions/types";

const DEFAULT_MAXIMUM_BYTES = 2 * 1024 * 1024;
const PLUGIN_RESPONSE_KEYS = [
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

const FIXED_PLUGIN_PREFIX = [
  "run",
  "--project",
  "plugin/trusted-ceo-agent",
  "--frozen",
  "--offline",
  "--no-sync",
  "python",
  "plugin/trusted-ceo-agent/scripts/trusted_ceo_agent.py",
] as const;

export type PluginCliCommand = Readonly<{
  executable: string;
  args: string[];
  shell: false;
}>;

export type PluginCliRunOptions = Readonly<{
  signal?: AbortSignal;
  maximumBytes?: number;
  redactions?: readonly string[];
}>;

export type PluginCliRunner = <T>(
  args: readonly string[],
  options?: PluginCliRunOptions,
) => Promise<PluginCliResult<T>>;

export type PluginCliRunnerDependencies = Readonly<{
  executable?: string;
  prefixArgs?: readonly string[];
  repositoryRoot?: string;
  environment?: NodeJS.ProcessEnv;
  spawnProcess?: typeof spawn;
}>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  );
}

function inferredRepositoryRoot(): string {
  const configured = process.env.TRUSTED_CEO_REPO_ROOT;
  if (configured !== undefined) {
    if (!path.isAbsolute(configured)) {
      throw new Error("plugin repository root must be absolute");
    }
    return configured;
  }
  const candidates = [
    process.cwd(),
    path.resolve(process.cwd(), ".."),
  ];
  const found = candidates.find((candidate) =>
    existsSync(
      path.join(
        candidate,
        "plugin",
        "trusted-ceo-agent",
        "scripts",
        "trusted_ceo_agent.py",
      ),
    ),
  );
  if (found === undefined) {
    throw new Error("plugin repository root is unavailable");
  }
  return found;
}

function parsePluginResponse<T>(
  stdout: string,
): PluginCliResult<T> {
  let value: unknown;
  try {
    value = JSON.parse(stdout.trim()) as unknown;
  } catch {
    throw new Error("plugin output is not one JSON object");
  }
  if (!isRecord(value)) {
    throw new Error("plugin output is not one JSON object");
  }
  const keys = Object.keys(value).sort();
  if (
    keys.length !== PLUGIN_RESPONSE_KEYS.length ||
    keys.some(
      (key, index) => key !== PLUGIN_RESPONSE_KEYS[index],
    ) ||
    value.contract_version !== "1.0.0" ||
    typeof value.ok !== "boolean" ||
    !Number.isInteger(value.code) ||
    typeof value.command !== "string" ||
    typeof value.message !== "string" ||
    (value.run_id !== null &&
      typeof value.run_id !== "string") ||
    (value.revision !== null &&
      !Number.isInteger(value.revision)) ||
    (value.state !== null && typeof value.state !== "string")
  ) {
    throw new Error("plugin response contract is invalid");
  }
  return Object.freeze({
    ok: value.ok,
    code: value.code as number,
    command: value.command,
    run_id: value.run_id as string | null,
    revision: value.revision as number | null,
    state: value.state as string | null,
    data: value.data as T,
  });
}

export function buildPluginCliCommand(
  args: readonly string[],
): PluginCliCommand {
  if (
    args.length === 0 ||
    args.some(
      (argument) =>
        typeof argument !== "string" ||
        argument.includes("\0"),
    )
  ) {
    throw new Error("plugin arguments are invalid");
  }
  return Object.freeze({
    executable: "uv",
    args: [...FIXED_PLUGIN_PREFIX, ...args],
    shell: false as const,
  });
}

export function createPluginCliRunner(
  dependencies: PluginCliRunnerDependencies = {},
): PluginCliRunner {
  const executable = dependencies.executable ?? "uv";
  const prefixArgs =
    dependencies.prefixArgs ?? FIXED_PLUGIN_PREFIX;
  const repositoryRoot =
    dependencies.repositoryRoot ?? inferredRepositoryRoot();
  if (!path.isAbsolute(repositoryRoot)) {
    throw new Error("plugin repository root must be absolute");
  }
  const spawnProcess = dependencies.spawnProcess ?? spawn;
  const environment =
    dependencies.environment ??
    minimalPluginEnvironment(process.env);

  return async function run<T>(
    args: readonly string[],
    options: PluginCliRunOptions = {},
  ): Promise<PluginCliResult<T>> {
    if (
      args.length === 0 ||
      args.some(
        (argument) =>
          typeof argument !== "string" ||
          argument.includes("\0"),
      )
    ) {
      throw new Error("plugin arguments are invalid");
    }
    const maximumBytes =
      options.maximumBytes ?? DEFAULT_MAXIMUM_BYTES;
    if (
      !Number.isSafeInteger(maximumBytes) ||
      maximumBytes < 1
    ) {
      throw new Error("plugin output limit is invalid");
    }

    return new Promise<PluginCliResult<T>>((resolve, reject) => {
      let child: ChildProcessWithoutNullStreams;
      try {
        child = spawnProcess(
          executable,
          [...prefixArgs, ...args],
          {
            cwd: repositoryRoot,
            env: environment,
            shell: false,
            windowsHide: true,
            stdio: ["pipe", "pipe", "pipe"],
          },
        ) as ChildProcessWithoutNullStreams;
      } catch {
        reject(new Error("plugin command could not start"));
        return;
      }
      child.stdin.end();
      const stdout: Buffer[] = [];
      let totalBytes = 0;
      let exceeded = false;
      let aborted = false;
      const acceptChunk = (
        collection: Buffer[],
        chunk: Buffer | string,
      ): void => {
        const buffer = Buffer.isBuffer(chunk)
          ? chunk
          : Buffer.from(chunk);
        totalBytes += buffer.byteLength;
        if (totalBytes > maximumBytes) {
          exceeded = true;
          child.kill("SIGKILL");
          return;
        }
        collection.push(buffer);
      };
      child.stdout.on("data", (chunk: Buffer) => {
        acceptChunk(stdout, chunk);
      });
      child.stderr.on("data", (chunk: Buffer) => {
        acceptChunk([], chunk);
      });
      const abort = (): void => {
        aborted = true;
        child.kill("SIGKILL");
      };
      if (options.signal?.aborted) {
        abort();
      } else {
        options.signal?.addEventListener("abort", abort, {
          once: true,
        });
      }
      child.once("error", () => {
        options.signal?.removeEventListener("abort", abort);
        reject(new Error("plugin command failed"));
      });
      child.once("close", (code) => {
        options.signal?.removeEventListener("abort", abort);
        if (aborted) {
          reject(new Error("plugin command was cancelled"));
          return;
        }
        if (exceeded) {
          reject(new Error("plugin output limit exceeded"));
          return;
        }
        let response: PluginCliResult<T>;
        try {
          response = parsePluginResponse<T>(
            Buffer.concat(stdout).toString("utf8"),
          );
        } catch (error) {
          reject(error);
          return;
        }
        if (code !== response.code) {
          reject(new Error("plugin exit code did not match response"));
          return;
        }
        resolve(response);
      });
    });
  };
}

let defaultRunner: PluginCliRunner | undefined;

export async function runPluginCli<T>(
  args: readonly string[],
  options: PluginCliRunOptions = {},
): Promise<PluginCliResult<T>> {
  defaultRunner ??= createPluginCliRunner();
  return defaultRunner<T>(args, options);
}
