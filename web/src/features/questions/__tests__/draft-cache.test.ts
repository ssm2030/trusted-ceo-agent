import { describe, expect, it } from "vitest";

import {
  QuestionDraftCache,
  serializeConversationKey,
  type ConversationKey,
} from "@/features/questions/model/draft-cache";

const EVIDENCE_KEY: ConversationKey = {
  runId: "run_demo",
  revision: 3,
  scopeKind: "evidence",
  scopeInstanceId: "evidence_a",
};

describe("QuestionDraftCache", () => {
  it("uses all four conversation key fields", () => {
    expect(serializeConversationKey(EVIDENCE_KEY)).toBe(
      "run_demo\u001f3\u001fevidence\u001fevidence_a",
    );
    expect(
      serializeConversationKey({
        ...EVIDENCE_KEY,
        scopeInstanceId: "evidence_b",
      }),
    ).not.toBe(serializeConversationKey(EVIDENCE_KEY));
  });

  it("restores only the matching session-scoped draft", async () => {
    sessionStorage.clear();
    const cache = new QuestionDraftCache({
      digest: async (value) => `digest:${value.length}:${value.at(-1)}`,
      storage: sessionStorage,
    });
    await cache.save(EVIDENCE_KEY, {
      drawerOpen: false,
      scrollTop: 128,
      text: "첫 번째 근거 질문",
    });
    await cache.save(
      { ...EVIDENCE_KEY, scopeInstanceId: "evidence_b" },
      {
        drawerOpen: true,
        scrollTop: 0,
        text: "두 번째 근거 질문",
      },
    );

    const reloaded = new QuestionDraftCache({
      digest: async (value) => `digest:${value.length}:${value.at(-1)}`,
      storage: sessionStorage,
    });
    await expect(reloaded.load(EVIDENCE_KEY)).resolves.toEqual({
      drawerOpen: false,
      scrollTop: 128,
      text: "첫 번째 근거 질문",
    });
    await expect(
      reloaded.load({
        ...EVIDENCE_KEY,
        scopeInstanceId: "evidence_b",
      }),
    ).resolves.toEqual({
      drawerOpen: true,
      scrollTop: 0,
      text: "두 번째 근거 질문",
    });
  });

  it("falls back to memory when session storage is unavailable", async () => {
    const blockedStorage = {
      getItem: () => {
        throw new DOMException("blocked");
      },
      setItem: () => {
        throw new DOMException("blocked");
      },
    };
    const cache = new QuestionDraftCache({
      digest: async () => "blocked",
      storage: blockedStorage,
    });
    await cache.save(EVIDENCE_KEY, {
      drawerOpen: true,
      scrollTop: 9,
      text: "메모리 초안",
    });

    await expect(cache.load(EVIDENCE_KEY)).resolves.toEqual({
      drawerOpen: true,
      scrollTop: 9,
      text: "메모리 초안",
    });
  });
});
