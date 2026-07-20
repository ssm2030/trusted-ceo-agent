import { randomUUID } from "node:crypto";
import {
  mkdir,
  open,
  readFile,
  rm,
} from "node:fs/promises";
import path from "node:path";

import type {
  QuestionRunContext,
  QuestionScope,
  ResultAnswer,
} from "@/lib/server/questions/types";

const MAX_WAITING = 3;
const RATE_LIMIT = 6;
const RATE_WINDOW_MS = 5 * 60 * 1000;
const STALE_LOCK_MS = 2 * 90_000;
const LOCK_POLL_MS = 50;

export type QuestionRequestState =
  | "queued"
  | "preparing"
  | "asking"
  | "validating"
  | "completed"
  | "scope_required"
  | "failed"
  | "cancelled";

export interface ScopeSuggestion {
  kind: string;
  instanceId: string;
}

export interface QuestionRequestSnapshot {
  requestId: string;
  clientRequestId: string;
  state: QuestionRequestState;
  queuePosition: number | null;
  answer: ResultAnswer | null;
  scopeSuggestions: ScopeSuggestion[];
  errorCode: string | null;
}

export interface SubmitQuestionInput {
  clientRequestId: string;
  context: QuestionRunContext;
  question: string;
  scope: QuestionScope;
  rateKey: string;
}

export class QuestionCoordinatorError extends Error {
  constructor(
    readonly code:
      | "QUESTION_QUEUE_FULL"
      | "QUESTION_RATE_LIMITED"
      | "QUESTION_INVALID",
  ) {
    super(code);
    this.name = "QuestionCoordinatorError";
  }
}

export class QuestionExecutionError extends Error {
  constructor(
    readonly code: string,
    readonly transient = false,
  ) {
    super(code);
    this.name = "QuestionExecutionError";
  }
}

export class ScopeRequiredError extends Error {
  constructor(readonly suggestions: ScopeSuggestion[]) {
    super("SCOPE_REQUIRED");
    this.name = "ScopeRequiredError";
  }
}

type CoordinatorAnswerInput = Readonly<{
  clientRequestId: string;
  context: QuestionRunContext;
  question: string;
  scope: QuestionScope;
  signal: AbortSignal;
  setState: (
    state: "preparing" | "asking" | "validating",
  ) => void;
}>;

export type QuestionCoordinatorDependencies = Readonly<{
  lockRoot: string;
  answer: (
    input: CoordinatorAnswerInput,
  ) => Promise<ResultAnswer>;
  now?: () => number;
  onTerminal?: (
    input: SubmitQuestionInput,
    snapshot: QuestionRequestSnapshot,
  ) => Promise<void>;
}>;

type Entry = {
  input: SubmitQuestionInput;
  snapshot: QuestionRequestSnapshot;
  controller: AbortController;
};

function frozenSnapshot(
  snapshot: QuestionRequestSnapshot,
): QuestionRequestSnapshot {
  return Object.freeze({
    ...snapshot,
    scopeSuggestions: Object.freeze(
      snapshot.scopeSuggestions.map((item) =>
        Object.freeze({ ...item }),
      ),
    ) as ScopeSuggestion[],
  });
}

function processExists(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return !(
      typeof error === "object" &&
      error !== null &&
      "code" in error &&
      error.code === "ESRCH"
    );
  }
}

function isValidLock(
  value: unknown,
): value is {
  pid: number;
  requestId: string;
  createdAt: string;
} {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    Object.keys(value).sort().join(",") ===
      "createdAt,pid,requestId" &&
    "pid" in value &&
    Number.isInteger(value.pid) &&
    "requestId" in value &&
    typeof value.requestId === "string" &&
    "createdAt" in value &&
    typeof value.createdAt === "string" &&
    Number.isFinite(Date.parse(value.createdAt))
  );
}

