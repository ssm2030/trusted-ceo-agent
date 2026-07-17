// @vitest-environment node
import { describe, expect, it } from "vitest";

import {
  serializeConversationKey,
  type ConversationKey,
} from "@/lib/server/questions/types";

describe("serializeConversationKey", () => {
  it("uses all four scope fields and separates evidence conversations", () => {
    const first: ConversationKey = {
      runId: "run_20260717T010203Z_0123456789abcdef",
      revision: 7,
      scopeKind: "evidence",
      scopeInstanceId: "evidence_link_1",
    };
    const second: ConversationKey = {
      ...first,
      scopeInstanceId: "evidence_link_2",
    };

    expect(serializeConversationKey(first)).toBe(
      [
        first.runId,
        String(first.revision),
        first.scopeKind,
        first.scopeInstanceId,
      ].join("\u001f"),
    );
    expect(serializeConversationKey(first)).not.toBe(
      serializeConversationKey(second),
    );
  });
});
