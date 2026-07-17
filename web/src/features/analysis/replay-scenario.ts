import type { ProviderSnapshot } from "@/features/analysis/analysis-provider";

export const REPLAY_RUN_ID = "replay-demo";

export function createInitialReplaySnapshot(): ProviderSnapshot {
  return {
    provider_kind: "replay",
    display_badge: "저장된 시연 흐름",
    run_id: REPLAY_RUN_ID,
    revision: 0,
    workflow_status: "created",
    ui_phase: 1,
    pending_action: "provider_work",
    pending_approval_request_id: null,
    allowed_actions: ["attach_data", "start_or_continue"],
    latest_event: "저장된 작업 흐름을 열었습니다.",
    progress: 4,
    result_ref: null,
    error: null,
  };
}

export const REPLAY_PHASE_EVENTS = Object.freeze({
  context: "경영 목표와 우선순위를 확인할 차례입니다.",
  data: "선택한 자료의 파일 메타데이터를 기록했습니다.",
  terminal: "기존 터미널 승인 요청의 상태를 기다리고 있습니다.",
  changes: "변경 요청을 반영할 저장된 장면을 준비했습니다.",
} as const);