async function acquireActiveLock(
  root: string,
  requestId: string,
  signal: AbortSignal,
): Promise<() => Promise<void>> {
  await mkdir(root, { recursive: true, mode: 0o700 });
  const lockPath = path.join(root, "active.lock");
  while (!signal.aborted) {
    try {
      const handle = await open(lockPath, "wx", 0o600);
      try {
        await handle.writeFile(
          JSON.stringify({
            pid: process.pid,
            requestId,
            createdAt: new Date().toISOString(),
          }),
          "utf8",
        );
        await handle.sync();
      } finally {
        await handle.close();
      }
      return async () => {
        let ownsLock = false;
        try {
          const value = JSON.parse(
            await readFile(lockPath, "utf8"),
          ) as unknown;
          ownsLock =
            isValidLock(value) &&
            value.pid === process.pid &&
            value.requestId === requestId;
        } catch {
          ownsLock = false;
        }
        if (ownsLock) {
          await rm(lockPath, { force: true });
        }
      };
    } catch (error) {
      const code =
        typeof error === "object" &&
        error !== null &&
        "code" in error
          ? error.code
          : undefined;
      if (code !== "EEXIST") {
        throw error;
      }
      let stale = false;
      try {
        const value = JSON.parse(
          await readFile(lockPath, "utf8"),
        ) as unknown;
        stale =
          isValidLock(value) &&
          Date.now() - Date.parse(value.createdAt) >
            STALE_LOCK_MS &&
          !processExists(value.pid);
      } catch {
        stale = false;
      }
      if (stale) {
        await rm(lockPath, { force: true });
        continue;
      }
      await new Promise<void>((resolve) => {
        const timer = setTimeout(resolve, LOCK_POLL_MS);
        const abort = (): void => {
          clearTimeout(timer);
          resolve();
        };
        signal.addEventListener("abort", abort, {
          once: true,
        });
      });
    }
  }
  throw new QuestionExecutionError("QUESTION_CANCELLED");
}

export class QuestionCoordinator {
  private readonly requests = new Map<string, Entry>();
  private readonly clientRequests = new Map<string, string>();
  private readonly waiting: Entry[] = [];
  private readonly rateHistory = new Map<string, number[]>();
  private active: Entry | null = null;

  constructor(
    private readonly dependencies: QuestionCoordinatorDependencies,
  ) {
    if (!path.isAbsolute(dependencies.lockRoot)) {
      throw new Error("question lock root must be absolute");
    }
  }

  async submit(
    input: SubmitQuestionInput,
  ): Promise<QuestionRequestSnapshot> {
    const existingId = this.clientRequests.get(
      input.clientRequestId,
    );
    if (existingId !== undefined) {
      return this.get(existingId) as QuestionRequestSnapshot;
    }
    const normalizedQuestion = input.question.normalize("NFC").trim();
    if (
      !/^[A-Za-z0-9_-]{1,128}$/.test(input.clientRequestId) ||
      !input.rateKey ||
      normalizedQuestion.length === 0 ||
      Array.from(normalizedQuestion).length > 2_000
    ) {
      throw new QuestionCoordinatorError("QUESTION_INVALID");
    }
    if (this.active !== null && this.waiting.length >= MAX_WAITING) {
      throw new QuestionCoordinatorError("QUESTION_QUEUE_FULL");
    }
    const now = (this.dependencies.now ?? Date.now)();
    const recent = (
      this.rateHistory.get(input.rateKey) ?? []
    ).filter((timestamp) => now - timestamp < RATE_WINDOW_MS);
    if (recent.length >= RATE_LIMIT) {
      throw new QuestionCoordinatorError(
        "QUESTION_RATE_LIMITED",
      );
    }
    recent.push(now);
    this.rateHistory.set(input.rateKey, recent);

    const requestId = randomUUID();
    const entry: Entry = {
      input: {
        ...input,
        question: normalizedQuestion,
      },
      snapshot: {
        requestId,
        clientRequestId: input.clientRequestId,
        state: "queued",
        queuePosition:
          this.active === null ? null : this.waiting.length + 1,
        answer: null,
        scopeSuggestions: [],
        errorCode: null,
      },
      controller: new AbortController(),
    };
    this.requests.set(requestId, entry);
    this.clientRequests.set(input.clientRequestId, requestId);
    if (this.active === null) {
      this.active = entry;
      queueMicrotask(() => {
        void this.execute(entry);
      });
    } else {
      this.waiting.push(entry);
    }
    return frozenSnapshot(entry.snapshot);
  }

  get(requestId: string): QuestionRequestSnapshot | null {
    const entry = this.requests.get(requestId);
    return entry === undefined
      ? null
      : frozenSnapshot(entry.snapshot);
  }

