# Trusted CEO Agent 대회 Fast Path Runbook

- 문서 역할: `HDF-01` 빠른 진단과 기존 HD 작업 연결을 위한 제한 운영 계약
- 기본 정책: 코드 변경 금지
- 예외 예산: `HD-02` 최대 1건, `HD-04` 최대 1건
- 금지 경로: `HD-03`
- 적용 범위: 대회 시간 안에 검증 가능한 핵심 결과를 제한 범위로 완성
- 비적용 범위: Trust Kernel, 승인, authority, 불변 revision, Validator 완화

## 1. 정본과 충돌 처리

아래 순서가 높을수록 우선한다.

1. 현재 코드가 검증하는 Schema, Trust Kernel, 불변 revision, 승인,
   authority, hash, Validator 계약
2. `docs/superpowers/specs/2026-07-17-professional-system-integration-index.md`와
   그 문서가 지정한 D01~D18
3. `docs/operations/HACKATHON_DAY_RUNBOOK.md`
4. 이 Fast Path Runbook
5. `docs/operations/prompts/HDF-01-fast-diagnose-route.md`
6. 특정 대화의 임시 지시와 모델의 추정

Fast Path는 상위 계약을 좁힐 수만 있고 완화하지 못한다. 상위 계약과 충돌하면
우회하지 않고 `BLOCKED_CONTRACT_CONFLICT`로 종료한다.

## 2. Fast Path Registry

| ID | 정확한 경로 | 책임 | 쓰기 경계 |
|---|---|---|---|
| `HDF-01` | `docs/operations/prompts/HDF-01-fast-diagnose-route.md` | 최소 읽기 전용 진단, 범위 제외, 기존 HD Prompt 선택 | 없음 |

`HDF-01` 이후 실제 작업은 기존 Prompt를 그대로 사용한다.

| 기존 ID | Fast Path에서의 용도 |
|---|---|
| `HD-02` | 핵심 열을 읽을 수 없을 때 최소 Adapter Gap 최대 1건 |
| `HD-04` | CEO 결론에 필수적인 결정적 계산 Gap 최대 1건 |
| `HD-05` | 제한된 범위를 포함한 실제 분석·HITL·최종화 |
| `HD-06` | finalized 또는 승인된 limited-finalized 결과 내보내기 |
| `HD-07` | 검증된 bundle의 공식 웹 import와 화면 확인 |

`HD-03`은 Fast Path에서 실행하지 않는다. Pack 부족을 일반 LLM 지식으로
메우지 않고 Generic 또는 Boundary 결과와 명시적 limitations로 남긴다.

## 3. 고정 정책

### 3.1 기본값

- 코드·Schema·Pack·Component를 변경하지 않는다.
- 기존 Adapter, Green 매핑, 기존 Component를 먼저 재사용한다.
- 비핵심 Gap에 의존하는 데이터·계산·Finding은 분석 범위에서 제외한다.
- 제외 후에도 CEO에게 유용한 검증 결과가 남으면 `HD-05`로 간다.
- 제한 결과는 정상 결과처럼 숨기지 않고 `LIMITED_FINALIZED` 후보로 전달한다.

### 3.2 HD-02 예외

`HD-02`는 다음을 모두 만족할 때만 최대 1건 허용한다.

1. 읽지 못하는 열이 CEO 질문과 핵심 결과에 직접 필요하다.
2. 기존 Adapter와 Green 매핑으로 의미와 lineage를 보존할 수 없다.
3. 해당 열을 제외하면 핵심 결과 자체가 성립하지 않는다.
4. 최소 필드·단위·기간·부호·locator 지원으로 변경을 닫을 수 있다.
5. 특정 Gap ID, 최소 쓰기 경로, focused RED/GREEN과 롤백 대상을 제시한다.
6. 사용자가 그 Gap ID와 쓰기 경로를 명시 승인한다.

핵심 열의 경제적 의미가 불명확하면 Adapter를 추측하지 않고
`USER_RESPONSE`로 보낸다.

### 3.3 HD-04 예외

`HD-04`는 다음을 모두 만족할 때만 최대 1건 허용한다.

1. 계산이 CEO 결론에 직접 필요하다.
2. 기존 Component 또는 검증된 조합으로 계산할 수 없다.
3. 계산을 제외하면 핵심 결과 자체가 성립하지 않는다.
4. 입력 Canonical Fact가 이미 있거나 선행 HD-02 결과로 제공된다.
5. 하나의 결정적 계약과 focused RED/GREEN으로 변경을 닫을 수 있다.
6. 사용자가 그 Gap ID와 쓰기 경로를 명시 승인한다.

