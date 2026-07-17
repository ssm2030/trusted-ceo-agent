# Consultant Analysis View B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 다섯 결과 화면을 유지하면서 `컨설턴트 근거 분석` 안에 `분석 결론 / 근거·출처 / 검증 계획` 보조 탭을 구현한다.

**Architecture:** `ReportWorkspace`가 보조 탭 상태를 소유하고 `ConsultantAnalysisView`가 공통 머리말과 탭 접근성을 담당한다. 결론과 검증 패널은 현재 `WebReportBundle v1.0.0`의 정본 필드만 필터링해 표시하며, 기존 `EvidenceWorkbench`는 근거·출처 본문으로 재사용한다.

**Tech Stack:** Next.js 16, React 19, TypeScript, CSS Modules, Vitest, Testing Library

---

## File structure

- Create `web/src/features/report/AnalysisConclusionPanel.tsx`: 현재 문제의 결론·가설·충돌·조건부 대응만 표시한다.
- Create `web/src/features/report/VerificationPlanPanel.tsx`: 검증 단계·전문가 경계·문제 closure에 연결된 미해결 자료 품질만 표시한다.
- Create `web/src/features/report/ConsultantAnalysisView.tsx`: 공통 머리말, 세 보조 탭, 키보드 탐색과 패널 전환을 담당한다.
- Modify `web/src/features/report/EvidenceWorkbench.tsx`: 중복 머리말을 제거하고 근거·출처 본문만 렌더링한다.
- Modify `web/src/features/report/ReportWorkspace.tsx`: 보조 탭 상태를 보존하고 차트·질문 근거 이동을 `근거·출처`와 연결한다.
- Modify `web/src/features/report/ReportWorkspace.module.css`: 낮은 위계의 보조 탭, 2열 가설 대조, 검증 패널과 반응형 규칙을 추가한다.
- Modify `web/src/features/report/__tests__/report-fixture.ts`: 이슈별 분석 내용과 자료 품질 격리를 검증할 fixture를 보강한다.
- Create `web/src/features/report/__tests__/AnalysisConclusionPanel.test.tsx`
- Create `web/src/features/report/__tests__/VerificationPlanPanel.test.tsx`
- Create `web/src/features/report/__tests__/ConsultantAnalysisView.test.tsx`
- Modify `web/src/features/report/__tests__/ReportWorkspace.test.tsx`

계약, 플러그인, 변환기와 `ReportSectionNav.tsx`는 변경하지 않는다.

### Task 1: 분석 fixture와 결론 패널

**Files:**
- Modify: `web/src/features/report/__tests__/report-fixture.ts`
- Create: `web/src/features/report/__tests__/AnalysisConclusionPanel.test.tsx`
- Create: `web/src/features/report/AnalysisConclusionPanel.tsx`

- [ ] **Step 1: fixture에서 두 이슈의 분석 내용을 명확히 분리한다**

`makeClientReportPayload()`에서 주 이슈와 보조 이슈가 서로 다른 가설·충돌·조건부 대응을 갖도록 다음 값을 고정한다.

```ts
primaryIssue.secondary_flags = ["margin_watch"];
primaryIssue.cause_hypotheses = [
  { claim_code: "고정비 증가가 수익성 저하를 설명할 수 있습니다." },
];
primaryIssue.counter_hypotheses = [
  { claim_code: "일시적인 매출 인식 시점 차이일 수 있습니다." },
];
primaryIssue.unresolved_conflicts = ["원가 배부 기준의 일관성이 확인되지 않았습니다."];
primaryIssue.verification_next_steps = ["비용 구조의 승인 범위를 확인"];
primaryIssue.conditional_response_refs = ["response_margin"];

bundle.final_result.conditional_responses = [
  {
    response_id: "response_margin",
    condition_template: "원가 배부 오류가 확인되면",
    direction_template: "수익성 지표를 재계산합니다.",
  },
  {
    response_id: "response_collection",
    condition_template: "회수 예정일이 승인 범위를 벗어나면",
    direction_template: "현금 보전 대응안을 다시 확인합니다.",
  },
];
```

