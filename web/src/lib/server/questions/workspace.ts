import {
  chmod,
  lstat,
  mkdir,
  mkdtemp,
  open,
  readFile,
  rm,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import type { ResultQuestionJob } from "@/lib/server/questions/types";

export interface QuestionWorkspace {
  root: string;
  jobPath: string;
  schemaPath: string;
  outputPath: string;
  temporaryParent: string;
  cleanup(): Promise<void>;
}

export type QuestionWorkspaceOptions = Readonly<{
  skillPath?: string;
  schemaPath?: string;
  temporaryParent?: string;
}>;

function repositoryRootCandidates(): string[] {
  return [
    process.cwd(),
    path.resolve(process.cwd(), ".."),
    path.resolve(__dirname, "../../../../.."),
  ];
}

async function firstRegularFile(
  candidates: readonly string[],
  label: string,
): Promise<string> {
  for (const candidate of candidates) {
    try {
      const details = await lstat(candidate);
      if (details.isFile() && !details.isSymbolicLink()) {
        return candidate;
      }
    } catch {
      // Continue through fixed repository-root candidates.
    }
  }
  throw new Error(`${label} source must be a regular file`);
}

async function resolveSkillPath(
  supplied?: string,
): Promise<string> {
  if (supplied !== undefined) {
    return firstRegularFile([supplied], "question Skill");
  }
  return firstRegularFile(
    repositoryRootCandidates().map((root) =>
      path.join(
        root,
        "plugin",
        "trusted-ceo-agent",
        "templates",
        "result-question",
        "SKILL.md",
      ),
    ),
    "question Skill",
  );
}

async function resolveSchemaPath(
  supplied?: string,
): Promise<string> {
  if (supplied !== undefined) {
    return firstRegularFile([supplied], "answer schema");
  }
  return firstRegularFile(
    repositoryRootCandidates().map((root) =>
      path.join(
        root,
        "contracts",
        "web-report",
        "v1",
        "result-answer-draft.schema.json",
      ),
    ),
    "answer schema",
  );
}

async function ensurePrivateDirectory(
  directory: string,
): Promise<void> {
  await mkdir(directory, { recursive: true, mode: 0o700 });
  if (process.platform !== "win32") {
    await chmod(directory, 0o700);
  }
}

async function writePrivateFile(
  filePath: string,
  contents: string | Uint8Array,
): Promise<void> {
  const handle = await open(filePath, "wx", 0o600);
  try {
    if (process.platform !== "win32") {
      await handle.chmod(0o600);
    }
    await handle.writeFile(contents);
    await handle.sync();
  } finally {
    await handle.close();
  }
}

function ensureInside(root: string, candidate: string): void {
  const relative = path.relative(root, candidate);
  if (
    relative === ".." ||
    relative.startsWith(`..${path.sep}`) ||
    path.isAbsolute(relative)
  ) {
    throw new Error("question workspace path escaped its root");
  }
}

export async function createQuestionWorkspace(
  job: ResultQuestionJob,
  options: QuestionWorkspaceOptions = {},
): Promise<QuestionWorkspace> {
  const temporaryParent = path.resolve(
    options.temporaryParent ?? tmpdir(),
  );
  await ensurePrivateDirectory(temporaryParent);
  const [skillPath, answerSchemaPath] = await Promise.all([
    resolveSkillPath(options.skillPath),
    resolveSchemaPath(options.schemaPath),
  ]);
  const [skillBytes, schemaBytes] = await Promise.all([
    readFile(skillPath),
    readFile(answerSchemaPath),
  ]);

  const inputRoot = await mkdtemp(
    path.join(temporaryParent, "trusted-ceo-question-"),
  );
  const outputRoot = await mkdtemp(
    path.join(temporaryParent, "trusted-ceo-question-output-"),
  );
  let complete = false;
  try {
    if (process.platform !== "win32") {
      await Promise.all([
        chmod(inputRoot, 0o700),
        chmod(outputRoot, 0o700),
      ]);
    }
    const skillRoot = path.join(
      inputRoot,
      ".agents",
      "skills",
      "trusted-ceo-agent",
    );
    await ensurePrivateDirectory(skillRoot);
    const jobPath = path.join(inputRoot, "question-job.json");
    const schemaPath = path.join(
      inputRoot,
      "result-answer-draft.schema.json",
    );
    const copiedSkillPath = path.join(skillRoot, "SKILL.md");
    const outputPath = path.join(outputRoot, "answer-draft.json");
    for (const candidate of [
      jobPath,
      schemaPath,
      copiedSkillPath,
    ]) {
      ensureInside(inputRoot, candidate);
    }
    ensureInside(outputRoot, outputPath);
    await Promise.all([
      writePrivateFile(
        jobPath,
        `${JSON.stringify(job)}\n`,
      ),
      writePrivateFile(schemaPath, schemaBytes),
      writePrivateFile(copiedSkillPath, skillBytes),
    ]);

    const cleanup = async (): Promise<void> => {
      await Promise.all([
        rm(inputRoot, { recursive: true, force: true }),
        rm(outputRoot, { recursive: true, force: true }),
      ]);
    };
    complete = true;
    return Object.freeze({
      root: inputRoot,
      jobPath,
      schemaPath,
      outputPath,
      temporaryParent,
      cleanup,
    });
  } finally {
    if (!complete) {
      await Promise.all([
        rm(inputRoot, { recursive: true, force: true }),
        rm(outputRoot, { recursive: true, force: true }),
      ]);
    }
  }
}
