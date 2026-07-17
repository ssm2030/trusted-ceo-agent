// @vitest-environment node
import {
  appendFile,
  mkdtemp,
  mkdir,
  readFile,
  readdir,
  stat,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  ConversationStore,
  type ConversationRecord,
} from "@/lib/server/questions/conversation-store";
import type { ConversationKey } from "@/lib/server/questions/types";

const roots: string[] = [];

async function temporaryRoot(): Promise<string> {
  const root = await mkdtemp(
    path.join(tmpdir(), "trusted-ceo-conversation-test-"),
  );
  roots.push(root);
  return path.join(root, "var", "conversations");
}

const key: ConversationKey = {
  runId: "run_20260717T010203Z_0123456789abcdef",
  revision: 3,
  scopeKind: "evidence",
  scopeInstanceId: "evidence_link_main",
};

function questionRecord(
  recordId: string,
  createdAt = "2026-07-17T01:02:03.000Z",
): ConversationRecord {
  return {
    recordVersion: "1.0.0",
    recordId,
    type: "question_submitted",
    key,
    question: "이 근거가 결론을 어떻게 뒷받침하나요?",
    createdAt,
  };
}

afterEach(async () => {
  const { rm } = await import("node:fs/promises");
  await Promise.all(
    roots.splice(0).map((root) =>
      rm(root, { recursive: true, force: true }),
    ),
  );
});

describe("ConversationStore", () => {
  it("appends and reloads records in order while hashing run paths", async () => {
    const root = await temporaryRoot();
    const store = new ConversationStore(root);
    await store.append(questionRecord("record-1"));
    await store.append(questionRecord("record-2"));

    expect(
      (await store.read(key)).map((record) => record.recordId),
    ).toEqual(["record-1", "record-2"]);
    const runDirectories = await readdir(root);
    expect(runDirectories).toHaveLength(1);
    expect(runDirectories[0]).toMatch(/^[0-9a-f]{64}$/);
    expect(runDirectories[0]).not.toContain(key.runId);
  });

  it("rotates per run at the configured byte threshold", async () => {
    const root = await temporaryRoot();
    const store = new ConversationStore(root, {
      rotationBytes: 420,
    });
    await store.append(questionRecord("record-1"));
    await store.append(questionRecord("record-2"));

    const [runDirectory] = await readdir(root);
    const segments = (await readdir(path.join(root, runDirectory))).filter(
      (name) => name.endsWith(".jsonl"),
    );
    expect(segments).toEqual(["000001.jsonl", "000002.jsonl"]);
  });

  it("uses private POSIX directory and file modes", async () => {
    const root = await temporaryRoot();
    const store = new ConversationStore(root);
    await store.append(questionRecord("record-1"));

    if (process.platform !== "win32") {
      const [runDirectory] = await readdir(root);
      const filePath = path.join(root, runDirectory, "000001.jsonl");
      expect((await stat(root)).mode & 0o777).toBe(0o700);
      expect(
        (await stat(path.join(root, runDirectory))).mode & 0o777,
      ).toBe(0o700);
      expect((await stat(filePath)).mode & 0o777).toBe(0o600);
    }
  });

  it("recovers prior records and quarantines a malformed final line", async () => {
    const root = await temporaryRoot();
    const store = new ConversationStore(root);
    await store.append(questionRecord("record-1"));
    const [runDirectory] = await readdir(root);
    const runRoot = path.join(root, runDirectory);
    await appendFile(
      path.join(runRoot, "000001.jsonl"),
      '{"recordVersion":',
      "utf8",
    );

    expect(
      (await store.read(key)).map((record) => record.recordId),
    ).toEqual(["record-1"]);
    expect(
      (await readdir(runRoot)).some((name) =>
        name.startsWith("000001.quarantine-"),
      ),
    ).toBe(true);
  });

  it("fails closed for a malformed middle line", async () => {
    const root = await temporaryRoot();
    const store = new ConversationStore(root);
    await store.append(questionRecord("record-1"));
    const [runDirectory] = await readdir(root);
    const segment = path.join(root, runDirectory, "000001.jsonl");
    const valid = await readFile(segment, "utf8");
    await writeFile(
      segment,
      `${valid}{"broken":\n${JSON.stringify(questionRecord("record-2"))}\n`,
      "utf8",
    );

    await expect(store.read(key)).rejects.toThrow(
      "conversation segment is corrupt",
    );
  });

  it("prunes expired segments and deletes only the conversation root", async () => {
    const root = await temporaryRoot();
    const runtimeRoot = path.dirname(path.dirname(root));
    const store = new ConversationStore(root);
    await store.append(
      questionRecord("old", "2026-05-01T00:00:00.000Z"),
    );
    await store.prune(new Date("2026-07-17T00:00:00.000Z"));
    expect(await store.read(key)).toEqual([]);

    await store.append(questionRecord("current"));
    await mkdir(path.join(runtimeRoot, "bundles"), { recursive: true });
    await writeFile(
      path.join(runtimeRoot, "bundles", "current.json"),
      "{}",
    );
    await store.deleteAll();
    await expect(stat(root)).rejects.toMatchObject({ code: "ENOENT" });
    expect(
      await readFile(
        path.join(runtimeRoot, "bundles", "current.json"),
        "utf8",
      ),
    ).toBe("{}");
  });
});
