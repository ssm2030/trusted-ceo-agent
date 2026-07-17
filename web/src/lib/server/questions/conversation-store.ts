import { createHash, randomUUID } from "node:crypto";
import {
  chmod,
  mkdir,
  open,
  readFile,
  readdir,
  rename,
  rm,
  stat,
} from "node:fs/promises";
import path from "node:path";

import type {
  ConversationKey,
  ResultAnswer,
} from "@/lib/server/questions/types";
import {
  SCOPE_KINDS,
  serializeConversationKey,
} from "@/lib/server/questions/types";

const DEFAULT_ROTATION_BYTES = 10 * 1024 * 1024;
const DEFAULT_RETENTION_MS = 30 * 24 * 60 * 60 * 1000;
const SEGMENT_PATTERN = /^[0-9]{6}\.jsonl$/;
const LOCK_RETRY_LIMIT = 200;
const LOCK_RETRY_MS = 10;

export type ConversationRecord =
  | {
      recordVersion: "1.0.0";
      recordId: string;
      type: "question_submitted";
      key: ConversationKey;
      question: string;
      createdAt: string;
    }
  | {
      recordVersion: "1.0.0";
      recordId: string;
      type: "answer_verified";
      key: ConversationKey;
      requestId: string;
      answer: ResultAnswer;
      createdAt: string;
    }
  | {
      recordVersion: "1.0.0";
      recordId: string;
      type: "question_failed";
      key: ConversationKey;
      requestId: string;
      errorCode: string;
      createdAt: string;
    };

export type ConversationStoreOptions = Readonly<{
  rotationBytes?: number;
  retentionMs?: number;
}>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  );
}

function isConversationKey(value: unknown): value is ConversationKey {
  return (
    isRecord(value) &&
    typeof value.runId === "string" &&
    Number.isInteger(value.revision) &&
    typeof value.scopeKind === "string" &&
    SCOPE_KINDS.includes(
      value.scopeKind as (typeof SCOPE_KINDS)[number],
    ) &&
    typeof value.scopeInstanceId === "string"
  );
}

function isIsoTimestamp(value: unknown): value is string {
  return (
    typeof value === "string" &&
    Number.isFinite(Date.parse(value))
  );
}

function isConversationRecord(
  value: unknown,
): value is ConversationRecord {
  if (
    !isRecord(value) ||
    value.recordVersion !== "1.0.0" ||
    typeof value.recordId !== "string" ||
    !isConversationKey(value.key) ||
    !isIsoTimestamp(value.createdAt)
  ) {
    return false;
  }
  if (value.type === "question_submitted") {
    return (
      Object.keys(value).length === 6 &&
      typeof value.question === "string"
    );
  }
  if (value.type === "answer_verified") {
    return (
      Object.keys(value).length === 7 &&
      typeof value.requestId === "string" &&
      isRecord(value.answer)
    );
  }
  if (value.type === "question_failed") {
    return (
      Object.keys(value).length === 7 &&
      typeof value.requestId === "string" &&
      typeof value.errorCode === "string"
    );
  }
  return false;
}

function errorCode(error: unknown): string | undefined {
  return isRecord(error) && typeof error.code === "string"
    ? error.code
    : undefined;
}

async function ensurePrivateDirectory(
  directory: string,
): Promise<void> {
  await mkdir(directory, {
    recursive: true,
    mode: 0o700,
  });
  if (process.platform !== "win32") {
    await chmod(directory, 0o700);
  }
}

async function writeSynced(
  filePath: string,
  contents: string,
  flag: "a" | "wx",
): Promise<void> {
  const handle = await open(filePath, flag, 0o600);
  try {
    if (process.platform !== "win32") {
      await handle.chmod(0o600);
    }
    await handle.writeFile(contents, "utf8");
    await handle.sync();
  } finally {
    await handle.close();
  }
}

async function atomicRewrite(
  filePath: string,
  contents: string,
): Promise<void> {
  const temporaryPath = `${filePath}.${randomUUID()}.tmp`;
  try {
    await writeSynced(temporaryPath, contents, "wx");
    await rename(temporaryPath, filePath);
  } finally {
    await rm(temporaryPath, { force: true }).catch(() => undefined);
  }
}

function runDirectoryName(runId: string): string {
  return createHash("sha256").update(runId, "utf8").digest("hex");
}

async function segmentNames(runRoot: string): Promise<string[]> {
  try {
    return (await readdir(runRoot))
      .filter((name) => SEGMENT_PATTERN.test(name))
      .sort();
  } catch (error) {
    if (errorCode(error) === "ENOENT") {
      return [];
    }
    throw error;
  }
}

function nextSegmentName(previous?: string): string {
  const next =
    previous === undefined
      ? 1
      : Number(previous.slice(0, 6)) + 1;
  if (!Number.isSafeInteger(next) || next > 999_999) {
    throw new Error("conversation segment limit reached");
  }
  return `${String(next).padStart(6, "0")}.jsonl`;
}

async function acquireAppendLock(
  runRoot: string,
): Promise<() => Promise<void>> {
  const lockPath = path.join(runRoot, ".append.lock");
  for (let attempt = 0; attempt < LOCK_RETRY_LIMIT; attempt += 1) {
    try {
      const handle = await open(lockPath, "wx", 0o600);
      await handle.writeFile(
        JSON.stringify({
          pid: process.pid,
          createdAt: new Date().toISOString(),
        }),
        "utf8",
      );
      await handle.sync();
      await handle.close();
      return async () => {
        await rm(lockPath, { force: true });
      };
    } catch (error) {
      if (errorCode(error) !== "EEXIST") {
        throw error;
      }
      await new Promise<void>((resolve) => {
        setTimeout(resolve, LOCK_RETRY_MS);
      });
    }
  }
  throw new Error("conversation store is busy");
}

