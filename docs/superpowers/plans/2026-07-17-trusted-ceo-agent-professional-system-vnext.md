# Trusted CEO Agent Professional System vNext Implementation Plan

> 상태: Hard Gate 통과 후 실행하는 수직 구현계획. 기존 `2026-07-17-trusted-ceo-agent-plugin.md`를 대체하지 않고 그 기준선 위에 추가한다.

**Goal:** 기존 Trust Kernel과 플러그인 회귀를 보존하면서 전문추론, 회계 64 Issue Family, Knowledge Foundry, 다중 도메인, 유한 DAG, Signal Case, Finding, 종료, 결정적 결과 변환기, 웹 탭 2를 설계 누락 없이 연결한다.

**Architecture:** 결정적 엔진이 Fact, Event, Route, SignalCase, Finding, Grade, Approval, Completion과 publish를 소유한다. 모델 출력은 검증 전 draft이며, Pack·Knowledge authority와 Evidence lineage를 통과한 뒤에만 Analysis Plane으로 승격된다. 독립 작업은 격리된 fragment로 실행하고 Join 뒤 단일 Integrator가 결론을 만든다. 웹은 검증된 revision의 읽기 전용 투영이며 분석 판단을 복제하지 않는다.

**Tech stack:** Python 3.11, strict JSON Schema Draft 2020-12, RFC 8785/JCS, `jsonschema`, `unittest`, 기존 ArtifactStore/RevisionManager/ApprovalService, Next.js/TypeScript/Vitest/Playwright, frozen/offline `uv`.

## 0. Canonical inputs, baseline, and execution rules

- 단일 진입점: `docs/superpowers/specs/2026-07-17-professional-system-integration-index.md`
- Hard Gate 통합 커밋: `6adbfb9c7c33d61f369e0e4a46d504925d1fd414`
- Hard Gate 증거 커밋: `433b7852cf0454dca864e72520ed439d3434a4fe`
- 필수 설계: Integration Index의 D01–D18 전부. D04와 D05는 함께 적용하고, 회계는 D10·D11 제어 문서와 D12–D18 payload 7개를 모두 사용한다.
- 2026-07-17 기준 전체 Python 회귀: 223개 실행, 222개 PASS, 동시 작성 중인 `tests/contracts/test_web_report_contract_semantics.py::test_wrong_hash_and_dangling_reference_are_rejected_separately` 1개 FAIL. 제품 구현으로 새 실패를 추가하지 않고 M 수직 단위에서 이 기준 실패를 닫는다.
- 플러그인·테스트·웹·계약은 미추적 사용자 소유 기준선이다. 요청된 구현을 위해 수정할 수 있으나 임의 스테이징·커밋은 하지 않는다.
- RED → 기대한 이유의 실패 확인 → 최소 GREEN → 관련 회귀 → 전체 회귀 순서를 각 Task에 적용한다. 기존 통과 테스트가 RED가 되면 새 테스트 격리가 잘못된 것이므로 구현 전에 중단한다.
- required Procedure·반증·Coverage·authority는 예산 때문에 생략할 수 없다. required 실패는 writer fallback이나 제한 완료로 대체하지 않는다.
- `machine_draft`, `Boundary`, `Provisional`, `Full`과 제품 표시를 별도 필드로 유지한다. 실제 전문가 승인이 없는 Full·시니어급 표시는 금지한다.
- 숨겨진 chain-of-thought는 저장하지 않는다. 사실, 기준, 결론, 반증, 불확실성, 검증절차와 참조만 구조화한다.

## 1. Vertical execution order

1. A 기준선·회귀 보호와 알려진 실패 장부
2. B Human Action → Response-to-Revision 완결 수직 단위
3. G/H 통합 Schema, AnalysisWorkGraph, WorkItem, budget, checkpoint, retry/cancel/resume
4. I/J Signal → SignalCase Queue → terminal immutable Finding
5. C/D Economic Event → Multi-domain Route → required-domain Join
6. K Cross-domain/Cross-Finding Integrator
7. L CompletionAssessment와 정상·제한 완료
8. M WebReport converter와 fail-closed publish
9. E D1–D12 Card/Norm/Procedure/authority Gate
10. F Account Universe·Coverage·Tier 0 → AC 16 → RV 16 → CF 16 → CA 16 → 64 통합
11. O Feedback → Patch → Regression → 3단계 Release·rollback
12. N 탭 1 provider와 탭 2 실제 Bundle 투영
13. P 순차/병렬 결정성, AI non-inferiority, 성능·rollback Gate

B를 DAG보다 먼저 두는 이유는 기존 CAS·overlay·approval을 그대로 재사용해 사용자 응답의 원자성·리비전 경계를 먼저 고정하기 때문이다. I/J는 C/D보다 먼저 계약과 lifecycle을 구현하되, Event·DomainRoute 참조가 없으면 활성화하지 않는 fail-closed adapter로 둔다. 동시 변경 중인 `contracts/web-report/**`와 `web/**`는 M/N 전까지 수정하지 않고 스냅샷 변화를 재검토한다.

## 2. Common completion definition

각 Task는 아래 증거가 모두 있을 때만 `완료`다.

- [ ] strict Schema와 런타임 validator가 같은 계약을 강제한다.
- [ ] 정상, 오류, 경계, stale, duplicate, timeout/cancel/resume 중 관련 사례가 RED/GREEN으로 존재한다.
- [ ] 새 Artifact는 canonical bytes, stable ID, run/revision/hash, Evidence/authority ref를 가진다.
- [ ] 실패는 부분 publish 없이 명시적 상태와 복구 경로를 남긴다.
- [ ] 기존 revision·Finding·Source·Approval은 byte 불변이다.
- [ ] 제품 표시가 §1의 실제 완료 범위를 넘지 않는다.
- [ ] focused tests와 전체 회귀 결과를 계획 하단의 증거 표에 기록한다.

