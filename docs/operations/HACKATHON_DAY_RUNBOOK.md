# Trusted CEO Agent 대회 당일 Runbook

- 문서 역할: HD-01~HD-07 운영 계약의 단일 진입점
- 적용 범위: 데이터 진단, 승인된 조건부 변경, 분석·HITL·최종화, 웹 변환·게시
- 비적용 범위: Trust Kernel 변경, 전문 권한 승격, 분석·웹 제품 기능의 신규 설계

## 1. 정본 우선순위와 충돌 처리

아래 순서가 높을수록 우선한다.

1. 현재 코드가 검증하는 Schema, Trust Kernel, 불변 revision, 승인, authority, hash, Validator 계약
2. `docs/superpowers/specs/2026-07-17-professional-system-integration-index.md`와 그 문서가 지정한 D01~D18
3. 이 Runbook
4. 아래 Prompt Registry에 적힌 `HD-01`~`HD-07`의 정확한 파일
5. 특정 대화의 임시 지시와 모델의 추정

하위 문서는 상위 계약을 완화하지 못한다. 충돌을 발견하면 우회하거나 문서를
임의 수정하지 말고 `BLOCKED_CONTRACT_CONFLICT`로 종료한다. 운영 프롬프트는
전문지식, Schema, 승인 또는 Validator의 정본이 아니다.

## 2. 모든 HD 작업의 시작 순서

각 HD 작업은 새 대화라고 가정하고 다음을 순서대로 수행한다.

1. 실행 중인 Prompt ID와 파일의 정확한 상대경로가 일치하는지 확인한다.
2. 이 Runbook 전체를 읽는다.
3. 통합 인덱스 전체를 읽고, 작업에 관련된 D01~D18 원문을 그 인덱스 순서대로 읽는다.
4. Registry, Schema, CLI, 테스트를 포함한 현재 코드를 읽어 실제 계약을 확인한다.
5. 입력 변수와 직전 `HANDOFF`의 ID, 경로, Gap, run/revision을 검증한다.
6. 허용 쓰기 경계를 고정한 뒤 작업한다.
7. 작업별 완료 Gate를 검사한다.
8. 공통 `NEXT_DECISION`과 `HANDOFF`를 출력한다.

이전 대화, “몇 번 작업”, 파일의 최신 수정 시각을 근거로 상태를 추정하지 않는다.
후보가 여러 개면 임의로 고르지 않는다.

## 3. Prompt Registry

