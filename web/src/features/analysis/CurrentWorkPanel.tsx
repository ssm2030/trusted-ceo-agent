import type { ProviderSnapshot } from "@/features/analysis/analysis-provider";
import { getWorkflowStatusLabel } from "@/features/analysis/analysis-model";
import { HumanResponseForm } from "@/features/analysis/HumanResponseForm";
import { TerminalApprovalNotice } from "@/features/analysis/TerminalApprovalNotice";

type CurrentWorkPanelProps = {
  draft: string;
  snapshot: ProviderSnapshot;
  onDraftChange: (draft: string) => void;
  onPrepareTerminalRequest: () => void;
  onStartOrContinue: () => void;
  onSubmitHumanResponse: () => void;
};

export function CurrentWorkPanel({
  draft,
  snapshot,
  onDraftChange,
  onPrepareTerminalRequest,
  onStartOrContinue,
  onSubmitHumanResponse,
}: CurrentWorkPanelProps) {
  const statusLabel = getWorkflowStatusLabel(snapshot);

  return (
    <section className="current-work-panel">
      <div className="work-heading">
        <div>
          <p className="eyebrow">현재 작업</p>
          <h2>지금 해야 할 작업</h2>
        </div>
        <span className="phase-chip">단계 {snapshot.ui_phase} / 7</span>
      </div>
      <div className="status-overview">
        <div>
          <span className="pulse-dot" aria-hidden="true" />
          <p>{statusLabel}</p>
        </div>
        <strong>{snapshot.progress}%</strong>
      </div>
      <div
        aria-label={`진행률 ${snapshot.progress}%`}
        aria-valuemax={100}
        aria-valuemin={0}
        aria-valuenow={snapshot.progress}
        className="progress-track"
        role="progressbar"
      >
        <span style={{ width: `${snapshot.progress}%` }} />
      </div>

      <div className="work-body">
        {snapshot.pending_action === "human_response" ? (
          <HumanResponseForm
            draft={draft}
            onDraftChange={onDraftChange}
            onSubmit={onSubmitHumanResponse}
          />
        ) : null}

        {snapshot.pending_action === "terminal_approval" ? (
          <>
            <TerminalApprovalNotice
              instruction={
                snapshot.pending_approval_request_id
                  ? "터미널에서 기존 요청을 확인한 뒤 상태를 새로 확인하세요."
                  : "승인 요청은 준비만 할 수 있습니다. 실제 결정은 터미널 TTY에서 진행합니다."
              }
              requestId={snapshot.pending_approval_request_id}
            />
            {!snapshot.pending_approval_request_id ? (
              <button
                className="secondary-action"
                onClick={onPrepareTerminalRequest}
                type="button"
              >
                터미널 요청 준비
              </button>
            ) : null}
          </>
        ) : null}

        {snapshot.pending_action === "provider_work" ? (
          <div className="provider-work">
            <p>
              준비된 이벤트 순서를 따라 다음 장면으로 이동합니다. 새 분석은
              수행하지 않습니다.
            </p>
            <button
              className="primary-action"
              onClick={onStartOrContinue}
              type="button"
            >
              {snapshot.workflow_status === "created"
                ? "시연 흐름 시작"
                : "저장된 다음 장면 보기"}
            </button>
          </div>
        ) : null}

        {snapshot.error ? (
          <p className="inline-error" role="alert">
            {snapshot.error.message}
          </p>
        ) : null}
      </div>
    </section>
  );
}