## Task A. 기존 플러그인 기준선과 회귀 보호

**상태:** Trust Kernel 기준선·focused 회귀·최종 Full 검증 완료  
**출처:** D01 §8; D02 AD-02/06/07/09/11/12; D03 §§2–19; D09 §§1,11 A,12; Integration Index §4 A

**선행조건:** Hard Gate 완료, 필수 문서 18/18 tracked.  
**수정 파일:** `docs/PLUGIN_IMPLEMENTATION_STATUS.md`, 신규 `tests/baseline/test_vnext_baseline.py`, 신규 `tests/fixtures/baseline/vnext-known-failures.json`. 기존 Trust Kernel 코드는 기준선 검사 실패가 입증될 때만 수정한다.  
**Schema/계약:** known-failure record는 test ID, snapshot hash, owner scope, observed failure, closing Task를 가진다. 코드·테스트 파일 hash와 Pack/runtime lock을 기록하되 절대 경로·비밀은 저장하지 않는다.  
**실패·복구:** 알려진 실패 외 신규 실패면 이후 Task를 차단한다. concurrent 파일 hash가 바뀌면 해당 영역 기준선을 재실행하고 장부를 새 revision으로 갱신한다.  
**테스트:** bootstrap preflight, 223개 전체 unittest, contract/Pack/Artifact hash smoke, source/Pack TOCTOU, TTY approval.  
**합격 기준:** 기존 222 PASS 유지, 알려진 WebReport 1 FAIL만 명시, 신규 실패 0, Trust Kernel hash/authority 동작 불변.  
**제품 표시:** 변화 없음. 현재 Pack authority는 `provisional`, 전문 품질은 `machine_draft/Boundary` 상한.

- [ ] RED: 장부가 없으면 baseline test가 실패하도록 작성한다.
- [ ] GREEN: 실행 명령·해시·known failure 1건을 정규화해 기록한다.
- [ ] 회귀: `python -m unittest discover -s tests -v`와 preflight를 실행한다.

## Task B. Human Action Card와 Response-to-Revision

**상태:** 플러그인 수직 단위와 provider 경계 구현·focused·최종 Full 검증 완료  
**출처:** D01 §§3–4; D02 AD-09; D03 §12; D04 §§4.5,9,11–12; D05 §§1–2; D09 §§2–4,11 A–B,12.1; Integration Index §4 B

**선행조건:** A 기준선, 현재 workflow state와 revision snapshot, action별 evidence refs.  
**수정 파일:** 신규 `trusted_ceo_agent/workflow/human_actions.py`, `workflow/responses.py`, `workflow/human_response_policy.py`, `workflow/snapshot_validation.py`; 수정 `trust/artifact_store.py`, `workflow/approvals.py`, `workflow/overlays.py`, `cli.py`; 신규 `schemas/human-action-card.schema.json`, `human-action-resolution.schema.json`, `human-response.schema.json`, `human-response-receipt.schema.json`, `human-response-policy.schema.json`, `human-response-policy-decision.schema.json`; 신규 tests `contracts/test_human_interaction_schemas.py`, `contracts/test_human_response_policy_schemas.py`, `unit/workflow/test_human_actions.py`, `unit/workflow/test_responses.py`, `integration/test_cli_human_response.py`. 웹 provider adapter는 N에서 실제 transport와 연결하되 이 Task에서 command contract fixture를 고정한다.  
**Schema/계약:** D09 §3.1의 필드 전부, 응답 allowlist 11종, `proceed_limited` 제한 세부, deterministic `content_hash`, immutable `HumanResponseRecord`, D09 §4.5 receipt. idempotency key는 request hash와 receipt ref에 바인딩한다.  
**실패·복구:** stale revision/card, 만료/hash 불일치, response type/payload 오류, 같은 key 다른 payload는 mutation 0. publish 실패는 snapshot·response·idempotency receipt 모두 0. timeout 후 동일 key 조회/재제출은 같은 receipt. `request_explanation`은 별도 read-only response이며 revision 0.  
**테스트:** 카드 표시 순서/필드, 데이터 5개 선택지, 11 response 유형, exactly +1 revision, 이전 bytes 불변, stale/expired/hash/duplicate conflict, approval record 0, downstream invalidation, CLI one-object response.  
**합격 기준:** D09 §12.1 8개 기준 전부, mutation 응답 정확히 revision 1개, 동일 요청 byte-identical receipt, TTY approval 분리.  
**제품 표시:** 분석 품질 표시는 올리지 않는다. 탭 1은 `response_recorded` 또는 `terminal_approval_required`만 정직하게 표시할 수 있다.

- [x] RED: 세 Schema와 compiler/service import가 없어 실패하는 계약·단위 테스트를 먼저 작성한다.
- [x] RED: stale, duplicate, explanation revision 0, approval record 0 통합 테스트의 정확한 실패를 확인한다.
- [x] GREEN: existing `RevisionManager.commit`, `apply_overlay`, `invalidated_gates`, `ApprovalService` record reader를 재사용해 원자 submit을 구현한다.
- [x] GREEN: CLI `pending-action`, `preview-human-response`, `submit-human-response`를 추가하고 모든 mutation에 `--expected-revision`을 강제한다.
- [x] 보강: Action resolution, trusted local principal 정책, Source access policy, operational read-only idempotency cache, 전체 snapshot validator, option binding을 fail-closed로 연결한다.
- [ ] 회귀: 보강 후 B focused 19/19 PASS; 전체 Python suite는 G/H·I/J·C/D 병합 뒤 1회 재실행한다.

## Task C. Economic Event materialization

**상태:** 결정적 Event materialization·lineage·stale 차단 구현 및 focused·최종 Full 검증 완료  
**출처:** D07 §§3.1–3.2; D09 §§5.2,11 C,12.2; D12 §5; D15 §1; D17 §1; Integration Index §4 C

