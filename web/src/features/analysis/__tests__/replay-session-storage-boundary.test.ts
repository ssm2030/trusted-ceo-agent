import { afterEach, describe, expect, it, vi } from "vitest";

import {
  loadReplaySession,
  REPLAY_SESSION_KEY,
  saveReplaySession,
  type ReplaySession,
} from "@/features/analysis/replay-session-store";

const safeSession: ReplaySession = {
  snapshot: {
    provider_kind: "replay",
    display_badge: "저장된 시연 흐름",
    run_id: "replay-demo",
    revision: 0,
    workflow_status: "created",
    ui_phase: 1,
    pending_action: "provider_work",
    pending_approval_request_id: null,
    allowed_actions: ["start_or_continue"],
    latest_event: "저장된 작업 흐름을 열었습니다.",
    progress: 4,
    result_ref: null,
    error: null,
  },
  selectedFiles: [],
  humanDraft: "",
};

describe("replay session storage boundary", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("versions the persisted session schema", () => {
    expect(REPLAY_SESSION_KEY).toBe("trusted-ceo-replay:v1");
  });

  it("keeps replay usable when session storage rejects writes", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });

    expect(() => saveReplaySession(safeSession)).not.toThrow();
  });

  it("falls back to a fresh replay when session storage rejects reads", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });

    expect(loadReplaySession()).toBeNull();
  });
});