  cancel(requestId: string): boolean {
    const entry = this.requests.get(requestId);
    if (
      entry === undefined ||
      ["completed", "scope_required", "failed", "cancelled"].includes(
        entry.snapshot.state,
      )
    ) {
      return false;
    }
    entry.snapshot.state = "cancelled";
    entry.snapshot.queuePosition = null;
    entry.snapshot.errorCode = "QUESTION_CANCELLED";
    entry.controller.abort();
    const index = this.waiting.indexOf(entry);
    if (index >= 0) {
      this.waiting.splice(index, 1);
      this.refreshQueuePositions();
    }
    return true;
  }

  cancelForRunRevision(
    runId: string,
    revision: number,
  ): void {
    for (const entry of this.requests.values()) {
      if (
        entry.input.context.runId === runId &&
        entry.input.context.revision === revision
      ) {
        this.cancel(entry.snapshot.requestId);
      }
    }
  }

  private refreshQueuePositions(): void {
    this.waiting.forEach((entry, index) => {
      entry.snapshot.queuePosition = index + 1;
    });
  }

  private async execute(entry: Entry): Promise<void> {
    let release: (() => Promise<void>) | null = null;
    try {
      try {
        release = await acquireActiveLock(
          this.dependencies.lockRoot,
          entry.snapshot.requestId,
          entry.controller.signal,
        );
      } catch (error) {
        if (
          entry.controller.signal.aborted ||
          (error instanceof QuestionExecutionError &&
            error.code === "QUESTION_CANCELLED")
        ) {
          entry.snapshot.state = "cancelled";
          entry.snapshot.errorCode = "QUESTION_CANCELLED";
        } else {
          entry.snapshot.state = "failed";
          entry.snapshot.errorCode = "QUESTION_COORDINATOR_LOCK_FAILED";
        }
        entry.snapshot.queuePosition = null;
        return;
      }
      if (entry.snapshot.state === "cancelled") {
        return;
      }
      entry.snapshot.state = "preparing";
      const setState = (
        state: "preparing" | "asking" | "validating",
      ): void => {
        if (entry.snapshot.state !== "cancelled") {
          entry.snapshot.state = state;
        }
      };
      let attempt = 0;
      while (true) {
        try {
          const answer = await this.dependencies.answer({
            clientRequestId: entry.input.clientRequestId,
            context: entry.input.context,
            question: entry.input.question,
            scope: entry.input.scope,
            signal: entry.controller.signal,
            setState,
          });
          if (!entry.controller.signal.aborted) {
            entry.snapshot.answer = answer;
            entry.snapshot.state = "completed";
            entry.snapshot.queuePosition = null;
          }
          break;
        } catch (error) {
          if (
            error instanceof QuestionExecutionError &&
            error.transient &&
            attempt === 0 &&
            !entry.controller.signal.aborted
          ) {
            attempt += 1;
            continue;
          }
          if (
            error instanceof ScopeRequiredError &&
            !entry.controller.signal.aborted
          ) {
            entry.snapshot.state = "scope_required";
            entry.snapshot.scopeSuggestions =
              error.suggestions.map((item) => ({ ...item }));
            entry.snapshot.errorCode = "SCOPE_REQUIRED";
          } else if (entry.controller.signal.aborted) {
            entry.snapshot.state = "cancelled";
            entry.snapshot.errorCode = "QUESTION_CANCELLED";
          } else {
            entry.snapshot.state = "failed";
            entry.snapshot.errorCode =
              error instanceof QuestionExecutionError
                ? error.code
                : "QUESTION_FAILED";
          }
          entry.snapshot.queuePosition = null;
          break;
        }
      }
      if (
        this.dependencies.onTerminal !== undefined &&
        ["completed", "scope_required", "failed", "cancelled"].includes(
          entry.snapshot.state,
        )
      ) {
        await this.dependencies.onTerminal(
          entry.input,
          frozenSnapshot(entry.snapshot),
        );
      }
    } finally {
      await release?.();
      if (this.active === entry) {
        this.active = this.waiting.shift() ?? null;
        this.refreshQueuePositions();
        if (this.active !== null) {
          this.active.snapshot.queuePosition = null;
          queueMicrotask(() => {
            if (this.active !== null) {
              void this.execute(this.active);
            }
          });
        }
      }
    }
  }
}