**선행조건:** 검증된 observed/derived Fact, Source lineage, Quality/Capability 결과.  
**수정 파일:** 신규 `trusted_ceo_agent/analysis/economic_events.py`, `analysis/__init__.py`, `schemas/economic-event.schema.json`; tests `contracts/test_economic_event_schema.py`, `unit/analysis/test_economic_events.py`, `determinism/test_economic_event_ids.py`, `safety/test_economic_event_lineage.py`.  
**Schema/계약:** stable event ID, event kind/time/scope/amount refs, fact/source/evidence refs, quality flags, materialization rule ID/version, revision. Event는 Fact를 복사하거나 새 판단을 만들지 않는다.  
**실패·복구:** dangling/stale Fact, invalid quality, mixed currency/unit, 불완전 lineage는 Event publish 0과 명시적 not-materialized reason. 같은 canonical facts는 같은 ID/bytes.  
**테스트:** same facts/order variance, one event multi-domain reuse, source reachability, stale revision, invalid unit, no invented values.  
**합격 기준:** 모든 event field가 Fact/Rule로 재계산 가능하고 Evidence Core validation 통과.  
**제품 표시:** 없음. Event만으로 Finding/Grade/전문 결론을 표시하지 않는다.

- [ ] RED: schema/lineage/order tests를 먼저 작성한다.
- [ ] GREEN: pure materializer와 Artifact validator adapter를 구현한다.
- [ ] 회귀: intake→Fact→Event integration과 Evidence suite를 실행한다.

## Task D. Multi-domain Router

**상태:** 4-domain 결정적 Router·AI additive-only·unsupported Boundary 구현 및 focused·최종 Full 검증 완료  
**출처:** D03 §§9.9,15.4; D06 §§5,11–12; D07 §13; D09 §§5,11 D,12.2; D13 §§2,4,7; Integration Index §4 D

**선행조건:** C Event, current Mission, immutable Pack snapshot와 authority.  
**수정 파일:** 신규 `trusted_ceo_agent/routing/__init__.py`, `routing/domain_router.py`, `schemas/domain-route.schema.json`; 최소 확장 `packs/selector.py`, `packs/runtime_index.py`; tests `contracts/test_domain_route_schema.py`, `unit/routing/test_domain_router.py`, `determinism/test_domain_route_order.py`, `integration/test_multi_domain_route.py`, `safety/test_unsupported_domain_boundary.py`.  
**Schema/계약:** Event별 applicability 결과, deterministic candidates, additive-only AI candidates, selected 0/1/2+/4 domains, Pack snapshot/hash/authority, unsupported reason, same event ID.  
**실패·복구:** AI candidate는 결정적 screen을 제거할 수 없다. Pack 없음/미승인은 Boundary와 `unsupported_pack`; 한 domain 실패를 다른 성공으로 숨기지 않는다. stale snapshot은 route publish 0.  
**테스트:** 0/1/2+/4 route, completion order equivalence, unsupported 법무·노무·세무, Pack authority downgrade, duplicate candidate dedupe.  
**합격 기준:** D09 §12.2 전부, 모든 route가 Event/Pack hash에 묶이고 required domain 실패가 보존됨.  
**제품 표시:** 승인 없는 domain은 Boundary. 다중 도메인 성공 자체로 Full을 주장하지 않는다.

- [ ] RED: 0/1/2+/4와 additive-only/Boundary tests를 작성한다.
- [ ] GREEN: 기존 `select_domain`은 legacy adapter로 보존하고 새 router가 domain collection을 반환하게 한다.
- [ ] 회귀: Pack loader/selector/authority와 multi-domain integration을 실행한다.

## Task E. 전문 깊이 D1–D12 Gate

**상태:** D1–D12 typed Gate·authority/release 차단 구현 및 focused·최종 Full 검증 완료; 공식 근거와 외부 전문가 승격 필요  
**출처:** D06 §§7,9–12; D07 §§4–6; D09 §§6,11 E,12.3; D12 §§8–9,13,15; D18 §8; Integration Index §4 E

**선행조건:** immutable Pack snapshot, Issue Family ID, jurisdiction/effective period, official source refs, expert/release authority.  
**수정 파일:** 신규 `trusted_ceo_agent/knowledge/{__init__,registry,resolver,compiler,depth_gate}.py`; schemas `knowledge-artifact`, `method-card`, `norm-card`, `expectation-card`, `procedure-card`, `counter-hypothesis-card`, `cross-domain-trigger-card`, `issue-family`, `issue-evidence-packet`, `professional-depth-assessment`, `knowledge-release`; tests `contracts/test_professional_knowledge_schemas.py`, `unit/knowledge/test_depth_gate.py`, `unit/knowledge/test_norm_resolver.py`, `safety/test_knowledge_authority.py`.  
**Schema/계약:** D1 사건/모집단부터 D12 oracle까지 12개 slot을 typed ref로 강제한다. Knowledge trust와 기존 Pack authority는 직교하며 effective authority는 둘과 expert/release gate 중 최저값이다.  
**실패·복구:** card 누락, remote/unapproved source, effective-date gap, expired Norm, missing counter-evidence/procedure/oracle, expert 미승인은 activation 0과 원인 목록. 일반 LLM 지식 fallback 금지.  
**테스트:** D1–D12 각 slot 단독 누락, norm 기간 경계, jurisdiction, source hash, revoked release, 전문가 없는 Full, deterministic assessment.  
**합격 기준:** incomplete/expired/unapproved family가 Analysis Plane이나 Full grade로 진입한 사례 0.  
**제품 표시:** expert/release 전 `machine_draft`/Boundary만. Gate 통과만으로 시니어급 표시는 금지.

- [ ] RED: 12-slot omission matrix와 authority precedence tests를 작성한다.
- [ ] GREEN: read-only registry/resolver/compiler/depth assessment를 구현한다.
- [ ] 회귀: Pack authority·grading·schema suite를 실행한다.