| ID | 정확한 경로 | 진입 조건 | 성공 상태 | 차단·대기 상태 | 쓰기 경계 |
|---|---|---|---|---|---|
| `HD-01` | `docs/operations/prompts/HD-01-diagnose-route.md` | 절대 `data_path` | `GO`, `CONDITIONAL_GO`, `LIMITED_GO` | `NEEDS_USER_CLARIFICATION`, `NO_GO`, `BLOCKED_CONTRACT_CONFLICT` | 없음. 저장소·데이터 읽기 전용 |
| `HD-02` | `docs/operations/prompts/HD-02-adapter-change.md` | 명시 승인된 `ADAPTER` Gap ID와 쓰기 경로 | `ADAPTER_READY` | `NEEDS_USER_CLARIFICATION`, `BLOCKED_UNAPPROVED_GAP`, `BLOCKED_RED_CHANGE`, `BLOCKED_CONTRACT_CONFLICT` | 승인된 Adapter·관련 Schema·테스트만 |
| `HD-03` | `docs/operations/prompts/HD-03-provisional-pack.md` | 명시 승인된 `PACK` Gap ID와 쓰기 경로 | `PROVISIONAL_PACK_READY` | `NEEDS_EXPERT_SOURCE`, `BLOCKED_UNAPPROVED_GAP`, `BLOCKED_RED_CHANGE`, `BLOCKED_CONTRACT_CONFLICT` | 승인된 Pack·Registry 후보·관련 Schema·테스트만 |
| `HD-04` | `docs/operations/prompts/HD-04-deterministic-component.md` | 명시 승인된 `COMPONENT` Gap ID와 쓰기 경로 | `COMPONENT_READY` | `NEEDS_CANONICAL_FACT`, `BLOCKED_UNAPPROVED_GAP`, `BLOCKED_RED_CHANGE`, `BLOCKED_CONTRACT_CONFLICT` | 승인된 Component·관련 계약·테스트만 |
| `HD-05` | `docs/operations/prompts/HD-05-analysis-hitl-finalize.md` | 데이터 경로와 검증된 기능 기준선 | `FINALIZED`, `LIMITED_FINALIZED` | `NEEDS_INPUT`, `BLOCKED_REQUIRED_FAILURE`, `BLOCKED_ANALYSIS_PERSISTENCE`, `BLOCKED_CONTRACT_CONFLICT` | 공식 CLI의 mutation·revision 경계와 지정 artifact root만 |
| `HD-06` | `docs/operations/prompts/HD-06-export-web-report.md` | finalized 또는 승인된 limited-finalized run/revision | `READY_FOR_WEB_IMPORT` | `BLOCKED`, `BLOCKED_CONTRACT_CONFLICT` | 새 `exports/<run_id>/revision-<revision>/web-report-bundle.json`만 |
| `HD-07` | `docs/operations/prompts/HD-07-publish-tab2.md` | `READY_FOR_WEB_IMPORT`와 검증된 단일 bundle | `WEB_PUBLISHED_UNVERIFIED` | `BLOCKED`, `BLOCKED_CONTRACT_CONFLICT` | 웹의 공식 import를 통한 `unverified_import` ReportStore 교체만 |
`HD-07`의 공식 파일 import는 bundle의 구조·hash·참조를 다시 검증하지만
HD-06의 source viewer mode를 보존하지 않고 `unverified_import`로 게시한다.
`trusted_final` 등록 게시 경로의 신규 설계·수정은 이 Runbook 범위가 아니다.


단순 숫자는 설명용 별칭일 뿐이다. 실행과 Handoff에는 Prompt ID와 정확한
상대경로를 함께 쓴다.

## 4. 변경 등급과 승인

- `Green`: 기존 계약 안의 설정, 명백한 열 이름 매핑, 검증된 단위 변환처럼
  코드·Schema·authority를 바꾸지 않는 가역 작업. 별도 코드 변경 없이
  `HD-05`에서 수행할 수 있다.
- `Yellow`: Adapter, Provisional Pack, 결정적 Component, 관련 Schema·테스트의
  범위 제한 변경. Gap ID, 예상 쓰기 경로, 테스트, 롤백 대상을 제시하고
  사용자가 해당 Gap ID를 명시 승인해야 한다.
- `Red`: 원본 불변성, Evidence chain, 사실·해석 분리, revision CAS, 승인,
  authority, Final Validator, 감사로그, 보안 경계 또는 기존 finalized
  revision을 바꾸거나 우회하는 변경. 실행하지 않는다.

사용자 승인은 승인된 Gap ID, 허용 쓰기 경로, 승인 근거 참조를 Handoff에
남긴다. 단순 동의로 범위를 확대하지 않는다. `HD-02`~`HD-04`는 승인된
Gap ID가 없거나 Gap 유형이 맞지 않으면 코드를 수정하지 않는다.

## 5. 공통 쓰기·신뢰 경계

- 원본 입력, source snapshot, 기존 immutable revision, 승인 기록, state pointer,
  Pack authority, hash, finalized 파일을 수정하지 않는다.
- 현재 저장소에서 확인하지 못한 Adapter, Pack, Component, Schema, 테스트,
  CLI 명령이 존재한다고 추정하지 않는다.
- 모델은 Fact, Signal, Grade, 승인 또는 전문 최종결론을 직접 만들지 않는다.
- 미지원 도메인은 일반 LLM 지식으로 메우지 않고 `unsupported_pack`,
  `not_assessable`, `needs_expert` 또는 명시적 Boundary로 보존한다.
