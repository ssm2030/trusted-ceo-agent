import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ProviderSnapshot } from "@/features/analysis/analysis-provider";
import { CurrentWorkPanel } from "@/features/analysis/CurrentWorkPanel";
import { RunDetailsPanel } from "@/features/analysis/RunDetailsPanel";
import { StageRail } from "@/features/analysis/StageRail";
import AnalysisPage from "@/app/analysis/page";

const snapshot: ProviderSnapshot = {
  provider_kind: "replay",
  display_badge: "저장된 시연 흐름",
  run_id: "replay-demo",
  revision: 1,
  workflow_status: "created",
  ui_phase: 1,
  pending_action: "provider_work",
  pending_approval_request_id: null,
  allowed_actions: ["start_or_continue"],
  latest_event: "저장된 작업 흐름을 열었습니다.",
  progress: 4,
  result_ref: null,
  error: null,
  uploaded_files: [],
};

describe("분석 화면 한국어 문구", () => {
  it("제품 경계와 화면 보조 제목을 한국어로 표시한다", () => {
    render(<AnalysisPage />);

    expect(screen.getByText("신뢰 기반 의사결정 운영")).toBeVisible();
    expect(screen.getByText("분석 지휘 화면")).toBeVisible();
    expect(screen.queryByText("TRUSTED DECISION OPERATIONS")).not.toBeInTheDocument();
    expect(screen.queryByText("ANALYSIS COMMAND CENTER")).not.toBeInTheDocument();
  });

  it("단계와 현재 작업의 보조 제목을 한국어로 표시한다", () => {
    render(
      <>
        <StageRail activePhase={1} />
        <CurrentWorkPanel
          draft=""
          onDraftChange={vi.fn()}
          onPrepareTerminalRequest={vi.fn()}
          onStartOrContinue={vi.fn()}
          onSubmitHumanResponse={vi.fn()}
          snapshot={snapshot}
        />
      </>,
    );

    expect(screen.getByText("작업 흐름")).toBeVisible();
    expect(screen.getByText("현재 작업")).toBeVisible();
    expect(screen.queryByText("WORKFLOW")).not.toBeInTheDocument();
    expect(screen.queryByText("CURRENT WORK")).not.toBeInTheDocument();
  });

  it("실행 상세에서 내부 상태 코드를 노출하지 않는다", () => {
    render(<RunDetailsPanel snapshot={snapshot} />);

    expect(screen.getByText("이벤트 흐름")).toBeVisible();
    expect(screen.getByText("요청 자료")).toBeVisible();
    expect(screen.getByText("준비")).toBeVisible();
    expect(screen.getByText("다음 장면 준비")).toBeVisible();
    expect(screen.queryByText("created")).not.toBeInTheDocument();
    expect(screen.queryByText("provider_work")).not.toBeInTheDocument();
  });
});