## Task F. 회계 콘텐츠 Suite 64 Issue Family

**상태:** 원시 분개 adapter, AC15/16 분리, 64 Family 실제 Dispatcher·불변 실행 Manifest·승인된 CLI publish 구현 및 focused·최종 Full 검증 완료; 공식 Norm grounding·전문가 승인·production Oracle 필요  
**출처:** D06 §§8–10,14–16; D07 §12,§18 Phase 4; D09 §§6,11 E/H,12.3–12.4; D10–D18 전체; Integration Index §§3–5

**선행조건:** E Depth Gate, Account Universe/Coverage, 공식 Norm source, 9개 결정적 Component와 필요한 신규 Component, expert release boundary.  
**수정 파일:** 신규 `trusted_ceo_agent/accounting/{__init__,manifest,universe,coverage,procedures,product_claims}.py`; `packs/problem/accounting-*` immutable pack payloads; schemas `accounting-content-manifest`, `account-universe`, `account-coverage`, `accounting-pack`, `procedure-result`, `accounting-product-claim`; contract/unit/integration/evaluation tests 아래 Pack별 분리.  
**Schema/계약:** exact unique IDs AC/RV/CF/CA 각 01–16, 총 64; D1–D12 refs; Account Family 상태 빈칸 금지; Tier 0 AC-01~05; 정상/오류/경계/반증/누락/복합 case oracle; Pack·Card·Norm·Procedure·Coverage·expert authority 연결.  
**실패·복구:** Universe 빈 상태, Tier 0 실패, missing family/oracle/official source, cross-cycle conflict는 final claim 차단. 지원 밖 계정은 `pack_required`/`not_assessable`, 법무·노무·세무는 Boundary. partial Pack publish는 새 claim을 만들지 않는다.  
**테스트:** `contracts/test_accounting_content_manifest.py`; `unit/accounting/test_{account_universe,coverage_gate,product_claims}.py`; `integration/test_accounting_{core,revenue,cash,cost}_vertical.py`, `test_accounting_cross_cycle.py`; evaluation Pack별 case; exact 64/duplicate 0/blank 0.  
**합격 기준:** Core Tier 0 → AC 16 → RV 16 → CF 16 → CA 16 각각 별도 수직 합격, 최종 64 unique와 cross-cycle stand-back 통과.  
**제품 표시:** Core만 `accounting_core_screened`; 세 Cycle pre-expert `three_cycles_boundary`; 64+D1–D12+official source+oracle+blank 0+expert elevation 후에만 `senior_accountant_draft_scope`; `company_wide_accounting_full`은 계속 금지.

- [x] RED: manifest exact-ID/duplicate/missing/blank tests와 product claim downgrade tests를 작성한다.
- [x] GREEN-1: Account Universe·Coverage·Tier 0 AC-01~05를 end-to-end 구현한다.
- [x] GREEN-2: AC-01~16과 oracle를 완결한 뒤에만 `accounting_core_screened`를 연다.
- [x] GREEN-3: RV-01~16, CF-01~16, CA-01~16을 각각 독립 수직 단위로 구현한다.
- [x] GREEN-4: 64-family/cross-cycle/stand-back Gate와 finalization을 연결한다.
- [x] 회귀: 회계 contract/unit/integration/evaluation/determinism/safety 및 전체 suite를 실행한다.

## Task G. Orchestration Harness와 유한 AnalysisWorkGraph

**상태:** Event→Route→Signal Case→유한 DAG/Scheduler→CAS→Finding→Join/Integrator 최상위 Runtime과 CLI publish 구현 및 focused·최종 Full 검증 완료  
**출처:** D01 §7; D02 AD-07; D03 §§10.9–10.11,13; D09 §§8.1–8.2,11 J,12.5; Integration Index §4 G

**선행조건:** A 기준선, immutable inputs, Task type registry, concurrency profile.  
**수정 파일:** 신규 `trusted_ceo_agent/orchestration/{__init__,graph,scheduler}.py`; schemas `analysis-work-graph.schema.json`, `analysis-work-item.schema.json`; 기존 `reasoning/jobs.py`, `reasoning/join.py` adapter; tests `contracts/test_orchestration_schemas.py`, `unit/orchestration/test_graph.py`, `test_scheduler.py`, `determinism/test_work_graph_order.py`, `integration/test_required_work_barrier.py`.  
**Schema/계약:** finite node set, dependencies, required/optional, idempotency key, input/output refs+hash, attempt policy, timeout, concurrency class, terminal status, stable topological order. Join/post-Join는 worker 1.  
**실패·복구:** cycle/dangling dependency/duplicate node/stale hash는 graph activation 0. required failure는 Join 0; optional timeout은 명시적 terminal로만 통과. late fragment는 current run을 변경하지 않는다.  
**테스트:** cycle/dangling/duplicate, dependency readiness, required barrier, cancellation propagation, completion order byte equivalence, bounded worker profiles.  
**합격 기준:** 유한 DAG만 실행되고 모든 node가 terminal이며 required success 전 Join publish 0.  
**제품 표시:** 변화 없음. orchestration 완료를 분석 품질로 표시하지 않는다.

- [ ] RED: graph schema와 topological/barrier tests를 작성한다.
- [ ] GREEN: pure graph compiler와 isolated-fragment scheduler를 구현한다.
- [ ] GREEN: 기존 ReasoningJob/Join을 WorkItem adapter로 감싼다.
- [ ] 회귀: reasoning/determinism/state guard suite를 실행한다.

## Task H. WorkBudgetPolicy, checkpoint/resume, retry, cancellation

**상태:** WorkBudget·checkpoint/resume·bounded retry·cancellation·stale 차단 구현 및 focused·최종 Full 검증 완료  
**출처:** D03 §§12.1–12.2,13.3–13.5; D04 §§4.3,12,14; D09 §§8.2–8.4,8.8,11 J,12.5; Integration Index §4 H