- [ ] **Step 2: 결론 패널 RED 테스트를 작성한다**

```tsx
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnalysisConclusionPanel } from "@/features/report/AnalysisConclusionPanel";
import { makeClientReportPayload } from "@/features/report/__tests__/report-fixture";

describe("AnalysisConclusionPanel", () => {
  it("현재 문제의 정본 분석만 표시한다", () => {
    const { report } = makeClientReportPayload();
    const issue = report.final_result.issues[0];

    render(<AnalysisConclusionPanel activeIssue={issue} report={report} />);

    expect(screen.getByText(issue.primary_grade)).toBeInTheDocument();
    expect(screen.getByText(issue.title_template)).toBeInTheDocument();
    expect(screen.getByText(issue.why_it_matters_template)).toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: "원인 가설" })).getByText(
        "고정비 증가가 수익성 저하를 설명할 수 있습니다.",
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: "반대 가설" })).getByText(
        "일시적인 매출 인식 시점 차이일 수 있습니다.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("원가 배부 기준의 일관성이 확인되지 않았습니다.")).toBeInTheDocument();
    expect(screen.getByText("원가 배부 오류가 확인되면")).toBeInTheDocument();
    expect(screen.getByText("수익성 지표를 재계산합니다.")).toBeInTheDocument();
    expect(screen.queryByText("회수 예정일이 승인 범위를 벗어나면")).not.toBeInTheDocument();
  });

  it("없는 가설을 생성하지 않고 명시적 빈 상태를 표시한다", () => {
    const { report } = makeClientReportPayload();
    const issue = structuredClone(report.final_result.issues[0]);
    issue.cause_hypotheses = [];
    issue.counter_hypotheses = [];

    render(<AnalysisConclusionPanel activeIssue={issue} report={report} />);

    expect(screen.getByText("등록된 원인 가설 없음")).toBeInTheDocument();
    expect(screen.getByText("등록된 반대 가설 없음")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: 테스트가 예상대로 실패하는지 확인한다**

Run:

```text
npm --prefix web run test:focused -- src/features/report/__tests__/AnalysisConclusionPanel.test.tsx
```

Expected: `AnalysisConclusionPanel` 모듈이 없어 FAIL.

- [ ] **Step 4: 정본 필드만 투영하는 최소 패널을 구현한다**

`AnalysisConclusionPanel.tsx`는 `Issue`와 `ClientReportBundle`을 받고 응답을 참조 ID로만 연결한다.

```tsx
import type { Issue } from "../../../../contracts/web-report/v1/generated/types";

import type { ClientReportBundle } from "@/features/report/report-model";
import styles from "@/features/report/ReportWorkspace.module.css";

type AnalysisConclusionPanelProps = {
  activeIssue: Issue;
  report: ClientReportBundle;
};

