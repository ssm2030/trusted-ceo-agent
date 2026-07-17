# Hackathon Fast Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 HD-01~HD-07을 수정하지 않고 신규 구현 예산을 HD-02 1건과 HD-04 1건으로 제한하는 빠른 읽기 전용 진단 경로를 추가한다.

**Architecture:** 새 `HACKATHON_FAST_PATH_RUNBOOK.md`가 기존 Runbook보다 좁은 실행 정책과 Handoff 예산을 정의하고, 새 `HDF-01-fast-diagnose-route.md`가 최소 진단 후 기존 HD-02·04·05로 라우팅한다. HD-03은 금지하고 Pack 부족은 Generic·Boundary와 명시적 limitations로 보존한다.

**Tech Stack:** Markdown 운영 계약, 기존 `NEXT_DECISION`·`HANDOFF` 형식, PowerShell 정적 검증

---

### Task 1: 구현 전 정적 RED 확인

**Files:**
- Verify missing: `docs/operations/HACKATHON_FAST_PATH_RUNBOOK.md`
- Verify missing: `docs/operations/prompts/HDF-01-fast-diagnose-route.md`

- [x] **Step 1: 신규 파일 부재로 검사가 실패하는지 확인**

```powershell
$required = @(
  "docs/operations/HACKATHON_FAST_PATH_RUNBOOK.md",
  "docs/operations/prompts/HDF-01-fast-diagnose-route.md"
)
$missing = $required | Where-Object { -not (Test-Path -LiteralPath $_) }
if ($missing.Count -ne 0) {
  throw "Fast Path files missing: $($missing -join ', ')"
}
```

Expected: non-zero exit와 두 신규 경로가 포함된 `Fast Path files missing`.

### Task 2: Fast Path Runbook 구현

**Files:**
- Create: `docs/operations/HACKATHON_FAST_PATH_RUNBOOK.md`

- [x] **Step 1: 정본·적용 범위·예외 예산 작성**

문서 머리말에 다음 고정 계약을 작성한다.

```markdown
# Trusted CEO Agent 대회 Fast Path Runbook

- Prompt ID: `HDF-01`
- 기본 정책: 코드 변경 금지
- 예외 예산: `HD-02` 최대 1건, `HD-04` 최대 1건
- 금지 경로: `HD-03`
- 변경 불가: Trust Kernel, 승인, authority, 불변 revision, Validator
```

정본 우선순위는 코드·통합 정본·기존 Runbook·Fast Path Runbook·Prompt 순으로
고정하고 충돌 상태를 `BLOCKED_CONTRACT_CONFLICT`로 정의한다.

- [x] **Step 2: 라우팅과 예외 조건 작성**

다음 여섯 경로와 HD-02·HD-04의 필요조건을 그대로 작성한다.

```text
HDF-01 → HD-05
HDF-01 → HD-02 → HD-05
HDF-01 → HD-04 → HD-05
HDF-01 → HD-02 → HDF-01 → HD-04 → HD-05
HDF-01 → USER_RESPONSE → HDF-01
HDF-01 → STOP
```

HD-03은 어떤 경로에도 넣지 않고 Pack 부족은 Generic·Boundary로 제한한다.

- [x] **Step 3: Handoff 확장과 예산 보존 작성**

기존 Handoff에 다음 블록을 추가하고 모든 Fast Path 후속 작업이 값을 보존하게
한다.

```yaml
fast_path:
  policy_version: "1.0"
  hd02_budget: 1
  hd02_used: 0
  hd04_budget: 1
  hd04_used: 0
  hd03_allowed: false
  generic_boundary_required: false
  excluded_gap_ids: []
  excluded_analysis_scopes: []
  exception_sequence: []
  resume_prompt_id: null
  resume_prompt_path: null
  post_exception_prompt_id: null
  post_exception_prompt_path: null
  pending_exception:
    gap_id: null
    gap_type: null
    evidence_refs: []
    proposed_write_paths: []
    component_contract_refs: []
    canonical_fact_refs: []
    pack_procedure_refs: []
  diagnostic_context:
    company: null
    industry: null
    analysis_goal: null
    ceo_question: null
    analysis_period: null
    as_of_date: null
    known_constraints: []
    core_ceo_question: null
    minimum_useful_result: null
    core_columns: []
    core_calculations: []
    excluded_by_default: []
    resolved_field_meanings: {}
```

- [x] **Step 4: 최초·후속 사용자 입력 템플릿 작성**

최초 입력은 Fast Runbook과 HDF-01을 읽고 절대 `data_path`를 받는다. 후속
입력은 Fast Runbook과 기존 Runbook을 읽고, hash 검증 후 resume/post-exception
overlay 또는 base next 필드에서 effective Prompt ID/path를 하나 파생한다.
완전한 Handoff와 특정 Gap 승인을 받고 Windows 경로를 macOS에서 재검증한다.

### Task 3: HDF-01 빠른 진단 Prompt 구현

**Files:**
- Create: `docs/operations/prompts/HDF-01-fast-diagnose-route.md`

- [x] **Step 1: 입력·읽기 전용 Hard Gate 작성**

다음 입력을 정의한다.