**선행조건:** G WorkGraph/WorkItem, ArtifactStore CAS.  
**수정 파일:** 신규 `orchestration/{budget,checkpoint}.py`; schema `work-budget-policy.schema.json`, `work-checkpoint.schema.json`; 수정 `runtime_policy.py`, `workflow/state_machine.py`, CLI resume/cancel adapter; tests `unit/orchestration/test_budget.py`, `test_checkpoint.py`, `integration/test_work_resume.py`, `safety/test_work_cancellation.py`, `determinism/test_resume_equivalence.py`.  
**Schema/계약:** workload class, time/attempt/token/parallel ceilings, required-procedure set, retryable failure codes, checkpoint input hashes/completed node refs/pending set, cancellation receipt. Telemetry는 semantic hash 밖 별도 artifact.  
**실패·복구:** budget overflow는 required 작업 생략 권한이 아니다. required 미완료는 blocked; retry는 same idempotency key와 bounded attempts; stale checkpoint/resume는 mutation 0; cancel은 새 작업 시작을 막고 late output 폐기.  
**테스트:** timeout, retry exhaustion, cancellation, stale resume, exact-once output, sequential resume byte equivalence, required procedure preservation.  
**합격 기준:** 중단/재개가 clean run과 semantic/required byte 결과 동등, terminal 중복 0.  
**제품 표시:** 제한/blocked 이유만 표시; 약한 답변으로 품질 표시 유지 금지.

- [ ] RED: required budget preservation와 stale/cancel/resume tests를 작성한다.
- [ ] GREEN: immutable checkpoint와 policy evaluator를 구현한다.
- [ ] GREEN: scheduler와 CLI/state machine에 fail-closed adapter를 연결한다.
- [ ] 회귀: runtime policy/retry/state guard/determinism suite를 실행한다.

## Task I. Signal Case Queue와 PriorityRecord

**상태:** 결정적 PriorityRecord·dedupe/merge·single deep-case lease 구현 및 focused·최종 Full 검증 완료  
**출처:** D09 §§8.4,10.1,11 J–K,12.6; Integration Index §4 I

**선행조건:** 검증된 Signal, Event/DomainRoute refs 또는 미활성 boundary refs, G/H scheduler/checkpoint.  
**수정 파일:** 신규 `analysis/{signal_queue,case_controller}.py`; schemas `signal-case.schema.json`, `priority-record.schema.json`; tests `contracts/test_analysis_case_schemas.py`, `unit/analysis/test_signal_queue.py`, `determinism/test_signal_queue_order.py`, `integration/test_signal_case_lifecycle.py`.  
**Schema/계약:** stable case ID, signal/event/domain refs, dedupe key, materiality/urgency/human impact priority inputs, state, terminal disposition, attempt/checkpoint refs. 기본 active deep case는 1개.  
**실패·복구:** duplicate는 merge하고 새 결론을 만들지 않는다. 근거 변화 없는 data request 반복 금지. queue 이탈은 terminal/needs_input/needs_expert/pause 중 명시 상태; crash는 checkpoint부터 exact-once resume.  
**테스트:** stable sorting/order variance, duplicate merge, active=1, starvation boundary, all-exit disposition, checkpoint/retry/cancel.  
**합격 기준:** 중요 Signal 누락 0, 중복 deep analysis 0, 모든 이탈 추적 가능.  
**제품 표시:** Case는 후보일 뿐 Finding/문제로 표시하지 않는다.

- [ ] RED: dedupe/stable priority/active-one/lifecycle tests를 작성한다.
- [ ] GREEN: pure queue와 one-case controller를 구현한다.
- [ ] 회귀: Signal/Evidence와 scheduler/checkpoint suite를 실행한다.

## Task J. FindingRecord, 관계, IssueCluster

**상태:** 불변 Finding·supersession·관계·IssueCluster 구현 및 focused·최종 Full 검증 완료  
**출처:** D09 §§10.2–10.3,11 K,12.6; Integration Index §4 J

**선행조건:** terminal SignalCase, Procedure/counter-evidence coverage, Evidence refs.  
**수정 파일:** 신규 `analysis/{findings,relations}.py`; schemas `finding-record.schema.json`, `finding-relation.schema.json`, `issue-cluster.schema.json`; tests `contracts/test_finding_schemas.py`, `unit/analysis/test_findings.py`, `test_relations.py`, `safety/test_finding_immutability.py`, `integration/test_finding_supersession.py`.  
**Schema/계약:** disposition별 필수 필드, fact/criteria/conclusion/counter-evidence/uncertainty/verification refs, Grade ref는 engine-owned, relation 근거와 반대근거, `supersedes_finding_id`, revision.  
**실패·복구:** 필수 Procedure/반증/근거 누락은 `substantiated` publish 0; `inconclusive`는 missing evidence/procedure를 요구; 이전 Finding overwrite 금지; 근거 없는 인과는 relation publish 0.  
**테스트:** 모든 disposition, substantiated coverage, inconclusive gaps, supersession bytes, relation evidence, cluster order determinism, no model grade.  
**합격 기준:** D09 §12.6, 이전 revision byte 변경 0, 새 결론은 supersession만 사용.  
**제품 표시:** terminal Finding만 결과 후보. `expert_review_required`는 packet/boundary/owner 완성 후 terminal이며 Full 아님.

- [ ] RED: disposition matrix, immutability, relation-evidence tests를 작성한다.
- [ ] GREEN: Finding factory/validator, supersession, relation/cluster reducer를 구현한다.
- [ ] 회귀: I lifecycle, Evidence, grading, deterministic order suite를 실행한다.

## Task K. Cross-domain·Cross-Finding Integrator

