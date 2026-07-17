// @vitest-environment node
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

import type { CodexCommand } from "@/lib/server/questions/codex-command";
import { runCodexQuestion } from "@/lib/server/questions/codex-runner";

const fixture = fileURLToPath(
  new URL("./fixtures/fake-codex.mjs", import.meta.url),
);
const roots: string[] = [];

afterEach(async () => {
  await Promise.all(
    roots.splice(0).map((root) =>
      rm(root, { recursive: true, force: true }),
    ),
  );
});

async function command(
  mode: string,
): Promise<{ command: CodexCommand; outputPath: string }> {
  const root = await mkdtemp(
    path.join(tmpdir(), "trusted-ceo-codex-test-"),
  );
  roots.push(root);
  const outputPath = path.join(root, "answer.json");
  return {
    outputPath,
    command: {
      executable: process.execPath,
      args: [
        fixture,
        "--output-last-message",
        outputPath,
      ],
      env: {
        ...process.env,
        FAKE_CODEX_MODE: mode,
      },
    },
  };
}

describe("runCodexQuestion", () => {
  it.each(["success", "stderr-warning"])(
    "returns only the final draft in %s mode",
    async (mode) => {
      const input = await command(mode);
      const result = await runCodexQuestion({
        command: input.command,
        outputPath: input.outputPath,
        sandbox: "poc_explicit",
        signal: new AbortController().signal,
      });
      expect(result.draft).toMatchObject({
        draft_version: "1.0.0",
        job_id: "job_123",
        answer_blocks: [],
      });
      expect(result.progressEventCount).toBe(1);
    },
  );

  it("enforces timeout and combined output limits", async () => {
    const timed = await command("timeout");
    await expect(
      runCodexQuestion({
        command: timed.command,
        outputPath: timed.outputPath,
        sandbox: "poc_explicit",
        signal: new AbortController().signal,
        timeoutMs: 50,
      }),
    ).rejects.toThrow("timed out");

    const oversized = await command("oversize");
    await expect(
      runCodexQuestion({
        command: oversized.command,
        outputPath: oversized.outputPath,
        sandbox: "poc_explicit",
        signal: new AbortController().signal,
        maximumOutputBytes: 1024,
      }),
    ).rejects.toThrow("output limit");
  });

  it("rejects malformed final model JSON", async () => {
    const input = await command("invalid-json");
    await expect(
      runCodexQuestion({
        command: input.command,
        outputPath: input.outputPath,
        sandbox: "poc_explicit",
        signal: new AbortController().signal,
      }),
    ).rejects.toThrow("invalid final JSON");
  });
});
