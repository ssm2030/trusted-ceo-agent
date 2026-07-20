import type { ProviderSnapshot } from "@/features/analysis/analysis-provider";
import { getWorkflowStatusLabel } from "@/features/analysis/analysis-model";
import { HumanResponseForm } from "@/features/analysis/HumanResponseForm";

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
        <div><span className="pulse-dot" aria-hidden="true" /><p>{getWorkflowStatusLabel(snapshot)}</p></div>
        <strong>{snapshot.progress}%</strong>
      </div>
      <div aria-label={`진행률 ${snapshot.progress}%`} aria-valuemax={100} aria-valuemin={0} aria-valuenow={snapshot.progress} className="progress-track" role="progressbar">
        <span style={{ width: `${snapshot.progress}%` }} />
      </div>
      <div className="work-body">
        {snapshot.pending_action === "human_response" ? (
          <HumanResponseForm draft={draft} onDraftChange={onDraftChange} onSubmit={onSubmitHumanResponse} />
        ) : null}
        {snapshot.pending_action === "terminal_approval" ? (
          <div className="terminal-notice">
            <span className="terminal-icon" aria-hidden="true">H</span>
            <div>
              <p className="eyebrow">승인 체크포인트</p>
              <h3>저장된 시연 승인 요청</h3>
              <p>회귀 시연용 요청을 준비한 뒤 저장된 다음 장면으로 이동합니다.</p>
              {!snapshot.pending_approval_request_id ? (
                <button className="secondary-action" onClick={onPrepareTerminalRequest} type="button">승인 요청 준비</button>
              ) : null}
            </div>
          </div>
        ) : null}
        {snapshot.pending_action === "provider_work" ? (
          <div className="provider-work">
            <p>준비된 작업 순서에 따라 다음 분석 장면으로 이동합니다.</p>
            <button className="primary-action" onClick={onStartOrContinue} type="button">
              {snapshot.workflow_status === "created" ? "시연 흐름 시작" : "저장된 다음 장면 보기"}
            </button>
          </div>
        ) : null}
        {snapshot.error ? <p className="inline-error" role="alert">{snapshot.error.message}</p> : null}
      </div>
    </section>
  );
}