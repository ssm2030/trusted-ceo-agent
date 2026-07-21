import { createHash } from "node:crypto";
import path from "node:path";

export const REQUIRED_FLAGS = [
  "--json",
  "--ephemeral",
  "--sandbox",
  "--ignore-user-config",
  "--skip-git-repo-check",
  "--output-schema",
  "--output-last-message",
  "--cd",
];
export const MAX_OUTPUT_BYTES = 2 * 1024 * 1024;
export const TIMEOUT_MS = 90_000;


export function parseArguments(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    const name = argv[index];
    const value = argv[index + 1];
    if (
      !["--codex", "--codex-home", "--output"].includes(name) ||
      typeof value !== "string"
    ) {
      throw new Error(
        "usage: question-preflight.mjs --codex ABSOLUTE_PATH --codex-home ABSOLUTE_PATH --output ABSOLUTE_PATH",
      );
    }
    result[name.slice(2)] = value;
  }
  if (
    typeof result.codex !== "string" ||
    typeof result["codex-home"] !== "string" ||
    typeof result.output !== "string" ||
    !path.isAbsolute(result.codex) ||
    !path.isAbsolute(result["codex-home"]) ||
    !path.isAbsolute(result.output)
  ) {
    throw new Error("all preflight paths must be absolute");
  }
  return {
    codex: result.codex,
    codexHome: result["codex-home"],
    output: result.output,
  };
}

export function canonicalize(value) {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonicalize).join(",")}]`;
  }
  return `{${Object.keys(value)
    .sort()
    .map(
      (key) =>
        `${JSON.stringify(key)}:${canonicalize(value[key])}`,
    )
    .join(",")}}`;
}

export function receiptHash(receipt) {
  return createHash("sha256")
    .update(canonicalize(receipt), "utf8")
    .digest("hex");
}


export function seatbeltProfile({
  codexExecutable,
  questionRoot,
  outputRoot,
}) {
  const literal = (value) => `(literal "${value}")`;
  const subpath = (value) => `(subpath "${value}")`;
  return [
    "(version 1)",
    "(deny default)",
    "(allow process-exec",
    `  ${literal(codexExecutable)}`,
    '  (subpath "/usr/bin")',
    '  (subpath "/bin"))',
    "(allow process-fork)",
    "(allow signal (target self))",
    "(allow sysctl-read)",
    "(allow network-outbound)",
    "(allow mach-lookup",
    '  (global-name "com.apple.SecurityServer")',
    '  (global-name "com.apple.system.logger"))',
    "(allow file-read*",
    `  ${literal(codexExecutable)}`,
    `  ${subpath(questionRoot)}`,
    '  (subpath "/System")',
    '  (subpath "/usr/lib")',
    '  (subpath "/Library/Apple/System/Library"))',
    "(allow file-write*",
    `  ${subpath(outputRoot)})`,
    "(deny file-write*",
    `  ${subpath(questionRoot)})`,
    "",
  ].join("\n");
}
