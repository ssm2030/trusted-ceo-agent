# Trusted CEO Agent 플러그인 상세 설계

- 문서 상태: 사용자 최종 확인 대상
- 버전: 1.0-rc2
- 작성일: 2026-07-17
- 설계 정본: docs/PRD.md, docs/ARCHITECTURE_DECISIONS.md
- 적용 범위: 전체 작업 순서 중 1단계인 플러그인 상세 설계와 구현
- 기준선 정책: 기존 예선 프로젝트와 submission.zip은 읽기 전용이며 신규 프로젝트만 수정한다.

## 1. 설계 결론

Trusted CEO Agent는 로컬의 결정적 Python 엔진과 Codex 플러그인 Skill을 결합한다. Python 엔진은 원본 snapshot, Fact·Signal, Pack 권한, 상태 전이, 승인, 결과 등급, 감사 기록을 통제한다. 모델은 동결된 Fact·Signal·Pack allowlist 안에서 진단 payload만 제안한다. 모델의 제안은 비신뢰 draft이며, 런타임 검증과 불변 revision 물질화를 거쳐야 신뢰 산출물에 들어간다.

구현 의존 순서는 다음과 같다.

1. strict JSON, 정규화, 해시, stable ID, 안전한 파일 저장
2. Source·Fact·Signal·Evidence와 Evidence Core
3. 결정적 분석 Component
4. Mission Contract와 Mission·Domain·Problem Pack
5. Reasoning Job과 진단 카드
6. Join Barrier와 단일 통합
7. HITL 상태 머신과 승인
8. 결정적 결과 등급과 조건부 대응 eligibility
9. 최종 출력·감사·플러그인 Skill
10. POC 시나리오와 합격 평가

## 2. 제품 범위와 불변 원칙

### 2.1 목표

- 제공된 기업 데이터에서 CEO가 놓친 중요한 문제 후보를 탐지한다.
- 계산 사실, 규칙 기반 Signal, AI 해석을 구조적으로 분리한다.
- 고객의 원인 설명을 가설로 취급하고 최소 하나의 challenge 관점을 검사한다.
- 원인 가설과 반대 가설, 구별 검증, 누락 데이터를 함께 제시한다.
- 조건부 대응 방향과 전문가에게 물을 정확한 질문을 만든다.
- 모든 중요한 주장에서 원본 snapshot까지 추적한다.
- 데이터 부족, 미지원 도메인, 근거 충돌, 내부 실패를 서로 다르게 처리한다.
- 사람의 승인 없이는 심화 범위와 최종 고객 전달물을 확정하지 않는다.

### 2.2 비목표

- CEO의 최종 의사결정 대체
- 회계·세무·법무·노무·감사의 최종 전문 결론
- 근거 없는 인과관계 확정
- 외부 시스템 자동 쓰기·전송·거래
- 원본 파일, 공식 대화 logs, 기존 예선 프로젝트 수정
- 플러그인과 다른 분석 로직을 가진 웹 구현

### 2.3 Trust Kernel 불변 규칙

- 원본은 content-addressed snapshot으로 보존한다.
- Fact와 Signal은 결정적 코드만 생성한다.
- AI와 사람은 Fact·Signal·원본을 덮어쓰지 못한다.
- 중요한 주장에는 유효한 Evidence Link가 있어야 한다.
- Signal → Fact → Source 또는 Fact → Source 계보가 해소되어야 한다.
- 고객 주장은 unverified hypothesis로 시작한다.
- required challenge를 생략하지 않는다.
- 승인 없는 상태 전이를 차단한다.
- 전문직 trigger를 숨기거나 낮추지 않는다.
- Not Assessable과 failed·blocked를 혼용하지 않는다.
- 최종 출력 전에 전체 Validator를 다시 실행한다.

## 3. 네 층과 실행 주체

    Evidence Core
        ↓
    Pack Stack(Mission · Domain · Problem)
        ↓
    Bounded AI Reasoning
        ↓
    Join Barrier
        ↓
    Single Integrated Reasoning
        ↓
    Deterministic Grade + HITL
        ↓
    Human Decision

| 산출물 | 신뢰 수준 | 생성 주체 |
|---|---|---|
| Source snapshot·Registry | trusted | 런타임 |
| Data Quality·Capability | trusted | 런타임 |
| Fact Register | trusted | intake와 결정적 Component |
| Signal Register | trusted | 결정적 Component |
| Model draft | untrusted | Codex 모델 역할 |
| Normalized Card | validated interpretation | 런타임 normalizer |
| Integrated Assessment | validated interpretation | 단일 integrator 후 런타임 |
| Grade Record | trusted | 결정적 grader |
| Approval Record | trusted | HITL 런타임 |
| Final Result | trusted | 런타임 |

로컬 엔진은 네트워크와 모델 API를 사용하지 않는다. Codex Skill이 현재 호스트 모델로 Reasoning Job을 처리한다. 모델 가용성이나 병렬 도구가 없어도 결정적 엔진의 정확성이 달라지지 않아야 한다.

## 4. 기술·배포·디렉터리

### 4.1 기술 선택

- Python 3.11 이상
- Pack·계약: UTF-8 JSON
- JSON Schema: Draft 2020-12
- JSON 검증: jsonschema 4.x
- XLSX 읽기: openpyxl 3.1.x
- 숫자: 최초 파싱부터 Decimal
- 시간: RFC 3339 UTC
- 런타임 네트워크: 금지
- Pack YAML: 지원하지 않음
- pandas·데이터베이스: 사용하지 않음

실제 플러그인 루트는 plugin/trusted-ceo-agent이며 폴더명과 manifest name을 일치시킨다. plugin/trusted-ceo-agent/pyproject.toml은 호환 범위를, plugin/trusted-ceo-agent/uv.lock은 정확한 버전과 해시를 기록한다. 표준 라이브러리만 사용하는 plugin/trusted-ceo-agent/scripts/bootstrap.py가 uv 실행보다 먼저 Python, uv, lock hash, 준비된 가상환경, 필수 import를 검사한다.

설치와 분석 실행을 분리한다.

1. preflight: python plugin/trusted-ceo-agent/scripts/bootstrap.py preflight
2. 환경이 없을 때만 사용자가 별도로 승인한 설치: uv sync --project plugin/trusted-ceo-agent --frozen
3. 실제 분석: uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python plugin/trusted-ceo-agent/scripts/trusted_ceo_agent.py ...

preflight와 실제 분석은 네트워크를 사용하지 않는다. uv sync는 분석 실행이 아니며 사용자의 명시적 설치 승인 아래에서만 수행한다. preflight가 실패하면 설치 명령을 안내하고 분석은 시작하지 않는다.

계산 입력은 CSV, XLSX, JSON이다. TXT, Markdown, PDF는 선택형 Source로 snapshot하고 전문가 패킷의 필요 문서로 참조할 수 있지만 초기 POC에서 자동 Fact를 추출하지 않는다. 비정형 문서는 capability를 partial로 만들며, 그 내용에 근거한 진단은 Not Assessable로 남긴다.

### 4.2 디렉터리

    plugin/
      trusted-ceo-agent/
        .codex-plugin/
          plugin.json
        skills/
          trusted-ceo-agent/
            SKILL.md
            references/
              workflow.md
              reasoning-contract.md
        scripts/
          bootstrap.py
          trusted_ceo_agent.py
        trusted_ceo_agent/
          cli.py
          canonical.py
          errors.py
          filesystem.py
          contracts/
          trust/
          workflow/
          intake/
          evidence/
          components/
          packs/
          reasoning/
          grading/
          outputs/
        schemas/
        packs/
          mission/
          domain/
          problem/
        trust/
          pack-registry.json
          approval-records/
        templates/
        pyproject.toml
        uv.lock
    tests/
      unit/
      contracts/
      integration/
      determinism/
      safety/
      plugin/
      evaluation/
      fixtures/
    artifacts/

scripts/trusted_ceo_agent.py는 한글·공백 경로에서 plugin root를 찾고 cli.main만 호출한다. plugin root는 설치 후 읽기 전용일 수 있으므로 모든 실행 쓰기는 사용자가 지정한 workspace 내부 artifact root로만 간다.

### 4.3 필수 Schema 목록

- strict-json-envelope.schema.json
- condition-expression.schema.json
- source.schema.json
- source-reference.schema.json
- source-resolver.schema.json
- data-quality.schema.json
- lineage-set.schema.json
- fact.schema.json
- signal.schema.json
- evidence-link.schema.json
- capability-map.schema.json
- component-contract.schema.json
- component-run.schema.json
- evidence-core.schema.json
- mission-contract.schema.json
- mission-pack.schema.json
- domain-pack.schema.json
- problem-pack.schema.json
- pack-registry.schema.json
- pack-manifest.schema.json
- reasoning-job.schema.json
- schema-mapping-draft.schema.json
- lens-card-draft.schema.json
- normalized-card.schema.json
- join-manifest.schema.json
- integrated-draft.schema.json
- deep-dive-draft.schema.json
- writer-draft.schema.json
- grading-input.schema.json
- grade-record.schema.json
- hitl-overlay.schema.json
- approval-request.schema.json
- approval.schema.json
- workflow-state.schema.json
- snapshot-manifest.schema.json
- final-result.schema.json
- audit-manifest.schema.json
- cli-response.schema.json
- poc-oracle.schema.json

모든 Schema는 additionalProperties false를 기본으로 하고, 로컬 번들 안의 상대 $ref만 허용한다. 원격 URL과 file URI $ref를 거부한다.

## 5. 공통 계약

### 5.1 Strict JSON Decoder

모든 JSON 입력과 중간 산출물은 Schema 검증 전에 같은 decoder를 통과한다.

- 중복 key 거부
- NaN, Infinity, -Infinity 거부
- 최대 깊이 32
- 객체 key 최대 256개
- 기본 배열 최대 10,000개
- 기본 문자열 최대 64 KiB
- 파일별 별도 상한은 Schema에서 더 작게 제한
- UTF-8과 Unicode NFC 강제

