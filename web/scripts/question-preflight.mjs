#!/usr/bin/env node
import {
  chmod,
  lstat,
  mkdir,
  mkdtemp,
  readFile,
  realpath,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import {
  REQUIRED_FLAGS,
  parseArguments,
  receiptHash,
  seatbeltProfile,
} from "./question-preflight-policy.mjs";
import {
  atomicReceipt,
  hasFileBackedAuth,
  runBounded,
  writePrivate,
} from "./question-preflight-io.mjs";

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exitCode = 2;
}


async function main() {
  if (process.platform !== "darwin") {
    throw new Error(
      "macOS target에서만 질문 강격리 preflight를 실행할 수 있습니다.",
    );
  }
  const options = parseArguments(process.argv.slice(2));
  const codexExecutable = await realpath(options.codex);
  const executableDetails = await lstat(codexExecutable);
  if (
    !executableDetails.isFile() ||
    (executableDetails.mode & 0o111) === 0
  ) {
    throw new Error("Codex executable is not one executable file");
  }
  const sandboxExecutable = "/usr/bin/sandbox-exec";
  const sandboxDetails = await lstat(sandboxExecutable);
  if (!sandboxDetails.isFile()) {
    throw new Error("macOS sandbox-exec is unavailable");
  }

  const [versionResult, helpResult] = await Promise.all([
    runBounded(codexExecutable, ["--version"]),
    runBounded(codexExecutable, ["exec", "--help"]),
  ]);
  const requiredFlagsPresent =
    helpResult.code === 0 &&
    !helpResult.exceeded &&
    REQUIRED_FLAGS.every((flag) =>
      helpResult.stdout.includes(flag),
    );
  const codexVersion =
    versionResult.code === 0
      ? versionResult.stdout.trim().slice(0, 200)
      : "unavailable";

  const requestParent = await mkdtemp(
    path.join(tmpdir(), "trusted-ceo-preflight-"),
  );
  const questionRoot = path.join(requestParent, "input");
  const outputRoot = path.join(requestParent, "output");
  const outsideRoot = await mkdtemp(
    path.join(tmpdir(), "trusted-ceo-outside-"),
  );
  try {
    await Promise.all([
      mkdir(
        path.join(
          questionRoot,
          ".agents",
          "skills",
          "trusted-ceo-agent",
        ),
        { recursive: true, mode: 0o700 },
      ),
      mkdir(outputRoot, { recursive: true, mode: 0o700 }),
    ]);
    await Promise.all([
      chmod(questionRoot, 0o700),
      chmod(outputRoot, 0o700),
      writeFile(
        path.join(questionRoot, "inside-canary.txt"),
        "inside",
        { mode: 0o600 },
      ),
      writeFile(
        path.join(outsideRoot, "outside-canary.txt"),
        "outside",
        { mode: 0o600 },
      ),
      writeFile(
        path.join(
          questionRoot,
          ".agents",
          "skills",
          "trusted-ceo-agent",
          "SKILL.md",
        ),
        [
          "---",
          "name: trusted-ceo-agent",
          "description: Return the governed preflight JSON object.",
          "---",
          "Do not call tools. Return only {\"ok\":true}.",
          "",
        ].join("\n"),
        { mode: 0o600 },
      ),
      writeFile(
        path.join(questionRoot, "result.schema.json"),
        JSON.stringify({
          type: "object",
          additionalProperties: false,
          required: ["ok"],
          properties: { ok: { const: true } },
        }),
        { mode: 0o600 },
      ),
    ]);
    const profilePath = path.join(outputRoot, "profile.sb");
    await writePrivate(
      profilePath,
      seatbeltProfile({
        codexExecutable,
        questionRoot,
        outputRoot,
      }),
    );
    const insideProbe = await runBounded(sandboxExecutable, [
      "-f",
      profilePath,
      "/bin/cat",
      path.join(questionRoot, "inside-canary.txt"),
    ]);
    const outsideProbe = await runBounded(sandboxExecutable, [
      "-f",
      profilePath,
      "/bin/cat",
      path.join(outsideRoot, "outside-canary.txt"),
    ]);
    const outputProbePath = path.join(outputRoot, "write-canary");
    const outputProbe = await runBounded(sandboxExecutable, [
      "-f",
      profilePath,
      "/usr/bin/touch",
      outputProbePath,
    ]);
    const outsideWriteProbe = await runBounded(
      sandboxExecutable,
      [
        "-f",
        profilePath,
        "/usr/bin/touch",
        path.join(outsideRoot, "write-canary"),
      ],
    );

    const answerPath = path.join(outputRoot, "answer.json");
    const minimalEnvironment = {
      HOME: options.codexHome,
      USER: process.env.USER,
      LOGNAME: process.env.LOGNAME,
      PATH: "/usr/bin:/bin:/usr/sbin:/sbin",
      TMPDIR: outputRoot,
      LANG: "ko_KR.UTF-8",
      LC_ALL: "ko_KR.UTF-8",
      CODEX_HOME: options.codexHome,
    };
    const oneShot = requiredFlagsPresent
      ? await runBounded(
          sandboxExecutable,
          [
            "-f",
            profilePath,
            codexExecutable,
            "exec",
            "--json",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--ignore-user-config",
            "--skip-git-repo-check",
            "--output-schema",
            path.join(questionRoot, "result.schema.json"),
            "--output-last-message",
            answerPath,
            "--cd",
            questionRoot,
            "Use $trusted-ceo-agent. Return only the required JSON object.",
          ],
          {
            cwd: questionRoot,
            env: minimalEnvironment,
          },
        )
      : { code: null, stdout: "", exceeded: false, timedOut: false };
    let validAnswer = false;
    try {
      const parsed = JSON.parse(await readFile(answerPath, "utf8"));
      validAnswer =
        parsed !== null &&
        typeof parsed === "object" &&
        !Array.isArray(parsed) &&
        Object.keys(parsed).length === 1 &&
        parsed.ok === true;
    } catch {
      validAnswer = false;
    }
    const authenticationSucceeded =
      oneShot.code === 0 &&
      !oneShot.exceeded &&
      !oneShot.timedOut &&
      validAnswer;
    const connectorPattern =
      /(?:mcp|connector|tool[_ .-]?call)/iu;
    const connectorsUnavailableVerified =
      authenticationSucceeded &&
      !connectorPattern.test(oneShot.stdout);
    const receiptBody = {
      receiptVersion: "1.0.0",
      platform: "darwin",
      codexVersion,
      requiredFlagsPresent,
      ignoreUserConfigVerified:
        requiredFlagsPresent && authenticationSucceeded,
      localSkillOnlyVerified:
        authenticationSucceeded && validAnswer,
      connectorsUnavailableVerified,
      insideReadSucceeded:
        insideProbe.code === 0 &&
        insideProbe.stdout.trim() === "inside",
      outsideReadDenied: outsideProbe.code !== 0,
      outputWriteRestricted:
        outputProbe.code === 0 && outsideWriteProbe.code !== 0,
      authenticationSucceeded,
      authIsolationVerified:
        authenticationSucceeded &&
        !(await hasFileBackedAuth(options.codexHome)),
      completedAt: new Date().toISOString(),
    };
    const receipt = {
      ...receiptBody,
      receiptHash: receiptHash(receiptBody),
    };
    await atomicReceipt(options.output, receipt);
    process.stdout.write(
      `${JSON.stringify({
        receiptWritten: true,
        companyDataEnabled:
          receipt.requiredFlagsPresent &&
          receipt.ignoreUserConfigVerified &&
          receipt.localSkillOnlyVerified &&
          receipt.connectorsUnavailableVerified &&
          receipt.insideReadSucceeded &&
          receipt.outsideReadDenied &&
          receipt.outputWriteRestricted &&
          receipt.authenticationSucceeded &&
          receipt.authIsolationVerified,
        pocQuestionReady:
          receipt.requiredFlagsPresent &&
          receipt.authenticationSucceeded,
      })}\n`,
    );
  } finally {
    await Promise.all([
      rm(requestParent, { recursive: true, force: true }),
      rm(outsideRoot, { recursive: true, force: true }),
    ]);
  }
}

main().catch((error) => {
  fail(
    error instanceof Error
      ? error.message
      : "질문 preflight에 실패했습니다.",
  );
});
