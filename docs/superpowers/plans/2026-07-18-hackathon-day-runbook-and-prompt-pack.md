# Hackathon Day Runbook and Prompt Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 승인된 대회 당일 운영 설계를 실제 Runbook과 HD-01~HD-07 실행 계약으로 구현하고, 분석 저장·웹 투영 한계·다음 의사결정을 새 대화에서도 복원 가능하게 만든다.

**Architecture:** Runbook은 정본 우선순위, 라우팅, 공통 안전 규칙, `NEXT_DECISION`과 `HANDOFF` 형식을 한 번만 정의한다. 개별 HD 프롬프트는 변수 입력과 단일 작업 계약만 가지며, HD-05는 불변 Artifact 저장을, HD-06은 무추론 변환과 투영 Coverage를, HD-07은 웹 게시와 실제 화면 검증을 책임진다.

**Tech Stack:** Markdown 운영 계약, Trusted CEO Agent CLI·ArtifactStore·WebReportBundle v1, PowerShell 정적 검증

---

### Task 1: 승인 설계에 누락된 운영 Gate 고정

**Files:**
- Modify: `docs/superpowers/specs/2026-07-18-hackathon-day-runbook-and-prompt-pack-design.md`

- [ ] **Step 1: 상태를 구현 대상 설계로 명확히 유지**

설계가 실제 파일의 존재를 의미하지 않음을 명시하고, 구현 완료 여부는 `docs/operations/` 파일과 정적 검증으로만 판단하게 한다.

- [ ] **Step 2: 공통 `NEXT_DECISION` 계약 추가**

모든 프롬프트가 유효한 선택지, 선택 이유·대가, 권장안, 권장 이유, 승인 필요 여부, 사용자의 정확한 다음 행동, 다음 Prompt ID·경로를 출력하도록 고정한다. 불법·Red 선택지는 옵션으로 제시하지 않는다.

- [ ] **Step 3: HD-05 Analysis Persistence Gate 추가**

다음 Artifact가 같은 run/revision에 저장·검증되지 않았거나 실질적 분석이 대화에만 있으면 `BLOCKED_ANALYSIS_PERSISTENCE`로 종료하도록 고정한다.

```text
analysis/professional/runtime-result.json
analysis/professional/signal-cases.json
analysis/professional/findings.json
analysis/professional/relations.json
analysis/professional/issue-clusters.json
analysis/professional/completion-assessment.json
analysis/professional/grading-inputs.json
analysis/professional/grade-records.json
analysis/professional/execution-authority.json
final/structured-output.json
final/result.json
final/ceo-brief.md
```

- [ ] **Step 4: HD-06 Projection Coverage Gate와 HD-07 화면 Gate 추가**

HD-06은 저장 Artifact→Final Result→WebReportBundle 매핑과 비투영 필드를 보고하고, chat-only 내용을 내보내지 않는다. HD-07은 상단 다섯 화면과 `분석 결론·근거·출처·검증 계획` 내부 화면을 확인한다.

### Task 2: 정본 Runbook 구현

**Files:**
- Create: `docs/operations/HACKATHON_DAY_RUNBOOK.md`

- [ ] **Step 1: 정본·충돌·공통 안전 규칙 작성**

코드 Schema·Trust Kernel, D01~D18 통합 인덱스, Runbook, 개별 HD 프롬프트 순으로 우선하며 충돌 시 `BLOCKED_CONTRACT_CONFLICT`로 종료한다.

- [ ] **Step 2: HD-01~HD-07 Registry와 라우팅 작성**

모든 Prompt ID, 정확한 상대경로, 진입 조건, 성공·차단 상태, 쓰기 범위, 정상·복합 경로를 정의한다.

- [ ] **Step 3: `NEXT_DECISION`과 `HANDOFF` 정본 작성**

`HANDOFF`에는 `analysis_artifact_refs`, `projection_coverage`, `limitations`를 포함하고, 새 대화는 ID·경로·run/revision 불일치 시 실행하지 않는다.

- [ ] **Step 4: 최초·후속 대화용 짧은 부트스트랩 작성**

