# Accounting Multitable JSON Adapter Design

## 1. 목적

`evaluation/synthetic/analysis-input/<scenario>/dataset.json`과 같은
`accounting-multitable-json/1.0.0` 입력을 Trusted CEO Agent의 불변 snapshot,
Canonical Field, 회계 64 Family 실행 경로에 연결한다.

이 Adapter는 특정 파일 경로, 시나리오 ID 또는 합성 데이터 생성기에 종속되지
않는다. 동일한 스키마 계약을 따르는 새 입력에는 계속 재사용하고, 다른 스키마는
자동 추측하지 않고 기존 진단·승인 절차로 되돌린다.

## 2. 승인된 범위

- 승인 Gap: `G-01`
- 변경 등급: Yellow
- 허용:
  - 신규 다중 테이블 JSON Adapter
  - content-aware Adapter selector
  - 동일 immutable source snapshot에서 회계 closed request 생성
  - 관련 unit, integration, determinism, lineage, CLI 테스트
- 금지:
  - 원본 데이터 수정
  - `evaluation/synthetic/truth/` 접근
  - 기존 Evidence Lineage 또는 SourceReference Schema 변경
  - HITL, Pack 권한, Final Validator, 감사로그, immutable revision 변경
  - `machine_draft/Boundary`보다 높은 결론 권한
  - 평가 helper의 임의 `0`, `false`, 날짜, ID 기본값을 운영 의미로 승격

## 3. 현재 간극

현재 `JsonAdapter`는 root 또는 `records_pointer`가 선택한 값이
`list[object]`일 때만 동작한다. `IntakePipeline`과 `runtime_scan`은 파일
확장자만 보고 기본 `JsonAdapter()`를 선택하므로, root object 아래
`tables`에 33개 배열을 가진 입력은 수집되지 않는다.

또한 기존 Canonical mapping은 `source_id + source_field`를 필드 정체성으로
사용하고 확정된 mapping을 dataset의 모든 record에 적용한다. 따라서 서로 다른
테이블의 `amount`, `period`, `status` 같은 이름을 그대로 한 dataset에 합치면
의미 충돌과 잘못된 결측 판정이 생긴다.

평가용 `tools/synthetic_data/plugin_adapter.py`는 64 Family 입력을 만드는
구현 가능성을 입증하지만 운영 Registry에 등록되지 않았고, 일부 결측을 기본값으로
채운다. 운영 Adapter는 이 동작을 그대로 import하거나 승격하지 않는다.

## 4. 검토한 접근

### 접근 A: 기존 `JsonAdapter`에 다중 테이블 모드 추가

장점은 파일 수가 적다는 것이다. 단점은 단일 배열이라는 기존 계약이 흐려지고,
flat JSON 회귀 가능성이 커지며, suffix 기반 두 선택 경로의 중복도 남는다는
것이다. 채택하지 않는다.

### 접근 B: 평가 helper로 외부 accounting request를 만들어 기존 CLI에 전달

구현은 빠르지만 운영 Plugin이 `tools/`에 의존하고, 원본 snapshot과 request의
결속이 약하며, 결측 기본값이 `not_assessable`을 약한 통과로 바꿀 수 있다.
채택하지 않는다.

### 접근 C: 전용 Adapter, 공용 selector, snapshot-bound request builder

전용 Adapter가 스키마와 raw row locator를 검증하고, 공용 selector가 일반 JSON과
회계 JSON을 내용 서명으로 구분한다. 별도의 준비 명령은 외부 원본 경로가 아니라
현재 revision의 `source_id`를 받아 동일 content-addressed snapshot에서 회계
closed request를 생성한다. 실행은 기존 `run-components --accounting-input`
계약을 변경하지 않고 재사용한다.

이 접근을 채택한다. 기존 flat Adapter와 Trust Kernel을 유지하면서 TOCTOU를
피하고, 새 데이터 작업에서도 동일 스키마일 때 재사용할 수 있기 때문이다.

## 5. 입력 계약

Adapter ID는 `accounting-multitable-json`, Adapter version은 `1.0.0`이다.

필수 최상위 필드:

- `company_id`
- `company_name`
- `currency`
- `entity`
- `generator_version`
- `reporting_period.start`
- `reporting_period.end`
- `scenario_id`
- `schema_version`
- `seed`
- `tables`

`schema_version`은 정확히 `1.0.0`이어야 한다. `tables`는 승인된 33개 named
array를 정확히 포함하고 각 row는 문자열 key를 가진 object여야 한다. JSON은
기존 strict decoder를 사용해 duplicate key, non-finite number 및 비정상
Unicode를 fail-closed한다.

`tables`가 있는 root object는 회계 Adapter 후보로 간주한다. 후보가 schema
검증에 실패하면 일반 `JsonAdapter`로 fallback하지 않는다.

필수 table 이름은 다음 33개로 고정한다.

