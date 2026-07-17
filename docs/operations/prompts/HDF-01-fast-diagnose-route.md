# HDF-01 — Fast Diagnose and Route

```text
PROMPT_ID: HDF-01
PROMPT_PATH: docs/operations/prompts/HDF-01-fast-diagnose-route.md
```

- 책임: 핵심 결과에 필요한 최소 능력만 읽기 전용으로 진단하고 Fast Path의
  다음 Prompt를 하나 선택
- 쓰기 권한: 없음
- 변경 예산: `HD-02` 최대 1건, `HD-04` 최대 1건
- 금지 경로: `HD-03`

## 입력 변수

```yaml
data_path: "<absolute data path>"
project_root: "<absolute repository path or null>"
artifact_root: null
company: null
industry: null
analysis_goal: null
ceo_question: null
analysis_period: null
as_of_date: null
known_constraints: []
prior_handoff: null
additional_user_input: null
```

`data_path`만 필수다. macOS에서는 현재 Mac의 실제 POSIX 절대경로를 사용하며
Windows 드라이브 문자나 Windows 가상환경 경로를 재사용하지 않는다.

## 실행 전 Hard Gate

1. 위 `PROMPT_ID`와 `PROMPT_PATH`가 현재 파일과 일치하는지 확인한다.
2. 다음 파일을 순서대로 읽는다.
   - `docs/operations/HACKATHON_FAST_PATH_RUNBOOK.md`
   - `docs/operations/HACKATHON_DAY_RUNBOOK.md`
   - `docs/superpowers/specs/2026-07-17-professional-system-integration-index.md`
3. `data_path`와 `project_root`가 현재 운영체제의 실제 절대경로인지 확인한다.
   If `project_root` is null, resolve the current repository root deterministically;
   continue only after recording its absolute path. If resolution is ambiguous,
   return `NEEDS_USER_CLARIFICATION`. If `artifact_root` is null, resolve
   `<project_root>/artifacts` and record its absolute path after confirming that it
   does not overlap `data_path`; ambiguity or overlap requires clarification.
4. 선행 Handoff가 있으면 hash, `fast_path` 예산, 사용량, 제외 범위를 검증한다.
   Restore fast_path.diagnostic_context and prior evidence before diagnosis; only
   explicit current user input may update them, and missing input never resets them.
5. 코드, 설정, 원본 데이터, snapshot, run, revision과 Artifact를 수정하거나
   만들지 않는다.
6. 테스트, build, dependency 설치·업데이트를 실행하지 않는다.
7. 상위 계약과 충돌하면 `BLOCKED_CONTRACT_CONFLICT`로 종료한다.

## 핵심 범위 정의

먼저 다음을 한 문단씩 명시한다.

- `core_ceo_question`: 이번 실행이 답해야 하는 CEO 질문
- `minimum_useful_result`: 대회 결과로 의미가 있는 최소 검증 결과
- `core_columns`: 최소 결과에 직접 필요한 입력 열·필드
- `core_calculations`: 최소 결과에 직접 필요한 결정적 계산
- `excluded_by_default`: 없어도 최소 결과가 성립하는 부가 분석

CEO 질문이 비어 있으면 입력 구조와 기존 Mission 계약에서 후보를 최대 3개
제시한다. 핵심 열이 달라질 정도로 후보가 갈리면 임의 선택하지 않고
`NEEDS_USER_CLARIFICATION`으로 종료한다.

## 최소 진단 절차

### 1. 입력 구조

다음만 확인한다.

- 파일 형식과 파일 수
- 표·시트·객체 이름
- 헤더·필드, 자료형과 최소 표본
- 핵심 열의 단위·통화·기간·부호
- 핵심 join key와 결측·중복 여부

원본 값을 장문으로 출력하거나 전체 데이터를 대화에 복사하지 않는다.

### 2. 기존 능력

`rg`와 `rg --files`로 핵심 범위에 관련된 다음 위치와 참조자만 확인한다.

- `plugin/trusted-ceo-agent/trusted_ceo_agent/intake/`
- `plugin/trusted-ceo-agent/trusted_ceo_agent/components/`
- `plugin/trusted-ceo-agent/trusted_ceo_agent/contracts/`
- `plugin/trusted-ceo-agent/trusted_ceo_agent/packs/`
- `plugin/trusted-ceo-agent/packs/`
- 관련 Schema와 focused 테스트 파일

전체 구현 디렉터리와 전체 테스트를 읽지 않는다. 마지막 확인 가능한 테스트
기록은 기준선 증거로만 사용하고 현재 통과했다고 표현하지 않는다.

