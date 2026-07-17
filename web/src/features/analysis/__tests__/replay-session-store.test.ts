import { beforeEach, describe, expect, it } from "vitest";

import type { ProviderSnapshot } from "@/features/analysis/analysis-provider";
import {
  loadReplaySession,
  REPLAY_SESSION_KEY,
  saveReplaySession,
} from "@/features/analysis/replay-session-store";

const snapshot: ProviderSnapshot = {
  provider_kind: "replay",
  display_badge: "저장된 시연 흐름",
  run_id: "replay-demo",
  revision: 1,
  workflow_status: "context_confirmation_required",
  ui_phase: 1,
  pending_action: "human_response",
  pending_approval_request_id: null,
  allowed_actions: ["submit_human_response"],
  latest_event: "목표 확인 질문을 준비했습니다.",
  progress: 12,
  result_ref: null,
  error: null,
};

describe("replay session storage", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("persists only serializable file metadata and the human draft", () => {
    saveReplaySession({
      snapshot,
      selectedFiles: [
        { name: "매출.xlsx", size: 321, type: "application/octet-stream" },
      ],
      humanDraft: "성장보다 현금 흐름을 우선합니다.",
    });

    expect(loadReplaySession()).toEqual({
      snapshot,
      selectedFiles: [
        { name: "매출.xlsx", size: 321, type: "application/octet-stream" },
      ],
      humanDraft: "성장보다 현금 흐름을 우선합니다.",
    });
    expect(sessionStorage.getItem(REPLAY_SESSION_KEY)).not.toContain(
      "approval_nonce",
    );
  });
});
