"use client";

import { useMemo, useState } from "react";

import type {
  HitlDecision,
  ProviderHitlCard,
} from "@/features/analysis/analysis-provider";

type HitlDecisionPanelProps = Readonly<{
  busy: boolean;
  card: ProviderHitlCard;
  onDecision: (
    decision: HitlDecision,
    edits: Readonly<Record<string, unknown>>,
    rationale: string | null,
  ) => Promise<void> | void;
}>;

function parsedEdit(value: string): unknown {
  const normalized = value.normalize("NFC").trim();
  try {
    return JSON.parse(normalized) as unknown;
  } catch {
    return normalized;
  }
}

function nestedEdits(
  fields: readonly string[],
  values: Readonly<Record<string, string>>,
): Readonly<Record<string, unknown>> {
  const result: Record<string, unknown> = {};
  for (const field of fields) {
    const raw = values[field]?.trim();
    if (!raw) continue;
    const segments = field.split(".");
    let cursor = result;
    for (const segment of segments.slice(0, -1)) {
      const existing = cursor[segment];
      if (
        existing === null ||
        typeof existing !== "object" ||
        Array.isArray(existing)
      ) {
        cursor[segment] = {};
      }
      cursor = cursor[segment] as Record<string, unknown>;
    }
    cursor[segments.at(-1)!] = parsedEdit(raw);
  }
  return result;
}

function decisionLabel(decision: HitlDecision): string {
  return {
    approve: "승인",
    approve_with_edits: "수정 후 승인",
    reanalyze: "재분석",
    stop: "중단",
  }[decision];
}

export function HitlDecisionPanel({
  busy,
  card,
  onDecision,
}: HitlDecisionPanelProps) {
  const [editValues, setEditValues] = useState<Record<string, string>>({});
  const [rationale, setRationale] = useState("");


  const edits = useMemo(
    () => nestedEdits(card.editable_fields, editValues),
    [card.editable_fields, editValues],
  );
  const hasEdits = Object.keys(edits).length > 0;

  async function submit(decision: HitlDecision) {
    if (busy) return;
    const needsRationale = decision === "reanalyze" || decision === "stop";
    const normalizedRationale = rationale.normalize("NFC").trim();
    if (needsRationale && !normalizedRationale) return;
    await onDecision(
      decision,
      decision === "approve_with_edits" ? edits : {},
      needsRationale ? normalizedRationale : null,
    );
  }

  return (
    <section className="hitl-decision-panel" aria-labelledby="hitl-title">
      <header className="hitl-card-header">
        <div>
          <p className="eyebrow">
            {card.hitl_kind === "context_data"
              ? "맥락·데이터 확인"
              : "진단·최종 확인"}
          </p>
          <h3 id="hitl-title">{card.title}</h3>
        </div>
        <span className="revision-seal">revision {card.base_revision}</span>
      </header>
      <p className="hitl-summary">{card.summary}</p>

      <div className="hitl-targets" aria-label="검토 대상 근거">
        <span>검토 대상</span>
        {card.target_refs.map((target) => (
          <code key={target}>{target}</code>
        ))}
      </div>

      <div className="hitl-sections">
        {card.sections.map((section, index) => (
          <article key={`${section.kind}-${index}`}>
            <div>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <h4>{section.title}</h4>
            </div>
            <ul>
              {section.items.map((item) => <li key={item}>{item}</li>)}
            </ul>
            {section.target_refs.length > 0 ? (
              <div className="section-targets">
                {section.target_refs.map((target) => (
                  <code key={target}>{target}</code>
                ))}
              </div>
            ) : null}
          </article>
        ))}
      </div>

      {card.editable_fields.length > 0 ? (
        <details className="hitl-edits">
          <summary>승인 전 수정값 입력</summary>
          <p>문자열은 그대로, 배열·객체·boolean은 JSON 형식으로 입력하세요.</p>
          <div>
            {card.editable_fields.map((field) => (
              <label key={field}>
                <span>{field} 수정값</span>
                <textarea
                  aria-label={`${field} 수정값`}
                  disabled={busy}
                  onChange={(event) => setEditValues((current) => ({
                    ...current,
                    [field]: event.target.value,
                  }))}
                  rows={2}
                  value={editValues[field] ?? ""}
                />
              </label>
            ))}
          </div>
        </details>
      ) : null}

      <label className="hitl-rationale">
        <span>결정 근거</span>
        <textarea
          aria-label="결정 근거"
          disabled={busy}
          onChange={(event) => setRationale(event.target.value)}
          placeholder="재분석과 중단에는 결정 근거가 필요합니다."
          rows={3}
          value={rationale}
        />
      </label>

      <p className="decision-consequence">
        이 결정은 현재 revision에 기록되며 다음 분석 단계의 공식 입력이 됩니다.
      </p>
      <div className="hitl-actions">
        {card.allowed_decisions.map((decision) => (
          <button
            className={
              decision === "approve"
                ? "primary-action"
                : decision === "stop"
                  ? "danger-action"
                  : "tertiary-action"
            }
            disabled={
              busy ||
              (decision === "approve_with_edits" && !hasEdits) ||
              ((decision === "reanalyze" || decision === "stop") &&
                !rationale.trim())
            }
            key={decision}
            onClick={() => void submit(decision)}
            type="button"
          >
            {decisionLabel(decision)}
          </button>
        ))}
      </div>
    </section>
  );
}