- `machine_draft`, `Boundary`, `Provisional`, `Full`을 서로 바꾸어 쓰지 않는다.
- 실패를 제한 성공으로 바꾸지 않는다. required 실패는 finalization을 차단한다.
- 민감한 원본 값, 비밀키, 자격증명은 Handoff에 넣지 않는다.
- 동시 작업자의 범위 밖 변경을 되돌리거나 함께 커밋하지 않는다.

## 6. 라우팅

### 6.1 기본 경로

```text
HD-01
  ├─ 기존 기능 충분 또는 Green 설정만 필요 → HD-05
  ├─ 승인된 Adapter Gap                  → HD-02
  ├─ 승인된 Pack Gap                     → HD-03
  ├─ 승인된 Component Gap                → HD-04
  ├─ 경제적 의미 확인 필요               → USER_RESPONSE
  └─ Red 변경 또는 required 능력 부재     → STOP

검증된 조건부 변경 → HD-05 → HD-06 → MANUAL_UPLOAD 또는 HD-07
```

### 6.2 복합 Gap의 의존 순서

1. 구조적 입력 Gap은 `HD-02`에서 먼저 해결한다.
2. Adapter 출력의 Canonical Fact와 Evidence lineage가 검증된 뒤 Pack에 전달한다.
3. 새 전문 방법론은 `HD-03`에서 Procedure와 계산 요구를 먼저 정의한다.
4. 기존 Pack이 계산 계약을 이미 정의했다면 `HD-04`만 실행할 수 있다.
5. 새 Pack이 새 계산을 요구하면 `HD-03` 다음 `HD-04`를 실행한다.
6. 모든 Yellow 변경은 승인 Gap ID별 정상·경계·실패·회귀 테스트를 통과해야 한다.
7. `prompts_after_success`의 순서를 유지하고 성공하지 않은 작업을 건너뛰지 않는다.

유효한 예시는 다음과 같다.

```text
HD-01 → HD-05 → HD-06 → MANUAL_UPLOAD
HD-01 → HD-02 → HD-05 → HD-06
HD-01 → HD-03 → HD-04 → HD-05 → HD-06
HD-01 → USER_RESPONSE → HD-02 → HD-05
HD-01 → STOP
HD-06 → HD-07
```

## 7. 공통 `NEXT_DECISION` 계약

모든 HD 프롬프트는 실행 결과 뒤에 아래 구조를 출력한다.

```yaml
NEXT_DECISION:
  decision_status: "READY | USER_ACTION_REQUIRED | BLOCKED | COMPLETE"
  decision_required: <true|false>
  summary: "<what was decided or what must be decided>"
  options:
    - option_id: "<stable option id>"
      action: "<what happens>"
      reason: "<why this option is valid>"
      tradeoff: "<cost, limitation, or consequence>"
      approval_required: <true|false>
      next_prompt_id: "HD-0X | USER_RESPONSE | MANUAL_UPLOAD | STOP"
      next_prompt_path: "<repo-relative path or null>"
      user_action: "<one exact action>"
  recommended_option_id: "<one option id or null>"
  recommendation_reason: "<evidence-based reason or null>"
  exact_user_action: "<one exact next action or none>"
  if_no_decision: "<safe state and consequence when the user does not decide>"
```

규칙:

- 현재 상태에서 안전하고 유효한 선택지만 최대 3개 제시한다.
- 각 선택지에 이유와 대가를 함께 적는다.
- 증거에 기반한 권장안 하나를 고르되 판단 근거가 없으면 `null`로 둔다.
- Red, 계약 우회, 검증 생략은 선택지로 제시하지 않는다.
- 사용자 승인·답변이 필요하면 승인할 Gap ID 또는 답할 질문을 정확히 적는다.

## 8. 공통 `HANDOFF` 계약

`NEXT_DECISION` 바로 뒤에 아래 구조를 출력한다.

