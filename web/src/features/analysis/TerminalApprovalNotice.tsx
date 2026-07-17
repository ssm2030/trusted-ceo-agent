type TerminalApprovalNoticeProps = {
  instruction: string;
  requestId?: string | null;
};

export function TerminalApprovalNotice({
  instruction,
  requestId = null,
}: TerminalApprovalNoticeProps) {
  return (
    <section aria-live="polite" className="terminal-notice">
      <div className="terminal-icon" aria-hidden="true">
        &gt;_
      </div>
      <div>
        <p className="eyebrow">사람 확인 단계</p>
        <h3>터미널 승인 필요</h3>
        <p>{instruction}</p>
        {requestId ? (
          <p className="request-id">요청 ID {requestId}</p>
        ) : null}
        <p className="polling-status">
          <span aria-hidden="true" />
          터미널 결정을 기다리는 중
        </p>
      </div>
    </section>
  );
}