JSON parser가 중복 key를 소실한 뒤 Schema를 실행하는 구현은 금지한다.

### 5.2 정규 JSON

- 객체 key는 코드포인트 순으로 정렬한다.
- 집합 의미 배열은 Schema에 선언된 복합 key로 정렬하고 중복을 거부한다.
- 순서 의미 배열만 입력 순서를 보존한다.
- Decimal은 JSON number가 아니라 정규 문자열로 저장한다.
- 0과 -0은 0으로 통일한다.
- 공백 없는 UTF-8 JSON을 해시 입력으로 사용한다.

### 5.3 ID와 해시

ID 형식은 kind prefix와 SHA-256 앞 24 hex다. 전체 해시는 integrity 필드에 보존한다.

- Source ID: raw byte SHA-256
- observed Fact ID: fact_code, observation_role, scope, time, comparison context, source lineage fingerprint
- aggregated/calculated Fact ID: fact_code, semantic_role, scope, time, comparison context
- Signal ID: signal_code, rule version, scope, time, threshold ref
- Evidence Link ID: target ref, evidence ref, polarity, role, stage
- Job ID: artifact hash, Pack manifest hash, stage, role/lens, shard
- Claim ID: job ID, local key, normalized payload
- Approval ID: gate, base artifact hash, actor, decision, patch

동일 raw data를 파일 분할해도 aggregated/calculated Fact ID는 같아야 한다. 동일 metric·scope·기간이라도 원장이 다른 observed Fact는 observation_role과 lineage가 달라 공존하며 reconcile Component가 차이를 검증한다.

artifact_hash는 run과 revision을 포함한 snapshot 전체의 해시다. semantic_fingerprint는 run ID, 시간, 물리 경로, duration, 표시용 actor name을 제외한 분석 의미의 해시다. 해시 필드 자신은 해당 해시 입력에서 제외한다.

### 5.4 Condition Expression DSL

Pack 조건은 문자열 코드나 eval이 아니라 canonical AST만 사용한다.

논리 node:

- all: args 1개 이상
- any: args 1개 이상
- not: arg 정확히 1개

leaf operator:

- eq, ne, gt, gte, lt, lte
- in, not_in
- exists, missing
- outcome_is

operand:

- fact_ref: fact_code와 reducer
- signal_ref: signal_code와 outcome
- mission_ref: 허용된 Mission Contract JSON Pointer
- hitl_ref: 허용된 overlay JSON Pointer
- literal: decimal, integer, string, boolean, date

DSL 안에서 산술하지 않는다. 비율, 증감, 기간 정렬은 등록 Component가 Fact를 만든 뒤 비교한다. 최대 깊이 8, node 64개, args 16개다. operand 타입·단위·scope가 맞지 않으면 false가 아니라 not_assessable reason을 반환한다.

## 6. Source와 원본 보존

### 6.1 Snapshot

start는 입력 파일을 안정된 read-only handle로 연다. 열기 전후 file identity, size, last-write metadata를 비교하고, 읽은 바이트의 SHA-256을 계산하며 staging에 물리 복사한다. 원본이 읽는 동안 바뀌면 실패한다.

snapshot 위치:

    artifacts/<run_id>/sources/blobs/<sha256>

hardlink를 만들지 않고 실제 바이트를 복사한다. 임시 파일을 검증한 뒤 새 이름으로 원자 이동한다. 이후 모든 분석은 snapshot을 읽으며 사용자의 원본 경로를 다시 읽지 않는다.

### 6.2 Source Registry

필수 필드:

- source_id
- source_type: uploaded_file, official_external, synthetic
- access_policy: permitted, restricted, prohibited
- evidence_usage: primary, corroboration_only, context_only
- observation_roles
- display_name
- media_type
- sha256
- size_bytes
- received_at
- snapshot_ref
- original_path_token
- aliases
- metadata

official_external의 기본 evidence_usage는 corroboration_only다. 외부 자료만으로 회사 문제를 생성할 수 없으며 회사 primary evidence를 보강할 수만 있다. context_only는 문제·가설의 supports Evidence가 될 수 없다.

source-resolver.json은 original_path_token과 실제 원본 경로를 로컬 감사용으로 연결한다. 고객 전달 package에서는 resolver와 절대 경로를 제외한다.

### 6.3 Source Reference와 Lineage Set

Source Reference 공통 필드:

- source_id
- observation_role
- locator_type: csv_records, json_pointer, xlsx_cells
- locator
- selected_fields
- record_count
- filters
- group_by
- operation
- normalized_rows_hash
- row_multiset_hash
- lineage_set_ref
- extraction_hash

CSV는 physical line과 별개인 1-based logical record index를 저장한다. quoted newline이 있어도 record index가 변하지 않아야 한다. JSON은 RFC 6901 Pointer, XLSX는 sheet와 A1 cell/range를 사용한다.

lineage set은 각 row의 정규 content fingerprint와 동일 row 중복 occurrence index의 정렬된 multiset이다. POC 상한에서는 전체 multiset을 content-addressed 파일로 보존해 교집합을 정확히 계산한다. 단순 set hash만으로 독립성을 추정하지 않는다.

### 6.4 파일별 안전

- CSV encoding은 UTF-8 BOM, UTF-8, 명시적 CP949 순서로 검사하며 선택 결과를 기록한다.
- JSON은 공통 strict decoder를 사용한다.
- XLSX는 openpyxl 전에 ZIP entry 수, 압축률, 총 비압축 크기, path traversal을 검사한다.
- XLSX macro, external link, DDE를 실행하지 않는다.
- formula cached value는 존재만으로 trusted Fact가 되지 않는다.
- formula 결과는 사용자가 재계산·저장한 workbook임을 Context/Data Gate에서 확인하거나 별도 값 export로 대조할 때만 사용한다.
- 확인되지 않은 formula는 quality issue와 not_assessable로 처리한다.

## 7. Evidence Core

### 7.1 Data Quality

파싱 실패와 의미 불명확 값을 Fact로 만들지 않는다.

필드:

- quality_issue_id
- source_ref
- issue_code
- severity: blocking, warning, info
- affected_field
- raw_value_hash
- normalized_role
- reason_code
- suggested_resolution
- resolution_status

핵심 issue code:

- missing_required_field
- invalid_decimal
- invalid_date
- ambiguous_unit
- ambiguous_period
- ambiguous_observation_role
- duplicate_business_key
- inconsistent_dimension
- untrusted_formula_value
- unsupported_type

### 7.2 Fact

Fact는 원본 관찰 또는 재현 가능한 결정적 계산이다.

필수 필드:

- fact_id
- fact_code
- fact_type: observed, aggregated, calculated
- metric_code
- semantic_role
- observation_role
- scope
- time_context
- value
- source_refs
- derivation
- quality
- producer
- integrity

scope는 dimension_code와 member_code의 정렬 배열이다. time_context는 period, as_of, window 중 정확히 하나다.

value:

- value_type: decimal, integer, string, boolean, date, datetime, category
- canonical_value
- unit_code
- currency_code
- scale

aggregated/calculated Fact의 derivation:

- component_id
- component_version
- operation_code
- formula_ref
- parameter_hash
- input_fact_ids
- component_run_id

producer는 runtime_intake 또는 deterministic_component만 허용한다. unknown, null, n/a는 Fact가 아니라 Quality 또는 not_assessable Signal이다.

### 7.3 Signal

Signal은 Pack 규칙이 Fact를 결정적으로 평가한 결과다. 실행된 규칙은 triggered 여부와 무관하게 모두 기록한다.

필수 필드:

- signal_id
- signal_code
- rule_ref
- component_ref
- threshold_ref
- input_fact_ids
- required_fact_codes
- missing_fact_codes
- scope
- time_context
- evaluation
- outcome: triggered, not_triggered, not_assessable
- direction
- impact_band_candidate
- urgency_band_candidate
- reason_codes
- producer

impact·urgency candidate는 Domain threshold가 부여한 기계 값이며 최종 전사 중요도가 아니다. not_assessable은 missing Fact 또는 blocking Quality ref가 있어야 한다. Signal은 경영 의미, 원인, grade를 포함하지 않는다.

### 7.4 Evidence Link

필수 필드:

- evidence_link_id
- target_ref
- evidence_ref
- polarity: supports, contradicts
- role: observation, corroboration, mechanism, counter_evidence, boundary
- rationale_template
- value_refs
- stage
- materialized_by
- origin
- independence_group_id

target type:

- business_meaning
- problem_candidate
- cause_hypothesis
- counter_hypothesis
- integrated_issue
- causal_relation_hypothesis
- cross_issue_conflict
- conditional_response
- expert_review_need

evidence_ref는 Fact 또는 Signal이다. 값을 rationale에 복사하지 않고 value_refs로 참조한다.

origin:

- origin_type: model_proposal, deterministic_rule, human_overlay
- origin_job_id
- model_profile
- prompt_hash
- proposal_hash

materialized_by는 runtime_normalizer, runtime_integrator, runtime_grader, runtime_hitl 중 하나다. 모델의 제안과 런타임 검증을 감사에서 분리한다.

not_assessable Signal은 boundary 또는 expert_review_need에만 supports로 연결할 수 있다. not_triggered Signal은 원인 가설을 contradicts하거나 반대 가설을 supports할 수 있다. none_found는 Evidence Link가 아니라 실제 검색 범위를 가진 challenge record다.

### 7.5 Independence

독립 Evidence chain은 Pack의 independence_policy와 실제 lineage 교집합으로 판정한다.

- 서로 다른 source role이면서 Pack이 독립 role로 선언
- 또는 같은 role이지만 lineage set 교집합이 0이고 Pack이 분리 표본을 허용
- Component가 다르다는 이유만으로 독립으로 세지 않음
- 같은 Fact에서 파생한 여러 Signal은 같은 independence_group_id

