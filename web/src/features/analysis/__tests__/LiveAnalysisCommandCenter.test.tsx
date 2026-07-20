import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LiveAnalysisCommandCenter } from "@/features/analysis/LiveAnalysisCommandCenter";
import type {
  AnalysisProvider,
  ProviderSnapshot,
} from "@/features/analysis/analysis-provider";

const RUN_ID = "run_20260719T000000Z_0123456789abcdef";

function snapshot(
  overrides: Partial<ProviderSnapshot> = {},
): ProviderSnapshot {
  return {
    provider_kind: "service",
    display_badge: "실시간 AI 분석",
    run_id: RUN_ID,
    revision: 3,
    workflow_status: "context_confirmation_required",
    ui_phase: 1,
    pending_action: "human_response",
    pending_approval_request_id: "approval_context_01",
    allowed_actions: ["submit_human_response"],
    latest_event: "분석 목표 확인을 기다리고 있습니다.",
    progress: 12,
    result_ref: null,
    hitl_card: {
      hitl_kind: "context_data",
      request_id: "approval_context_01",
      base_revision: 3,
      title: "분석 목표와 범위를 확인해 주세요",
      summary: "검증된 Mission 초안입니다.",
      target_refs: ["mission_main"],
      allowed_decisions: ["approve", "approve_with_edits", "stop"],
      editable_fields: ["business_question"],
      sections: [],
    },
    error: null,
    ...overrides,
  };
}

function provider(initial = snapshot()) {
  return {
    getHealth: vi.fn(async () => ({
      status: "ok" as const,
      aiReady: true,
      model: "gpt-5.6" as const,
    })),
    createRun: vi.fn(async () => initial),
    attachData: vi.fn(async () => ({
      ...initial,
      revision: initial.revision + 1,
      latest_event: "업로드한 자료를 연결했습니다.",
    })),
    submitHumanResponse: vi.fn(),
    submitDecision: vi.fn(async () => ({
      ...initial,
      revision: initial.revision + 1,
      pending_action: "provider_work" as const,
      hitl_card: null,
    })),
    requestChanges: vi.fn(),
    startOrContinue: vi.fn(async () => initial),
    prepareTerminalApprovalRequest: vi.fn(),
    getStatus: vi.fn(async () => initial),
    getPendingAction: vi.fn(),
    getTerminalApprovalInstruction: vi.fn(),
    retry: vi.fn(async () => initial),
    resume: vi.fn(async () => initial),
    stop: vi.fn(async () => initial),
    cancel: vi.fn(async () => initial),
    deleteRun: vi.fn(async () => undefined),
    openFinalizedReport: vi.fn(async () => "/report"),
  } satisfies AnalysisProvider & {
    getHealth(): Promise<{
      status: "ok";
      aiReady: boolean;
      model: "gpt-5.6";
    }>;
  };
}

beforeEach(() => {
  window.sessionStorage.clear();
});

describe("LiveAnalysisCommandCenter", () => {
  it("creates a service run on first entry and stores only its run ID", async () => {
    const service = provider();
    render(<LiveAnalysisCommandCenter provider={service} />);

    expect(await screen.findByText("분석 목표와 범위를 확인해 주세요")).toBeVisible();
    expect(service.createRun).toHaveBeenCalledTimes(1);
    expect(window.sessionStorage.getItem("trusted-ceo-live-run-id")).toBe(RUN_ID);
    expect(JSON.stringify(window.sessionStorage)).not.toContain("approval_context_01");
    expect(service.getStatus).not.toHaveBeenCalled();
  });

  it("restores the canonical snapshot from a stored run ID without creating another run", async () => {
    window.sessionStorage.setItem("trusted-ceo-live-run-id", RUN_ID);
    const service = provider();
    render(<LiveAnalysisCommandCenter provider={service} />);

    await screen.findByText("분석 목표와 범위를 확인해 주세요");
    expect(service.getStatus).toHaveBeenCalledWith(RUN_ID);
    expect(service.createRun).not.toHaveBeenCalled();
  });

  it("shows a keyless disabled state without starting a run", async () => {
    const service = provider();
    service.getHealth.mockResolvedValue({
      status: "ok",
      aiReady: false,
      model: "gpt-5.6",
    });
    render(<LiveAnalysisCommandCenter provider={service} />);

    expect(await screen.findByText(/OpenAI API 키가 필요합니다/u)).toBeVisible();
    expect(service.createRun).not.toHaveBeenCalled();
    expect(screen.queryByText(/Codex|플러그인|터미널 승인/u)).not.toBeInTheDocument();
  });

  it("refreshes the canonical snapshot when a mutation response fails", async () => {
    const user = userEvent.setup();
    const service = provider();
    const refreshed = snapshot({
      revision: 4,
      latest_event: "서버의 최신 revision을 다시 불러왔습니다.",
    });
    service.submitDecision.mockRejectedValueOnce(new Error("response lost"));
    service.getStatus.mockResolvedValue(refreshed);
    render(<LiveAnalysisCommandCenter provider={service} />);

    await screen.findByText("분석 목표와 범위를 확인해 주세요");
    await user.click(screen.getByRole("button", { name: "승인" }));

    await waitFor(() => expect(service.getStatus).toHaveBeenCalledWith(RUN_ID));
    expect(await screen.findByText("서버의 최신 revision을 다시 불러왔습니다.")).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "현재 revision을 새로 확인해 주세요.",
    );
  });
  it("uploads bounded files and exposes final report and confirmed deletion actions", async () => {
    const user = userEvent.setup();
    const finalized = snapshot({
      revision: 9,
      workflow_status: "finalized",
      ui_phase: 7,
      pending_action: "terminal",
      pending_approval_request_id: null,
      allowed_actions: ["delete"],
      hitl_card: null,
      progress: 100,
      result_ref: "report.json",
    });
    const service = provider(finalized);
    const navigate = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<LiveAnalysisCommandCenter provider={service} onNavigate={navigate} />);

    await screen.findByText("업로드 자료");
    await user.upload(
      screen.getByLabelText("분석 자료 선택"),
      new File(["period,value\n2026-01,1"], "monthly.csv", {
        type: "text/csv",
      }),
    );
    await waitFor(() => expect(service.attachData).toHaveBeenCalled());
    expect(screen.getByText("monthly.csv")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "최종 보고서 열기" }));
    expect(service.openFinalizedReport).toHaveBeenCalledWith(RUN_ID);
    expect(navigate).toHaveBeenCalledWith("/report");

    await user.click(screen.getByRole("button", { name: "실행 데이터 삭제" }));
    expect(service.deleteRun).toHaveBeenCalledWith(RUN_ID, 10);
    expect(window.sessionStorage.getItem("trusted-ceo-live-run-id")).toBeNull();
    expect(await screen.findByText("실행 데이터가 삭제되었습니다.")).toBeVisible();
  });
});