export function AnalysisConclusionPanel({
  activeIssue,
  report,
}: AnalysisConclusionPanelProps) {
  const responseById = new Map(
    report.final_result.conditional_responses.map((response) => [
      response.response_id,
      response,
    ]),
  );
  const responses = activeIssue.conditional_response_refs
    .map((reference) => responseById.get(reference))
    .filter((response) => response !== undefined);

  return (
    <div className={styles.analysisPanel}>
      <article className={styles.analysisSummary}>
        <span className={styles.grade}>{activeIssue.primary_grade}</span>
        <h3>{activeIssue.title_template}</h3>
        <p className={styles.issueReason}>{activeIssue.why_it_matters_template}</p>
        {activeIssue.secondary_flags.length > 0 ? (
          <ul className={styles.analysisTagList} aria-label="보조 플래그">
            {activeIssue.secondary_flags.map((flag) => <li key={flag}>{flag}</li>)}
          </ul>
        ) : null}
      </article>

      <div className={styles.hypothesisGrid}>
        <section aria-label="원인 가설" className={styles.hypothesisPanel}>
          <h3>원인 가설</h3>
          {activeIssue.cause_hypotheses.length > 0 ? (
            <ul className={styles.analysisList}>
              {activeIssue.cause_hypotheses.map(({ claim_code }) => (
                <li key={claim_code}>{claim_code}</li>
              ))}
            </ul>
          ) : <p className={styles.empty}>등록된 원인 가설 없음</p>}
        </section>
        <section aria-label="반대 가설" className={styles.hypothesisPanel}>
          <h3>반대 가설</h3>
          {activeIssue.counter_hypotheses.length > 0 ? (
            <ul className={styles.analysisList}>
              {activeIssue.counter_hypotheses.map(({ claim_code }) => (
                <li key={claim_code}>{claim_code}</li>
              ))}
            </ul>
          ) : <p className={styles.empty}>등록된 반대 가설 없음</p>}
        </section>
      </div>

      <section className={styles.analysisBlock}>
        <h3>미해결 사항</h3>
        {activeIssue.unresolved_conflicts.length > 0 ? (
          <ul className={styles.analysisList}>
            {activeIssue.unresolved_conflicts.map((conflict) => <li key={conflict}>{conflict}</li>)}
          </ul>
        ) : <p className={styles.empty}>기록된 미해결 충돌 없음</p>}
      </section>

      <section className={styles.analysisBlock}>
        <h3>조건부 대응</h3>
        {responses.length > 0 ? (
          <ul className={styles.responseList}>
            {responses.map((response) => (
              <li key={response.response_id}>
                <strong>{response.condition_template}</strong>
                <span>{response.direction_template}</span>
              </li>
            ))}
          </ul>
        ) : <p className={styles.empty}>등록된 조건부 대응 없음</p>}
      </section>
    </div>
  );
}
```

- [ ] **Step 5: focused 테스트를 GREEN으로 만든다**

Run:

```text
npm --prefix web run test:focused -- src/features/report/__tests__/AnalysisConclusionPanel.test.tsx
```

Expected: 2 tests PASS.

- [ ] **Step 6: Task 1 파일만 커밋한다**

```text
git add web/src/features/report/AnalysisConclusionPanel.tsx web/src/features/report/__tests__/AnalysisConclusionPanel.test.tsx web/src/features/report/__tests__/report-fixture.ts
git commit -m "feat(web): add consultant conclusion panel"
```

### Task 2: 검증 계획 패널

**Files:**
- Modify: `web/src/features/report/__tests__/report-fixture.ts`
- Create: `web/src/features/report/__tests__/VerificationPlanPanel.test.tsx`
- Create: `web/src/features/report/VerificationPlanPanel.tsx`

- [ ] **Step 1: 자료 품질 격리 fixture를 추가한다**

```ts
bundle.evidence_view.data_quality = [
  {
    quality_issue_id: "quality_current_open",
    source_ref: "source_main",
    issue_code: "ambiguous_unit",
    severity: "warning",
    affected_field: "amount",
    raw_value_hash: null,
    normalized_role: "amount",
    reason_code: "unit_requires_confirmation",
    suggested_resolution: "원본 통화와 금액 단위를 확인하세요.",
    resolution_status: "open",
  },
  {
    quality_issue_id: "quality_other_open",
    source_ref: "source_other",
    issue_code: "invalid_date",
    severity: "blocking",
    affected_field: "date",
    raw_value_hash: null,
    normalized_role: "transaction_date",
    reason_code: "date_requires_confirmation",
    suggested_resolution: "다른 이슈의 날짜를 확인하세요.",
    resolution_status: "open",
  },
  {
    quality_issue_id: "quality_current_resolved",
    source_ref: "source_main",
    issue_code: "duplicate_business_key",
    severity: "info",
    affected_field: "document_id",
    raw_value_hash: null,
    normalized_role: "document_id",
    reason_code: "duplicate_reviewed",
    suggested_resolution: "이미 해소된 중복입니다.",
    resolution_status: "resolved",
  },
];
```

- [ ] **Step 2: 검증 계획 RED 테스트를 작성한다**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VerificationPlanPanel } from "@/features/report/VerificationPlanPanel";
import { makeClientReportPayload } from "@/features/report/__tests__/report-fixture";

describe("VerificationPlanPanel", () => {
  it("현재 문제에 연결된 검증 항목만 표시한다", () => {
    const { report } = makeClientReportPayload();
    render(
      <VerificationPlanPanel
        activeIssue={report.final_result.issues[0]}
        report={report}
      />,
    );

    expect(screen.getByText("비용 구조의 승인 범위를 확인")).toBeInTheDocument();
    expect(screen.getByText("법률")).toBeInTheDocument();
    expect(screen.getByText(/현재 계약 조항/)).toBeInTheDocument();
    expect(screen.getByText("원본 통화와 금액 단위를 확인하세요.")).toBeInTheDocument();
    expect(screen.queryByText("다른 이슈의 날짜를 확인하세요.")).not.toBeInTheDocument();
    expect(screen.queryByText("이미 해소된 중복입니다.")).not.toBeInTheDocument();
  });

  it("자료가 없을 때 영역별 빈 상태를 유지한다", () => {
    const { report } = makeClientReportPayload();
    const issue = structuredClone(report.final_result.issues[0]);
    issue.verification_next_steps = [];
    issue.unresolved_conflicts = [];
    issue.expert_review_refs = [];
    report.evidence_view.data_quality = [];

    render(<VerificationPlanPanel activeIssue={issue} report={report} />);

    expect(screen.getByText("등록된 다음 검증 단계 없음")).toBeInTheDocument();
    expect(screen.getByText("기록된 미해결 충돌 없음")).toBeInTheDocument();
    expect(screen.getByText("요청된 전문가 검토 없음")).toBeInTheDocument();
    expect(screen.getByText("현재 범위에 연결된 미해결 자료 제한 없음")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: 테스트가 예상대로 실패하는지 확인한다**

Run:

```text
npm --prefix web run test:focused -- src/features/report/__tests__/VerificationPlanPanel.test.tsx
```

Expected: `VerificationPlanPanel` 모듈이 없어 FAIL.

- [ ] **Step 4: closure 기반 검증 계획 패널을 구현한다**

핵심 필터는 다음과 같이 고정한다.

```ts
const closure = report.evidence_view.issue_claim_closure.find(
  (candidate) => candidate.issue_ref === activeIssue.issue_id,
);
const sourceRefs = new Set(closure?.source_refs ?? []);
const qualityItems = report.evidence_view.data_quality.filter(
  (item) =>
    item.resolution_status === "open" &&
    item.source_ref !== null &&
    sourceRefs.has(item.source_ref),
);
const packetRefs = new Set(activeIssue.expert_review_refs);
const packets = report.expert_packet_view.filter((packet) =>
  packetRefs.has(packet.expert_packet_id),
);
```

`VerificationPlanPanel.tsx`는 네 개의 `<section>`을 `다음 검증 단계`, `미해결 충돌`, `전문가 검토 경계`, `현재 자료 제한` 순서로 렌더링한다. 자료 제한에는 `suggested_resolution`, `affected_field`, `reason_code`만 표시하고 `raw_value_hash`나 로컬 경로를 표시하지 않는다.

- [ ] **Step 5: focused 테스트를 GREEN으로 만든다**

Run:

```text
npm --prefix web run test:focused -- src/features/report/__tests__/VerificationPlanPanel.test.tsx
```

Expected: 2 tests PASS.

- [ ] **Step 6: Task 2 파일만 커밋한다**

```text
git add web/src/features/report/VerificationPlanPanel.tsx web/src/features/report/__tests__/VerificationPlanPanel.test.tsx web/src/features/report/__tests__/report-fixture.ts
git commit -m "feat(web): add consultant verification plan"
```

### Task 3: 세 보조 탭과 근거 본문 재사용

**Files:**
- Create: `web/src/features/report/__tests__/ConsultantAnalysisView.test.tsx`
- Create: `web/src/features/report/ConsultantAnalysisView.tsx`
- Modify: `web/src/features/report/EvidenceWorkbench.tsx`

- [ ] **Step 1: 보조 탭 RED 테스트를 작성한다**

테스트용 controlled wrapper는 `useState<ConsultantAnalysisSection>("analysis")`를 사용한다. 다음을 assertion한다.

```tsx
const tablist = screen.getByRole("tablist", { name: "컨설턴트 분석 보기" });
expect(within(tablist).getAllByRole("tab")).toHaveLength(3);
expect(within(tablist).getByRole("tab", { name: "분석 결론" })).toHaveAttribute("aria-selected", "true");
expect(screen.getByRole("tabpanel", { name: "분석 결론" })).toBeInTheDocument();