```yaml
HANDOFF:
  handoff_version: "1.0"
  operation_id: "<stable operation identifier>"
  completed_prompt_id: "HD-0X"
  status: "<terminal status>"
  project_root: "<absolute path>"
  data_path: "<absolute path or null>"
  artifact_root: "<absolute path or null>"
  run_id: "<run id or null>"
  revision: "<integer or null>"
  input_handoff_hash: "<prior HANDOFF.handoff_hash or null>"
  handoff_hash: "<JCS SHA-256 of this HANDOFF with handoff_hash omitted>"
  proposed_gap_ids: []
  approved_gap_ids: []
  approval_refs: []
  approved_write_paths: []
  produced_paths: []
  validation_evidence: []
  analysis_artifact_refs: []
  projection_coverage:
    status: "not_applicable | not_started | complete | partial | blocked"
    mapped: []
    omitted: []
    chat_only_forbidden: []
    blocked: []
  blocking_questions: []
  limitations: []
  next_prompt_id: "HD-0X | USER_RESPONSE | MANUAL_UPLOAD | STOP"
  next_prompt_path: "<repo-relative path or null>"
  prompts_after_success: []
```

필드를 제거하거나 의미를 바꾸지 않는다. Prompt별 필드는 추가할 수 있다.
`handoff_hash`는 승인이나 서명이 아니라 전달 중 우발적 변형을 검출하는
chain fingerprint다. 출력자는 `handoff_hash` 필드를 제외한 Handoff 객체를
JSON 호환 값으로 만든 뒤 RFC 8785 JCS로 canonicalize하고 UTF-8 bytes의
SHA-256 lowercase hex를 기록한다. 최초 Handoff의 `input_handoff_hash`는
`null`이다. 후속 Prompt는 이전 Handoff를 같은 방식으로 다시 계산해 이전
`handoff_hash`와 일치하는지 확인하고, 새 Handoff의 `input_handoff_hash`에
그 값을 그대로 복사한다. 불일치는 `BLOCKED_CONTRACT_CONFLICT`다.
일치하더라도 Prompt ID·경로·Gap 승인·run/revision과 Artifact hash는
원본 코드·snapshot에서 독립적으로 다시 검증한다.

`HD-01`~`HD-04`의 `analysis_artifact_refs`는 비어 있고
`projection_coverage.status`는 `not_applicable`이다. `HD-05` 이후에는
artifact root, run ID, revision과 분석 Artifact 참조를 구체화한다.

새 대화는 다음 중 하나라도 맞지 않으면 실행하지 않는다.

- `completed_prompt_id`와 실제 선행 작업
- `next_prompt_id`와 실행할 Prompt ID
- `next_prompt_path`와 실제 파일 경로
- 승인 Gap ID와 쓰기 범위
- artifact root의 run ID·revision과 Handoff

## 9. 새 대화 입력

### 최초 진단

```text
다음 파일을 순서대로 완전히 읽고 HD-01을 실행하세요.

1. docs/operations/HACKATHON_DAY_RUNBOOK.md
2. docs/operations/prompts/HD-01-diagnose-route.md

[변수]
data_path: "<absolute data path>"
project_root: "<absolute repository path or null>"
company: null
industry: null
analysis_goal: null
ceo_question: null
analysis_period: null
as_of_date: null
known_constraints: []
change_policy: "green_allowed_yellow_requires_approval_red_forbidden"
```

### 후속 작업

```text
다음 파일을 순서대로 완전히 읽고 HANDOFF가 지정한 Prompt ID를 실행하세요.

1. docs/operations/HACKATHON_DAY_RUNBOOK.md
2. <HANDOFF.next_prompt_path>

[변수]
prior_handoff:
<paste the complete HANDOFF block>

additional_user_input:
approved_gap_ids:
approval_refs:
```

## 10. 종료 원칙

- `NEXT_DECISION.decision_status=READY`는 지정된 다음 Prompt를 실행할 수 있다는 뜻이다.
- `USER_ACTION_REQUIRED`는 사용자의 명시 답변 또는 승인을 받기 전 멈춘다.
- `BLOCKED`는 우회하지 않고 안전한 복구 행동만 제시한다.
- `COMPLETE`는 요청 범위에 후속 작업이 없을 때만 사용한다.
- 대화가 끝났다는 사실은 완료 증거가 아니다. Prompt별 Validator와 Handoff가
  완료 상태를 결정한다.