**상태:** required barrier·frozen hash·single-writer Cross-domain/Cross-Finding Integrator 구현 및 focused·최종 Full 검증 완료  
**출처:** D02 AD-07; D03 §§10.9–10.11; D06 §11; D07 §13; D09 §§8.5,10.3–10.4,11 F/K,12.2/12.6; Integration Index §4 K

**선행조건:** D route set, J immutable Finding set, required domain/work terminal barrier.  
**수정 파일:** 신규 `analysis/integrator.py`; schemas `finding-join-manifest.schema.json`, `cross-domain-integration.schema.json`; 최소 확장 `reasoning/join.py`, `runtime_finalization.py`; tests `unit/analysis/test_integrator.py`, `determinism/test_integrator_order.py`, `integration/test_required_domain_barrier.py`, `safety/test_integrator_no_new_facts.py`.  
**Schema/계약:** input manifests/hashes, required domain terminal map, conflicts, cross-domain triggers, relation/cluster refs, single post-Join result. Integrator는 기존 Finding을 비교·연결할 뿐 새 Fact/Signal/Grade/Evidence를 만들지 않는다.  
**실패·복구:** required domain 미종결/failed/stale hash는 integration publish 0. 충돌은 삭제·평균하지 않고 양쪽 근거와 불확실성을 보존. late result는 새 revision에서만 재통합.  
**테스트:** barrier, completion-order byte equivalence, conflicting findings, unsupported domain preservation, no new fact/grade/evidence, single writer.  
**합격 기준:** 순차/병렬 동일 bytes, required domain failure 숨김 0, conflict lineage 완전.  
**제품 표시:** 통합 성공만으로 전문 authority를 올리지 않는다.

- [ ] RED: required-domain barrier/conflict/order/no-invention tests를 작성한다.
- [ ] GREEN: frozen Finding Join과 single Integrator를 구현한다.
- [ ] 회귀: legacy reasoning Join과 multi-domain/finding suite를 실행한다.

## Task L. 정상·제한 완료와 Completion Controller

**상태:** Artifact 기반 CompletionAssessment·normal/limited·expert terminal과 required 실패의 CLI/finalization 차단 구현 및 focused·최종 Full 검증 완료  
**출처:** D03 §§12,14.3; D06 §§12,16; D07 §§16,19; D09 §§8.8,10.5,11 L,12.7,13; D13 §7; Integration Index §4 L

**선행조건:** 모든 중요 Case, required Domain/WorkItem, Finding, Coverage/authority 상태.  
**수정 파일:** 신규 `trusted_ceo_agent/completion/{__init__,controller}.py`; schemas `completion-assessment.schema.json`, `completion-action-card.schema.json`; 수정 `workflow/state_machine.py`, `workflow-state.schema.json`, `cli.py`, `runtime_finalization.py`; tests `unit/completion/test_controller.py`, `integration/test_completion_action_revision.py`, `safety/test_limited_completion_guards.py`, `integration/test_expert_terminal_completion.py`.  
**Schema/계약:** normal/limited/not-ready, disposition counts, required failures, data/coverage limits, expert packets, available choices, next revision action. `needs_expert`는 packet+boundary+owner 후 `expert_review_required` terminal로만 완료 후보.  
**실패·복구:** integrity/stale/required failure는 normal·limited 모두 차단. `needs_input`은 사용자 확인 후 explicit disposition으로 전환. final choice는 exactly +1 revision과 final approval request를 만들고 웹 response가 승인하지 않는다.  
**테스트:** unclosed case, required fail, limited bypass, data unavailable confirmation, expert terminal no wait, duplicate/stale completion, empty bounded legacy case의 새 Gate.  
**합격 기준:** D09 §12.7 전부, 제한 완료 우회 0, final approval TTY 분리.  
**제품 표시:** limited reason/Coverage를 전면 표시하고 기존 quality label을 자동 유지하지 않는다.

- [ ] RED: required/limited/expert/empty-boundary tests를 작성한다.
- [ ] GREEN: pure assessment와 Completion Action submit adapter를 구현한다.
- [ ] GREEN: state machine/finalization 앞에 mandatory assessment gate를 연결한다.
- [ ] 회귀: finalization/approval/state guard suite를 실행한다.

## Task M. Final Result Converter

**상태:** revision/hash fail-closed Final Result Converter·immutable manifest·CLI export 구현 및 focused·최종 Full 검증 완료  
**출처:** D03 §14.3; D04 §§5–6; D09 §§8.1,10.6,11 M,12.8; Integration Index §4 M

**선행조건:** finalized current revision, passed Completion/Final validator, trusted viewer eligibility, current input manifest.  
**수정 파일:** 완료 시점의 concurrent diff를 먼저 재검토한 뒤 `trusted_ceo_agent/web_report/{contracts,converter,eligibility,presentation}.py`, schema `web-report-input-manifest.schema.json`, `cli.py`; tests `unit/web_report/test_{contracts,converter}.py`, `contracts/test_web_report_contract_semantics.py`, `determinism/test_web_report_bytes.py`, `integration/test_cli_export_web_report.py`, `safety/test_web_report_stale_input.py`.  
**Schema/계약:** converter input revision/hash/file manifest, D04 §6.3 WebReportBundle+D05 보정, JCS bundle/preview hash, viewer receipt, source/evidence/finding/grade/relation one-to-one refs.  
**실패·복구:** input revision/hash mismatch, schema/semantic/dangling ref, preview/bundle hash, oversize/privacy, eligibility false는 publish 0이고 이전 bundle을 새 결과처럼 열지 않는다. partial output 금지.  
**테스트:** 현재 invalid hash failure, dangling refs, duplicate IDs, preview limits, absolute path, restricted preview, same revision byte equivalence, stale/current hash, converter no-invention diff.  
**합격 기준:** 알려진 WebReport 실패 0, 같은 final revision byte-equivalent, 새 Finding/Grade/relation/evidence 생성 0.  
**제품 표시:** eligibility receipt가 허용한 `trusted_final`, `poc_fixture`, `unverified_import`만 정확히 표시.

