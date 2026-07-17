import type { FormEvent } from "react";

type HumanResponseFormProps = {
  draft: string;
  onDraftChange: (draft: string) => void;
  onSubmit: () => void;
};

export function HumanResponseForm({
  draft,
  onDraftChange,
  onSubmit,
}: HumanResponseFormProps) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit();
  }

  return (
    <form className="human-response-form" onSubmit={handleSubmit}>
      <label htmlFor="human-response">사람 확인 답변</label>
      <p>
        이번 시연에서 가장 먼저 보호해야 할 경영 목표와 판단 기준을 적어 주세요.
      </p>
      <textarea
        id="human-response"
        onChange={(event) => onDraftChange(event.target.value)}
        placeholder="예: 성장률보다 6개월 현금 흐름을 우선합니다."
        rows={5}
        value={draft}
      />
      <button className="primary-action" disabled={!draft.trim()} type="submit">
        답변 제출
      </button>
    </form>
  );
}
