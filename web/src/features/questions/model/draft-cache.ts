import type { ReportScopeKind } from "@/features/report/report-model";

export type ConversationKey = {
  revision: number;
  runId: string;
  scopeInstanceId: string;
  scopeKind: ReportScopeKind;
};

export type QuestionDraftState = {
  drawerOpen: boolean;
  scrollTop: number;
  text: string;
};

type StorageLike = Pick<Storage, "getItem" | "setItem">;
type Digest = (value: string) => Promise<string>;

type QuestionDraftCacheOptions = {
  digest?: Digest;
  storage?: StorageLike | null;
};

const EMPTY_DRAFT: QuestionDraftState = {
  drawerOpen: false,
  scrollTop: 0,
  text: "",
};

export function serializeConversationKey(key: ConversationKey): string {
  return [
    key.runId,
    String(key.revision),
    key.scopeKind,
    key.scopeInstanceId,
  ].join("\u001f");
}

function isDraftState(value: unknown): value is QuestionDraftState {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }
  const candidate = value as Partial<QuestionDraftState>;
  return (
    typeof candidate.drawerOpen === "boolean" &&
    Number.isFinite(candidate.scrollTop) &&
    (candidate.scrollTop ?? -1) >= 0 &&
    typeof candidate.text === "string"
  );
}

async function sha256ForBrowser(value: string): Promise<string> {
  if (globalThis.crypto?.subtle === undefined) {
    throw new Error("browser digest unavailable");
  }
  const bytes = new TextEncoder().encode(value);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

function defaultSessionStorage(): StorageLike | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

export class QuestionDraftCache {
  private readonly digest: Digest;
  private readonly memory = new Map<string, QuestionDraftState>();
  private readonly storage: StorageLike | null;

  constructor(options: QuestionDraftCacheOptions = {}) {
    this.digest = options.digest ?? sha256ForBrowser;
    this.storage =
      options.storage === undefined
        ? defaultSessionStorage()
        : options.storage;
  }

  private async storageKey(serializedKey: string): Promise<string | null> {
    try {
      return `trusted-ceo:q-draft:${await this.digest(serializedKey)}`;
    } catch {
      return null;
    }
  }

  async load(key: ConversationKey): Promise<QuestionDraftState> {
    const serializedKey = serializeConversationKey(key);
    const storageKey = await this.storageKey(serializedKey);
    if (storageKey !== null && this.storage !== null) {
      try {
        const serialized = this.storage.getItem(storageKey);
        if (serialized !== null) {
          const parsed = JSON.parse(serialized) as unknown;
          if (isDraftState(parsed)) {
            this.memory.set(serializedKey, parsed);
            return { ...parsed };
          }
        }
      } catch {
        // Session storage is optional; the in-memory copy remains authoritative.
      }
    }
    return { ...(this.memory.get(serializedKey) ?? EMPTY_DRAFT) };
  }

  async save(
    key: ConversationKey,
    draft: QuestionDraftState,
  ): Promise<void> {
    if (!isDraftState(draft)) {
      throw new Error("question draft state is invalid");
    }
    const serializedKey = serializeConversationKey(key);
    const copy = { ...draft };
    this.memory.set(serializedKey, copy);
    const storageKey = await this.storageKey(serializedKey);
    if (storageKey === null || this.storage === null) {
      return;
    }
    try {
      this.storage.setItem(storageKey, JSON.stringify(copy));
    } catch {
      // Quota and security errors intentionally degrade to the memory copy.
    }
  }
}

export const browserQuestionDraftCache = new QuestionDraftCache();
