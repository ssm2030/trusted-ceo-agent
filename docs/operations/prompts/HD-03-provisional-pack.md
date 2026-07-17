# HD-03 — Approved Provisional Pack

- Prompt ID: `HD-03`
- 정확한 파일 경로: `docs/operations/prompts/HD-03-provisional-pack.md`
- 책임: 승인된 전문지식 Gap만 Provisional Pack 후보로 구현하고 검증
- 쓰기 권한: 승인된 Pack·Registry 후보·관련 Schema·테스트만

## 입력 변수

```yaml
prior_handoff: "<complete preceding HANDOFF>"
approved_gap_ids: []
approval_refs: []
approved_write_paths: []
jurisdiction: null
effective_date: null
authoritative_source_refs: []
expert_review_refs: []
```

## 진입 Gate

1. 이 파일의 Prompt ID와 경로를 확인한다.
2. `docs/operations/HACKATHON_DAY_RUNBOOK.md`와
   `docs/superpowers/specs/2026-07-17-professional-system-integration-index.md`
   전체를 먼저 읽는다.
3. 통합 인덱스가 지정한 관련 도메인·Issue Family 원문과 현재 Pack,
   Knowledge Registry·Release, depth gate, Schema, Router, Component 계약과
   테스트 코드를 읽는다.
4. Runbook JCS 규칙으로 이전 Handoff hash를 다시 계산해 일치시키고
   `next_prompt_id=HD-03`, `next_prompt_path`, 선행 Adapter 산출물과
   Canonical Fact 계약을 독립적으로 검증한다.
5. 명시 승인된 Gap ID가 모두 `PACK` 유형이고 승인 근거와 쓰기 경로가
   있는지 확인한다.

승인 Gap이 없거나 유형·경로가 다르면 수정하지 않고
`BLOCKED_UNAPPROVED_GAP`으로 종료한다.

## Pack 계약

승인된 각 Issue Family는 현재 Schema가 요구하는 작은 Knowledge Artifact로
작성하며 다음 깊이를 모두 연결한다.

- D1 사건·모집단과 건수·금액·기간 Coverage
- D2 계정·주장·현금·운영·고객·계약·의사결정 영향
- D3 정상 기대관계, 근거와 적용 제외조건
- D4 오류·부정·정상 사유·매핑 오류·복합 가설
- D5 Norm의 출처·관할·시행일·요건·예외·불확실성
- D6 가설 구별 Procedure의 입력·계산·판정·실패상태
- D7 지지 Evidence와 반대 Evidence 및 필수 Evidence role
- D8 확정·범위 금액, 기간별·현금/비현금 영향과 계산불가 사유
- D9 조건부 처리·조치 후보, 수정 후보, 통제 개선, 추가 질문
- D10 Cross-domain Trigger, 전달 Fact, 금지할 미확정 결론, 충돌 상태
- D11 `Full`·`Boundary`·`Not Assessable`, 전문가 Trigger와 금지 결론
- D12 정상·오류·경계·반증·누락·매핑·복합·동일 Signal 다원인·도메인 충돌 Oracle

Method, Norm, Expectation, Procedure, Counter-Hypothesis, Evidence,
Cross-domain Trigger와 Expert Trigger를 분리한다. LLM 일반지식을 Norm의
출처로 사용하지 않는다. 관할·시행일·공식 근거 또는 전문가 승격이 없으면
authority는 `Provisional` 또는 현재 코드가 허용하는 더 낮은 상한으로 둔다.
`Full`, `senior_accountant` 또는 미지원 법무·노무·세무 전문결론으로
승격하지 않는다.

새 계산이 필요하면 Pack은 입력 Fact, 공식, 단위·기간·부호, 출력과 실패조건의
계약만 정의하고 계산 코드를 만들지 않는다. 해당 Gap을 `COMPONENT`로 남겨
`HD-04`에 전달한다. 활성 Knowledge Release, 기존 authority, 승인 기록 또는
실행 중 run을 자동 변경하지 않는다.

## 검증 Gate

- Schema와 D1~D12 depth gate
- 정상·오류·경계·반증·누락·복합·Cross-domain 사례
- 적용 범위, 관할, 시행일, 출처와 만료 처리
- required Evidence·Procedure 누락 시 fail-closed
- 반대 증거에 따른 결론 약화와 `Not Assessable`
- 공유 Norm·Method, 관련 Issue Family와 전체 도메인 회귀
- Pack 선택·Router·Component 계약 및 결정성·병렬 동등성 회귀
- 승인 쓰기 경로 밖 diff가 없음

완료 상태는 `PROVISIONAL_PACK_READY`, `NEEDS_EXPERT_SOURCE`,
`BLOCKED_RED_CHANGE`, `BLOCKED_UNAPPROVED_GAP`,
`BLOCKED_CONTRACT_CONFLICT` 중 하나다.

성공하고 새 Component가 필요하면 `HD-04`와
`docs/operations/prompts/HD-04-deterministic-component.md`를 지정한다.
그 외에는 Handoff의 다음 미완료 의존 작업을 선택하고, 없으면 `HD-05`를
지정한다.

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
      next_prompt_id: "HD-04 | HD-05 | USER_RESPONSE | STOP"
      next_prompt_path: "<exact repo-relative path or null>"
      user_action: "<one exact action>"
  recommended_option_id: "<option id or null>"
  recommendation_reason: "<reason or null>"
  exact_user_action: "<one exact next action or none>"
  if_no_decision: "<safe state and consequence when the user does not decide>"
HANDOFF:
  handoff_version: "1.0"
  operation_id: "<unchanged operation id>"
  completed_prompt_id: "HD-03"
  status: "<PROVISIONAL_PACK_READY|NEEDS_EXPERT_SOURCE|BLOCKED_UNAPPROVED_GAP|BLOCKED_RED_CHANGE|BLOCKED_CONTRACT_CONFLICT>"
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
  next_prompt_id: "HD-04 | HD-05 | USER_RESPONSE | STOP"
  next_prompt_path: "<exact repo-relative path or null>"
  prompts_after_success: []
```