### 3. 핵심 열 판정

각 `core_columns` 항목을 다음 중 하나로 판정한다.

- `existing_adapter`: 기존 Adapter가 의미·단위·기간·lineage를 보존
- `green_mapping`: 코드 변경 없는 명백한 매핑
- `ambiguous_meaning`: 경제적 의미 확인 필요
- `core_adapter_gap`: 기존 기능으로 읽을 수 없고 제외하면 핵심 결과 불성립
- `excludable`: 관련 분석을 제외해도 최소 결과 성립

`ambiguous_meaning`은 Adapter 구현 사유가 아니다. 결론을 바꾸는 질문만 최대
3개로 묶어 `USER_RESPONSE`로 보낸다.

### 4. 필수 계산 판정

각 `core_calculations` 항목을 다음 중 하나로 판정한다.

- `existing_component`: 기존 Component로 결정적으로 계산 가능
- `verified_composition`: 검증된 기존 Component 조합으로 계산 가능
- `core_component_gap`: 기존 기능이 없고 제외하면 핵심 결과 불성립
- `excludable`: 계산과 관련 Finding을 제외해도 최소 결과 성립

Pack 부족은 `core_component_gap`으로 바꾸지 않는다. Generic 또는 Boundary로
제한하고 강한 전문 판단, Norm 적용, 인과·규제 결론을 금지한다.

## Fast Path Gap 분류

각 부족 항목은 안정적인 `GAP-FAST-*` ID와 실제 근거를 가지고 다음 중 정확히
하나로 분류한다.

- `REUSE_OR_GREEN`: 기존 기능 또는 Green 매핑
- `EXCLUDE_AND_LIMIT`: 관련 범위를 제외하고 제한 분석
- `CORE_ADAPTER_EXCEPTION`: HD-02 예외 후보
- `CORE_COMPONENT_EXCEPTION`: HD-04 예외 후보
- `STOP_REQUIRED`: 예외 예산으로도 최소 결과 불성립

Existing HD Gap type mapping is binding:

- `CORE_ADAPTER_EXCEPTION` maps to the existing `ADAPTER` Gap type.
- `CORE_COMPONENT_EXCEPTION` maps to the existing `COMPONENT` Gap type.

When an exception is proposed, populate `fast_path.pending_exception` with its
stable Gap ID, mapped existing HD Gap type, evidence refs, and minimum write paths.
For a Component proposal also include the exact Component contract, Canonical Fact,
and existing verified Pack Procedure refs required by HD-04. HD-02 or HD-04
independently validates this proposal and the user's exact approval; the metadata
itself is never approval.

선택적 개선, 결과 장식, 추가 산업 지식, 있으면 좋은 계산은 Gap으로 만들지
않는다.

## 라우팅 판정

다음 순서에서 처음 일치하는 경로 하나만 선택한다. 이 순서는 binding이며 뒤의
규칙이 앞선 규칙을 덮어쓰지 않는다.

1. 계약 충돌이 있으면 `BLOCKED_CONTRACT_CONFLICT`.
2. 핵심 경제적 의미가 불명확하면 `NEEDS_USER_CLARIFICATION`과
   `USER_RESPONSE`.
3. 핵심 Adapter Gap이 2건 이상이거나 최소 변경으로 닫히지 않으면, 의존
   분석을 제외해 최소 결과가 성립하는지 확인한다. 성립하면
   `FAST_LIMITED_GO`, 아니면 `NO_GO`와 `STOP`.
4. 핵심 Adapter Gap 1건과 핵심 Component 관찰이 함께
   있으면 다음을 먼저 적용한다.
   - 두 예산 중 하나라도 `used >= budget`이면 의존 범위를 제외한다. 제외 후
     `minimum_useful_result`가 성립하면 `FAST_LIMITED_GO`, 아니면 `NO_GO`와
     `STOP`.
   - 두 예산이 모두 남으면 Adapter Gap만 `pending_exception`으로 제안하고
     `FAST_EXCEPTION_REQUIRED`와 `HD-02`를 선택한다. `exception_sequence`는
     `["HD-02", "HDF-01"]`, post-exception Prompt는 `HDF-01`이다. HDF-01은
     base `prompts_after_success`에 넣지 않고 post-exception overlay에만 둔다.
   - Component 관찰은 HD-02 전에는 Gap으로 제안·승인·이월하지 않는다.