런타임이 independence_group_id를 생성하며 모델은 값을 정하지 못한다.

### 7.6 Evidence Core Artifact

구획:

- envelope
- mission_contract_ref
- pack_manifest
- component_manifest
- source_registry
- data_quality_register
- fact_register
- signal_register
- evidence_links
- capability_map
- integrity

envelope:

- schema_version
- artifact_id
- run_id
- revision
- parent_artifact_hash
- stage
- created_at
- semantic_fingerprint
- artifact_hash

### 7.7 Validator

순서:

1. strict JSON과 Schema
2. ID 형식·중복
3. Source snapshot hash
4. 모든 참조 존재
5. Fact derivation 재계산
6. Signal 조건 재평가
7. Evidence lineage 해소
8. Pack effective authority
9. 안전·개인정보·전문 경계
10. snapshot manifest와 parent chain

즉시 차단:

- Source·Pack hash 불일치
- 중복 ID나 알 수 없는 참조
- Fact 계산 불일치
- Signal 재평가 불일치
- 미지원 Schema
- 위조·stale 승인
- 권한 상한 상승

degraded:

- 실제 데이터 부족
- 비핵심 매핑 모호성
- 비차단 품질 경고
- 미지원 Domain

degraded는 capability를 partial 또는 unsupported로 만들며 내부 오류로 기록하지 않는다.

## 8. 결정적 Component

### 8.1 공통 계약

- component_id와 semantic version
- supported_input_fact_codes
- required_dimensions
- parameter_schema
- output_fact_codes
- output_signal_codes
- failure_reason_codes
- parallel_safe
- max_input_records
- timeout_seconds

Component Run:

- component_run_id
- component_id와 version
- input_artifact_hash
- sorted_input_fact_ids
- parameter_hash
- pack_refs
- output_fact_ids
- output_signal_ids
- status: completed, not_assessable, failed
- reason_codes
- duration

Component는 순수 함수이고 네트워크, 모델, 난수, 전역 mutable state를 사용하지 않는다. 임계값은 Pack threshold_ref에서만 받는다. 입력 부족은 not_assessable, 코드 예외·계약 위반은 failed다.

### 8.2 최소 9개

| Component | 기능 | 핵심 안전 조건 |
|---|---|---|
| aggregate | 합계·평균·최소·최대·count | 단위·통화 불일치 시 변환 Pack 없으면 중단 |
| compare | 전기·전년·기준·목표 대비 | baseline 0이면 변화율 미생성 |
| ratio | 두 metric 비율 | 분모 0·scope 불일치 시 판단 불가 |
| trend_persistence | 연속 방향·지속·변곡 | 최소 관측 수는 Pack 참조 |
| mix_concentration | share·Top N·HHI | 모집단 reconcile 실패 시 해석 Signal 금지 |
| reconcile | 전체·부분·원장 항등 검증 | 오차는 Pack threshold만 사용 |
| flow_aging | 유입·처리·잔존·aging | 관측 종료일과 censoring 기록 |
| bridge_decompose | 가격·수량·mix·기타 기여 | residual reconcile 실패 시 원인 근거 승격 금지 |
| temporal_alignment | 인식·서비스·검수·청구·현금일 정렬 | date role 모호 시 Data Gate |

신규 Component는 Yellow change다. 계약, 정상·경계·실패 3종 이상, Decimal·순차/병렬 동등성, regression, 사람 승인, version 기록이 필요하다.

## 9. Mission Contract와 Pack Stack

### 9.1 실행별 Mission Contract

고객 요청은 Pack이 아니라 실행별 Mission Contract다.

필수 필드:

- mission_contract_id
- contract_version
- business_question
- business_model
- current_symptoms
- customer_hypotheses
- decision_context
- decision_units
- decision_deadline
- analysis_horizon
- organization_scope
- priority_dimensions
- constraints
- recent_business_changes
- recent_organization_changes
- recent_policy_changes
- included_scopes
- excluded_scopes
- comparison_preferences
- materiality_context
- data_definitions
- confidentiality
- required_human_roles
- confirmation

customer_hypotheses 항목은 hypothesis_id, statement, status: unverified, source: customer를 가진다. Fact로 승격하지 않는다.

decision unit:

- decision_unit_ref
- unit_type: enterprise, business_unit, customer_portfolio, product_portfolio, contract, process, control
- scope_key
- owner_role
- deadline

요청이 없으면 business_question은 제공된 데이터에서 CEO가 인지하지 못한 중요한 경영 문제를 탐색한다로 생성한다. 자동 기본값도 Context Gate에서 사람이 확인해야 한다.

confirmation:

- confirmed: literal true
- actor_id
- actor_role
- confirmed_at
- contract_hash

### 9.2 Mission Pack

Mission Pack은 거의 고정된 공통 정책을 가진다.

- customer_hypothesis_policy
- required_challenge_policy
- reasoning_sequence
- result_grade_definitions
- required_output_sections
- professional_boundaries
- hitl_minimum_gates
- trust_kernel_rules
- default_privacy_policy
- model_role_profiles
- default_limits

Mission Pack에는 회사명, 실제 질문, 기간, 고객 가설, 고객 우선순위를 넣지 않는다.

### 9.3 공통 Pack Envelope

- schema_version
- pack_type: mission, domain, problem
- pack_id
- pack_version
- requested_authority: full, provisional, boundary
- title
- description
- applicability
- dependencies
- safety
- content

Pack 내부 requested_authority는 신뢰 근거가 아니다.

### 9.4 외부 Pack Registry와 effective authority

plugin/trusted-ceo-agent/trust/pack-registry.json은 설치된 플러그인의 신뢰 원장이다.

Registry entry:

- pack_sha256
- pack_id
- pack_version
- effective_authority: full, boundary
- approval_record_hash
- approved_by_role
- approved_at
- contract_test_manifest_hash
- valid_from
- revoked_at

loader는 raw Pack hash를 Registry와 대조해 effective authority를 부여한다. Registry에 없는 Pack은 requested_authority와 무관하게 provisional이다. Day-of Pack은 Registry를 수정하지 않고 실행별 provisional approval과 결합한다.

Full 승격 조건:

- strict Schema와 모든 참조 통과
- 최소 3개 contract case
- 전체 regression
- 사람 승인
- version 1.0.0 이상
- Registry entry 생성

### 9.5 권한

Full:

- 검증 KPI·threshold·mechanism 사용
- 심화 계산과 조건부 대응
- Decision Required 후보
- 전문가 trigger

Provisional:

- 실행별 승인 필수
- 기존 검증 Component만 사용
- 모든 결과 provisional 표시
- Decision Required를 Immediate Verification으로 하향
- 검증·모니터링 방향만 허용
- Expert Review Required는 유지

Boundary:

- 적용 경계, 필요 데이터, 금지 분석, 안전 중단
- 공통 품질과 일반 Fact만 허용
- 도메인 문제·원인·대응은 Not Assessable

### 9.6 Domain Pack

필수 content:

- domain_code
- applicability_dimensions
- applicability_rules
- exclusions
- terminology
- metric_definitions
- threshold_definitions
- expected_relationships
- analysis_lenses
- mechanism_catalog
- expert_triggers
- required_data
- forbidden_interpretations
- safe_stop_rules
- independence_policy
- privacy_policy

metric_definition:

- metric_code
- business_definition
- accepted_observation_roles
- data_type
- unit_policy
- time_role
- allowed_dimensions
- aggregation_policy
- reconciliation_refs

threshold_definition:

- threshold_id
- condition_expression
- impact_band
- urgency_band
- provenance
- valid_from
- valid_to

mechanism:

- mechanism_ref
- explanation
- expected_support_patterns
- expected_counter_patterns
- distinguishing_test_refs
- prohibited_conclusion

expert trigger:

- expert_trigger_ref
- profession
- trigger_condition
- required_evidence_roles
- required_documents
- review_question_template
- prohibited_agent_conclusions

privacy_policy:

- direct_identifier_roles
- prohibited_dimensions
- minimum_group_size
- suppression_rule
- allowed_reasoning_dimensions

### 9.7 Problem Pack

필수 content:

- problem_family_code
- domain_pack_refs
- entry_conditions
- required_capabilities
- lens_plan
- analysis_plan
- hypothesis_templates
- evidence_requirements
- distinguishing_tests
- decision_type_catalog
- blocking_counter_evidence_conditions
- deep_dive_plan
- conditional_response_catalog
- expert_trigger_refs
- not_assessable_rules
- stop_rules

entry condition은 문제의 확정이 아니라 검사 권한만 연다.

lens plan:

- lens_id
- role: requested, challenge, control, timing, customer, operational, financial
- required
- capability_refs
- allowed_mechanism_refs
- max_shards

evidence requirement:

- target_type
- required_roles
- minimum_independent_chains
- allowed_fact_codes
- allowed_signal_codes
- quality_constraints

decision type:

- decision_type_ref
- label
- allowed_decision_unit_types
- required_evidence_roles
- executive_roles
- options_required

blocking counter evidence condition:

- condition_ref
- target_problem_family
- condition_expression
- reason_code

blocking 여부는 모델이 아니라 런타임이 이 AST를 평가해 정한다.

conditional response:

- response_ref
- applicable_patterns
- preconditions
- disqualifiers
- monitoring_metrics
- reversibility
- owner_role
- expert_review_refs
- forbidden_commitments

Problem Pack은 숫자 threshold를 복제하지 않고 Domain threshold_ref를 사용한다.

### 9.8 초기 Pack 세트

Mission:

- trusted-ceo-default@1.0.0, 목표 effective Full

Domain:

- b2b-services@1.0.0, 목표 effective Full
- generic-business-boundary@1.0.0, effective Boundary

b2b-services 범위:

- 프로젝트형·구독형·혼합형 B2B 서비스
- 월별 재무, 고객·계약·상품, 투입시간·원가, 검수·청구 데이터

제외:

