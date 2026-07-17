// @vitest-environment node
import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  RESULT_QUESTION_PROMPT,
  buildCodexCommand,
} from "@/lib/server/questions/codex-command";

describe("buildCodexCommand", () => {
  it("uses the exact one-shot arguments and a minimal environment", () => {
    const root = path.resolve("C:/question-root");
    const outputPath = path.resolve("C:/question-output/answer.json");
    const command = buildCodexCommand({
      codexExecutable: path.resolve("C:/bin/codex.exe"),
      codexHome: path.resolve("C:/codex-home"),
      workspace: {
        root,
        jobPath: path.join(root, "question-job.json"),
        schemaPath: path.join(
          root,
          "result-answer-draft.schema.json",
        ),
        outputPath,
        temporaryParent: path.dirname(root),
        cleanup: async () => undefined,
      },
      inheritedEnvironment: {
        OPENAI_API_KEY: "must-not-leak",
        HTTP_PROXY: "must-not-leak",
        HOME: "must-not-inherit",
        USER: "tester",
      },
      platform: "darwin",
    });

    expect(command).toEqual({
      executable: path.resolve("C:/bin/codex.exe"),
      args: [
        "exec",
        "--json",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--ignore-user-config",
        "--skip-git-repo-check",
        "--output-schema",
        path.join(root, "result-answer-draft.schema.json"),
        "--output-last-message",
        outputPath,
        "--cd",
        root,
        RESULT_QUESTION_PROMPT,
      ],
      env: expect.objectContaining({
        USER: "tester",
        PATH: "/usr/bin:/bin:/usr/sbin:/sbin",
        LANG: "ko_KR.UTF-8",
        LC_ALL: "ko_KR.UTF-8",
        CODEX_HOME: path.resolve("C:/codex-home"),
      }),
    });
    expect(command.env).not.toHaveProperty("OPENAI_API_KEY");
    expect(command.env).not.toHaveProperty("HTTP_PROXY");
    expect(command.env).not.toHaveProperty("HTTPS_PROXY");
  });
});
