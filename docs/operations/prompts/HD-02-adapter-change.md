# HD-02 — Approved Adapter Change

- Prompt ID: `HD-02`
- 정확한 파일 경로: `docs/operations/prompts/HD-02-adapter-change.md`
- 책임: 승인된 Adapter·정규화 Gap만 최소 변경으로 구현하고 검증
- 쓰기 권한: 승인된 Adapter 관련 파일·Schema·테스트만

## 입력 변수

```yaml
prior_handoff: "<complete HD-01 or preceding HD HANDOFF>"
approved_gap_ids: []
approval_refs: []
approved_write_paths: []
field_meaning_answers: {}
```

## 진입 Gate

1. 이 파일의 Prompt ID와 경로를 확인한다.
2. `docs/operations/HACKATHON_DAY_RUNBOOK.md`와
   `docs/superpowers/specs/2026-07-17-professional-system-integration-index.md`
   전체를 먼저 읽는다.
3. 현재 Adapter, intake, Canonical mapping, Evidence lineage, Schema와 관련
   테스트 코드를 읽는다.
4. Runbook JCS 규칙으로 이전 Handoff의 hash를 다시 계산해 그 Handoff의
   `handoff_hash`와 일치시키고, 새 Handoff의 `input_handoff_hash`로 복사할
   값을 확정한다. `next_prompt_id=HD-02`, `next_prompt_path`, 데이터 경로와
   기반 Artifact도 독립적으로 검증한다.
5. 명시 승인된 Gap ID가 모두 `ADAPTER` 유형인지, 승인 근거와 쓰기 경로가
   있는지 확인한다.

승인 Gap이 없거나 유형·경로가 다르면 수정하지 않고
`BLOCKED_UNAPPROVED_GAP`으로 종료한다. 필드의 경제적 의미가 불명확하면
추측하지 않고 `NEEDS_USER_CLARIFICATION`으로 종료한다.

## 구현 계약

- 원본 파일과 기존 snapshot은 byte 단위로 불변이어야 한다.
- 기존 `IntakeAdapter`, snapshot, source registry, mapping, quality, Fact·lineage
  계약을 재사용한다. 별도 신뢰 경계를 만들지 않는다.
- 파일·시트·행·셀 locator, source ID, row fingerprint, semantic hash와
  원본→Canonical mapping을 보존한다.
- 날짜·기간·기준일, 통화·단위·Decimal·부호, 결측·중복·취소·수정 거래를
  명시적으로 처리한다.
- 의미가 불명확하거나 무손실 매핑이 불가능한 값은 추정 변환하지 않고
  quality issue 또는 평가불가 조건으로 남긴다.
- 승인된 Gap을 닫는 최소 코드만 변경한다. Trust Kernel, 승인, authority,
  기존 immutable revision과 범위 밖 Adapter를 변경하지 않는다.

## 검증 Gate

변경 전에 해당 Gap을 재현하는 실패 테스트를 만들고, 최소 구현 후 다음을
검증한다.

- 정상, 경계, 실패 입력
- 결측·중복·취소·수정 및 단위·부호·기간 변형
- 같은 입력의 결정성
- 원본 hash와 locator·lineage 보존
- 기존 CSV·JSON·XLSX Adapter 및 관련 intake 회귀
- 승인 쓰기 경로 밖 diff가 없음

테스트 명령, 종료 코드, 핵심 판정과 변경 파일을 기록한다. 실패한 테스트를
통과로 표시하지 않는다. 완료 상태는 `ADAPTER_READY`,
`NEEDS_USER_CLARIFICATION`, `BLOCKED_RED_CHANGE`,
`BLOCKED_UNAPPROVED_GAP`, `BLOCKED_CONTRACT_CONFLICT` 중 하나다.

성공하면 Handoff의 `prompts_after_success`에서 다음 미완료 의존 작업을
선택하고, 없으면 `HD-05`와
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
      next_prompt_id: "HD-03 | HD-04 | HD-05 | USER_RESPONSE | STOP"
      next_prompt_path: "<exact repo-relative path or null>"
      user_action: "<one exact action>"
  recommended_option_id: "<option id or null>"
  recommendation_reason: "<reason or null>"
  exact_user_action: "<one exact next action or none>"
  if_no_decision: "<safe state and consequence when the user does not decide>"
HANDOFF:
  handoff_version: "1.0"
  operation_id: "<unchanged operation id>"
  completed_prompt_id: "HD-02"
  status: "<ADAPTER_READY|NEEDS_USER_CLARIFICATION|BLOCKED_UNAPPROVED_GAP|BLOCKED_RED_CHANGE|BLOCKED_CONTRACT_CONFLICT>"
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
  next_prompt_id: "HD-03 | HD-04 | HD-05 | USER_RESPONSE | STOP"
  next_prompt_path: "<exact repo-relative path or null>"
  prompts_after_success: []
```