- 제조 재고 원가
- 은행·보험 건전성
- 규제 자본
- 소비자 의료 임상 판단

Problem:

- profitability-erosion@1.0.0
- revenue-mix-quality@1.0.0
- customer-concentration@1.0.0
- delivery-capacity-overrun@1.0.0
- revenue-timing-control@1.0.0

초기 threshold:

| threshold_id | 규칙 |
|---|---|
| margin_decline_high | gross margin 하락 3 percentage point 이상 |
| margin_decline_critical | gross margin 하락 7 percentage point 이상 |
| mix_shift_high | 저마진 segment share 증가 10 percentage point 이상이고 margin gap 5 percentage point 이상 |
| driver_contribution_plausible | gap 설명 비중 30% 이상 |
| driver_contribution_leading | gap 설명 비중 60% 이상과 독립 corroboration |
| top3_concentration_high | Top 3 share 60% 이상 또는 10 percentage point 이상 증가 |
| top3_concentration_critical | Top 3 share 75% 이상 |
| delivery_overrun_high | plan 대비 10% 이상, 2개 기간 또는 대상 20% 이상 |
| delivery_overrun_critical | plan 대비 20% 이상 |
| revenue_timing_expert | 보고기간을 넘는 검수·인식 불일치 금액이 기간 매출 2% 이상 |

초기 privacy policy는 직접 식별자 reasoning 금지, minimum_group_size 5, 5 미만 집단 suppress로 고정한다.

초기 b2b-services Pack은 구현 직후 provisional로 로드한다. contract·regression과 경영·회계 검토 승인을 통과해 Registry에 등록된 뒤 POC Full 실행에 사용한다. 이 승격 없이 Decision Required 합격 시나리오를 통과한 것으로 보지 않는다.

### 9.9 Pack 선택

1. raw bytes, Registry, Schema, 참조를 검증한다.
2. Mission의 허용 범위와 data profile로 Domain 후보를 결정적으로 필터링한다.
3. 후보가 0이면 Boundary다.
4. 후보가 2개 이상이거나 의미가 모호하면 Data Gate를 연다.
5. entry condition으로 Problem 검사 목록을 만든다.
6. Mission이 명시한 문제는 entry Signal 없이 검사할 수 있지만 증거 없이 확정하지 않는다.
7. required_lens_ids에는 requested와 최소 하나의 challenge가 포함되어야 한다.

### 9.10 Pack Loader 안전

- Pack root 밖 경로 거부
- absolute path와 parent traversal 거부
- symlink, junction, reparse, hardlink target 거부
- load 전후 identity와 hash 검증
- strict JSON
- 크기·깊이·cardinality 제한
- condition DSL 외 조건 거부
- 존재하지 않는 Component·metric·threshold·mechanism ref 거부
- Registry가 없는 Full 자가 선언 거부

Pack raw bytes와 Registry entry는 run의 pack-snapshots에 복사하고 이후 snapshot만 사용한다.

## 10. Bounded AI Reasoning

### 10.1 모델 실행 경계

로컬 엔진은 모델을 호출하지 않는다. Skill은 Reasoning Job을 현재 Codex 모델에 전달하고 draft JSON을 CLI에 제출한다.

일반 Codex Skill은 현재 모델의 파일·shell 도구를 단계별로 제거한다고 보장할 수 없다. 따라서 tool isolation을 Trust Kernel의 보안 보장으로 주장하지 않는다. 현재 모델이 작성하거나 CLI에 전달한 모든 파일은 origin과 무관하게 untrusted input이며, strict Schema·allowlist·hash·state CAS를 통과하기 전에는 신뢰 산출물이 아니다.

Approval은 모델이 만든 JSON 파일로 받을 수 없다. 사용자가 실제 터미널 TTY에서 별도 interactive approval 명령을 실행하고 일회 nonce를 확인한 경우에만 런타임이 Approval Record를 생성한다. 비대화형 stdin, pipe, draft 파일, Skill의 자동 승인 요청은 거부한다. TTY 승인 채널이 없는 호스트는 approval_required 상태에서 멈추며 Trusted Final Result를 만들지 않는다.

이 POC의 위협 모델은 모델의 잘못된 해석·prompt injection·임의 draft를 방어하지만, 같은 OS 사용자 권한을 탈취한 악성 프로세스까지 격리한다고 주장하지 않는다. 그 위협에는 별도 OS 계정·sandbox가 필요하다.

역할 profile:

| 역할 | profile | 논리 동시성 | 출력 |
|---|---|---:|---|
| schema_mapper | balanced_structured | 1 | 매핑 후보 |
| lens_analyst | balanced_structured | 최대 3 | 독립 진단 카드 |
| integrator | strong_structured | 1 | 통합 issue 구조 |
| deep_dive_integrator | strong_structured | 1 | 승인 범위 심화 |
| output_writer | strong_structured | 1 | 숫자 없는 표현 template |

호스트가 sub-agent 병렬 실행을 지원하면 lens를 최대 3개 병렬로 처리하고, 지원하지 않으면 같은 Job을 순차 처리한다. 엔진은 completion 순서가 아니라 job_id 순으로 reduce한다. 실제 model ID·host version·profile·prompt hash·attempt를 알 수 있는 범위에서 감사 기록에 남기며, model ID가 노출되지 않으면 host_managed로 명시한다.

schema_mapper와 output_writer는 선택 역할이다. mapper가 없으면 결정적 후보를 Data Gate에 직접 제시하고, writer가 없거나 2회 실패하면 검증된 기본 template renderer를 사용한다. lens, integrator, 승인된 deep_dive_integrator는 해당 분석 범위에서 필수다.

### 10.2 단계별 Reasoning Job

공통 필드:

- contract_version
- job_id
- stage
- artifact_ref
- mission_contract_hash
- pack_manifest_hash
- prompt_template_hash
- model_profile
- capability_ids
- allowed_fact_ids
- allowed_signal_ids
- allowed_mechanism_refs
- allowed_test_refs
- allowed_expert_trigger_refs
- allowed_decision_type_refs
- allowed_decision_unit_refs
- required_signal_ids
- output_schema_ref
- limits_ref
- untrusted_text_markers

stage별 oneOf:

- schema_mapping: mapping_question_refs 필수
- lens: lens_id, shard_index, shard_count 필수
- integrated: join_manifest_ref 필수
- deep_dive: approved_scope_ref와 component_run_refs 필수
- writer: structured_output_ref와 allowed_claim_ids 필수

lens_id를 비-lens Job에 요구하지 않는다.

### 10.3 문맥 상한

- Job당 Fact 48
- Job당 Signal 48
- observation 12
- problem candidate 6
- 문제당 cause 4
- cause당 counter 2
- 문제당 verification 3
- data request 8
- human question 8
- expert candidate 6
- payload 64 KiB
- 제목 120자
- statement template 400자

상한 초과 시 scope, period, component_id 순으로 결정적 shard를 만든다. 모델은 continuation 여부를 정하지 않는다. 런타임이 required Signal과 disposition 차이로 추가 shard를 계산한다. 전체 lens card가 6개를 넘으면 scope_narrowing_required 상태로 이동하고 제외 범위를 blind spot에 기록한다.

### 10.4 숫자 표현

모델은 자유 텍스트에 숫자·통화·백분율을 쓰지 않는다.

주장 필드:

- statement_template
- value_refs

value_ref:

- token
- fact_or_signal_id
- display_field
- display_format_ref

template에는 token placeholder만 허용하고 숫자 literal을 거부한다. 최종 renderer가 Fact·Signal에서 값을 주입한다. 따라서 일반 문장에서 물질적 숫자를 의미적으로 판정할 필요가 없다.

### 10.5 Lens Draft

필수 배열:

- observations
- business_meanings
- problem_candidates
- cause_hypotheses
- counter_hypotheses
- challenge_reviews
- verification_tests
- signal_dispositions
- uncertainties
- data_requests
- human_questions
- expert_trigger_candidates

상태:

- assessment_status: complete, partial, not_assessable
- status_reason_codes

observation:

- local_key
- statement_template
- value_refs
- fact_ids
- signal_ids

business meaning:

- local_key
- observation_local_keys
- statement_template
- value_refs
- evidence_proposals

problem candidate:

- local_key
- business_meaning_local_keys
- problem_family_ref
- statement_template
- value_refs
- evidence_proposals

cause hypothesis:

- local_key
- problem_local_key
- mechanism_ref
- statement_template
- value_refs
- evidence_proposals
- support_condition_refs
- rejection_condition_refs
- distinguishing_test_refs

counter hypothesis:

- local_key
- challenged_hypothesis_local_key
- mechanism_ref
- statement_template
- value_refs
- evidence_proposals

challenge review:

- target_hypothesis_local_key
- outcome: found, none_found, not_assessable
- searched_fact_ids
- searched_signal_ids
- missing_fact_codes
- statement_template

verification test:

- test_ref
- target_hypothesis_local_key
- status: ready, needs_data, human_confirmation, completed
- required_fact_codes
- result_fact_ids
- result_signal_ids

signal disposition:

- signal_id
- disposition: used_support, used_counter, boundary, duplicate, contextual_only
- target_local_keys
- duplicate_of_signal_id
- context_evidence_ids
- rationale_template

uncertainty:

- local_key
- target_local_keys
- uncertainty_type: data, definition, mechanism, timing, scope
- reason_code
- missing_fact_codes
- statement_template

data request:

- local_key
- target_local_keys
- required_fact_codes
- requested_source_role
- required_fields
- period
- purpose_template

human question:

- local_key
- target_local_keys
- question_type: data_meaning, business_context, strategy_intent, priority, professional_boundary
- question_template
- allowed_answer_type

expert candidate:

- local_key
- target_problem_local_keys
- target_hypothesis_local_keys
- expert_trigger_ref
- evidence_proposals
- required_document_refs
- review_question_template

prohibited conclusions는 모델 필드가 아니다. normalizer가 Domain Pack에서 복사한다.

limitation:

- local_key
- capability_ref
- reason_code
- affected_target_local_keys
- statement_template

### 10.6 상태별 유효성

complete:

- assigned required Signal disposition 100%
- 발견된 cause마다 counter 또는 유효한 none_found/not_assessable
- blocking limitation 없음

partial:

- 하나 이상의 유효 observation 또는 boundary record
- 빠진 required Signal, capability, shard를 status reason에 명시
- 부분 범위 밖 문제를 확정하지 않음

not_assessable:

- problem, cause, counter 배열은 비어 있음
- data request 또는 limitation이 하나 이상
- missing Fact·Capability reason 필수

material claim type은 business_meaning, problem_candidate, cause_hypothesis, counter_hypothesis, expert_trigger_candidate다. 각 material claim은 supports proposal이 하나 이상이어야 한다.

### 10.7 Normalized Card

런타임이 다음 envelope를 붙인다.

- schema_version
- card_id
- job_id
- artifact_ref
- pack_manifest_hash
- lens_id
- model_profile
- assessment_status
- used_fact_ids
- used_signal_ids
- normalized_payload
- evidence_link_ids
- validation_result
- integrity

used Fact·Signal은 모델이 선언하지 않고 normalizer가 모든 내부 ref의 정확한 정렬 합집합으로 계산한다.

### 10.8 Draft 검증과 재시도

- strict JSON과 additionalProperties false
- Job allowlist와 current revision 참조
- local key 유일성·부모 타입
- material claim Evidence
- cause의 challenge
- 숫자 literal 금지와 value_ref 유효성
- lens의 최종 등급·전사 중요도·확정 해결책 금지
- 전문직 최종 결론 금지
- 모든 triggered·not_assessable Signal disposition

구조·참조 오류는 validation error만 전달해 한 번 repair한다. 총 attempt는 2회다.

- optional lens 재실패: coverage gap으로 제한 진행 가능
- required/challenge lens 재실패: blocked
- integrated 또는 승인된 deep 재실패: Trusted Output 차단
- schema mapper 재실패: 결정적 mapping 후보로 Data Gate 진행
- writer 재실패: 검증된 deterministic template fallback
- 데이터 부족: 재시도하지 않음
- 내부 실패를 Not Assessable로 변환하지 않음

### 10.8.1 단계별 보조 Draft

schema mapping draft:

- mapping_question_ref
- source_field_ref
- candidate_mappings
- ambiguity_reason_code
- required_human_choice

candidate mapping:

- observation_role
- metric_code
- unit_code
- scale
- time_role
- dimension_code
- supporting_header_refs

mapper는 confidence 점수나 확정 mapping을 만들지 않는다. Data Gate가 선택한다.

deep-dive draft:

- approved_scope_ref
- component_run_refs
- updated_cause_hypotheses
- updated_counter_hypotheses
- distinguishing_test_results
- conditional_response_candidates
- expert_review_candidates
- remaining_uncertainties
- additional_data_requests

conditional response candidate:

- local_key
- target_issue_ref
- response_ref
- action_template
- value_refs
- precondition_refs
- disqualifier_refs
- monitoring_metric_refs
- reversibility
- owner_role
- expert_review_refs

expert review candidate:

- local_key
- target_issue_ref
- expert_trigger_ref
- evidence_proposals
- required_document_refs
- review_question_template

writer draft:

- structured_output_ref
- claim_templates
- expert_packet_templates
- ceo_brief_section_order

writer의 각 template는 allowed_claim_ids 중 하나를 참조하고 새로운 claim·Evidence·grade·숫자를 만들 수 없다. writer 실패 fallback은 같은 structured output을 고정 template로 렌더하며 분석 내용과 grade를 바꾸지 않는다.

### 10.9 Join Barrier

task terminal:

- completed
- valid_not_assessable
- not_applicable
- timed_out
- failed_contract
- superseded

accepted_terminal은 completed, valid_not_assessable, not_applicable이다.

Barrier 요구 목록은 dispatch 전에 고정한다.

- Problem Pack required_lens_ids
- requested lens ID
- challenge lens ID
- 이미 결정적 expert-trigger Signal이 있는 경우 Pack에 등록된 대응 lens ID

Join 이후 알게 되는 impact를 Barrier 조건으로 사용하지 않는다.

통과 조건:

- 모든 task terminal
- required task가 accepted_terminal
- 같은 artifact·Pack·Mission hash
- 성공·판단 불가 카드 Schema·참조 통과
- required Signal disposition 완료

late result는 attempt_id, cutoff_at, timed_out 또는 superseded를 기록하고 현재 revision에 넣지 않는다.

### 10.10 결정적 Pre-Join

코드는 원인이나 중요도를 판단하지 않고 다음 exact key만 사전 묶음 후보로 만든다.

- problem_family_ref
- normalized scope key
- normalized period key
- exact shared Evidence ID

pre_join_cluster는 중복 후보일 뿐 개별 candidate를 삭제하지 않는다.

### 10.11 Integrated Draft

필수:

- join_manifest_ref
- card_refs
- issue_clusters
- integrated_issues
- causal_relation_hypotheses
- cross_issue_conflicts
- blind_spots
- response_type_candidates
- expert_review_candidates

integrated issue:

- local_key
- problem_family_ref
- scope_key
- decision_unit_ref
- source_candidate_ids
- observation_claim_refs
- cause_hypothesis_refs
- counter_hypothesis_refs
- unresolved_conflict_refs
- impact_evidence_refs
- urgency_evidence_refs
- decision_need_proposal
- verification_requirement_refs
- response_type_refs
- expert_trigger_refs

decision_need_proposal:

- decision_type_ref
- decision_unit_ref
- basis_claim_refs
- rationale_template

decision_type_ref와 decision_unit_ref는 Job allowlist 안에 있어야 한다. Diagnostic Overlay가 이 proposal을 수용·기각·분쟁 처리한 뒤에만 decision_needed를 계산한다.

issue cluster:

- cluster_local_key
- problem_family_ref
- scope_key
- decision_unit_ref
- source_candidate_ids
- grouping_reason: exact_family_scope_unit, shared_evidence_candidate

blind spot:

- blind_spot_local_key
- capability_ref
- affected_scope_keys
- reason_codes
- missing_fact_codes
- data_request_refs
- consequence_template

response type candidate:

- local_key
- target_issue_local_key
- response_ref
- precondition_refs
- disqualifier_refs
- verification_requirement_refs

pre-HITL expert review candidate:

- local_key
- target_issue_local_key
- expert_trigger_ref
- evidence_proposals
- required_document_refs
- review_question_template

causal relation:

- from_issue_local_key
- to_issue_local_key
- status: hypothesis, contradicted, unresolved
- mechanism_ref
- supports_evidence_proposals
- contradicts_evidence_proposals
- distinguishing_test_refs

conflict:

- conflict_local_key
- target_refs
- side_a_evidence_proposals
- side_b_evidence_proposals
- resolution_test_refs
- status: unresolved, resolved

integrator의 Evidence proposal 형식은 Lens와 동일하다. runtime integrator가 causal_relation_hypothesis 또는 cross_issue_conflict target ID를 먼저 만든 뒤 proposal을 Evidence Link로 물질화한다. supports·contradicts 필드에 Fact·Signal ID를 직접 넣지 않는다.

진단 승인 전에는 response type ref와 전제만 제안하며 실제 대응 문장·실행 권고를 만들지 않는다.

전역 issue 20개 제한을 두지 않는다. 많으면 problem_family_ref + scope_key + decision_unit_ref가 정확히 같은 것만 계층 view로 묶고 모든 개별 issue와 grade를 보존한다. Decision Required, Immediate Verification, Expert Review Required는 모두 본문에 표시한다.

## 11. 결과 등급

### 11.1 Grading Input

필수 필드:

- issue_id
- assessability: assessable, partial, not_assessable
- not_assessable_reason_codes
- evidence_state: sufficient, limited, conflicting, none
- impact_band: critical, high, medium, low, unknown
- urgency_band: immediate, near_term, routine, unknown
- mission_priority_match: true, false
- executive_materiality: true, false, unknown
- decision_needed: true, false, unknown
- expert_trigger_state: required, possible, none
- pack_authority: full, provisional, boundary
- diagnostic_disposition: accepted, rejected, disputed, pending
- verification_authorized: true, false
- issue_disposition: standalone, absorbed, duplicate, isolated_low
- trackable: true, false
- response_eligibility: eligible, needs_verification, prohibited
- provenance_refs

### 11.2 입력 산출 규칙

| 입력 | 결정적 산출 |
|---|---|
| assessability | Capability와 Problem required evidence의 충족 상태 |
| evidence_state | 11.3 우선순위 |
| impact_band | 유효 threshold candidate 중 critical > high > medium > low |
| urgency_band | immediate > near_term > routine |
| mission_priority_match | confirmed Mission priority와 issue scope/problem ref exact match |
| executive_materiality | impact critical/high 또는 urgency immediate/near_term 또는 mission priority면 true; 모두 low/routine/nonpriority면 false; 그 외 unknown |
| decision_needed | accepted decision proposal이면 true; accepted issue에서 decision disposition이 not_needed이면 false; disputed이면 unknown; pending/rejected이면 계산하지 않음 |
| expert trigger | Pack trigger AST와 required Evidence role을 코드가 검증 |
| trackable | monitoring metric과 재검토 주기가 모두 존재 |
| response eligibility | response precondition AST와 disqualifier를 코드가 평가 |

Mission/HITL은 threshold 자체를 바꾸지 않는다. confirmed priority는 executive_materiality만 올릴 수 있고 provenance를 남긴다.

### 11.3 Evidence State 우선순위

1. 유효 supports chain 0개: none
2. Problem Pack의 blocking_counter_evidence_conditions AST가 true인 unresolved contradiction 존재: conflicting
3. valid independence group 수가 Pack minimum 미만: limited
4. 필수 Evidence role, counter check, distinguishing test 중 하나라도 미충족: limited
5. 나머지: sufficient