사용자가 긴 본문을 복사하지 않고 Runbook, Prompt 파일, 변수 블록 또는 직전 Handoff만 전달하도록 한다.

### Task 3: 진단과 조건부 변경 프롬프트 구현

**Files:**
- Create: `docs/operations/prompts/HD-01-diagnose-route.md`
- Create: `docs/operations/prompts/HD-02-adapter-change.md`
- Create: `docs/operations/prompts/HD-03-provisional-pack.md`
- Create: `docs/operations/prompts/HD-04-deterministic-component.md`

- [ ] **Step 1: HD-01 작성**

필수 변수는 `data_path` 하나로 두고 회사·업종·목표·CEO 질문·기간·제약은 선택값으로 받는다. 저장소와 데이터를 읽기 전용으로 조사하고 승인 전에는 수정하지 않는다.

- [ ] **Step 2: HD-02 작성**

승인된 `ADAPTER` Gap ID만 처리하며 원본 불변, Canonical mapping, 단위·부호·기간, locator·lineage, 평가불가 조건과 회귀검증을 요구한다.

- [ ] **Step 3: HD-03 작성**

승인된 `PACK` Gap ID만 처리하며 D1~D12, Method·Norm·Expectation·Procedure·Counter-Hypothesis·Evidence·Trigger·authority·Oracle을 요구하고 Provisional 상한을 유지한다.

- [ ] **Step 4: HD-04 작성**

승인된 `COMPONENT` Gap ID만 처리하며 Decimal·단위·기간·부호·lineage·결정성·순차/병렬 동등성을 요구하고 Component가 전문 결론을 만들지 못하게 한다.

- [ ] **Step 5: 네 프롬프트의 종료 계약 작성**

각 파일은 공통 `NEXT_DECISION`과 `HANDOFF`를 출력하고, 성공·질문·차단별 유효 선택지만 제시한다.

### Task 4: 분석·변환·게시 프롬프트 구현

**Files:**
- Create: `docs/operations/prompts/HD-05-analysis-hitl-finalize.md`
- Create: `docs/operations/prompts/HD-06-export-web-report.md`
- Create: `docs/operations/prompts/HD-07-publish-tab2.md`

- [ ] **Step 1: HD-05 분석·HITL·종료 흐름 작성**

공식 플러그인 Skill과 Workflow를 사용하고, 사용자 답변은 `preview-human-response` 후 `submit-human-response`로 새 revision에 저장한다. 모든 required Case의 terminal disposition과 Completion·Final Validator·TTY 승인을 요구한다.

- [ ] **Step 2: HD-05 Analysis Persistence Gate 작성**

필수 Artifact의 존재, 같은 run/revision, 참조 폐쇄성, hash/validator 증거를 검사한다. Handoff에 Artifact 경로·식별자·검증 증거를 남기며 chat-only 결론이 있으면 finalization 성공으로 보고하지 않는다.

- [ ] **Step 3: HD-06 내보내기와 Projection Coverage 작성**

`exports/<run_id>/revision-<revision>/web-report-bundle.json`에 새 파일을 만들고 `validate`, render byte-equivalence, `export-web-report`, `validate-web-report`를 실행한다. 저장됐지만 공개 bundle에 매핑되지 않은 필드는 `projection_coverage.omitted`와 `limitations`에 기록한다.

- [ ] **Step 4: HD-07 게시·검증 작성**

검증된 단일 번들을 공식 웹 import 경로로 업로드하고 run ID·revision·bundle hash, 상단 다섯 화면, 컨설턴트 내부 세 화면을 확인한다. 실패 시 기존 ReportStore를 유지한다.

### Task 5: README 운영 진입점 보강

**Files:**
- Modify: `README.md`
- Modify: `web/README.md`

- [ ] **Step 1: 루트 README에 대회 당일 운영 절 추가**

Runbook 링크, 짧은 최초 실행 입력, 조건부 경로, HD-05 저장 원칙, HD-06 출력 경로, 수동 업로드·HD-07을 설명한다.

- [ ] **Step 2: 투영 범위와 한계를 명시**

