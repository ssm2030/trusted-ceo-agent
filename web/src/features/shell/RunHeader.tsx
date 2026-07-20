type RunHeaderProps = {
  badge: "저장된 시연 흐름" | "실시간 플러그인" | "실시간 AI 분석";
  runId: string;
  revision: number;
  status: string;
};

export function RunHeader({
  badge,
  runId,
  revision,
  status,
}: RunHeaderProps) {
  return (
    <dl className="run-header" aria-label="현재 실행 정보">
      <div>
        <dt>실행 방식</dt>
        <dd>
          <span className="status-badge" data-kind={badge === "저장된 시연 흐름" ? "replay" : "live"}>
            {badge}
          </span>
        </dd>
      </div>
      <div>
        <dt>현재 실행본</dt>
        <dd>{runId}</dd>
      </div>
      <div>
        <dt>리비전</dt>
        <dd>리비전 {revision}</dd>
      </div>
      <div>
        <dt>상태</dt>
        <dd>{status}</dd>
      </div>
    </dl>
  );
}