await user.click(within(tablist).getByRole("tab", { name: "근거·출처" }));
expect(screen.getByRole("tabpanel", { name: "근거·출처" })).toBeInTheDocument();
expect(screen.getByText("뒷받침 · 관찰")).toBeInTheDocument();
expect(screen.getAllByText("수익성 점검 필요 분석 검토")).toHaveLength(1);

await user.keyboard("{ArrowRight}");
expect(within(tablist).getByRole("tab", { name: "검증 계획" })).toHaveFocus();
expect(within(tablist).getByRole("tab", { name: "검증 계획" })).toHaveAttribute("aria-selected", "true");
```

- [ ] **Step 2: 테스트가 예상대로 실패하는지 확인한다**

Run:

```text
npm --prefix web run test:focused -- src/features/report/__tests__/ConsultantAnalysisView.test.tsx
```

Expected: `ConsultantAnalysisView` 모듈이 없어 FAIL.

- [ ] **Step 3: View 타입과 공통 shell을 구현한다**

```tsx
export type ConsultantAnalysisSection =
  | "analysis"
  | "evidence"
  | "verification";

const CONSULTANT_SECTIONS = [
  { id: "analysis", label: "분석 결론" },
  { id: "evidence", label: "근거·출처" },
  { id: "verification", label: "검증 계획" },
] as const;
```

`ConsultantAnalysisView` props는 아래 계약을 사용한다.

```tsx
type ConsultantAnalysisViewProps = {
  activeEvidenceRef: string | null;
  activeIssue: Issue;
  activeView: ConsultantAnalysisSection;
  onPreviewRequest: (request: PreviewRequest) => void;
  onViewSelect: (view: ConsultantAnalysisSection) => void;
  report: ClientReportBundle;
};
```

공통 `<section>`은 제목 `${activeIssue.title_template} 분석 검토`와 `현재 범위` 배지를 한 번만 렌더링한다. 탭은 `role="tab"`, `aria-selected`, `aria-controls`, `tabIndex`를 갖고 활성 패널 하나만 DOM에 렌더링한다. `ArrowLeft`, `ArrowRight`, `Home`, `End`에서 배열의 다음 탭을 선택하고 해당 버튼에 focus한다.

- [ ] **Step 4: EvidenceWorkbench의 중복 shell을 제거한다**

`EvidenceWorkbench`의 기존 `<section>`, `<header>`와 닫는 태그를 제거하고 다음처럼 근거 본문만 반환한다.

```tsx
return (
  <div className={styles.evidenceGrid}>
    <div className={styles.evidenceMain}>{/* 기존 Evidence와 Fact */}</div>
    <aside aria-label="출처" className={styles.evidenceAside}>
      {/* 기존 Source 목록과 action */}
    </aside>
  </div>
);
```

Evidence, Fact, Source의 closure 계산과 Source preview callback은 변경하지 않는다.

- [ ] **Step 5: focused 테스트를 GREEN으로 만든다**

Run:

```text
npm --prefix web run test:focused -- src/features/report/__tests__/ConsultantAnalysisView.test.tsx
```

Expected: 보조 탭, 키보드 이동, 근거 본문과 공통 머리말 tests PASS.

- [ ] **Step 6: Task 3 파일만 커밋한다**

```text
git add web/src/features/report/ConsultantAnalysisView.tsx web/src/features/report/EvidenceWorkbench.tsx web/src/features/report/__tests__/ConsultantAnalysisView.test.tsx
git commit -m "feat(web): add consultant analysis subnavigation"
```

### Task 4: Workspace 상태·scope 통합

**Files:**
- Modify: `web/src/features/report/ReportWorkspace.tsx`
- Modify: `web/src/features/report/__tests__/ReportWorkspace.test.tsx`

- [ ] **Step 1: 통합 RED 테스트를 먼저 수정한다**

기존 첫 테스트에 다음 assertion을 추가한다.

```tsx
expect(within(navigation).getAllByRole("button")).toHaveLength(5);

