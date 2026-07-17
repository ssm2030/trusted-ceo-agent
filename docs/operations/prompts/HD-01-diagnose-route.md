# HD-01 — Diagnose and Route

- Prompt ID: `HD-01`
- 정확한 파일 경로: `docs/operations/prompts/HD-01-diagnose-route.md`
- 책임: 저장소와 입력 데이터를 읽기 전용으로 진단하고 다음 작업을 결정
- 쓰기 권한: 없음

## 입력 변수

`data_path`만 필수다. 나머지는 비어 있으면 입력 데이터와 저장소에서 후보를
찾되 사실로 확정하지 않는다.

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
change_policy: "green_allowed_yellow_requires_approval_red_forbidden"
```

## 실행 계약

1. 이 파일의 Prompt ID와 경로를 확인한다.
2. `docs/operations/HACKATHON_DAY_RUNBOOK.md`와
   `docs/superpowers/specs/2026-07-17-professional-system-integration-index.md`
   전체를 먼저 읽는다.
3. 현재 코드를 읽어 실제 Adapter, Pack, Knowledge Release, Component, Schema,
   CLI와 테스트 기준선을 확인한다. 최소한 다음 구현 위치와 그 참조자를
   검색하되, 파일이 없으면 존재한다고 추정하지 않는다.
   - `plugin/trusted-ceo-agent/trusted_ceo_agent/intake/`
   - `plugin/trusted-ceo-agent/trusted_ceo_agent/packs/`
   - `plugin/trusted-ceo-agent/trusted_ceo_agent/knowledge/`
   - `plugin/trusted-ceo-agent/trusted_ceo_agent/components/`
   - `plugin/trusted-ceo-agent/trusted_ceo_agent/accounting/`
   - `plugin/trusted-ceo-agent/trusted_ceo_agent/contracts/`
   - `plugin/trusted-ceo-agent/packs/`
   - `tests/`
4. 현재 커밋, 관련 파일의 Git 상태, Schema·Pack·Component 버전과 마지막으로
   확인 가능한 정상 테스트 기준선을 기록한다. 미실행 테스트는 통과로 쓰지 않는다.
5. 입력을 수정하거나 snapshot·run을 만들지 말고 다음을 조사한다.
   - 파일 형식, 파일 수, 표·시트·객체 구조, 열과 자료형
   - 날짜·기간·기준일, 통화·단위·부호·Decimal 정밀도
   - 결측·중복·취소·수정 거래와 식별키
   - 원장·계약·입출금·원가·운영 데이터 사이의 연결 가능성
   - 기존 Adapter가 의미 손실 없이 Canonical Field와 lineage를 만들 수 있는지
   - 적용 가능한 Pack의 업종·관할·시행일·authority와 필요한 Component 존재 여부
6. 회사·업종·기간·CEO 질문의 후보를 제시할 수 있지만 확인되지 않은 후보는
   `unknown`으로 둔다. 필드의 경제적 의미를 추측하지 않는다.
7. 질문 없이 진행 가능한 범위와 질문이 필수인 범위를 분리한다. 필수 의미가
   불명확할 때만 결론을 바꿀 질문을 최대 3개로 묶는다.

## Gap 분류

각 Gap은 안정적인 `GAP-*` ID, 근거 데이터, 부족한 능력, 유형, 변경 등급,
의존 Gap, 예상 쓰기 경로, 테스트와 롤백 대상을 가진다. 유형은 아래 중 하나다.

- `NONE`: 기존 기능으로 처리 가능
- `CONFIG_MAPPING`: 코드 변경 없는 Green 설정·명백한 매핑
- `ADAPTER`: 파일·Schema·정규화·lineage 지원 부족
- `PACK`: Issue Family, Method, Norm, Procedure, 반증 또는 Trigger 부족
- `COMPONENT`: 대사·기간귀속·현금흐름·배부·정량화 계산 부족
- `USER_CLARIFICATION`: 경제적 의미를 확인해야 함
- `RED_CHANGE`: Trust Kernel 또는 불변·승인·authority 경계를 바꿔야 함
- `NOT_ASSESSABLE`: required 데이터나 검증된 능력이 없어 평가 불가

`ADAPTER`, `PACK`, `COMPONENT`는 Yellow다. 실제 데이터나 필수 전문 절차에
연결되지 않은 “있으면 좋음”은 Gap으로 만들지 않는다.

## 출력

다음을 간결하게 보고한다.

1. 입력 충분성: 충분, 제한 진행 가능, 차단 입력, 질문 최대 3개
2. 기존 기능 조사표: 필요한 능력, 지원 여부, 코드·Schema·테스트 근거, 재사용 대상
3. Capability Gap 표: Gap ID, 유형, 실제 근거, 등급, 의존성, 차단 여부
4. 권장 실행 순서: Prompt ID와 정확한 상대경로
5. Yellow 제안: 이유, 예상 파일, 입력·출력 계약, 테스트, 권한 상한, 롤백
6. 최종 판정: `GO`, `CONDITIONAL_GO`, `LIMITED_GO`,
   `NEEDS_USER_CLARIFICATION`, `NO_GO`, `BLOCKED_CONTRACT_CONFLICT`

코드·설정·데이터를 수정하거나 run을 만들지 않는다. 명시 승인을 받지 않은
Gap은 `proposed_gap_ids`에만 넣고 `approved_gap_ids`는 비워 둔다.

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
      next_prompt_id: "HD-02 | HD-03 | HD-04 | HD-05 | USER_RESPONSE | STOP"
      next_prompt_path: "<exact repo-relative path or null>"
      user_action: "<one exact action>"
  recommended_option_id: "<option id or null>"
  recommendation_reason: "<reason or null>"
  exact_user_action: "<one exact next action or none>"
  if_no_decision: "<safe state and consequence when the user does not decide>"
HANDOFF:
  handoff_version: "1.0"
  operation_id: "<stable diagnosis id>"
  completed_prompt_id: "HD-01"
  status: "<GO|CONDITIONAL_GO|LIMITED_GO|NEEDS_USER_CLARIFICATION|NO_GO|BLOCKED_CONTRACT_CONFLICT>"
  project_root: "<absolute path>"
  data_path: "<absolute path>"
  artifact_root: null
  run_id: null
  revision: null
  input_handoff_hash: null
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
  next_prompt_id: "HD-02 | HD-03 | HD-04 | HD-05 | USER_RESPONSE | STOP"
  next_prompt_path: "<exact repo-relative path or null>"
  prompts_after_success: []
```