- [ ] RED: converter/input-manifest/stale/no-invention tests와 현재 known failure를 격리한다.
- [ ] GREEN: semantic validator와 deterministic converter를 완결한다.
- [ ] GREEN: `export-web-report`를 CAS/read-current/fail-closed publish로 연결한다.
- [ ] 회귀: Python Contract 0, npm contract check, output/audit/validation suite를 실행한다.

## Task N. WebReportBundle과 탭 1·탭 2 실제 연결

**상태:** WebReportBundle 검증·탭 1/2 read-only projection·plugin export 연결 감사와 focused·web Full 검증 완료  
**출처:** D02 AD-11; D04 §§3–6,8,10–14,16–19; D05 §§1–4; D09 §§8.1,10.6,12.8; Integration Index §4 N

**선행조건:** B command contract, M valid Bundle/eligibility, concurrent web snapshot 재검토.  
**수정 파일:** 신규 `web/src/features/report/{bundle-loader,report-provider,ReportDashboard,ExecutiveSummary,EvidenceAnalysis,TrustLog,ExpertPackets,RevisionHistory,ResultQuestionPanel}.ts(x)` 및 tests; 수정 `web/src/app/report/page.tsx`, analysis provider transport; 필요 시 `vitest.config.ts`에서 Playwright 분리.  
**Schema/계약:** generated `WebReportBundleV1` 단일 타입, conversation key `run_id+revision+scope_kind+scope_instance_id`, 5 terminal gates, compact question panel, 탭별 upload policy, read-only Q&A.  
**실패·복구:** invalid/stale/oversize bundle은 dashboard 대신 제한 사유. provider timeout은 idempotency receipt 먼저 조회. 탭 2 mutation·새 판단·approval 생성 금지.  
**테스트:** bundle loader/eligibility, five panels/ref navigation, stale replacement, filter/download, Q&A revision 0, analysis responses exactly +1, 5 gate polling, CSV/JSON/XLSX vs result JSON policy, E2E two tabs.  
**합격 기준:** 실제 plugin adapter로 탭 1 submit과 탭 2 open, placeholder 0, generated type parity, 탭 2 분석 판단 0.  
**제품 표시:** Bundle authority/limits만 표시하고 프런트가 전문 label을 승격하지 않는다.

- [ ] RED: loader/provider/report page/Q&A/approval-boundary tests를 작성한다.
- [ ] GREEN: transport adapter와 report components를 generated type 기반으로 구현한다.
- [ ] 회귀: Vitest unit, Playwright E2E, contract npm check, Python provider integration을 실행한다.

## Task O. Knowledge Foundry Feedback→Patch→Release

**상태:** Feedback→Patch→3단계 승인→immutable Release·CAS persistence·rollback 구현 및 focused·최종 Full 검증 완료; 전문 콘텐츠 승격은 외부 전문가 필요  
**출처:** D02 AD-10; D07 §§1.2,5–11,14,16–18; D08 §§1–17,19–20; D09 §§7.4,11 I,12.3; D18 §8; Integration Index §4 O

**선행조건:** E Knowledge artifacts/authority, ArtifactStore/CAS, isolated evaluation fixtures, role policy.  
**수정 파일:** 신규 `knowledge/{foundry,release}.py`; schemas `feedback-record`, `feedback-receipt`, `patch-proposal`, `regression-case`, `release-candidate`, `knowledge-approval-request`, `knowledge-approval`; tests `contracts/test_foundry_schemas.py`, `integration/test_foundry_dual_loop.py`, `test_knowledge_stage_approvals.py`, `unit/knowledge/test_release_registry.py`, `safety/test_{foundry_approval_boundaries,feedback_privacy}.py`.  
**Schema/계약:** Stage 1 feedback preview/submit, reproduction+triage, patch+regression pair, Stage 2 approve, Stage 3 deploy; object/hash/expected revision/requested action/role separation; immutable release and rollback. Operational approval과 schema를 분리하되 nonce/CAS primitives는 재사용.  
**실패·복구:** raw feedback가 Analysis Plane을 직접 변경하지 못한다. reproduction/regression/role/approval 누락은 deploy 0. release는 진행 중 Run에 소급 적용하지 않고 새 Run만 사용. rollback은 이전 immutable release를 재활성화.  
**테스트:** duplicate feedback, privacy redaction, unreproduced patch, regression fail, same actor conflict, stale approval, deploy/rollback/new-run-only, rerun diff.  
**합격 기준:** 3단계 승인 우회 0, patch-only activation 0, rollback/reproducibility 완전.  
**제품 표시:** release·expert 승인 전 `machine_draft`; Foundry 존재만으로 Full 금지.

- [ ] RED: 3-stage authority/stale/privacy/reproduction tests를 작성한다.
- [ ] GREEN: intake→triage→patch/regression→release state machine을 구현한다.
- [ ] GREEN: immutable registry activation/rollback과 new-run binding을 구현한다.
- [ ] 회귀: Knowledge/Pack authority와 Foundry integration/safety suite를 실행한다.

## Task P. 평가·성능·병렬 non-inferiority Gate

**상태:** paired sequential/parallel evaluator·결정성·성능·activation/rollback Gate 구현 및 focused·최종 Full 검증 완료; 실제 외부 모델·전문가 non-inferiority 평가는 `not_evaluated`  
**출처:** D01 §8; D02 AD-07/12/13; D03 §§13.5,16–17; D04 §§17,19; D06 §§14–16; D07 §§11,14–15,19; D08 §§17–18,20; D09 §§7–9,12–13; D12–D18 Release Gate; Integration Index §4 P

