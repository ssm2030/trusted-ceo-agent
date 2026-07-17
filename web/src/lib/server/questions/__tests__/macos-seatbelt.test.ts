// @vitest-environment node
import { describe, expect, it } from "vitest";

import {
  buildSeatbeltProfile,
  wrapCodexWithSeatbelt,
} from "@/lib/server/questions/macos-seatbelt";

describe("macOS Seatbelt command", () => {
  it("starts deny-by-default and grants only governed roots", () => {
    const executable = "/Applications/Codex.app/Contents/MacOS/codex";
    const questionRoot = "/private/tmp/question/input";
    const outputRoot = "/private/tmp/question/output";
    const profile = buildSeatbeltProfile({
      codexExecutable: executable,
      questionRoot,
      outputRoot,
      temporaryRoot: "/private/tmp/question",
    });
    expect(profile.startsWith("(version 1)\n(deny default)")).toBe(
      true,
    );
    expect(profile).toContain(`(literal "${executable}")`);
    expect(profile).toContain(`(subpath "${questionRoot}")`);
    expect(profile).toContain(`(subpath "${outputRoot}")`);
    expect(profile).not.toContain("(subpath \"/Users\")");
    expect(profile).not.toContain("(allow file-read*)");
  });

  it("wraps the fixed executable as an argument array", () => {
    const command = wrapCodexWithSeatbelt({
      profilePath: "/private/tmp/question/profile.sb",
      command: {
        executable: "/Applications/Codex.app/Contents/MacOS/codex",
        args: ["exec", "--json"],
        env: { HOME: "/private/tmp/codex-home" },
      },
    });
    expect(command).toEqual({
      executable: "/usr/bin/sandbox-exec",
      args: [
        "-f",
        "/private/tmp/question/profile.sb",
        "/Applications/Codex.app/Contents/MacOS/codex",
        "exec",
        "--json",
      ],
      env: { HOME: "/private/tmp/codex-home" },
    });
  });

  it("rejects non-absolute and quote-bearing policy paths", () => {
    expect(() =>
      buildSeatbeltProfile({
        codexExecutable: "codex",
        questionRoot: "/private/tmp/question/input",
        outputRoot: "/private/tmp/question/output",
        temporaryRoot: "/private/tmp/question",
      }),
    ).toThrow("absolute");
    expect(() =>
      wrapCodexWithSeatbelt({
        profilePath: '/private/tmp/bad"profile',
        command: {
          executable: "/usr/bin/codex",
          args: [],
          env: {},
        },
      }),
    ).toThrow("safe absolute");
  });
});