5. 핵심 Adapter Gap이 정확히 1건이면, `hd02_used: 0`일 때만
   `FAST_EXCEPTION_REQUIRED`와 `HD-02`. 예산이 소진됐으면 의존 범위를
   제외해 `FAST_LIMITED_GO` 또는 `NO_GO`와 `STOP`.
6. 핵심 Component Gap이 2건 이상이거나 최소 변경으로 닫히지 않으면, 해당
   계산과 Finding을 제외해 최소 결과가 성립하는지 확인한다. 성립하면
   `FAST_LIMITED_GO`, 아니면 `NO_GO`와 `STOP`.
7. 핵심 Component Gap이 정확히 1건이면, `hd04_used: 0`일 때만
   `FAST_EXCEPTION_REQUIRED`와 `HD-04`. 예산이 소진됐으면 의존 범위를
   제외해 `FAST_LIMITED_GO` 또는 `NO_GO`와 `STOP`.
8. 비핵심 Gap 또는 Pack 부족만 있으면 제외 범위와 Generic·Boundary 한계를
   고정하고 `FAST_LIMITED_GO`와 `HD-05`.
9. 위 Gap이 없을 때만 `FAST_GO`와 `HD-05`.

After successful HD-02, HDF-01 re-diagnoses actual Canonical Facts and may propose
one specific HD-04 Gap with new approval metadata. A required exception with
`used >= budget` never falls through to `FAST_GO`.
Fast Path는 `HD-03`을 선택하거나 `next_prompt_id`로 출력하지 않는다.

## Yellow 예외 제안

`HD-02` 또는 `HD-04`가 필요할 때만 다음을 출력한다.

- 안정적인 단일 Gap ID
- 핵심 결과에 필수인 실제 근거
- 기존 기능으로 불가능한 코드·Schema 근거
- 최소 입력·출력 계약
- 최소 쓰기 경로
- focused RED/GREEN 테스트
- 롤백 대상
- 남은 예외 예산
- 사용자가 복사할 정확한 승인 문장

승인 문장은 다음 형식을 사용한다.

```text
<GAP-FAST-ID>의 <HD-02|HD-04> 실행과 approved_write_paths
[<정확한 경로 목록>]을 Fast Path 예외 1건으로 승인합니다.
```

특정 Gap ID 승인을 받기 전에는 `approved_gap_ids`,
`approval_refs`, `approved_write_paths`를 비워 둔다.

### USER_RESPONSE resumption

When status is `NEEDS_USER_CLARIFICATION`, set `next_prompt_id` to `USER_RESPONSE`,
set `fast_path.resume_prompt_id` to `HDF-01`, set `fast_path.resume_prompt_path` to
`docs/operations/prompts/HDF-01-fast-diagnose-route.md`, and set
`prompts_after_success` to `[]`; resumption uses only the resume overlay pair. On resume, store each confirmed answer by
stable question or field ID in `fast_path.diagnostic_context.resolved_field_meanings`;
when HD-02 is selected, hydrate its `field_meaning_answers` from that map.

## 출력

설명은 다음 순서로 간결하게 작성한다.

1. 핵심 질문과 최소 유용 결과
2. 핵심 열 지원표
3. 필수 계산 지원표
4. 제외 범위와 Generic·Boundary 한계
5. 예외 Gap 또는 중단 근거
6. 정확한 다음 Prompt ID와 경로

마지막 출력은 반드시 다음 두 블록으로 끝낸다.