await user.click(
  within(navigation).getByRole("button", { name: "컨설턴트 근거 분석" }),
);
const consultantTabs = screen.getByRole("tablist", { name: "컨설턴트 분석 보기" });
expect(within(consultantTabs).getAllByRole("tab")).toHaveLength(3);
expect(screen.getByRole("tabpanel", { name: "분석 결론" })).toBeInTheDocument();

await user.click(within(consultantTabs).getByRole("tab", { name: "검증 계획" }));
await user.click(within(navigation).getByRole("button", { name: "실행·신뢰 기록" }));
await user.click(within(navigation).getByRole("button", { name: "컨설턴트 근거 분석" }));
expect(screen.getByRole("tabpanel", { name: "검증 계획" })).toBeInTheDocument();
```

별도 테스트에서 `onScopeChange` mock을 마지막 호출 뒤 초기화하고 보조 탭만 전환한 다음 새 호출이 없음을 확인한다. 차트의 근거 버튼을 누른 뒤 `근거·출처` 탭과 해당 Evidence 카드가 동시에 활성화되는지도 고정한다.

- [ ] **Step 2: 현재 구현에서 RED를 확인한다**

Run:

```text
npm --prefix web run test:focused -- src/features/report/__tests__/ReportWorkspace.test.tsx
```

Expected: 보조 탭과 탭 유지 assertion이 FAIL.

- [ ] **Step 3: ReportWorkspace가 보조 탭 상태를 소유하게 한다**

```tsx
import {
  ConsultantAnalysisView,
  type ConsultantAnalysisSection,
} from "@/features/report/ConsultantAnalysisView";