LLM 계산이나 자유서술 수치를 Component 대신 사용하지 않는다.

### 3.4 예외 예산

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

- `hd02_used`와 `hd04_used`는 해당 Prompt가 성공 상태로 끝난 뒤에만 1로 바꾼다.
- 모든 Fast Path 후속 Handoff는 이 블록을 그대로 보존한다.
- `exception_sequence`는 남은 순서를 정확한 Prompt ID 배열로 보존한다.
- Any Fast Path prompt that emits `USER_RESPONSE` sets `resume_prompt_id` and
  `resume_prompt_path` to itself.
- `post_exception_prompt_id` and path force read-only re-diagnosis after an exception.
- Every Fast Path follow-up preserves prior standard Handoff fields as well as
  `fast_path`; empty arrays in a base HD output template do not erase prior evidence.
- `pending_exception` carries one proposed `ADAPTER` or `COMPONENT` Gap with its
  evidence, minimum write paths, and any Component/Canonical Fact/Pack refs.
  Proposal metadata is not approval.
- Before `HD-04`, copy the validated refs from `pending_exception` into the matching
  HD-04 input arrays; do not ask the user to re-enter refs already present.
- `diagnostic_context` preserves the CEO question, minimum useful result, scope, and
  core columns/calculations across `HD-02`, re-diagnosis, and `USER_RESPONSE`.
- `fast_path` is a prompt-specific Handoff extension permitted by the base Runbook.
  Base HD output enums remain unchanged; a non-null post-exception path is an overlay
  selected only by this Fast Path Runbook.
- A successful exception increments only its matching `used` field and clears
  `pending_exception`; a blocked or clarification result consumes no budget.
- Exception success is exact: `HD-02` must return `ADAPTER_READY`, or `HD-04` must
  return `COMPONENT_READY`. Every other status keeps `used` unchanged and must not
  consume `post_exception_prompt_path`.
- 사용한 예산을 되돌리거나 새 대화에서 0으로 초기화하지 않는다.
- 예산 소진 후 추가 변경이 필요하면 관련 분석을 제외한다. 제외하면 핵심
  결과가 성립하지 않는 경우 `STOP`한다.
- Fast Path 선택은 아직 발견되지 않은 Gap의 포괄 승인이 아니다.

## 4. 라우팅

```text
HDF-01
  ├─ 기존 기능 또는 Green 매핑으로 충분
  │    └─ HD-05
  ├─ 비핵심 Gap만 존재
  │    └─ 의존 분석 제외 + Generic/Boundary → HD-05
  ├─ 핵심 열을 읽을 수 없음
  │    └─ HD-02 최대 1건 → HD-05
  ├─ 필수 계산이 없음
  │    └─ HD-04 최대 1건 → HD-05
  ├─ 핵심 열과 필수 계산이 모두 없음
  │    └─ HD-02 최대 1건 → HDF-01 재진단 → HD-04 최대 1건 → HD-05
  ├─ 핵심 경제적 의미 확인 필요
  │    └─ USER_RESPONSE 후 HDF-01 재진단
  └─ 예외 예산으로도 핵심 결과 불성립
       └─ STOP
```

HD-02와 HD-04가 모두 필요하면 구조적 입력을 담당하는 HD-02를 먼저
실행한다. Fast Path는 한 번에 하나의 다음 Prompt만 지정한다.
The combined branch is binding and re-diagnoses after Adapter work:
`HDF-01 -> HD-02 -> HDF-01 -> HD-04 -> HD-05`.

Valid end-to-end routes:

```text
HDF-01 -> HD-05
HDF-01 -> HD-02 -> HD-05
HDF-01 -> HD-04 -> HD-05
HDF-01 -> HD-02 -> HDF-01 -> HD-04 -> HD-05
HDF-01 -> USER_RESPONSE -> HDF-01
HDF-01 -> STOP
```

## 5. HDF-01 종료 상태

- `FAST_GO`: 변경 없이 `HD-05` 진행
- `FAST_LIMITED_GO`: 제외 범위와 Generic·Boundary 한계로 `HD-05` 진행
- `FAST_EXCEPTION_REQUIRED`: 특정 `HD-02` 또는 `HD-04` Gap 승인 필요
- `NEEDS_USER_CLARIFICATION`: 핵심 열의 경제적 의미 확인 필요
- `NO_GO`: 예외 예산으로도 핵심 결과 불가능
- `BLOCKED_CONTRACT_CONFLICT`: 상위 계약과 실행 계약 충돌

제한 범위를 합법적으로 제외할 수 있다는 사실과 required 실패를 혼동하지
않는다. required 실패, 무결성 실패, 분석 저장 실패는 limited 성공이 아니다.