```yaml
NEXT_DECISION:
  decision_status: "<READY|USER_ACTION_REQUIRED|BLOCKED>"
  decision_required: <true|false>
  summary: "<Fast Path 판정과 이유>"
  options:
    - option_id: "<stable option id>"
      action: "<유효한 다음 행동>"
      reason: "<코드·데이터 근거>"
      tradeoff: "<범위·시간·결과 한계>"
      approval_required: <true|false>
      next_prompt_id: "<HD-02|HD-04|HD-05|USER_RESPONSE|STOP>"
      next_prompt_path: "<정확한 상대경로 또는 null>"
      user_action: "<정확한 한 가지 행동>"
  recommended_option_id: "<option id or null>"
  recommendation_reason: "<evidence-based reason or null>"
  exact_user_action: "<사용자의 정확한 다음 행동 또는 none>"
  if_no_decision: "<안전한 대기·중단 상태>"

HANDOFF:
  handoff_version: "1.0"
  operation_id: "<stable fast diagnosis id>"
  completed_prompt_id: "HDF-01"
  status: "<FAST_GO|FAST_LIMITED_GO|FAST_EXCEPTION_REQUIRED|NEEDS_USER_CLARIFICATION|NO_GO|BLOCKED_CONTRACT_CONFLICT>"
  project_root: "<absolute current-platform path>"
  data_path: "<absolute current-platform path>"
  artifact_root: "<preserve prior absolute path or input artifact_root, or null>"
  run_id: "<preserve prior run_id or null>"
  revision: "<preserve prior revision or null>"
  input_handoff_hash: "<prior HANDOFF.handoff_hash or null>"
  handoff_hash: "<JCS SHA-256 of this HANDOFF with handoff_hash omitted>"
  proposed_gap_ids: ["<current proposed Gap IDs, or empty>"]
  approved_gap_ids: ["<preserve validated prior approvals, or empty>"]
  approval_refs: ["<preserve validated prior approval refs, or empty>"]
  approved_write_paths: ["<preserve validated prior write paths, or empty>"]
  produced_paths: ["<preserve prior produced paths, or empty>"]
  validation_evidence: ["<preserve prior validation evidence, or empty>"]
  analysis_artifact_refs: ["<preserve prior analysis artifact refs, or empty>"]
  projection_coverage:
    status: "<preserve prior status or not_applicable>"
    mapped: ["<preserve prior mapped refs, or empty>"]
    omitted: ["<preserve prior omitted refs, or empty>"]
    chat_only_forbidden: ["<preserve prior refs, or empty>"]
    blocked: ["<preserve prior blocked refs, or empty>"]
  blocking_questions: ["<current blocking questions, or empty>"]
  limitations: ["<preserve prior and append current limitations, or empty>"]
  fast_path:
    policy_version: "1.0"
    hd02_budget: 1
    hd02_used: <0|1, preserve prior value>
    hd04_budget: 1
    hd04_used: <0|1, preserve prior value>
    hd03_allowed: false
    generic_boundary_required: <prior true remains true; otherwise current true|false>
    excluded_gap_ids: ["<preserve prior and append current exclusions, or empty>"]
    excluded_analysis_scopes: ["<preserve prior and append current exclusions, or empty>"]
    exception_sequence: ["<remaining Prompt IDs in order, or empty>"]
    resume_prompt_id: "<HDF-01 for USER_RESPONSE, otherwise null>"
    resume_prompt_path: "<docs/operations/prompts/HDF-01-fast-diagnose-route.md for USER_RESPONSE, otherwise null>"
    post_exception_prompt_id: "<HDF-01 after HD-02 in a combined route, otherwise null>"
    post_exception_prompt_path: "<docs/operations/prompts/HDF-01-fast-diagnose-route.md after HD-02, otherwise null>"
    pending_exception:
      gap_id: "<current proposed Gap ID or null>"
      gap_type: "<ADAPTER|COMPONENT|null>"
      evidence_refs: ["<exact evidence refs, or empty>"]
      proposed_write_paths: ["<minimum proposed write paths, or empty>"]
      component_contract_refs: ["<validated refs for HD-04, or empty>"]
      canonical_fact_refs: ["<validated refs for HD-04, or empty>"]
      pack_procedure_refs: ["<existing verified refs for HD-04, or empty>"]
    diagnostic_context:
      company: "<preserve prior or current input, or null>"
      industry: "<preserve prior or current input, or null>"
      analysis_goal: "<preserve prior or current input, or null>"
      ceo_question: "<preserve prior or current input, or null>"
      analysis_period: "<preserve prior or current input, or null>"
      as_of_date: "<preserve prior or current input, or null>"
      known_constraints: ["<preserve prior plus current constraints, or empty>"]
      core_ceo_question: "<current binding question>"
      minimum_useful_result: "<current binding minimum result>"
      core_columns: ["<current core column definitions>"]
      core_calculations: ["<current core calculation definitions>"]
      excluded_by_default: ["<preserve prior plus current default exclusions>"]
      resolved_field_meanings: {"<stable field id>": "<confirmed meaning>"}
  next_prompt_id: "<HD-02|HD-04|HD-05|USER_RESPONSE|STOP>"
  next_prompt_path: "<정확한 상대경로 또는 null>"
  prompts_after_success: ["<base HD Prompt IDs only; never HDF-01; or empty>"]
```

`FAST_GO`와 `FAST_LIMITED_GO`만 `HD-05`로 바로 보낸다.
`FAST_EXCEPTION_REQUIRED`는 특정 Gap 승인 전까지 수정 작업을 시작하지 않는다.
`NO_GO`와 계약 충돌을 제한 성공으로 바꾸지 않는다.