```yaml
data_path: "<absolute data path>"
project_root: "<absolute repository path or null>"
company: null
industry: null
analysis_goal: null
ceo_question: null
analysis_period: null
as_of_date: null
known_constraints: []
```

HDF-01이 코드, 설정, 데이터, snapshot, run과 Artifact를 수정하거나 만들지
못하게 한다.

- [x] **Step 2: 최소 진단과 Gap 분류 작성**

핵심 열, 기존 Adapter·Green 매핑, 필수 결정적 계산, Generic·Boundary 가능성만
조사한다. Gap은 다음 다섯 분류로 제한한다.

```text
REUSE_OR_GREEN
EXCLUDE_AND_LIMIT
CORE_ADAPTER_EXCEPTION
CORE_COMPONENT_EXCEPTION
STOP_REQUIRED
```

전체 테스트 실행, 전체 구현 디렉터리·로그 반복 읽기와 선택적 개선 Gap 생성을
금지한다.

- [x] **Step 3: 단일 다음 경로와 특정 승인 작성**

HD-02 또는 HD-04가 필요하면 안정적인 Gap ID, 실제 근거, 최소 쓰기 경로,
focused RED/GREEN, 롤백 대상과 사용자가 복사할 정확한 승인 문장을 출력한다.
포괄 승인은 허용하지 않는다.

- [x] **Step 4: NEXT_DECISION과 HANDOFF 작성**

종료 상태를 `FAST_GO`, `FAST_LIMITED_GO`, `FAST_EXCEPTION_REQUIRED`,
`NEEDS_USER_CLARIFICATION`, `NO_GO`, `BLOCKED_CONTRACT_CONFLICT`로 제한한다.
기존 공통 필드를 유지하고 `fast_path` 블록을 포함한다.

### Task 4: 정적 GREEN과 경로 시뮬레이션

**Files:**
- Verify: `docs/operations/HACKATHON_FAST_PATH_RUNBOOK.md`
- Verify: `docs/operations/prompts/HDF-01-fast-diagnose-route.md`
- Verify unchanged: `docs/operations/prompts/HD-01-diagnose-route.md`
- Verify unchanged: `docs/operations/prompts/HD-02-adapter-change.md`
- Verify unchanged: `docs/operations/prompts/HD-03-provisional-pack.md`
- Verify unchanged: `docs/operations/prompts/HD-04-deterministic-component.md`
- Verify unchanged: `docs/operations/prompts/HD-05-analysis-hitl-finalize.md`
- Verify unchanged: `docs/operations/prompts/HD-06-export-web-report.md`
- Verify unchanged: `docs/operations/prompts/HD-07-publish-tab2.md`

- [x] **Step 1: 파일·ID·필수 계약 검사**

```powershell
$runbook = Get-Content -Raw -Encoding utf8 docs/operations/HACKATHON_FAST_PATH_RUNBOOK.md
$prompt = Get-Content -Raw -Encoding utf8 docs/operations/prompts/HDF-01-fast-diagnose-route.md
foreach ($term in @("HDF-01", "HD-02", "HD-04", "HD-03", "Generic", "Boundary", "fast_path", "NEXT_DECISION", "HANDOFF")) {
  if (-not $runbook.Contains($term)) { throw "Runbook missing $term" }
  if (-not $prompt.Contains($term)) { throw "HDF-01 missing $term" }
}
```

Expected: exit 0.

- [x] **Step 2: 예산과 금지 경로 검사**

```powershell
foreach ($text in @($runbook, $prompt)) {
  foreach ($term in @("hd02_budget: 1", "hd04_budget: 1", "hd03_allowed: false")) {
    if (-not $text.Contains($term)) { throw "Missing policy $term" }
  }
}
if ($runbook -match "HDF-01\s*(?:→|->)\s*HD-03") {
  throw "Fast Path must not route to HD-03"
}
```

Expected: exit 0.

- [x] **Step 3: 기존 HD 파일 비변경 확인**

```powershell
git diff --exit-code -- docs/operations/prompts/HD-01-diagnose-route.md docs/operations/prompts/HD-02-adapter-change.md docs/operations/prompts/HD-03-provisional-pack.md docs/operations/prompts/HD-04-deterministic-component.md docs/operations/prompts/HD-05-analysis-hitl-finalize.md docs/operations/prompts/HD-06-export-web-report.md docs/operations/prompts/HD-07-publish-tab2.md
```

Expected: 이 작업으로 생긴 diff가 없음. 기존 사용자 변경은 그대로 보존한다.

- [x] **Step 4: 문서 품질 검사**

```powershell
rg -n "TBD|TODO|앞 단계|5번 결과" docs/operations/HACKATHON_FAST_PATH_RUNBOOK.md docs/operations/prompts/HDF-01-fast-diagnose-route.md
git diff --check -- docs/operations/HACKATHON_FAST_PATH_RUNBOOK.md docs/operations/prompts/HDF-01-fast-diagnose-route.md
```

Expected: placeholder 검색 결과 없음, `git diff --check` exit 0.

- [x] **Step 5: 구현 파일만 커밋**

```powershell
git add docs/operations/HACKATHON_FAST_PATH_RUNBOOK.md docs/operations/prompts/HDF-01-fast-diagnose-route.md
git commit -m "docs: add hackathon fast path"
```