### Common output

`HDF-01` outputs `NEXT_DECISION` followed by `HANDOFF`.
Fast Path follow-up HD prompts preserve both contracts and the `fast_path` block.

## 6. 후속 Prompt 실행 규칙

Fast Path의 기존 HD Prompt를 실행할 때 다음 파일을 순서대로 읽는다.

1. 이 Fast Path Runbook
2. `docs/operations/HACKATHON_DAY_RUNBOOK.md`
3. 아래 순서로 선택한 `effective_prompt_id`와 `effective_prompt_path`의 정확한 파일
   - `next_prompt_id=USER_RESPONSE`: 답변을 받은 뒤 `resume_prompt_id/path`
   - 성공한 HD-02/04이고 post-exception pair가 non-null: 그 overlay ID/path
   - 그 외: `HANDOFF.next_prompt_id/path`

먼저 원본 Handoff hash를 변경 없이 검증한 뒤 effective ID/path를 파생한다.
대상 Prompt의 진입 Gate는 원본 `next_prompt_id/path` 대신 이 effective pair와
실행할 Prompt를 대조하고, overlay 선택 조건도 함께 검증한다. 원본 Handoff의
hashed 필드는 재작성하지 않는다. 기존 Prompt의 쓰기 경계, 승인, 테스트,
완료 Gate는 그대로 적용한다.

입력 hydrate 순서는 binding이다.

1. 직전 Handoff의 공통 필드와 `fast_path.diagnostic_context`를 복원한다.
2. 명시적인 non-null 현재 입력만 같은 필드를 덮어쓴다. 템플릿의 null, 빈
   배열, 빈 객체는 기존 값을 지우지 않는다.
3. `revision`은 HD-05의 `expected_revision`으로 전달한다.
4. `artifact_root`가 없으면 `<project_root>/artifacts`를 결정적 기본값으로
   사용하되 `data_path`와 겹치지 않는지 먼저 검증한다.
5. `resolved_field_meanings`는 HD-02의 `field_meaning_answers`로 전달한다.
6. HD-04의 세 참조 배열은 현재 `pending_exception`에서 전달한다.
7. 현재 Prompt의 `approved_gap_ids`, `approval_refs`, `approved_write_paths`에는
   현재 pending Gap의 정확한 승인만 넣는다. 과거 승인 이력과 합치지 않는다.

추가로 다음을 지킨다.

- 선행 `fast_path` 블록과 예산을 검증하고 다음 Handoff에 보존한다.
- 대상 HD Prompt의 기본 출력 예시에 `fast_path`가 없어도, 출력 HANDOFF에는
  입력받은 확장 블록을 반드시 추가하고 위 규칙에 따른 값만 갱신한다.
- Overlay ID/path는 base `next_prompt_id/path`나 `prompts_after_success`에 넣지
  않는다. 이 세 base 필드는 대상 HD Prompt가 원래 허용하는 enum 안에 둔다.
- HDF-01이 확정한 `excluded_gap_ids`, `excluded_analysis_scopes`,
  `generic_boundary_required`를 확대하거나 누락하지 않는다.
- HD-05는 이 제외 범위와 Generic/Boundary 요구를 hard scope로 적용하며,
  제외된 데이터·계산·Finding을 다시 도입하지 않는다.
- HD-02·HD-04는 승인된 단일 Gap 밖의 편의성 변경을 함께 하지 않는다.
- 성공한 예외만 해당 `used` 값을 1로 바꾸고 다음 `exception_sequence` 항목으로
  이동한다.
- 기존 Prompt가 차단 상태로 끝나면 Fast Path가 약한 성공으로 바꾸지 않는다.

## 7. 성능 규칙

- HDF-01은 테스트를 실행하지 않는다. 마지막 확인 가능한 테스트 기준선을
  증거로만 기록하며 미실행 테스트를 통과로 쓰지 않는다.
- 위치 탐색은 `rg`와 `rg --files`를 사용한다.
- CEO 질문과 핵심 열에 관련된 Adapter, Registry, Schema, Component만 읽는다.
- 전체 구현 디렉터리, 전체 테스트, 전체 로그를 반복해서 출력하지 않는다.
- 데이터는 구조와 핵심 열 판단에 필요한 최소 범위만 읽는다.
- 독립 읽기만 병렬화하고 쓰기·patch·검증 흐름은 하나만 유지한다.
- 같은 권한·sandbox·spawn 실패를 상태 변화 없이 재실행하지 않는다.
- HD-02·HD-04는 focused RED/GREEN을 먼저 실행한다.
- HD-05 finalization, Validator, HD-06 내보내기 검증, HD-07 웹 import 검증은
  생략하지 않는다.

