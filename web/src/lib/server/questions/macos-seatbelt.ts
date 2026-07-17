import type {
  CodexCommand,
} from "@/lib/server/questions/codex-command";

type SeatbeltRoots = Readonly<{
  codexExecutable: string;
  questionRoot: string;
  outputRoot: string;
  temporaryRoot: string;
}>;

function assertSafeAbsolute(
  value: string,
  label: string,
): void {
  if (
    !value.startsWith("/") ||
    value.includes('"') ||
    value.includes("\\") ||
    value.includes("\n") ||
    value.includes("\r") ||
    value.includes("\0")
  ) {
    throw new Error(`${label} must be a safe absolute macOS path`);
  }
}

function literal(value: string): string {
  return `(literal "${value}")`;
}

function subpath(value: string): string {
  return `(subpath "${value}")`;
}

export function buildSeatbeltProfile(
  input: SeatbeltRoots,
): string {
  assertSafeAbsolute(
    input.codexExecutable,
    "Codex executable",
  );
  assertSafeAbsolute(input.questionRoot, "question root");
  assertSafeAbsolute(input.outputRoot, "output root");
  assertSafeAbsolute(input.temporaryRoot, "temporary root");
  return [
    "(version 1)",
    "(deny default)",
    "(allow process-exec",
    `  ${literal(input.codexExecutable)}`,
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
    `  ${literal(input.codexExecutable)}`,
    `  ${subpath(input.questionRoot)}`,
    '  (subpath "/System")',
    '  (subpath "/usr/lib")',
    '  (subpath "/Library/Apple/System/Library"))',
    "(allow file-write*",
    `  ${subpath(input.outputRoot)}`,
    `  ${subpath(input.temporaryRoot)})`,
    "(deny file-write*",
    `  ${subpath(input.questionRoot)})`,
    "",
  ].join("\n");
}

export function wrapCodexWithSeatbelt(input: {
  profilePath: string;
  command: CodexCommand;
}): CodexCommand {
  assertSafeAbsolute(input.profilePath, "Seatbelt profile");
  assertSafeAbsolute(
    input.command.executable,
    "Codex executable",
  );
  if (
    input.command.args.some(
      (argument) =>
        typeof argument !== "string" ||
        argument.includes("\0"),
    )
  ) {
    throw new Error("Codex arguments are invalid");
  }
  return Object.freeze({
    executable: "/usr/bin/sandbox-exec",
    args: [
      "-f",
      input.profilePath,
      input.command.executable,
      ...input.command.args,
    ],
    env: input.command.env,
  });
}
