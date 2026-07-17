// @vitest-environment node
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  buildPluginCliCommand,
  createPluginCliRunner,
} from "@/lib/server/questions/plugin-cli";

const fixture = fileURLToPath(
  new URL("./fixtures/fake-plugin-cli.mjs", import.meta.url),
);

describe("question plugin CLI", () => {
  it("builds the frozen offline launcher without a shell", () => {
    expect(
      buildPluginCliCommand(["prepare-result-question"]),
    ).toEqual({
      executable: "uv",
      args: [
        "run",
        "--project",
        "plugin/trusted-ceo-agent",
        "--frozen",
        "--offline",
        "--no-sync",
        "python",
        "plugin/trusted-ceo-agent/scripts/trusted_ceo_agent.py",
        "prepare-result-question",
      ],
      shell: false,
    });
  });

  it("accepts exactly one bounded plugin response object", async () => {
    const runner = createPluginCliRunner({
      executable: process.execPath,
      prefixArgs: [fixture],
      repositoryRoot: path.resolve("."),
      environment: {
        ...process.env,
        FAKE_PLUGIN_MODE: "success",
      },
    });
    await expect(
      runner<{ marker: string }>(["prepare-result-question"]),
    ).resolves.toMatchObject({
      ok: true,
      code: 0,
      command: "prepare-result-question",
      data: { marker: "validated" },
    });
  });

  it("rejects oversized output and redacts paths and question text", async () => {
    const root = path.resolve(".");
    const oversized = createPluginCliRunner({
      executable: process.execPath,
      prefixArgs: [fixture],
      repositoryRoot: root,
      environment: {
        ...process.env,
        FAKE_PLUGIN_MODE: "oversize",
      },
    });
    await expect(
      oversized(["prepare-result-question"], {
        maximumBytes: 1024,
      }),
    ).rejects.toThrow("output limit");

    const failed = createPluginCliRunner({
      executable: process.execPath,
      prefixArgs: [fixture],
      repositoryRoot: root,
      environment: {
        ...process.env,
        FAKE_PLUGIN_MODE: "stderr",
      },
    });
    let message = "";
    try {
      await failed(["prepare-result-question"], {
        redactions: ["raw-secret-question"],
      });
    } catch (error) {
      message =
        error instanceof Error ? error.message : String(error);
    }
    expect(message).not.toContain(root);
    expect(message).not.toContain("raw-secret-question");
  });
});