**선행조건:** A–O relevant verticals, frozen scenario/oracles, sequential reference profile, approved evaluator policy.  
**수정 파일:** 신규 `trusted_ceo_agent/evaluation/{__init__,runner,metrics,non_inferiority,performance}.py`; schemas `evaluation-case`, `evaluation-result`, `quality-policy`, `concurrency-profile`, `performance-policy`, `stage-timing`, `non-inferiority-report`; tests `contracts/test_evaluation_policy_schemas.py`, `evaluation/test_non_inferiority_gate.py`, `determinism/test_accounting_profile_equivalence.py`, performance harness와 blinded human packet.  
**Schema/계약:** sequential/parallel_2/3/4 paired runs, deterministic semantic/byte fields, Critical recall/trigger/evidence/authority metrics, blinded expert score, p50/p95, workload class, activation/rollback receipt. Timing telemetry는 semantic hash 밖.  
**실패·복구:** deterministic mismatch나 non-inferiority/SLO 실패 profile은 비활성·rollback. AI 실패를 writer fallback으로 숨기지 않는다. 외부 모델/전문가 평가가 없으면 미수행으로 남기고 합격을 주장하지 않는다.  
**테스트:** seq/parallel deterministic equivalence, paired seeds/input hashes, statistical threshold boundary, timeout/cancel, p50/p95 calculation, failed profile rollback, no timing in semantic hash.  
**합격 기준:** deterministic 결과 동등, AI parallel이 sequential 대비 승인된 non-inferiority, 성능 SLO와 rollback drill 통과.  
**제품 표시:** 평가 전 profile은 experimental. 실제 expert/elevation 전 `senior_accountant_draft_scope` 주장 금지.

- [ ] RED: policy/profile/metric boundary와 semantic-hash separation tests를 작성한다.
- [ ] GREEN: paired runner/metrics/report/activation registry를 구현한다.
- [ ] GREEN: 실제 승인된 model profile과 전문가 평가가 제공된 경우에만 external run을 수행한다.
- [ ] 회귀: evaluation/determinism/performance/safety와 전체 suite를 실행한다.

## 3. Test commands and evidence log

PowerShell 기준 공통 prefix:

```powershell
$env:PYTHONPATH=(Resolve-Path 'plugin/trusted-ceo-agent').Path
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest <modules> -q
```

전체 Python 회귀:

```powershell
$env:PYTHONPATH=(Resolve-Path 'plugin/trusted-ceo-agent').Path
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest discover -s tests -q
```

Focused 실패 시에만 실패한 정확한 모듈을 `-v`로 다시 실행한다. Full 검증은
코드와 동작 설정을 동결한 최종 완료 게이트에서 한 번 실행한다. 측정값, 중복
방지 규칙, WebReport 별도 discovery 및 웹 최종 명령은
`docs/VALIDATION_WORKFLOW.md`를 따른다.

웹/contract 검증은 해당 package의 lockfile과 script를 먼저 확인한 뒤 offline install 상태에서 실행한다. Playwright spec은 Vitest unit 수집에서 분리한다.

| Checkpoint | RED evidence | GREEN focused | Full regression | Product claim |
|---|---|---|---|---|
| A baseline | initial WebReport hash FAIL 1 | Trust Kernel baseline 222 PASS | Python 434 + hidden 41 PASS | unchanged |
| B Human Response | missing schema/module/CLI: 1 FAIL+4 ERROR; 독립검토 경계 5건 | B 보강 focused 19/19 PASS (`7.775s`) | 공통 최종 게이트 PASS | no quality elevation; web transport는 N |
| G/H orchestration | missing graph/checkpoint contracts | 26/26 PASS | 공통 최종 게이트 PASS | no quality elevation |
| I/J case/finding | missing queue/finding contracts | 16/16 PASS | 공통 최종 게이트 PASS | terminal Finding only |
| C/D/K multi-domain | missing Event/Route/Join contracts | C/D 15/15 PASS; K 9 focused assertions PASS | 공통 최종 게이트 PASS | unsupported Boundary |
| L completion | missing CompletionAssessment | core 6/6 + artifact integration 2/2 PASS | 공통 최종 게이트 PASS | normal/limited explicit |
| M/N web report | initial hash FAIL 및 hidden unit FAIL 재현 | converter/CLI 3/3 + preview 4/4 PASS | hidden 41, contract parity, web 135, build, E2E 3 PASS | eligibility-bound |
| E/F accounting | missing depth/64-family execution contracts; AC-06~16 module RED 5 | Dispatcher·Registry·Raw adapter 9 PASS; CLI accounting 2 PASS | Python 434 PASS | machine_draft/Boundary; Tier 0 증거에만 `accounting_core_screened` |
| C–L runtime wiring | top-level runtime/CLI entrypoint missing | Runtime 3 PASS; CLI professional 2 PASS; required failure blocked | Python 434 PASS | verified artifacts only; no authority elevation |
| O Foundry | missing release/persistence contracts | core 20/20 + persistent CAS 4/4 PASS | 공통 최종 게이트 PASS | machine_draft until approval |
| P evaluation | missing paired activation contracts | 21/21 PASS | harness Full PASS; 실제 외부 대조는 `not_evaluated` | experimental until pass |

## 4. Stop conditions

다음 중 하나면 해당 변경 전에 중단하고 근거·선택지를 사용자에게 제시한다.

- 설계 우선순위로 해소할 수 없는 실제 계약 충돌
- 기존 immutable revision/Artifact/Approval/Pack authority를 마이그레이션하거나 다시 쓰는 비가역 변경
- 동시 사용자 변경과 동일 파일의 의미 충돌로 안전한 병합이 불가능함
- required behavior를 생략해야만 통과하는 예산·성능 제약
- 전문 authority 또는 공식 규범 승격을 위한 실제 전문가 승인 부재

그 밖의 additive Schema, 새 module, 실패 테스트, read-only adapter와 reversible integration은 이 계획에 따라 계속 진행한다.
