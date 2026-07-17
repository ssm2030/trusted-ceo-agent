# HD-04 — Approved Deterministic Component

- Prompt ID: `HD-04`
- 정확한 파일 경로: `docs/operations/prompts/HD-04-deterministic-component.md`
- 책임: 승인된 계산·대사·Signal Gap만 결정적 Component로 구현하고 검증
- 쓰기 권한: 승인된 Component·관련 계약·Schema·테스트만

## 입력 변수

```yaml
prior_handoff: "<complete preceding HANDOFF>"
approved_gap_ids: []
approval_refs: []
approved_write_paths: []
component_contract_refs: []
canonical_fact_refs: []
pack_procedure_refs: []
```

## 진입 Gate

1. 이 파일의 Prompt ID와 경로를 확인한다.
2. `docs/operations/HACKATHON_DAY_RUNBOOK.md`와
   `docs/superpowers/specs/2026-07-17-professional-system-integration-index.md`
   전체를 먼저 읽는다.
3. 현재 Component registry, parameter Schema, runner, plan, builtin 구현,
   Fact·Signal·lineage 계약, 관련 Pack Procedure와 테스트 코드를 읽는다.
4. Runbook JCS 규칙으로 이전 Handoff hash를 다시 계산해 일치시키고
   `next_prompt_id=HD-04`, `next_prompt_path`, 선행 Pack·Adapter 산출물의
   식별자와 hash를 독립적으로 검증한다.
5. 명시 승인된 Gap ID가 모두 `COMPONENT` 유형이고 승인 근거와 쓰기 경로가
   있는지 확인한다.

승인 Gap이 없거나 유형·경로가 다르면 수정하지 않고
`BLOCKED_UNAPPROVED_GAP`으로 종료한다. required Canonical Fact나 검증된 Pack
Procedure가 없으면 구현하지 않고 `NEEDS_CANONICAL_FACT`으로 종료한다.

## Component 계약

각 승인 Gap에 대해 구현 전 다음을 고정한다.

- 허용 입력 Fact code·ID, scope, time context와 최대 레코드 수
- 공식과 계산 순서, `Decimal` 정밀도·반올림 정책
- 통화·단위·기간·부호와 변환 금지 조건
- 출력 Fact·Signal code, semantic role과 lineage
- threshold reference와 threshold 부재 처리
- 결측·0 분모·단위/범위 불일치·불충분 Coverage·timeout 실패상태
- 결정적 ID, 버전, parameter hash, pack reference와 audit 정보

Component는 계산·대사·Signal 후보만 만들고 원본 Fact, Grade, Finding,
전문 결론, 승인 또는 authority를 만들지 않는다. LLM 계산이나 자유서술 값을
계산 Artifact로 사용하지 않는다. 기존 runner·registry·plan과 단일 publish
경계를 재사용하고 승인 범위 밖 기능을 함께 추가하지 않는다.

## 검증 Gate

변경 전에 Gap을 재현하는 실패 테스트를 만들고 최소 구현 후 다음을 검증한다.

- 정상, 경계, 실패와 고정 Oracle
- Decimal, 반올림, 통화·단위·기간·부호
- 결측, 0 분모, 범위·scope 불일치와 입력 한도
- 같은 입력·parameter·Pack hash의 byte 결정성
- 순차·병렬 실행 동등성, 정렬·병합·중복 실행 동등성
- lineage·parameter hash·Pack reference 보존
- 관련 Pack Procedure와 전체 Component registry 회귀
- 승인 쓰기 경로 밖 diff가 없음

완료 상태는 `COMPONENT_READY`, `NEEDS_CANONICAL_FACT`,
`BLOCKED_RED_CHANGE`, `BLOCKED_UNAPPROVED_GAP`,
`BLOCKED_CONTRACT_CONFLICT` 중 하나다.

성공하면 Handoff의 다음 미완료 의존 작업을 선택하고, 없으면 `HD-05`와
`docs/operations/prompts/HD-05-analysis-hitl-finalize.md`를 지정한다.

마지막 출력은 반드시 아래 두 블록으로 끝낸다.

```yaml
NEXT_DECISION:
  decision_status: "READY | USER_ACTION_REQUIRED | BLOCKED"
  decision_required: <true|false>
  summary: "<what was decided or what must be decided>"
  options:
    - option_id: "<stable option id>"
      action: "<valid next action>"
      reason: "<evidence>"
      tradeoff: "<cost or limitation>"
      approval_required: <true|false>
      next_prompt_id: "HD-05 | USER_RESPONSE | STOP"
      next_prompt_path: "<exact repo-relative path or null>"
      user_action: "<one exact action>"
  recommended_option_id: "<option id or null>"
  recommendation_reason: "<reason or null>"
  exact_user_action: "<one exact next action or none>"
  if_no_decision: "<safe state and consequence when the user does not decide>"
HANDOFF:
  handoff_version: "1.0"
  operation_id: "<unchanged operation id>"
  completed_prompt_id: "HD-04"
  status: "<COMPONENT_READY|NEEDS_CANONICAL_FACT|BLOCKED_UNAPPROVED_GAP|BLOCKED_RED_CHANGE|BLOCKED_CONTRACT_CONFLICT>"
  project_root: "<absolute path>"
  data_path: "<absolute path>"
  artifact_root: null
  run_id: null
  revision: null
  input_handoff_hash: "<exact prior HANDOFF.handoff_hash>"
  handoff_hash: "<JCS SHA-256 of this HANDOFF with handoff_hash omitted>"
  proposed_gap_ids: []
  approved_gap_ids: []
  approval_refs: []
  approved_write_paths: []
  produced_paths: []
  validation_evidence: []
  analysis_artifact_refs: []
  projection_coverage:
    status: "not_applicable"
    mapped: []
    omitted: []
    chat_only_forbidden: []
    blocked: []
  blocking_questions: []
  limitations: []
  next_prompt_id: "HD-05 | USER_RESPONSE | STOP"
  next_prompt_path: "<exact repo-relative path or null>"
  prompts_after_success: []
```
