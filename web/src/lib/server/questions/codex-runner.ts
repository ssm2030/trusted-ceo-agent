import {
  spawn,
  type ChildProcessWithoutNullStreams,
} from "node:child_process";
import { readFile } from "node:fs/promises";

import type { CodexCommand } from "@/lib/server/questions/codex-command";
import type {
  ResultAnswerDraft,
} from "@/lib/server/questions/types";

const DEFAULT_TIMEOUT_MS = 90_000;
const DEFAULT_OUTPUT_BYTES = 2 * 1024 * 1024;

export interface CodexRunResult {
  draft: ResultAnswerDraft;
  progressEventCount: number;
  durationMs: number;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  );
}

function parseDraft(serialized: string): ResultAnswerDraft {
  let value: unknown;
  try {
    value = JSON.parse(serialized) as unknown;
  } catch {
    throw new Error("Codex returned invalid final JSON");
  }
  if (
    !isRecord(value) ||
    value.draft_version !== "1.0.0" ||
    typeof value.job_id !== "string" ||
    typeof value.run_id !== "string" ||
    !Number.isInteger(value.revision) ||
    !Array.isArray(value.answer_blocks) ||
    value.answer_blocks.length > 12
  ) {
    throw new Error("Codex returned an invalid answer draft");
  }
  return value as unknown as ResultAnswerDraft;
}

function terminate(
  child: ChildProcessWithoutNullStreams,
  detached: boolean,
): void {
  if (
    detached &&
    child.pid !== undefined &&
    process.platform !== "win32"
  ) {
    try {
      process.kill(-child.pid, "SIGTERM");
      return;
    } catch {
      // Fall through to the direct child handle.
    }
  }
  child.kill("SIGTERM");
}

async function executeBounded(input: {
  command: CodexCommand;
  signal: AbortSignal;
  timeoutMs: number;
  maximumOutputBytes: number;
}): Promise<{ stdout: string; durationMs: number }> {
  const startedAt = Date.now();
  const detached = process.platform === "darwin";
  return new Promise((resolve, reject) => {
    let child: ChildProcessWithoutNullStreams;
    try {
      child = spawn(
        input.command.executable,
        input.command.args,
        {
          env: input.command.env as NodeJS.ProcessEnv,
          shell: false,
          windowsHide: true,
          detached,
          stdio: ["pipe", "pipe", "pipe"],
        },
      );
    } catch {
      reject(new Error("Codex could not start"));
      return;
    }
    child.stdin.end();
    const stdout: Buffer[] = [];
    let bytes = 0;
    let failure:
      | "timeout"
      | "cancelled"
      | "oversize"
      | null = null;
    let settled = false;
    const stop = (
      reason: NonNullable<typeof failure>,
    ): void => {
      if (failure !== null) {
        return;
      }
      failure = reason;
      terminate(child, detached);
      setTimeout(() => {
        if (!settled) {
          child.kill("SIGKILL");
        }
      }, 1_000).unref();
    };
    const timer = setTimeout(() => {
      stop("timeout");
    }, input.timeoutMs);
    const abort = (): void => {
      stop("cancelled");
    };
    if (input.signal.aborted) {
      abort();
    } else {
      input.signal.addEventListener("abort", abort, {
        once: true,
      });
    }
    const accept = (
      chunk: Buffer | string,
      keep: boolean,
    ): void => {
      const buffer = Buffer.isBuffer(chunk)
        ? chunk
        : Buffer.from(chunk);
      bytes += buffer.byteLength;
      if (bytes > input.maximumOutputBytes) {
        stop("oversize");
        return;
      }
      if (keep) {
        stdout.push(buffer);
      }
    };
    child.stdout.on("data", (chunk: Buffer) => {
      accept(chunk, true);
    });
    child.stderr.on("data", (chunk: Buffer) => {
      accept(chunk, false);
    });
    child.once("error", () => {
      settled = true;
      clearTimeout(timer);
      input.signal.removeEventListener("abort", abort);
      reject(new Error("Codex execution failed"));
    });
    child.once("close", (code) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);
      input.signal.removeEventListener("abort", abort);
      if (failure === "timeout") {
        reject(new Error("Codex execution timed out"));
        return;
      }
      if (failure === "cancelled") {
        reject(new Error("Codex execution was cancelled"));
        return;
      }
      if (failure === "oversize") {
        reject(new Error("Codex output limit exceeded"));
        return;
      }
      if (code !== 0) {
        reject(new Error("Codex execution failed"));
        return;
      }
      resolve({
        stdout: Buffer.concat(stdout).toString("utf8"),
        durationMs: Date.now() - startedAt,
      });
    });
  });
}

function countProgressEvents(stdout: string): number {
  const lines = stdout
    .split(/\r?\n/u)
    .filter((line) => line.trim().length > 0);
  for (const line of lines) {
    let value: unknown;
    try {
      value = JSON.parse(line) as unknown;
    } catch {
      throw new Error("Codex progress stream is invalid");
    }
    if (!isRecord(value)) {
      throw new Error("Codex progress stream is invalid");
    }
  }
  return lines.length;
}

export async function runCodexQuestion(input: {
  command: CodexCommand;
  outputPath: string;
  sandbox: "seatbelt_verified" | "poc_explicit";
  signal: AbortSignal;
  timeoutMs?: number;
  maximumOutputBytes?: number;
}): Promise<CodexRunResult> {
  const timeoutMs = input.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const maximumOutputBytes =
    input.maximumOutputBytes ?? DEFAULT_OUTPUT_BYTES;
  if (
    !Number.isSafeInteger(timeoutMs) ||
    timeoutMs < 1 ||
    !Number.isSafeInteger(maximumOutputBytes) ||
    maximumOutputBytes < 1
  ) {
    throw new Error("Codex execution limits are invalid");
  }
  if (
    input.sandbox === "seatbelt_verified" &&
    (process.platform !== "darwin" ||
      input.command.executable !== "/usr/bin/sandbox-exec")
  ) {
    throw new Error("verified Seatbelt mode requires macOS");
  }
  const result = await executeBounded({
    command: input.command,
    signal: input.signal,
    timeoutMs,
    maximumOutputBytes,
  });
  const output = await readFile(input.outputPath);
  if (output.byteLength > maximumOutputBytes) {
    throw new Error("Codex answer output limit exceeded");
  }
  return Object.freeze({
    draft: parseDraft(output.toString("utf8")),
    progressEventCount: countProgressEvents(result.stdout),
    durationMs: result.durationMs,
  });
}