const [activeConsultantView, setActiveConsultantView] =
  useState<ConsultantAnalysisSection>("analysis");
```

기존 `EvidenceWorkbench` 분기를 `ConsultantAnalysisView`로 교체한다. `selectEvidence()`와 `handleQuestionReference()`의 claim/evidence/source 분기에서 `setActiveConsultantView("evidence")`를 호출한다. 일반 상단 내비게이션 전환과 문제 선택에서는 보조 탭 상태를 초기화하지 않는다.

- [ ] **Step 4: focused 통합 테스트를 GREEN으로 만든다**

Run:

```text
npm --prefix web run test:focused -- src/features/report/__tests__/AnalysisConclusionPanel.test.tsx src/features/report/__tests__/VerificationPlanPanel.test.tsx src/features/report/__tests__/ConsultantAnalysisView.test.tsx src/features/report/__tests__/ReportWorkspace.test.tsx
```

Expected: 모든 focused tests PASS.

- [ ] **Step 5: Task 4 파일만 커밋한다**

```text
git add web/src/features/report/ReportWorkspace.tsx web/src/features/report/__tests__/ReportWorkspace.test.tsx
git commit -m "feat(web): integrate consultant analysis view"
```

### Task 5: 시각 계층·반응형·완료 게이트

**Files:**
- Modify: `web/src/features/report/ReportWorkspace.module.css`
- Modify: `web/src/features/report/__tests__/ConsultantAnalysisView.test.tsx`

- [ ] **Step 1: CSS class 존재와 접근성 상태를 focused test로 고정한다**

탭 테스트에서 활성 탭이 `aria-selected="true"`와 `tabIndex=0`, 비활성 탭이 `aria-selected="false"`와 `tabIndex=-1`을 갖는지 확인한다. 공통 제목이 한 번만 렌더링되는 assertion을 유지한다.

- [ ] **Step 2: B안 스타일을 추가한다**

다음 CSS 규칙을 추가하고 기존 report token만 사용한다.

```css
.analysisTabs {
  display: inline-flex;
  gap: 0.35rem;
  margin: 0 0 1.25rem;
  padding: 0.3rem;
  border: 1px solid var(--report-line);
  border-radius: 0.85rem;
  background: #f3f7f6;
}