function parseLine(line: string): ConversationRecord {
  let value: unknown;
  try {
    value = JSON.parse(line) as unknown;
  } catch {
    throw new Error("conversation segment is corrupt");
  }
  if (!isConversationRecord(value)) {
    throw new Error("conversation segment is corrupt");
  }
  return value;
}

export class ConversationStore {
  private readonly rotationBytes: number;
  private readonly retentionMs: number;
  private appendQueue: Promise<void> = Promise.resolve();

  constructor(
    private readonly root: string,
    options: ConversationStoreOptions = {},
  ) {
    if (!path.isAbsolute(root)) {
      throw new Error("conversation root must be absolute");
    }
    this.rotationBytes =
      options.rotationBytes ?? DEFAULT_ROTATION_BYTES;
    this.retentionMs = options.retentionMs ?? DEFAULT_RETENTION_MS;
    if (
      !Number.isSafeInteger(this.rotationBytes) ||
      this.rotationBytes < 1 ||
      !Number.isSafeInteger(this.retentionMs) ||
      this.retentionMs < 1
    ) {
      throw new Error("conversation store limits are invalid");
    }
  }

  async append(record: ConversationRecord): Promise<void> {
    if (!isConversationRecord(record)) {
      throw new Error("conversation record is invalid");
    }
    const operation = this.appendQueue.then(async () => {
      await ensurePrivateDirectory(this.root);
      const runRoot = path.join(
        this.root,
        runDirectoryName(record.key.runId),
      );
      await ensurePrivateDirectory(runRoot);
      const release = await acquireAppendLock(runRoot);
      try {
        const line = `${JSON.stringify(record)}\n`;
        const names = await segmentNames(runRoot);
        let segmentName = names.at(-1);
        if (segmentName === undefined) {
          segmentName = nextSegmentName();
        } else {
          const details = await stat(
            path.join(runRoot, segmentName),
          );
          if (
            details.size > 0 &&
            details.size + Buffer.byteLength(line, "utf8") >
              this.rotationBytes
          ) {
            segmentName = nextSegmentName(segmentName);
          }
        }
        await writeSynced(
          path.join(runRoot, segmentName),
          line,
          "a",
        );
      } finally {
        await release();
      }
    });
    this.appendQueue = operation.then(
      () => undefined,
      () => undefined,
    );
    return operation;
  }

  private async readSegment(
    filePath: string,
    mayRecoverTail: boolean,
  ): Promise<ConversationRecord[]> {
    const serialized = await readFile(filePath, "utf8");
    const lines = serialized.split("\n");
    if (lines.at(-1) === "") {
      lines.pop();
    }
    const records: ConversationRecord[] = [];
    for (let index = 0; index < lines.length; index += 1) {
      try {
        records.push(parseLine(lines[index]));
      } catch (error) {
        const isRecoverableTail =
          mayRecoverTail && index === lines.length - 1;
        if (!isRecoverableTail) {
          throw error;
        }
        const extension = path.extname(filePath);
        const base = filePath.slice(0, -extension.length);
        const quarantine = `${base}.quarantine-${randomUUID()}${extension}`;
        await rename(filePath, quarantine);
        await writeSynced(
          filePath,
          records.length === 0
            ? ""
            : `${records.map((record) => JSON.stringify(record)).join("\n")}\n`,
          "wx",
        );
      }
    }
    return records;
  }

  async read(
    key: ConversationKey,
  ): Promise<ConversationRecord[]> {
    if (!isConversationKey(key)) {
      throw new Error("conversation key is invalid");
    }
    const runRoot = path.join(
      this.root,
      runDirectoryName(key.runId),
    );
    const names = await segmentNames(runRoot);
    const records: ConversationRecord[] = [];
    for (let index = 0; index < names.length; index += 1) {
      records.push(
        ...(await this.readSegment(
          path.join(runRoot, names[index]),
          index === names.length - 1,
        )),
      );
    }
    const serializedKey = serializeConversationKey(key);
    return records.filter(
      (record) =>
        serializeConversationKey(record.key) === serializedKey,
    );
  }

  async prune(now = new Date()): Promise<void> {
    const cutoff = now.getTime() - this.retentionMs;
    let runDirectories: string[];
    try {
      runDirectories = await readdir(this.root);
    } catch (error) {
      if (errorCode(error) === "ENOENT") {
        return;
      }
      throw error;
    }
    for (const runDirectory of runDirectories) {
      if (!/^[0-9a-f]{64}$/.test(runDirectory)) {
        continue;
      }
      const runRoot = path.join(this.root, runDirectory);
      const names = await segmentNames(runRoot);
      for (const name of names) {
        const segmentPath = path.join(runRoot, name);
        const serialized = await readFile(segmentPath, "utf8");
        const lines = serialized
          .split("\n")
          .filter((line) => line.length > 0);
        const retained = lines
          .map(parseLine)
          .filter(
            (record) =>
              Date.parse(record.createdAt) >= cutoff,
          );
        if (retained.length === 0) {
          await rm(segmentPath, { force: true });
        } else if (retained.length !== lines.length) {
          await atomicRewrite(
            segmentPath,
            `${retained
              .map((record) => JSON.stringify(record))
              .join("\n")}\n`,
          );
        }
      }
      if ((await segmentNames(runRoot)).length === 0) {
        await rm(runRoot, { recursive: true, force: true });
      }
    }
  }

  async deleteAll(): Promise<void> {
    await rm(this.root, { recursive: true, force: true });
  }
}
