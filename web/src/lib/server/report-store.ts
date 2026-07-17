import { randomUUID } from "node:crypto";
import {
  mkdir,
  open,
  readFile,
  rename,
  rm,
} from "node:fs/promises";
import path from "node:path";

const GENERATION_PATTERN = /^[0-9a-f-]{36}$/;

export type CurrentReportPair = Readonly<{
  generation: string;
  bytes: Uint8Array;
  decision: unknown;
}>;

async function writeSyncedFile(
  filePath: string,
  value: Uint8Array | string,
): Promise<void> {
  const handle = await open(filePath, "wx", 0o600);
  try {
    await handle.writeFile(value);
    await handle.sync();
  } finally {
    await handle.close();
  }
}

async function replaceSyncedFile(
  filePath: string,
  value: Uint8Array | string,
): Promise<void> {
  const temporaryPath = `${filePath}.${randomUUID()}.tmp`;
  try {
    await writeSyncedFile(temporaryPath, value);
    await rename(temporaryPath, filePath);
  } finally {
    await rm(temporaryPath, { force: true }).catch(() => undefined);
  }
}

export class ReportStore {
  private writeQueue: Promise<void> = Promise.resolve();

  constructor(private readonly runtimeRoot: string) {
    if (!path.isAbsolute(runtimeRoot)) {
      throw new Error("report runtime root must be absolute");
    }
  }

  async publishVerified(
    bytes: Uint8Array,
    decision: unknown,
  ): Promise<void> {
    await this.replaceAfterValidation(bytes, async () => decision);
  }

  async replaceAfterValidation<T>(
    bytes: Uint8Array,
    validator: (candidatePath: string) => Promise<T>,
  ): Promise<T> {
    const operation = this.writeQueue.then(async () => {
      const generation = randomUUID();
      const generationsRoot = path.join(this.runtimeRoot, "generations");
      const candidateRoot = path.join(
        this.runtimeRoot,
        `.candidate-${generation}`,
      );
      const generationRoot = path.join(generationsRoot, generation);
      const candidateReport = path.join(
        candidateRoot,
        "current-report.json",
      );
      const candidateDecision = path.join(
        candidateRoot,
        "current-decision.json",
      );
      let committed = false;
      await mkdir(generationsRoot, { recursive: true, mode: 0o700 });
      await mkdir(candidateRoot, { mode: 0o700 });
      try {
        await writeSyncedFile(candidateReport, bytes);
        const decision = await validator(candidateReport);
        const decisionBytes = JSON.stringify(decision);
        await writeSyncedFile(candidateDecision, decisionBytes);
        await rename(candidateRoot, generationRoot);

        // Compatibility aliases must succeed before the authoritative
        // pointer is published. A failed publication therefore leaves the
        // previous report current.
        await replaceSyncedFile(
          path.join(this.runtimeRoot, "current-report.json"),
          bytes,
        );
        await replaceSyncedFile(
          path.join(this.runtimeRoot, "current-decision.json"),
          decisionBytes,
        );

        const pointer = JSON.stringify({ generation });
        await replaceSyncedFile(
          path.join(this.runtimeRoot, "current-pointer.json"),
          pointer,
        );
        committed = true;
        return decision;
      } finally {
        await rm(candidateRoot, { recursive: true, force: true }).catch(
          () => undefined,
        );
        if (!committed) {
          await rm(generationRoot, {
            recursive: true,
            force: true,
          }).catch(() => undefined);
        }
      }
    });
    this.writeQueue = operation.then(
      () => undefined,
      () => undefined,
    );
    return operation;
  }

  async readCurrentPair(): Promise<CurrentReportPair | null> {
    let pointerBytes: string;
    try {
      pointerBytes = await readFile(
        path.join(this.runtimeRoot, "current-pointer.json"),
        "utf8",
      );
    } catch (error) {
      if (
        typeof error === "object" &&
        error !== null &&
        "code" in error &&
        error.code === "ENOENT"
      ) {
        return null;
      }
      throw error;
    }
    const pointer = JSON.parse(pointerBytes) as unknown;
    if (
      typeof pointer !== "object" ||
      pointer === null ||
      Object.keys(pointer).length !== 1 ||
      !("generation" in pointer) ||
      typeof pointer.generation !== "string" ||
      !GENERATION_PATTERN.test(pointer.generation)
    ) {
      throw new Error("current report pointer is invalid");
    }
    const generationRoot = path.join(
      this.runtimeRoot,
      "generations",
      pointer.generation,
    );
    const [bytes, decisionBytes] = await Promise.all([
      readFile(path.join(generationRoot, "current-report.json")),
      readFile(
        path.join(generationRoot, "current-decision.json"),
        "utf8",
      ),
    ]);
    return Object.freeze({
      generation: pointer.generation,
      bytes: new Uint8Array(bytes),
      decision: JSON.parse(decisionBytes) as unknown,
    });
  }

  async readCurrent(): Promise<Uint8Array | null> {
    return (await this.readCurrentPair())?.bytes ?? null;
  }

  async readCurrentDecision(): Promise<unknown | null> {
    return (await this.readCurrentPair())?.decision ?? null;
  }
}