상태는 서로 배타적이다.

### 11.4 Grade 결정표

순서대로 첫 조건을 적용한다.

0. Schema·무결성·승인·grader 입력 검증 실패: grade 없음, run blocked 또는 failed
1. diagnostic_disposition pending: grade 미발행, Diagnostic Gate 대기
2. diagnostic_disposition rejected: grade 미발행, 최종 active issue에서 제외하고 감사에만 보존
3. diagnostic_disposition disputed이고 verification_authorized false: grade 미발행, Diagnostic Gate 미완료
4. pack_authority boundary: Not Assessable, reason unsupported_domain
5. expert_trigger_state required: Expert Review Required
6. assessability partial/not_assessable 또는 impact_band·urgency_band·executive_materiality 중 하나가 unknown: Not Assessable, 명시 reason 필수
7. issue_disposition duplicate/absorbed/isolated_low이고 executive_materiality false: Appendix Signal
8. evidence_state sufficient, executive_materiality true, decision_needed true, diagnostic accepted: Decision Required
9. executive_materiality true AND (evidence_state가 limited/conflicting OR decision_needed unknown OR diagnostic_disposition disputed): Immediate Verification
10. executive_materiality true, evidence_state sufficient, decision_needed false, diagnostic accepted, trackable true: Monitor와 secondary flag delegated_owner_action
11. executive_materiality false, evidence가 none이 아니고 trackable true: Monitor
12. 위 조합에 속하지 않는 유효 입력: GradeRuleUncovered 오류로 run blocked

decision_needed의 unknown은 Not Assessable 직행 필드가 아니다. Diagnostic dispute와 verification_authorized true 조합에서만 허용한다. diagnostic accepted에서는 decision_needed가 true 또는 false여야 한다.

Provisional은 8번 Decision Required를 Immediate Verification으로 하향하고 provisional flag를 붙인다. Expert Review Required는 유지한다.

expert_trigger_state possible은 secondary flag possible_expert_review다. 같은 issue가 전문가 검토와 CEO 결정을 함께 요구하면 primary는 Expert Review Required, secondary는 executive_decision_after_expert_review다.

response_eligibility는 grade에 영향을 주지 않는다.

- eligible: 승인 후 조건부 대응 게시 가능
- needs_verification: 대응 대신 검증 단계만 게시
- prohibited: 대응 숨김, 이유 표시

모든 enum Cartesian 조합을 exhaustive unit test로 실행한다. Not Assessable은 명시 reason 없이 생성할 수 없고 default fallback으로 사용하지 않는다.

### 11.5 Grade Record

- grade_record_id
- issue_id
- publication_status: published, withheld
- rule_version
- grading_input_hash
- input_snapshot_hash
- primary_grade
- secondary_flags
- reason_codes
- applied_threshold_refs
- applied_mission_refs
- applied_approval_refs
- authority_cap_applied
- computed_at

withheld record는 primary_grade를 갖지 않고 pending, rejected, unapproved_dispute reason을 가진다. rejected issue는 최종 active issue 배열에서 제외하지만 감사 패키지에는 원래 주장·Evidence·HITL disposition을 보존한다.

모델과 사람은 grade를 직접 수정하지 못한다. 입력을 새 revision으로 바꾸고 grader를 재실행한다.

## 12. HITL

### 12.1 상태

- created
- context_confirmation_required
- context_ready
- schema_mapping_job_ready
- mapping_proposal_ready
- data_confirmation_required
- evidence_ready
- scope_narrowing_required
- lens_jobs_ready
- lens_ready
- integrated_draft
- diagnostic_approval_required
- deep_dive_authorized
- deep_dive_jobs_ready
- deep_dive_ready
- finalization_jobs_ready
- writer_ready
- final_approval_required
- delivery_approved
- finalized
- blocked
- stopped_by_human
- failed
- cancelled

blocked는 resume_state와 blocker를 가진 복구 가능 상태다. failed, stopped_by_human, cancelled, finalized는 terminal이다. 외부 자동 전달은 비목표이므로 delivered 상태를 두지 않는다.

### 12.2 전이표

| From | Event·Command | Guard | To |
|---|---|---|---|
| created | start | Mission 미확인 | context_confirmation_required |
| created | start | confirmed Mission 유효 | context_ready |
| context_confirmation_required | approve context | 유효 승인 | context_ready |
| context_confirmation_required | reject | 전체 중단 | stopped_by_human |
| context_ready | scan | 중요 mapping 모호 | schema_mapping_job_ready |
| context_ready | scan | mapping 명확, scan 통과 | evidence_ready |
| schema_mapping_job_ready | ingest schema mapping | draft 유효 또는 결정적 fallback | mapping_proposal_ready |
| mapping_proposal_ready | request data approval | proposal·diff 유효 | data_confirmation_required |
| data_confirmation_required | approve data | mapping patch 유효, 재scan 통과 | evidence_ready |
| data_confirmation_required | request changes | 새 mapping 필요 | data_confirmation_required |
| evidence_ready | prepare lens | card 예상 6 이하 | lens_jobs_ready |
| evidence_ready | prepare lens | card 예상 6 초과 | scope_narrowing_required |
| scope_narrowing_required | approve scope | 제외 범위와 blind spot 기록 | evidence_ready |
| scope_narrowing_required | reject | 전체 중단 | stopped_by_human |
| lens_jobs_ready | reduce lens | required task accepted terminal | lens_ready |
| lens_jobs_ready | contract failure | required task 실패 | blocked |
| lens_ready | join + ingest integrated | Barrier와 draft 유효 | integrated_draft |
| integrated_draft | request diagnostic approval | 모든 issue 구조 유효 | diagnostic_approval_required |
| diagnostic_approval_required | request changes | data/scan 영향 | evidence_ready |
| diagnostic_approval_required | request changes | reasoning만 영향 | lens_jobs_ready |
| diagnostic_approval_required | approve | deep scope 비어 있음 | finalization_jobs_ready |
| diagnostic_approval_required | approve | deep scope 존재 | deep_dive_authorized |
| diagnostic_approval_required | reject whole run | 명시 중단 | stopped_by_human |
| deep_dive_authorized | run deep components | 승인 component만 | deep_dive_jobs_ready |
| deep_dive_jobs_ready | ingest deep result | required deep Job 유효 | deep_dive_ready |
| deep_dive_jobs_ready | failure | 계약·실행 실패 | blocked |
| deep_dive_ready | prepare finalization | deep result 유효 | finalization_jobs_ready |
| finalization_jobs_ready | grade + ingest writer | grade와 writer draft 유효 | writer_ready |
| finalization_jobs_ready | writer fallback | writer 2회 실패, deterministic template 유효 | writer_ready |
| writer_ready | request final approval | output·expert packet·grade 유효 | final_approval_required |
| final_approval_required | request changes | deep scope 영향 | deep_dive_authorized |
| final_approval_required | request changes | 표현·routing만 영향 | finalization_jobs_ready |
| final_approval_required | approve | 모든 대상 disposition 완료 | delivery_approved |
| final_approval_required | reject whole run | 명시 중단 | stopped_by_human |
| delivery_approved | finalize | Final Validator 통과 | finalized |
| any nonterminal | integrity failure | 복구 불가 | failed |
| any nonterminal | cancel | 사용자 취소 | cancelled |
| any nonterminal | stop | 사용자 중단 | stopped_by_human |
| blocked | resume | blocker 해소, expected revision 일치 | resume_state |

approve_with_edits는 patch를 새 overlay revision으로 적용한 뒤 같은 행의 approve guard를 평가한다. issue 하나의 rejected disposition은 전체 run reject가 아니다.

### 12.3 HITL Overlay

사람은 AI artifact를 직접 patch하지 않고 별도 overlay를 만든다.

disposition:

- target_ref
- status: accepted, rejected, disputed, superseded
- rationale
- replacement_ref

decision disposition:

- decision_proposal_ref
- status: needed, not_needed, disputed, rejected
- verification_authorized: true, false
- rationale

disputed는 verification_authorized true일 때만 Diagnostic Gate 완료 조건을 만족한다. rejected issue는 active result에서 제외한다.

Gate별 허용 JSON Pointer:

Context:

- /mission_contract/business_question
- /mission_contract/customer_hypotheses
- /mission_contract/decision_context
- /mission_contract/analysis_horizon
- /mission_contract/priority_dimensions
- /mission_contract/recent_business_changes
- /mission_contract/included_scopes
- /mission_contract/excluded_scopes

Data:

- /mapping/columns/*/observation_role
- /mapping/columns/*/unit_code
- /mapping/columns/*/scale
- /mapping/columns/*/time_role
- /mapping/columns/*/dimension_code
- /mapping/sources/*/included

Scope narrowing:

- /scope_narrowing/included_scope_keys
- /scope_narrowing/excluded_scope_keys
- /scope_narrowing/blind_spot_reason_codes
- /scope_narrowing/estimated_card_count

included_scope_keys와 excluded_scope_keys는 서로소인 정렬 집합이다. estimated_card_count는 런타임이 다시 계산한 값과 같아야 하고 6 이하여야 한다. 모든 excluded scope는 blind_spot_reason_code와 최종 blind spot 항목을 가져야 한다.

Diagnostic:

- /issue_dispositions/*
- /decision_dispositions/*
- /verification_authorizations/*
- /issue_groups/*
- /materiality_context/*
- /requested_counter_checks/*
- /deep_dive_scope/component_ids
- /deep_dive_scope/issue_ids

Final:

- /response_dispositions/*
- /expert_routing/*
- /ceo_wording/*
- /delivery_scope/*

wildcard는 정확히 한 식별자 segment만 뜻한다. remove operation은 허용하지 않고 add·replace·test만 허용한다.

### 12.4 Approval Record

- approval_id
- approval_request_id
- gate
- base_artifact_ref
- result_artifact_ref
- decision: approve, approve_with_edits, request_changes, reject
- confirmed: literal true
- actor_id
- actor_role
- target_refs
- authorized_component_ids
- patch_operations
- rationale
- created_at
- input_method: interactive_tty
- nonce_hash
- tty_session_fingerprint
- supersedes_approval_id
- approval_hash

result_artifact_ref는 patch 물질화 후 산출된 revision을 가리킨다. stale base revision을 거부한다. Approval Request가 만든 일회 nonce는 10분 후 만료되고 한 번만 사용할 수 있다. approve-interactive는 stdin과 stdout이 모두 TTY인지 검사하며 redirect, pipe, approval JSON 입력을 거부한다. 실행 시 gate, base hash, 전체 patch diff, 무효화될 승인, result preview hash를 다시 표시하고 사용자가 actor ID·role·nonce와 정확한 APPROVE 문구를 직접 입력해야 한다.

역할:

| Gate | 허용 역할 |
|---|---|
| Context | ceo, delegated_executive, business_owner |
| Data | data_owner, business_owner |
| Scope narrowing | ceo, delegated_executive, business_owner |
| Diagnostic | ceo, delegated_executive |
| Final | ceo, delegated_executive |
| Expert packet 내용 확인 | 해당 profession expert |

POC에서 한 사람이 여러 역할을 가질 수 있지만 각 승인에 사용 역할을 명시한다.

### 12.5 승인 무효화

| 변경 | 무효화 |
|---|---|
| Source·mapping·Fact·Signal 변경 | diagnostic, deep authorization, final |
| Mission Contract 의미 변경 | diagnostic, deep authorization, final |
| Scope narrowing 변경 | diagnostic, deep authorization, final |
| Pack·Component version 변경 | diagnostic, deep authorization, final |
| issue 병합·분리·disposition 변경 | deep authorization, final |
| deep scope 변경 | deep authorization, final |
| response·expert routing·CEO wording 변경 | final |

무효 승인 파일은 삭제하지 않고 status invalidated와 invalidated_by_revision을 기록한다.

### 12.6 직접 수정 금지

- Source·Fact·Signal 값과 ID
- 기존 Evidence Link 덮어쓰기
- grade 직접 지정
- Pack effective authority 상승
- 판단 불가를 새 근거 없이 확정
- required expert trigger 삭제
- 전문직 결론
- 감사·해시·Validator 우회

## 13. 병렬·revision·시간

### 13.1 병렬 경계

- 파일별 schema·quality: 최대 4
- 독립 Component: 최대 4
- lens Job: 논리 최대 3
- Join 후 integrator: 1
- deep 계산: 최대 4
- deep integrator: 1
- grade·CEO 최종 서술: 1

원인 비교, 문제 간 인과, 중요도·긴급성, 해결책 충돌, grade, CEO 최종 서술은 Join 뒤 단일 단계에서만 한다.

### 13.2 병렬 쓰기 안전

병렬 task는 고유 job fragment만 쓴다. Evidence Core revision과 state를 직접 수정하지 않는다.

모든 mutation CLI는 expected_revision을 요구한다.

1. run lock 획득
2. state revision과 expected_revision CAS
3. staging directory에 전체 새 snapshot 작성
4. 파일별 hash와 snapshot-manifest 생성
5. 전체 Validator
6. staging directory 원자 publish
7. state pointer 원자 교체
8. lock 해제

lost update면 conflict error를 반환하고 자동 merge하지 않는다. snapshot-manifest는 같은 revision의 모든 파일 path·hash를 기록하며 Evidence Core 안의 중복 view와 외부 registry 파일이 byte/hash equivalent인지 검사한다.

### 13.3 모델 재시도

로컬 엔진에는 HTTP 재시도가 없다. Skill은 명시적 호스트 실패 또는 invalid JSON에 한해 같은 Job을 한 번 재시도한다. 총 attempt는 2회다. 데이터 부족·근거 충돌·expert trigger는 재시도하지 않는다.

### 13.4 시간 예산

사람 대기 제외:

| 단계 | 전체 attempt 포함 예산 |
|---|---:|
| Context·계약 | 5초 |
| intake·snapshot·quality | 20초 |
| capability·Pack | 5초 |
| 결정적 scan | 20초 |
| lens host reasoning | 45초 |
| Join | 5초 |
| integrated reasoning | 45초 |
| 승인 전 | 140초 |
| deep component | 20초 |
| deep reasoning | 35초 |
| writer·expert packet·render | 25초 |
| Final Validation | 5초 |
| 승인 후 | 85초 |
| 전체 목표 | 225초 |
| 전체 평가 hard limit | 300초 |

host가 모델 작업을 hard-cancel하지 못하면 300초는 엔진 보장이 아니라 POC 평가 실패 기준이다.

live demo는 저장된 pre-HITL snapshot을 사용하고 다음만 실행한다.

- 승인 Component 1개 이하: 10초
- deep integrator 1회: 25초
- writer 또는 deterministic fallback과 render: 10초
- validation: 5초

목표 50초, 평가 hard limit 75초다. Diagnostic·Final interactive 승인에 걸린 사람 시간은 제외한다. 전체 85초 post-HITL 경로와 다른 축소 분기임을 화면에 표시한다.

### 13.5 성능 측정

- 대상: 실제 데모 노트북
- 기록: OS, CPU, RAM, Python, plugin hash, host version, model ID 또는 host_managed, cold/warm, cache 상태
- 표본: 4개 시나리오 각 10회, 총 40회
- p95: 40회 전체 wall-clock의 nearest-rank 38번째 값
- 각 시나리오 첫 실행은 cold로 포함하고 별도 표시
- 사람 승인 대기만 제외

## 14. Artifact와 CLI

### 14.1 Run 구조

    artifacts/<run_id>/
      manifest.json
      state.json
      sources/
        blobs/<sha256>
        resolver.json
      pack-snapshots/
      lineage/
        sets/<sha256>.json
      snapshots/
        r0001/
          snapshot-manifest.json
          intake/
          evidence/
          reasoning/
          approvals/
          deep-dive/
          final/
            structured-output.json
            result.json
            ceo-brief.md
            issue-tree.json
            evidence-cards.json
            monitoring-and-blind-spots.json
            expert-packets.json
            audit-manifest.json
            validation-summary.json
      tasks/
        <job_id>/
          job.json
          draft.json
          validation.json
      audit/

run_id는 run_ + UTC basic timestamp + 16 hex random을 런타임이 생성한다. 사용자가 run_id 경로를 지정하지 못한다.

raw draft는 내부 감사용으로 보존한다. 고객 전달 package에서는 raw draft와 resolver를 제외하지만 normalized card, integrated assessment, model provenance, validation result는 포함한다.

공식 대화 logs는 이 artifact tree와 별개다. 플러그인 CLI는 logs 경로를 읽거나 쓰지 않는다.

### 14.2 CLI

- preflight
- start --artifact-root --mission-contract --input
- scan --expected-revision
- prepare-jobs --stage schema_mapping|lens|integrated|deep_dive|writer --expected-revision
- ingest-result --job-id --draft --expected-revision
- reduce-stage --stage schema_mapping|lens|integrated|deep_dive|writer --expected-revision
- approval-request --gate context|data|scope_narrowing|diagnostic|final --overlay --expected-revision
- approve-interactive --request-id --expected-revision
- run-components --scope-ref --expected-revision
- prepare-finalization --expected-revision
- finalize --expected-revision
- status
- validate --revision
- render --revision
- resume --expected-revision
- stop --expected-revision
- cancel --expected-revision

artifact-root는 명시적이고 workspace 내부여야 하며 plugin root·input root·logs와 겹치면 거부한다.

approval-request는 검토할 overlay와 diff를 생성할 뿐 승인하지 않는다. approve-interactive만 Approval Record를 만들며 파일 기반 approve 명령은 제공하지 않는다.

stdout은 cli-response Schema JSON 한 개, stderr는 사람용 진단이다.

exit code:

- 0 성공
- 2 HITL 또는 추가 입력 필요
- 3 계약·Schema 위반
- 4 무결성·승인 실패
- 5 내부 오류
- 6 revision conflict

### 14.3 Final Result

- run_summary
- mission_summary
- capability_summary
- issues
- cross_issue_relations
- conditional_responses
- monitoring
- blind_spots
- expert_review_packets
- approvals
- integrity

issue:

- issue_id
- title_template
- primary_grade
- secondary_flags
- why_it_matters_template
- value_refs
- evidence_link_ids
- cause_hypotheses
- counter_hypotheses
- unresolved_conflicts
- verification_next_steps
- conditional_response_refs
- expert_review_refs

CEO brief는 Final Result의 결정적 view다. 새로운 숫자·주장·grade를 만들지 않는다. Decision Required, Immediate Verification, Expert Review Required issue를 고정 개수로 자르지 않는다.

## 15. 보안·개인정보·전문 경계

### 15.1 경로와 파일

- Resolve 후 허용 root 밖 접근 거부
- input, plugin, artifact root 중첩 거부
- symlink, junction, reparse point, 기존 hardlink target 거부
- 기존 파일 직접 overwrite 금지
- temp 작성 후 fsync와 atomic publish
- Pack과 Source TOCTOU 검증
- XLSX ZIP preflight 후 parser 호출
- CSV formula injection 문자는 렌더·export에서 escape

### 15.2 Prompt injection

원본 text는 untrusted_source_text로 표시한다. Reasoning Job Schema에는 command, path, URL fetch, tool invocation 필드가 없다. 현재 Codex 모델이 호스트 도구를 가질 수 있다는 사실은 숨기지 않는다. 도구 사용 여부와 무관하게 모델 draft, 모델이 만든 approval 파일, allowlist 밖 ID를 신뢰하지 않는다. Source snapshot·Pack Registry·state hash·TTY approval을 런타임이 다시 검증한다. 의미 기반 injection 탐지 성공이나 모델 tool isolation을 보안 보장으로 주장하지 않는다.

### 15.3 개인정보

- direct identifier role은 Reasoning Job 전에 제거 또는 pseudonymize
- Domain privacy minimum group 미만은 suppress
- prohibited dimension Fact 생성 금지
- 원본 절대 경로는 고객 출력 제외
- 개인 단위 raw value는 CEO brief에 렌더하지 않음

### 15.4 전문직

- Expert trigger는 Pack AST와 required Evidence role을 코드가 검증
- 최종 회계처리, 세액, 위법, 감사의견, 투자 권유 금지
- Expert packet은 관찰, Evidence, 불확실성, 필요 문서, 정확한 질문, 금지 결론을 포함
- 해당 전문가는 packet 내용을 검토할 수 있으나 CEO 최종 전달 승인과는 별도

## 16. POC

### 16.1 Oracle

각 시나리오는 runtime input과 물리적으로 분리된 tests/evaluation/oracles/<scenario>.json을 가진다. plugin artifact root와 Reasoning Job에서 oracle 경로 접근을 금지한다.

Oracle:

- scenario_id
- hidden_problem_families
- expected_fact_codes
- expected_signal_codes
- expected_issue_keys
- expected_primary_grades
- expected_secondary_flags
- required_evidence_roles
- required_counter_checks
- expected_data_requests
- hitl_script
- forbidden_claim_codes
- forbidden_professional_conclusions
- performance_class

ID가 run마다 달라질 수 있으므로 evaluator는 semantic code와 scope key로 결과를 찾고 실제 Evidence chain을 별도로 검증한다.

### 16.2 정상 수직 시나리오

데이터:

- B2B 서비스 24개월
- 매출 +10%
- gross margin 31%에서 24%로 하락
- 저마진 맞춤 계약 share 25%에서 55%
- mix가 margin gap의 72% 설명
- 인건비·투입시간 +1%로 고객의 급여 원인 가설을 교란
- Top 3 고객 share 48%에서 70%
- 일부 매출 인식일과 검수일이 보고기간을 넘고 금액 share 2% 이상

HITL script:

- Context: 급여 원인은 unverified로 확인
- Data: 검수일과 인식일 role 확인
- Diagnostic: margin/mix·집중 문제 수용, 급여 단독 원인 disputed, bridge와 timing deep scope 승인
- Final: 조건부 portfolio 대응 수용, revenue timing expert packet 승인

기대:

- profitability/mix와 concentration은 하나의 상위 portfolio issue tree 아래 보존
- 해당 CEO decision issue primary Decision Required
- 별도 revenue timing control issue primary Expert Review Required
- 급여 단독 원인 확정 0
- 회계처리 결론 0

### 16.3 충돌 시나리오

- margin gap 중 가격·mix 45%, 초과 작업 40%
- 두 설명의 기간·scope가 일부 다름
- remaining residual과 timing conflict 존재

기대:

- 같은 margin issue 아래 두 cause와 counter Evidence
- unresolved conflict 보존
- primary Immediate Verification
- 구별할 기간 정렬·계약별 원가·검수 데이터 요청
- 단일 원인 확정 0

### 16.4 누락 시나리오

- 월별 P&L만 제공
- 고객·계약·상품·작업시간·검수 data 없음

기대:

- margin 하락 Fact와 Signal은 가능
- 원인 primary Not Assessable
- customer, contract, delivery, timing source role을 정확히 요청
- 확정 대응 0

### 16.5 미지원 Domain

- b2b-services applicability와 일치하지 않는 산업·사업모델

기대:

- generic Boundary
- 공통 품질과 일반 Fact만 생성
- 도메인 원인·대응 Not Assessable
- Provisional 자동 작성·실행 0

### 16.6 자동 합격

- 모든 Schema·참조·해시·승인·전문 경계 위반 0
- material claim Evidence Link 100%
- Evidence chain Source 도달 100%
- expected critical Fact·Signal recall 100%
- fabricated Fact·Signal·Evidence 0
- 고정 draft fixture에서 순차·병렬 deterministic artifact byte-equivalent
- 실제 Codex 모델 각 시나리오 10회에서 핵심 problem family·grade route·expert route·Not Assessable route 10/10
- 충돌 원인 확정 0
- 누락 확정 대응 0
- 미지원 Domain 추론·자동 Provisional 0
- alias, 열 순서, row 순서, unit 표현, 파일 분할, 무관 열 6종 변형에서 핵심 semantic 결과 보존
- p95 승인 전 140초 이하
- p95 전체 225초 이하
- 어떤 평가 run도 300초 초과 없음
- stored run load와 hash validation 3초 이하
- live branch p95 50초 이하

로컬 pytest의 canned/fixed draft 검증과 실제 Codex host 반복 평가는 별도다. canned draft 통과를 모델 품질 합격으로 대체하지 않는다.

### 16.7 사람 평가

평가자:

- 경영·사업 1명 이상
- 회계·컨설팅 1명 이상
- CEO 역할 1명 이상

5점 척도:

- 문제 정의 타당성
- 중요한 반대 가설
- 의사결정 유용성
- 근거 추적성
- 판단 불가 정직성
- CEO 가독성
- 전문가 packet 실용성

합격:

- 전체 평균 4.0 이상
- 평가자별 평균 3.5 이상
- CEO 역할이 2분 안에 문제, 근거, 결정, 불확실성을 정확히 찾음

LLM judge는 보조이며 단독 합격 판정에 사용하지 않는다.

### 16.8 데모

- 최종 데이터·Pack·model profile로 stored run과 대체 HITL branch를 사전 검증
- STORED RUN과 LIVE DELTA 명시
- live 실패 시 마지막 유효 revision, 실패 단계, stored fallback을 공개
- stored 결과를 live 성공처럼 표시하지 않음

## 17. 테스트 전략

### 17.1 Unit

- strict JSON
- Decimal과 canonical JSON
- ID와 semantic fingerprint
- Condition DSL
- Source snapshot
- lineage multiset과 교집합
- 9개 Component
- grading input reducer와 exhaustive decision table
- state transition
- patch allowlist와 invalidation

### 17.2 Contract

- 모든 Schema positive·negative fixture
- Mission Contract와 Mission Pack 분리
- Pack Registry authority
- Reasoning Job stage oneOf
- draft → Normalized Card
- Evidence provenance와 independence
- stale approval·result artifact

### 17.3 Integration

- CSV, JSON, XLSX
- Context·Data conditional Gate
- Evidence → lens → Join → integrated
- Diagnostic approval → deep dive
- Expert routing → Final approval → finalized
- request changes revision loop
- scope narrowing
- blocked → resume

### 17.4 Determinism

- 입력 파일 순서
- row 순서
- 파일 분할
- Component worker 1 대 4
- lens completion 순서
- 동일 draft 반복 ingest
- Final Result 재render

고정 draft에서 runtime semantic projection은 byte-equivalent여야 한다. 실제 모델 반복은 핵심 의미 불변성으로 평가한다.

### 17.5 Safety

- path traversal
- symlink·junction·reparse·hardlink
- Source·Pack TOCTOU
- JSON duplicate key·depth bomb
- Condition DSL injection
- XLSX ZIP bomb·macro·external link·formula
- CSV formula injection
- prompt injection cell
- allowlist 밖 ID
- forged·stale approval
- pipe·redirect·모델 생성 파일을 이용한 비TTY approval
- 만료·재사용 nonce
- Pack Full 자가 선언
- model의 Fact·grade 직접 생성
- 전문직 결론
- logs 쓰기 시도

### 17.6 Plugin

- plugin.json과 SKILL path
- SKILL 명령과 CLI 일치
- 한글·공백 경로
- read-only plugin root
- workspace artifact root
- lock preflight
- 네트워크 없이 deterministic stage 실행

## 18. 구현 Slice

### Slice 1: Trust Kernel

- strict JSON, canonical, ID
- safe filesystem, snapshot store, CAS revision
- 핵심 Schema와 validator

완료: 변조·중복·경로·revision 경쟁 테스트 통과.

### Slice 2: Intake와 Evidence

- CSV·JSON·XLSX
- mapping·Quality·Capability
- Fact·Signal·Evidence Core

완료: 세 형식과 원장 충돌 reconcile, Context/Data Gate 통과.

### Slice 3: Component와 Pack

- 9개 Component
- Condition DSL
- Pack Registry·loader·selector
- 초기 Mission·Domain·Problem Pack

완료: contract·determinism·authority·safety 통과.

### Slice 4: Reasoning

- stage별 Job
- Lens Draft·Normalizer
- Join Barrier·Pre-Join
- Integrated Draft

완료: allowlist 밖 주장과 required lens 계약 실패 차단.

### Slice 5: HITL·Grade·Output

- 전이표·overlay·approval
- invalidation
- grading input·decision table
- Final Result·renderer·audit

완료: 승인 우회·grade 직접 수정·새 출력 주장 차단.

### Slice 6: Plugin·POC

- manifest·Skill
- 4개 oracle 시나리오
- stored/live demo
- 자동·반복·사람 평가 packet

완료: 16장의 합격 기준 충족 또는 실패 항목과 잔여 위험 명시.

## 19. 변경 통제

구현 중 다음은 자율 수정한다.

- 내부 함수 분리
- 명백한 버그·타입·fixture 오류
- 테스트 추가
- 성능 최적화
- 문구와 오류 메시지 개선

다음은 다시 사용자 승인을 받는다.

- PRD 또는 Architecture Decisions와 충돌
- Fact·Signal·Evidence 의미 변경
- Mission Contract와 Pack 경계 변경
- Pack effective authority 상승 방식 변경
- HITL Gate 축소·우회
- 전문직·개인정보·보안 경계 완화
- grade 의미·우선순위 변경
- POC 합격 기준 완화
- 기존 프로젝트·submission.zip·logs 수정 필요

이 문서 승인 후 구현은 테스트 우선으로 진행하며 일상적인 구현 판단에는 추가 승인을 요구하지 않는다.
