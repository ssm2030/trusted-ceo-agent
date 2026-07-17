import { describe, expect, it } from "vitest";

import { ReplayAnalysisProvider } from "@/features/analysis/replay-provider";

describe("ReplayAnalysisProvider", () => {
  it("identifies every state as a saved replay", async () => {
    const provider = new ReplayAnalysisProvider();
    const created = await provider.createRun();

    expect(created.provider_kind).toBe("replay");
    expect(created.display_badge).toBe("저장된 시연 흐름");
    expect(created.workflow_status).toBe("created");
  });

  it("uses human_response returned by the provider instead of inferring an action", async () => {
    const provider = new ReplayAnalysisProvider();
    const created = await provider.createRun();
    const state = await provider.startOrContinue(created.run_id, created.revision);

    expect(state.pending_action).toBe("human_response");
    expect(state.allowed_actions).toContain("submit_human_response");
  });

  it("rejects stale mutations with the shared provider error", async () => {
    const provider = new ReplayAnalysisProvider();
    const created = await provider.createRun();
    const stale = await provider.startOrContinue(created.run_id, 99);

    expect(stale.error).toEqual({
      code: "STALE_REVISION",
      message: "화면의 실행 정보가 오래되었습니다. 최신 상태를 다시 확인해 주세요.",
    });
    expect(stale.revision).toBe(created.revision);
  });

  it("never exposes approve as a browser action", async () => {
    const provider = new ReplayAnalysisProvider();
    const created = await provider.createRun();
    const waiting = await provider.prepareTerminalApprovalRequest(
      created.run_id,
      created.revision,
    );

    expect(waiting.pending_action).toBe("terminal_approval");
    expect(waiting.allowed_actions).not.toContain("approve");
    expect(waiting.pending_approval_request_id).toBeTruthy();
  });
});