`allocation_drivers`, `allocation_pools`, `allocation_results`, `bank_accounts`,
`bank_transactions`, `budgets`, `cash_receipts`, `chart_of_accounts`,
`contract_amendments`, `contracts`, `credit_notes`, `customers`, `departments`,
`direct_costs`, `employee_assignments`, `employees`, `forecasts`, `indirect_costs`,
`invoices`, `journal_headers`, `journal_lines`, `management_kpis`, `milestones`,
`payable_aging`, `payroll_costs`, `performance_obligations`, `projects`,
`receivable_aging`, `trial_balance`, `vendor_costs`, `vendor_payments`, `vendors`,
`work_logs`.

## 6. Intake 표현과 lineage

Adapter는 기존 `ParsedDataset`과 `ParsedRecord`를 그대로 사용한다.

- 각 행 locator:
  `/tables/{RFC6901-escaped-table-name}/{zero-based-index}`
- `locator_type`:
  `json_pointer`
- locator object:
  기존 계약대로 `{"pointer": "..."}`만 사용
- normalized field:
  `{table_name}.{raw_field_name}`
- raw value:
  문자열 decimal, 날짜, 부호, 불리언, `null`을 변환 없이 보존
- logical order:
  정렬된 table name, 각 table의 원래 row 순서
- metadata:
  Adapter ID/version, input schema version, 최상위 회사·기간 메타데이터,
  table별 row count

table 이름을 field namespace에 포함하는 이유는 locator와 metadata가
`semantic_rows_hash`에 포함되지 않기 때문이다. 따라서 행을 다른 테이블로
옮기면 semantic hash가 달라지고, 같은 이름의 열도 Canonical Field 정체성이
충돌하지 않는다.

`ParsedDataset`, `Snapshotter`, `SourceRegistry`, SourceReference Schema,
lineage-set Schema 및 `materialize.py`는 변경하지 않는다.

namespaced field는 일반 Pack metric에 자동 매핑하지 않는다. 회계 builder가 승인된
회계 의미 매핑을 담당하며, 일반 KPI Canonical mapping이 필요하면 별도의 Green
mapping과 기존 Data HITL을 거친다. Adapter 선택만으로 Canonical 의미가 승인된
것으로 취급하지 않는다.

## 7. Adapter 선택

신규 공용 selector는 `select_adapter(display_name, immutable_blob)` 계약을
제공한다.

- CSV: 기존 `CsvAdapter`
- XLSX: 기존 `XlsxAdapter`
- root-array JSON: 기존 `JsonAdapter`
- `tables`를 가진 root-object JSON: 신규 `AccountingMultitableJsonAdapter`
- 지원하지 않는 suffix 또는 잘못된 회계 후보: `ContractError`

`IntakePipeline`과 `runtime_scan`은 이 selector를 함께 사용해 중복된 suffix
분기와 선택 불일치를 제거한다. 두 경로 모두 snapshot 생성 이후 immutable
blob만 Adapter에 넘긴다는 현재 순서를 유지한다.

## 8. 회계 closed request 생성

운영 모듈 `trusted_ceo_agent.accounting.input_adapter`는 검증된
`accounting-multitable-json/1.0.0` document와 다음 runtime binding을 받아
기존 7-field request를 생성한다.

- `run_id`
- 다음 publish 대상 `revision`
- 승인된 `scope_ref`
- Source Registry의 `source_id`
- snapshot SHA-256

출력 key는 기존 CLI 계약과 정확히 일치한다.

- `scope_ref`
- `suite`
- `tier_zero_input`
- `raw_core_population`
- `revenue_input`
- `cashflow_input`
- `project_cost_inputs`

request와 64 Family execution bundle은 기존 `run-components` artifact 경로에
저장한다. source snapshot SHA-256은 Adapter provenance와 request source
binding에 사용하되 Suite release ID로 사용하지 않는다. 고정 release ID는
`accounting-suite-2026-07-17`이며, effective period만 입력의
`reporting_period`와 대조한다.

accounting-local `source_refs`와 `counter_evidence_refs`는
`{source_id}@{full_snapshot_sha256}#{json_pointer}` 형식으로 생성한다. 이 문자열은
request와 raw snapshot을 검증 가능하게 결속하지만, 기존 Evidence Core의
SourceReference object나 lineage Schema를 대체하거나 변경하지 않는다.

읽기 전용 `prepare-accounting-input` 명령을 추가한다.

- 입력: `--artifact-root`, `--run-id`, `--revision`, `--source-id`,
  `--scope-ref`, `--output`
- 허용 상태: Diagnostic HITL이 승인되고 해당 deep-dive scope가
  `accounting` 입력을 요구하는 상태
- source: 지정 revision의 Source Registry와 content-addressed snapshot
- 출력: 다음 publish revision에 결속된 canonical 7-field request
- 부작용: ArtifactStore revision을 생성하거나 수정하지 않음

생성된 파일은 기존 `run-components --accounting-input`에 전달한다.
`run-components`의 closed-contract, 승인 scope, run ID 및 `current+1` revision
검증은 변경하지 않는다.

## 9. 결측과 오류 처리