## 8. 운영체제 경계

- 현재 운영체제와 `project_root`, `data_path`, `artifact_root` 절대경로를
  각 새 대화에서 확인한다.
- macOS에서는 POSIX 경로와 준비된 Python 3.11 환경을 사용한다.
- Windows에서 복사한 `.venv`, `node_modules`, 드라이브 문자 경로를
  macOS에서 재사용하지 않는다.
- `--frozen --offline --no-sync`는 사전 준비된 환경의 preflight가 성공한
  뒤에만 사용한다.

## 9. 최초 입력 프롬프트

아래 블록을 새 Codex 대화에 복사한다.

```text
다음 파일을 순서대로 완전히 읽고 HDF-01 Fast Path 진단을 실행하세요.

1. docs/operations/HACKATHON_FAST_PATH_RUNBOOK.md
2. docs/operations/prompts/HDF-01-fast-diagnose-route.md

Fast Path 고정 정책:
- 기본 코드 변경 금지
- 핵심 열을 읽을 수 없을 때만 HD-02 최대 1건
- CEO 결론에 직접 필요한 계산만 HD-04 최대 1건
- HD-03 실행 금지, Pack 부족은 Generic/Boundary로 제한
- 비핵심 Gap은 관련 분석에서 제외
- 예외 예산으로도 핵심 결과가 성립하지 않으면 STOP

[변수]
data_path: "<macOS의 실제 절대 데이터 경로>"
project_root: "<macOS의 실제 절대 저장소 경로>"
artifact_root: null
company: null
industry: null
analysis_goal: null
ceo_question: null
analysis_period: null
as_of_date: null
known_constraints: []
```

## 10. 후속 입력 프롬프트

HDF-01 또는 후속 HD Prompt가 출력한 완전한 Handoff를 아래에 붙인다.

```text
다음 파일을 순서대로 완전히 읽고 Fast Path HANDOFF가 지정한 Prompt를
실행하세요.

1. docs/operations/HACKATHON_FAST_PATH_RUNBOOK.md
2. docs/operations/HACKATHON_DAY_RUNBOOK.md
3. Choose exactly one effective Prompt ID/path pair with this precedence:
   - when `HANDOFF.next_prompt_id` is `USER_RESPONSE`, supply the answer and use
     `HANDOFF.fast_path.resume_prompt_id` plus `resume_prompt_path`;
   - otherwise, after a successful `HD-02` or `HD-04`, use the non-null
     `HANDOFF.fast_path.post_exception_prompt_id` plus `post_exception_prompt_path`;
   - otherwise use `HANDOFF.next_prompt_id` plus `HANDOFF.next_prompt_path`.
   `USER_RESPONSE` always wins over an unconsumed post-exception pair. Verify the
   original hash first, do not mutate it, never dereference null, and clear a
   consumed overlay pair in the next Handoff.

Fast Path 규칙:
- HANDOFF.fast_path 예산과 제외 범위를 검증하고 보존
- HD-03 실행 금지
- 승인된 HD-02·HD-04 단일 Gap 밖의 변경 금지
- 기존 Prompt의 승인·검증·완료 Gate 유지

[변수]
prior_handoff:
<완전한 HANDOFF 블록>

additional_user_input:
  user_response: null
approved_gap_ids: []
approval_refs: []
approved_write_paths: []
field_meaning_answers: {}
component_contract_refs: []
canonical_fact_refs: []
pack_procedure_refs: []
artifact_root: null
run_id: null
expected_revision: null
mission_contract_path: null
approved_release_refs: []
approved_scope_ref: null
accounting_input_path: null
professional_input_path: null
```

Yellow 예외 승인이 필요하면 HDF-01이 출력한 정확한 Gap ID와 쓰기 경로를
위 배열에 넣는다. 포괄 승인이나 단순 “진행”으로 Gap 범위를 확대하지 않는다.

## 11. 종료 원칙

- `FAST_GO`, `FAST_LIMITED_GO`는 지정된 `HD-05`를 실행할 수 있다는 뜻이다.
- `FAST_EXCEPTION_REQUIRED`는 특정 Gap 승인 전까지 수정하지 않는다.
- `NEEDS_USER_CLARIFICATION`은 답변 후 HDF-01을 다시 실행한다.
- `NO_GO`, `STOP`, `BLOCKED_CONTRACT_CONFLICT`는 우회하지 않는다.
- 빠른 실행은 범위를 줄이는 것이며 검증 강도나 신뢰 경계를 줄이는 것이 아니다.