.analysisTab {
  min-height: 2.5rem;
  padding: 0.55rem 0.85rem;
  border: 0;
  border-radius: 0.65rem;
  color: var(--report-muted);
  background: transparent;
  font: inherit;
  font-size: 0.8rem;
  font-weight: 800;
  cursor: pointer;
}

.analysisTabActive {
  color: var(--report-ink);
  background: white;
  box-shadow: 0 0.35rem 1rem rgba(16, 39, 51, 0.08);
}

.analysisPanel,
.analysisList,
.responseList,
.analysisTagList {
  display: grid;
  gap: 0.8rem;
}

.analysisSummary,
.hypothesisPanel,
.analysisBlock,
.verificationBlock {
  padding: 1rem;
  border: 1px solid var(--report-line);
  border-radius: 0.9rem;
  background: white;
}

.analysisSummary {
  border-left: 4px solid var(--report-cyan);
}

.hypothesisGrid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.analysisList,
.responseList,
.analysisTagList {
  margin: 0;
  padding: 0;
  list-style: none;
}

.analysisList li,
.responseList li {
  padding: 0.75rem;
  border-left: 3px solid var(--report-line);
  background: #f8fbfa;
  overflow-wrap: anywhere;
}

.responseList li {
  display: grid;
  gap: 0.35rem;
}

.analysisTagList {
  grid-template-columns: repeat(auto-fit, minmax(8rem, max-content));
  margin-top: 0.8rem;
}

.analysisTagList li {
  padding: 0.3rem 0.55rem;
  border-radius: 999px;
  background: var(--report-cyan-soft);
  font-size: 0.72rem;
  font-weight: 750;
  overflow-wrap: anywhere;
}
```

`@media (max-width: 58rem)`에서 `.hypothesisGrid { grid-template-columns: 1fr; }`를 추가하고, `@media (max-width: 40rem)`에서 `.analysisTabs { display: flex; width: 100%; overflow-x: auto; }`와 `.analysisTab { flex: 0 0 auto; }`를 추가한다.

- [ ] **Step 3: focused test, typecheck와 lint를 실행한다**

Run:

```text
npm --prefix web run test:focused -- src/features/report/__tests__/AnalysisConclusionPanel.test.tsx src/features/report/__tests__/VerificationPlanPanel.test.tsx src/features/report/__tests__/ConsultantAnalysisView.test.tsx src/features/report/__tests__/ReportWorkspace.test.tsx
npm --prefix web run typecheck
npm --prefix web run lint
```

Expected: 모두 exit code 0.

- [ ] **Step 4: Web 완료 게이트를 한 번 실행한다**

Run:

```text
npm --prefix web run test
npm --prefix web run build
npm --prefix web run test:e2e
```

Expected: unit, build, Playwright 모두 exit code 0.

- [ ] **Step 5: 브라우저에서 실제 화면을 확인한다**

`http://127.0.0.1:3000/report`에서 검증된 fixture를 불러온 뒤 다음을 확인한다.

- 상단 화면 5개
- 보조 탭 3개와 키보드 이동
- 문제 변경 후 현재 문제 내용만 표시
- 차트 근거 이동 시 `근거·출처` 자동 선택
- Source preview의 기존 접근 정책
- 좁은 viewport에서 가설 1열과 본문 수평 overflow 없음

- [ ] **Step 6: Task 5 파일을 커밋한다**

```text
git add web/src/features/report/ReportWorkspace.module.css web/src/features/report/__tests__/ConsultantAnalysisView.test.tsx
git commit -m "style(web): refine consultant analysis layout"
```

## Self-review result

- Spec coverage: 상단 5개 유지, 내부 3개 보조 탭, 같은 issue scope, 차트 근거 이동, 빈 상태, closure 필터, 반응형과 접근성을 Tasks 1~5에 연결했다.
- Contract boundary: WebReportBundle, plugin, converter와 Source policy는 변경하지 않는다.
- Type consistency: `ConsultantAnalysisSection`은 `ConsultantAnalysisView.tsx`에서 한 번 정의하고 `ReportWorkspace.tsx`가 import한다.
- Inference boundary: 모든 표시값은 bundle 원문이며 웹은 ID 연결, 필터링, 그룹화만 수행한다.