탭 2는 저장·검증되고 Converter가 WebReportBundle에 매핑한 공개 데이터만 표시한다. 대화 전용 내용과 비공개 중간 Artifact는 표시하지 않으며 웹이 누락 내용을 새로 추론하지 않는다고 명시한다.

- [ ] **Step 3: 저장소 구조와 문서 읽기 순서 갱신**

`docs/operations/`와 Runbook·Prompt Pack을 추가한다.

- [ ] **Step 4: Web README에 import 계약 추가**

`/report`, 정확한 파일명, 50 MiB 제한, 다섯 화면과 컨설턴트 내부 세 화면, 검증 실패 시 기존 결과 보존을 설명한다.

### Task 6: 정적 검증과 운영 경로 시뮬레이션

**Files:**
- Verify only: `docs/operations/HACKATHON_DAY_RUNBOOK.md`
- Verify only: `docs/operations/prompts/HD-01-diagnose-route.md`
- Verify only: `docs/operations/prompts/HD-02-adapter-change.md`
- Verify only: `docs/operations/prompts/HD-03-provisional-pack.md`
- Verify only: `docs/operations/prompts/HD-04-deterministic-component.md`
- Verify only: `docs/operations/prompts/HD-05-analysis-hitl-finalize.md`
- Verify only: `docs/operations/prompts/HD-06-export-web-report.md`
- Verify only: `docs/operations/prompts/HD-07-publish-tab2.md`

- [ ] **Step 1: 파일·ID·경로·공통 계약 검사**

```powershell
$files = Get-ChildItem docs/operations/prompts/HD-0*.md
if ($files.Count -ne 7) { throw "expected seven HD prompts" }
$files | ForEach-Object {
  $id = $_.BaseName.Substring(0, 5)
  $text = Get-Content -Raw -Encoding utf8 $_.FullName
  foreach ($required in @($id, "HACKATHON_DAY_RUNBOOK.md", "NEXT_DECISION:", "HANDOFF:")) {
    if (-not $text.Contains($required)) { throw "$($_.Name): missing $required" }
  }
}
```

Expected: exit 0.

- [ ] **Step 2: Persistence·Projection·게시 Gate 검사**

```powershell
$hd05 = Get-Content -Raw -Encoding utf8 docs/operations/prompts/HD-05-analysis-hitl-finalize.md
$hd06 = Get-Content -Raw -Encoding utf8 docs/operations/prompts/HD-06-export-web-report.md
$hd07 = Get-Content -Raw -Encoding utf8 docs/operations/prompts/HD-07-publish-tab2.md
foreach ($term in @("BLOCKED_ANALYSIS_PERSISTENCE", "runtime-result.json", "final/result.json")) {
  if (-not $hd05.Contains($term)) { throw "HD-05 missing $term" }
}
foreach ($term in @("projection_coverage", "validate-web-report", "web-report-bundle.json")) {
  if (-not $hd06.Contains($term)) { throw "HD-06 missing $term" }
}
foreach ($term in @("최고경영자 의사결정 요약", "컨설턴트 근거 분석", "분석 결론", "근거·출처", "검증 계획")) {
  if (-not $hd07.Contains($term)) { throw "HD-07 missing $term" }
}
```

Expected: exit 0.

- [ ] **Step 3: 문서 링크와 placeholder 검사**

Runbook과 README의 상대경로가 실제 파일을 가리키는지 확인하고, 사용자 입력 블록 밖에 `TBD`, `TODO`, “앞 단계”, “5번 결과”가 없는지 `rg`로 검사한다.

- [ ] **Step 4: 여섯 운영 경로를 수동 시뮬레이션**

```text
HD-01 → HD-05 → HD-06 → MANUAL_UPLOAD
HD-01 → HD-02 → HD-05 → HD-06
HD-01 → HD-03 → HD-04 → HD-05 → HD-06
HD-01 → USER_RESPONSE → HD-02 → HD-05
HD-01 → STOP
HD-06 → HD-07
```

각 경로에서 Prompt ID·경로·승인·run/revision이 Handoff만으로 복원돼야 한다.
