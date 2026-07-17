import type { ProviderSnapshot } from "@/features/analysis/analysis-provider";
import {
  getPendingActionLabel,
  getWorkflowStatusLabel,
} from "@/features/analysis/analysis-model";

type RunDetailsPanelProps = {
  snapshot: ProviderSnapshot;
};

export function RunDetailsPanel({ snapshot }: RunDetailsPanelProps) {
  return (
    <section className="run-details-panel">
      <div className="panel-heading">
        <p className="eyebrow">이벤트 흐름</p>
        <h2>최근 이벤트</h2>
      </div>
      <div className="event-card">
        <span aria-hidden="true" />
        <p>{snapshot.latest_event}</p>
      </div>
      <dl className="run-facts">
        <div>
          <dt>실행 ID</dt>
          <dd>{snapshot.run_id}</dd>
        </div>
        <div>
          <dt>리비전</dt>
          <dd>{snapshot.revision}</dd>
        </div>
        <div>
          <dt>작업 상태</dt>
          <dd>{getWorkflowStatusLabel(snapshot)}</dd>
        </div>
        <div>
          <dt>다음 작업</dt>
          <dd>{getPendingActionLabel(snapshot.pending_action)}</dd>
        </div>
      </dl>
      <div className="requested-data">
        <p className="eyebrow">요청 자료</p>
        <h3>요청 자료와 이유</h3>
        <ul>
          <li>
            <strong>최근 12개월 손익</strong>
            <span>매출 변화와 비용 압력을 함께 확인하기 위해 필요합니다.</span>
          </li>
          <li>
            <strong>월별 현금 흐름</strong>
            <span>단기 의사결정 여력을 판단할 입력 자료입니다.</span>
          </li>
        </ul>
      </div>
    </section>
  );
}