- required table, row type, PK, 날짜, decimal 또는 참조 계약이 깨지면
  request publish 전에 fail-closed한다.
- 경제적 의미가 불명확하면 Adapter가 값을 추정하지 않는다.
- source field가 `null`이면 `0`, `false`, 임의 날짜 또는 임의 상태로 바꾸지
  않는다.
- Tier 0, Revenue, Cashflow의 필수 field가 불완전하면 일부 행만 조용히
  제외하지 않고 해당 의존 population 전체를 비워 `not_assessable`을 생성한다.
- AC-06~16 raw-core의 필수 journal control이 원본에 없으면 근거 없는
  `false`, `automatic`, `neutral`을 만들지 않고 해당 population을 비운다.
- Project Cost는 실제 계산 가능한 metric key만 생성하고, 결측 metric key는
  생략해 기존 `missing_inputs`/`not_assessable` 경로를 사용한다.
- procedure input 계약이 결측 표현을 지원하지 않는 경우 전체 weak pass 대신
  명시적 Adapter 오류로 중단한다.
- optional descriptive field 결측은 raw intake에 `null`로 남기고 계산 결과를
  바꾸지 않는다.
- 서로 다른 scenario는 별도 run 또는 별도 source snapshot으로 처리하고
  병합하지 않는다.

## 10. 파일 경계

예상 신규 파일:

- `plugin/trusted-ceo-agent/trusted_ceo_agent/intake/adapters/accounting_json.py`
- `plugin/trusted-ceo-agent/trusted_ceo_agent/intake/adapters/selection.py`
- `plugin/trusted-ceo-agent/trusted_ceo_agent/accounting/input_adapter.py`
- `tests/unit/intake/test_accounting_json_adapter.py`
- `tests/unit/accounting/test_input_adapter.py`

예상 수정 파일:

- `plugin/trusted-ceo-agent/trusted_ceo_agent/intake/adapters/__init__.py`
- `plugin/trusted-ceo-agent/trusted_ceo_agent/intake/pipeline.py`
- `plugin/trusted-ceo-agent/trusted_ceo_agent/runtime_scan.py`
- `plugin/trusted-ceo-agent/trusted_ceo_agent/cli.py`
- `tests/integration/test_intake_formats.py`
- `tests/integration/test_intake_to_evidence.py`
- `tests/integration/test_cli_accounting_components.py`
- `tests/determinism/test_intake_determinism.py`
- `tests/evaluation/test_synthetic_plugin_integration.py`

평가 helper는 운영 코드의 dependency가 되지 않는다. 필요하면 운영 builder를
호출하는 얇은 호환 wrapper로 축소하지만, 평가 데이터 생성·정답·scoring 코드는
Plugin package로 이동하지 않는다.

## 11. 검증

### 정상

- clean 및 integrated 입력의 33개 table, 360개 row 보존
- 정확한 JSON pointer와 namespaced field
- Source Registry snapshot과 Adapter semantic hash 결속
- 7-field closed request 생성
- 64개 ordered Family와 30개 result artifact
- `machine_draft/Boundary`

### 경계

- 4개 boundary scenario의 명시적 `null` 보존
- 결측 의존 procedure의 `not_assessable`
- 보고기간 밖 계약·프로젝트 날짜와 보고기간 구분
- KRW, decimal 문자열, debit/credit 및 trial-balance 부호 보존
- table/object key 순서가 바뀌어도 semantic hash 동일
- 행이 다른 table로 이동하면 semantic hash 변경

### 실패

- root, schema version, table set, row type 오류
- duplicate JSON key
- duplicate/missing primary key
- 잘못된 날짜, decimal, currency
- 불균형 journal, 깨진 FK
- scope/run/revision/source-id 불일치
- 미승인 상태 또는 scope에서 `prepare-accounting-input` 실행
- Source Registry에 없거나 snapshot hash가 불일치하는 `source_id`
- 오류 시 새 immutable revision 미발행

## 12. 완료 조건과 후속 경로

1. 신규 테스트가 구현 전 예상 이유로 실패한다.
2. 최소 구현 후 focused Adapter/intake/accounting/CLI 테스트가 통과한다.
3. 계약 검사, Python 전체, Web typecheck·lint·unit·build, Playwright 완료
   게이트가 통과한다.
4. 기존 flat CSV/JSON/XLSX 동작이 유지된다.
5. 원본, Evidence Lineage, HITL, Pack 권한, Validator, 감사로그, 기존 revision에
   변경이 없다.
6. Prompt 2 Handoff가 `ADAPTER_READY`를 기록한다.
7. 이후 Prompt 5는 clean, single-issue, integrated, boundary scenario를 각각
   독립 실행하고 실제 HITL 경계에서 사용자 입력을 요청한다.

## 13. 롤백

공용 selector의 회계 분기, 신규 Adapter, source-id request 경로와 관련 테스트를
제거하면 기존 flat Adapter와 `--accounting-input` 경로로 복귀한다. 원본 데이터,
Registry, 기존 immutable revision 및 감사 artifact에는 롤백 변경이 없어야 한다.
