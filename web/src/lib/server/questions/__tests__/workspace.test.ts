// @vitest-environment node
import {
  lstat,
  mkdtemp,
  readFile,
  readdir,
  rm,
  stat,
  symlink,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  createQuestionWorkspace,
  type QuestionWorkspace,
} from "@/lib/server/questions/workspace";
import type { ResultQuestionJob } from "@/lib/server/questions/types";

const roots: string[] = [];
const workspaces: QuestionWorkspace[] = [];

async function fixtureFiles(): Promise<{
  root: string;
  skillPath: string;
  schemaPath: string;
}> {
  const root = await mkdtemp(
    path.join(tmpdir(), "trusted-ceo-workspace-fixture-"),
  );
  roots.push(root);
  const skillPath = path.join(root, "SKILL.md");
  const schemaPath = path.join(root, "schema.json");
  await writeFile(skillPath, "읽기 전용 질문 스킬", "utf8");
  await writeFile(
    schemaPath,
    JSON.stringify({ type: "object" }),
    "utf8",
  );
  return { root, skillPath, schemaPath };
}

const job = {
  job_version: "1.0.0",
  job_id: "job_123",
} as ResultQuestionJob;

afterEach(async () => {
  await Promise.all(
    workspaces.splice(0).map((workspace) => workspace.cleanup()),
  );
  await Promise.all(
    roots.splice(0).map((root) =>
      rm(root, { recursive: true, force: true }),
    ),
  );
});

async function listTree(root: string): Promise<string[]> {
  const result: string[] = [];
  async function walk(directory: string): Promise<void> {
    for (const name of (await readdir(directory)).sort()) {
      const target = path.join(directory, name);
      const details = await lstat(target);
      if (details.isDirectory()) {
        await walk(target);
      } else {
        result.push(
          path.relative(root, target).replaceAll(path.sep, "/"),
        );
      }
    }
  }
  await walk(root);
  return result;
}

describe("createQuestionWorkspace", () => {
  it("creates only the governed three-file input tree", async () => {
    const fixture = await fixtureFiles();
    const workspace = await createQuestionWorkspace(job, {
      skillPath: fixture.skillPath,
      schemaPath: fixture.schemaPath,
      temporaryParent: fixture.root,
    });
    workspaces.push(workspace);

    expect(await listTree(workspace.root)).toEqual([
      ".agents/skills/trusted-ceo-agent/SKILL.md",
      "question-job.json",
      "result-answer-draft.schema.json",
    ]);
    expect(
      JSON.parse(await readFile(workspace.jobPath, "utf8")),
    ).toEqual(job);
    expect(
      path.relative(workspace.root, workspace.outputPath).startsWith(
        "..",
      ),
    ).toBe(true);
    if (process.platform !== "win32") {
      expect((await stat(workspace.root)).mode & 0o777).toBe(0o700);
      expect((await stat(workspace.jobPath)).mode & 0o777).toBe(
        0o600,
      );
    }
  });

  it("rejects a symlinked source asset", async () => {
    const fixture = await fixtureFiles();
    const linkedSkill = path.join(fixture.root, "linked-skill.md");
    try {
      await symlink(fixture.skillPath, linkedSkill, "file");
    } catch (error) {
      if (
        process.platform === "win32" &&
        typeof error === "object" &&
        error !== null &&
        "code" in error &&
        error.code === "EPERM"
      ) {
        return;
      }
      throw error;
    }

    await expect(
      createQuestionWorkspace(job, {
        skillPath: linkedSkill,
        schemaPath: fixture.schemaPath,
        temporaryParent: fixture.root,
      }),
    ).rejects.toThrow("regular file");
  });
});
