# Trusted CEO Agent Professional System Integration Index

- 상태: 구현 전 Hard Gate를 위한 전문 시스템 단일 진입점
- 기준일: 2026-07-17
- 적용 범위: Trust Kernel 이후의 전문추론, 회계 Suite, Knowledge Foundry, 다중 도메인 라우팅, 오케스트레이션, Signal Queue, Finding, 종료, 결과 변환기, 웹 탭 1·2
- 감사 기준 HEAD: `65ae5f7`
- 불변 원칙: 이 문서는 아래 설계를 대체하지 않는다. 구현자는 이 문서의 읽기 순서와 완료 Gate를 통해 모든 원문 설계를 함께 사용한다.

## 0. Hard Gate 감사 결과

### 0.1 필수 문서 존재·내용·Git 상태

2026-07-17 감사에서 필수 문서 18개가 모두 존재하고 비어 있지 않으며 UTF-8 본문을 판독할 수 있음을 확인했다.

| 구분 | 문서 수 | 존재·내용 | 감사 시 Git 상태 |
|---|---:|---|---|
| 기반 문서 | 3 | 3/3 확인 | 3개 미추적 |
| 웹 정본 | 2 | 2/2 확인 | 2개 추적·clean |
| 전문화 상위 설계 | 4 | 4/4 확인 | 4개 추적·clean |
| 회계 콘텐츠 Suite | 9 | 9/9 확인 | 9개 추적·clean |
| 합계 | 18 | 18/18 확인 | 15개 추적, 3개 미추적 |

감사 시 미추적이었던 필수 기반 문서는 다음과 같다. 사용자는 2026-07-17 Hard Gate 문서 커밋에 이 세 파일을 포함하도록 승인했다.

| 문서 | 감사 시 SHA-256 |
|---|---|
| `docs/PRD.md` | `70559581164661fc425e419d59482641958961ac71d33a7eb19d5a0288dd4b7a` |
| `docs/ARCHITECTURE_DECISIONS.md` | `34c97b2f3bad5e592980df1ad65938989dfdaba5288562e0cfdfb1a82db3f24d` |
| `docs/superpowers/specs/2026-07-17-trusted-ceo-agent-plugin-design.md` | `25a90a5c85dc0f137f58925cf857f8ac623c78c8a8238be3f3befa6c380ff05a` |

`plugin/trusted-ceo-agent/**`, `tests/**`, `contracts/**`, `web/**`에는 광범위한 미추적 사용자 소유 기준선과 진행 중 작업이 있다. Hard Gate 문서 커밋은 이 경로를 스테이징하지 않는다. 코드의 “기존 구현” 상태는 기능 감사 결과일 뿐 Git 기준선 완료를 뜻하지 않는다.

### 0.2 회계 Suite 완전성

- 제어 문서: Suite Index와 Manifest 2개
- Manifest §3 payload: Coverage Matrix, Account Universe Gate, Norm & Procedure Catalog, Accounting Core, Contract & Revenue, Cash Flow & Working Capital, Project Cost & Allocation 7개
- Issue Family: AC 16 + RV 16 + CF 16 + CA 16 = 64개
- 정규식 대조 결과: unique 64, 누락 0, 중복 0
- 현재 Authority: `machine_draft`; Schema·Component·Oracle·공식 문단 grounding·전문가 승격은 미완료

## 1. 필수 읽기 순서와 문서 책임

아래 순서를 생략하거나 마지막 교차 설계만 읽고 구현할 수 없다.

| ID | 필수 문서 | 책임 범위와 핵심 절 |
|---|---|---|
| D01 | `docs/PRD.md` | 제품·사용자·입력·4층 구조·Trust Kernel·결과·검증 정본; §§0–10, 특히 §§3–4, 8 |
| D02 | `docs/ARCHITECTURE_DECISIONS.md` | 확정 기술·운영 결정; AD-02 Trust Kernel, AD-06 구조화 추론, AD-07 Join, AD-09 HITL, AD-11 단일 엔진, AD-12 검증 |
| D03 | `docs/superpowers/specs/2026-07-17-trusted-ceo-agent-plugin-design.md` | 기존 플러그인의 Schema, Artifact, revision, approval, Pack authority, CLI, 테스트 기준선; §§2–19 |
| D04 | `docs/superpowers/specs/2026-07-17-trusted-ceo-agent-web-design-final.md` | 웹 탭 1·2, WebReportBundle, Result Q&A, provider, 보안, 검증 정본; §§3–19 |
| D05 | `docs/superpowers/specs/2026-07-17-trusted-ceo-agent-web-design-final-addendum-v2.md` | D04의 네 필수 보정: 대화 키, 5 gate 승인 상태, compact panel, 탭별 업로드 정책; §§1–4 |
| D06 | `docs/superpowers/specs/2026-07-17-senior-accountant-review-expansion-design.md` | 보수적 Router, Coverage Auditor, Tier 0–3, 세 회계 Cycle, Issue Evidence Packet; §§2–16 |
| D07 | `docs/superpowers/specs/2026-07-17-professional-reasoning-knowledge-foundry-design.md` | Economic Event, Professional Kernel, D1–D12, 지식 Artifact·등급·Release·rollback; §§3–19 |
| D08 | `docs/superpowers/specs/2026-07-17-knowledge-foundry-feedback-intake-design.md` | Controlled Evaluation·Field Feedback, Feedback→Patch→Regression→Release, 3단계 승인; §§1–20 |
| D09 | `docs/superpowers/specs/2026-07-17-professional-analysis-interaction-routing-quality-gates-design.md` | Human Response revision, multi-domain, DAG·budget, SignalCase·Finding, Completion, Converter, 품질·성능 Gate; §§2–13 |
| D10 | `docs/superpowers/specs/2026-07-17-accounting-content-suite-index.md` | Suite 탐색, 64 Family 범위, 구현 순서, 제품 표시 Gate; §§2–7 |
| D11 | `docs/superpowers/specs/2026-07-17-accounting-content-suite-manifest.md` | Suite 최종 파일 목록과 완료 Gate; §§1–6, 파일 목록 충돌 시 D10보다 우선 |
| D12 | `docs/superpowers/specs/2026-07-17-accounting-review-coverage-matrix-design.md` | 주장·Capability·Tier·Cross-cycle·Release 및 Coverage 검사; §§4–15 |
| D13 | `docs/superpowers/specs/2026-07-17-accounting-account-universe-gate-design.md` | 중요 Account Family 누락·빈 상태 차단, 전체 Full 경계; §§1–7 |
| D14 | `docs/superpowers/specs/2026-07-17-accounting-core-journal-integrity-pack-design.md` | AC-01~AC-16, 원장·시산표·보조원장·분개, Tier 0; §§1–12 |
| D15 | `docs/superpowers/specs/2026-07-17-contract-revenue-pack-design.md` | RV-01~RV-16, Economic Event Graph, 계약·수익 절차·반증; §§1–12 |
| D16 | `docs/superpowers/specs/2026-07-17-cash-flow-working-capital-pack-design.md` | CF-01~CF-16, 현금·현금흐름·운전자본·유동성; §§1–12 |
| D17 | `docs/superpowers/specs/2026-07-17-project-cost-allocation-pack-design.md` | CA-01~CA-16, 원가·배부·WIP·계약원가·손실계약; §§1–13 |
| D18 | `docs/superpowers/specs/2026-07-17-accounting-norm-procedure-seed-catalog.md` | provisional Norm·예외·반증·공통 Procedure와 승격 전 검증; §§1–8 |

## 2. 우선순위와 충돌 규칙

1. 원본 불변성, Evidence lineage, revision CAS, 승인, Pack authority, hash, 최종 Validator는 D01–D03과 D02의 Trust Kernel 결정을 따른다. 후속 설계가 이를 우회할 수 없다.
2. 웹 정본은 D04와 D05를 함께 사용한다. D05가 명시한 네 항목만 D04보다 우선하고 나머지는 D04를 유지한다. 이전 `web-interface-design`, `web-design`, addendum v1은 참고 초안이며 구현 근거가 아니다.
3. D09는 교차 구현계약이며 D01–D08을 대체하지 않는다. 상위 설계의 의미를 보존하면서 상호작용·라우팅·오케스트레이션·종료·투영 Gate를 추가한다.
4. 회계 파일 목록이 다르면 D11 Manifest가 D10 Index보다 우선한다. 따라서 Norm & Procedure Catalog를 포함한 7개 payload가 모두 필수다.
5. 회계 Pack의 구체적 모집단·절차·가설·정량화는 D14–D18, 공통 Coverage와 Universe 차단은 D12–D13을 따른다.
6. 표현·정렬·차트·질문 UI는 분석 엔진의 Finding, Grade, 관계, Evidence, 승인 상태를 변경할 수 없다.
7. 도메인 Pack이 없거나 승인되지 않으면 일반 LLM 지식으로 메우지 않는다. 분석 중 상태는 `unsupported_pack`, `not_assessable`, `needs_expert` 또는 명시적 Boundary로 보존하고, 전문가 패킷·판단 경계·책임자가 준비된 경우에만 `needs_expert`를 terminal `expert_review_required`로 전환한다.
8. `machine_draft`, `Boundary`, `Provisional`, `Full`은 별도 상태다. 전문가 승인 없는 범위를 `Full` 또는 시니어급으로 표시하지 않는다.

### 2.1 이번 Gate에서 해소한 참조 충돌

| 충돌 | 해소 규칙 |
|---|---|
| D09가 미추적 `web-interface-design` 초안을 정본처럼 참조 | D04 final과 D05 Addendum v2 두 정본으로 교체 |
| D09가 회계 Suite 제어 문서를 필수 입력으로 연결하지 않음 | D10 Index와 D11 Manifest 및 Manifest payload 7개를 필수 입력·완료조건에 연결 |
| D10이 Norm Catalog를 누락하고 “여섯 설계서”라고 기술 | D11 우선권에 맞춰 Norm Catalog 포함 7개로 수정 |
| D04의 대화 키·승인 상태·업로드 문구와 D05 충돌 | D05 §§1–4가 해당 네 항목에 한해 우선 |

## 3. 제품 표시와 전문 권한 Gate

| 현재 충족 범위 | 허용 표시 | 금지 표시 |
|---|---|---|
| Accounting Core 무결성·대사만 구현·통과 | `accounting_core_screened` | 전문 회계검토 완료 |
| 세 Cycle 구현, 전문가 승격 전 | `three_cycles_boundary` | 시니어 회계사급, Full |
| 64 Family D1–D12, 공식 출처·시행일, 결정적 계산·Oracle, 중요 Account 상태 빈칸 0, 세 Cycle 전문가 승격 | `senior_accountant_draft_scope` | 최종 회계판단, 감사의견 |
| 초기 Suite만 구현 | 위 조건에 맞는 제한 표시 | `company_wide_accounting_full` |
| 모든 중요 Account Family에 검증·승격된 전문 Pack 보유 | `company_wide_accounting_full` 후보 | 자동 Full 또는 범위 밖 은폐 |

현재 회계 콘텐츠는 `machine_draft`다. 런타임 구현과 합성 검증만으로 전문가 승인을 대신하지 않으며, 법무·노무·세무 미지원 영역은 안전한 Boundary까지만 주장한다.

## 4. 요구사항 → 설계 → Task → 코드·Schema → 테스트 추적표

상태는 `완료`, `부분`, `미구현`, `외부 전문가 필요`로만 판정한다. “부분”은 기존 재사용 기반이 있다는 뜻이며 해당 Task의 합격을 뜻하지 않는다.

| Task | 요구사항 출처 | 구현 코드·Schema 연결 | 필수 테스트 연결 | 현재 상태·제품 영향 |
|---|---|---|---|---|
| A. 플러그인 기준선·회귀 | D01 §§3,8; D02 AD-02/12/13; D03 §§2.3,5–7,12–18; D06 §15 Phase 0 | 기존 `trust/artifact_store.py`, `workflow/revisions.py`, `evidence/core.py`, `workflow/approvals.py`, `outputs/validation.py`; 기존 core schemas | 기존 unit/contract/integration/determinism/safety/plugin/evaluation 전체 | `부분`: 기능은 광범위하나 코드·테스트가 미추적이고 전체 재검증 전 |
| B. Human Action·Response-to-Revision | D01 §§3–4; D02 AD-09; D03 §12; D04 §§4.5,9,11–12; D05 §§1–2; D09 §§2–4,11 A–B,12.1 | 신규 `workflow/human_actions.py`, `workflow/responses.py`; `human-action-card`, `human-response`, `human-response-receipt` schemas; 기존 approval/overlay/CAS 재사용 | action contract, stale card, duplicate idempotency, request_explanation read-only, exact +1 revision, TTY approval 분리 | `부분`: approval·overlay 기반만 존재; 제품 분석 상호작용 미연결 |
| C. Economic Event materialization | D07 §§3.1–3.2; D09 §§5.2,11 C,12.2; D12 §5; D15 §1; D17 §1 | 신규 `analysis/economic_events.py`, `economic-event.schema.json`; Fact·Source lineage 참조 | event ID 결정성, 품질·lineage, 동일 사건의 다중 도메인 공유, stale input 차단 | `미구현` |
| D. Multi-domain Router | D03 §§9.9,15.4; D06 §§5,11–12; D07 §13; D09 §§5,11 D,12.2; D13 §§2,4,7 | 신규 `routing/domain_router.py`, `domain-route.schema.json`; 기존 `packs/selector.py`는 단일 도메인 기준선으로만 재사용 | 0/1/2+/4 route, AI additive-only, unsupported boundary, domain별 실패 보존 | `부분`: 단일 selector만 존재; 다중 도메인 품질 주장 금지 |
| E. D1–D12 Gate | D06 §§7,9–12; D07 §§4–6; D09 §§6,11 E,12.3; D12 §§8–9,13,15; D18 §8 | 신규 `knowledge/depth_gate.py`; Method/Norm/Expectation/Procedure/Counter/Trigger schemas와 release metadata | D1–D12 누락·만료 Norm·출처/전문가 승인 누락 시 Full 0 | `미구현`, `외부 전문가 필요` |
| F. 회계 Suite 64 Family | D06 §§8–10,14–16; D07 §§12,18 Phase 4; D10–D18 | 신규 accounting Pack·Component·Coverage/Universe contracts; AC/RV/CF/CA 64 family registry | 64 unique·빈칸 0, Tier 0, 정상/오류/경계/반증/복합 Oracle, Pack별 결정성 | 설계 `완료`; 런타임 `미구현`; `외부 전문가 필요`; 현재 상한 `machine_draft` |
| G. Orchestration Harness·유한 DAG | D01 §7; D02 AD-07; D03 §§10.9–10.11,13; D09 §§8.1–8.2,11 J,12.5 | 신규 `orchestration/graph.py`, `scheduler.py`; `analysis-work-graph`, `analysis-work-item` schemas; 기존 reasoning Job/Join 재사용 | dependency, topological readiness, deterministic Join, idempotency, cancellation, required failure 차단 | `부분`: stage Job/Join만 존재 |
| H. WorkBudget·checkpoint/resume | D03 §§12.1–12.2,13.3–13.5; D04 §§4.3,12,14; D09 §§8.2–8.4,8.8,11 J,12.5 | 신규 `orchestration/budget.py`, `checkpoint.py`; `work-budget-policy.schema.json`; 기존 ArtifactStore/state machine 재사용 | overflow 명시, required 절차 보존, timeout/retry/cancel/resume, stale revision, terminal 중복 0 | `부분`: 정적 시간·병렬 상수와 coarse revision resume만 존재 |
| I. Signal Case Queue·Priority | D09 §§8.4,10.1,11 J–K,12.6 | 신규 `analysis/signal_queue.py`; `signal-case`, `priority-record` schemas | dedupe·merge, 안정 정렬, deep active 기본 1, 모든 이탈 terminal | `미구현` |
| J. Finding·관계·IssueCluster | D09 §§10.2–10.3,11 K,12.6 | 신규 `analysis/findings.py`, `relations.py`; `finding-record`, `finding-relation`, `issue-cluster` schemas | disposition별 필수 필드, supersession, 이전 revision byte 불변, 근거 없는 인과 0 | `부분`: legacy integrated issueCluster만 존재; 불변 Finding은 미구현 |
| K. Cross-domain·Cross-Finding Integrator | D02 AD-07; D03 §§10.9–10.11; D06 §11; D07 §13; D09 §§8.5,10.3–10.4,11 F/K,12.2/12.6 | 신규 `analysis/integrator.py`; domain/finding join manifests; 기존 `reasoning/join.py` 재사용 | required domain barrier, conflict 보존, completion-order equivalence, 단일 post-Join writer | `부분`: 단일 legacy integrator만 존재 |
| L. Completion Controller | D03 §§12,14.3; D06 §§12,16; D07 §§16,19; D09 §§8.8,10.5,11 L,12.7,13; D13 §7 | 신규 `completion/controller.py`; `completion-assessment`, `completion-action-card` schemas; 기존 final approval 전이 재사용 | 정상/제한 완료, required 우회 0, needs_expert packet, exact +1 revision·TTY final | `부분`: legacy finalize는 있으나 CompletionAssessment 없음 |
| M. Final Result Converter | D03 §14.3; D04 §§5–6; D09 §§8.1,10.6,11 M,12.8 | 신규 `outputs/web_report.py`; converter input manifest와 WebReportBundle contract; 기존 final validation/render 재사용 | 입력 hash·revision fail-closed, 동일 revision byte-equivalence, 새 Finding/Grade/관계 생성 0 | `부분`: Final Result renderer만 존재; converter 미구현 |
| N. WebReportBundle·탭 1·2 | D02 AD-11; D04 §§3–6,8,10–14,16–19; D05 §§1–4; D09 §§8.1,10.6,12.8 | `contracts/web-report/v1/**`, `web/**`, provider adapter; plugin `export-web-report` | schema/type parity, 탭별 upload policy, 5 gate polling, compact panel, tab2 mapping·Q&A read-only | `부분`: 사용자 소유 계약·웹 scaffold 진행 중; 실제 plugin 연결·converter·완전한 탭 2는 미검증 |
| O. Knowledge Foundry | D02 AD-10; D07 §§1.2,5–11,14,16–18; D08 §§1–17,19–20; D09 §§7.4,11 I,12.3; D18 §8 | 신규 `knowledge/foundry/**`; Feedback/Patch/Regression/Release schemas와 registry | 3단계 승인 분리, reproduction, regression, deploy 이후 Run만 적용, rollback·privacy | `미구현`, Norm·Method 승격은 `외부 전문가 필요` |
| P. 평가·성능·병렬 non-inferiority | D01 §8; D02 AD-07/12/13; D03 §§13.5,16–17; D04 §§17,19; D06 §§14–16; D07 §§11,14–15,19; D08 §§17–18,20; D09 §§7–9,12–13; D12–D18 Release Gate | 신규 benchmark/paired evaluator, `QualityPolicy`, `PerformancePolicy`, concurrency profile registry; 기존 deterministic runner/evaluator 재사용 | sequential/parallel 결정성, AI non-inferiority, p50/p95, 실패 profile 비활성·rollback | `부분`: 결정적 병렬 테스트만 존재; AI 대조·SLO activation Gate 미구현 |

## 5. 회계 64 Issue Family 구현 입력

| Pack | 필수 Family | 강제 범위·제품 상한 |
|---|---|---|
| Accounting Core D14 §3 | `AC-01`–`AC-16` | AC-01–05는 Tier 0 Mandatory. Core만 통과하면 `accounting_core_screened` |
| Contract & Revenue D15 §3 | `RV-01`–`RV-16` | 계약·수익·채권·계약잔액; 법·세무 Trigger를 숨기지 않음 |
| Cash Flow & Working Capital D16 §2 | `CF-01`–`CF-16` | 현금·분류·회수·지급·유동성; 법·세무·노무·계속기업 Trigger 보존 |
| Project Cost & Allocation D17 §3 | `CA-01`–`CA-16` | 직접·간접·배부·WIP·자산화·손실계약; 회계+관리회계 전문가 필요 |

Family ID가 존재하는 것만으로 구현 완료가 아니다. 각 Family는 D1–D12, 적용 Norm, 모집단·Coverage, 결정적 Procedure, 지지·반대 Evidence, 정량화, 정상·오류·경계·반증·복합 Oracle, 전문가 authority를 연결해야 한다.

## 6. 구현 순서와 수직 완료 단위

1. 기존 테스트와 상태 머신 기준선 고정
2. 통합 Schema와 Artifact 계약
3. AnalysisWorkGraph와 WorkItem
4. checkpoint, idempotency, retry, cancellation
5. Signal Case Queue와 한 건씩 진행하는 deep-case controller
6. Economic Event와 다중 도메인 라우팅
7. FindingRecord와 Cross-Finding 관계
8. CompletionAssessment와 종료 흐름
9. Final Result Converter와 WebReportBundle
10. Account Universe·Coverage·Accounting Core Tier 0
11. Accounting Core 16 Family
12. Contract & Revenue 16 Family
13. Cash Flow & Working Capital 16 Family
14. Project Cost & Allocation 16 Family
15. D1–D12·Norm·Procedure·Counter-Evidence
16. Knowledge Foundry와 3단계 승인
17. 웹 탭 1·2 실제 연결
18. 전체 회귀·평가·성능·병렬 non-inferiority 검증

각 수직 단위는 Schema·코드·테스트·실패/복구·제품 표시를 함께 끝낸다. 범위가 크다는 이유로 required Procedure, 반증, Coverage, authority 또는 fail-closed를 제거하지 않는다.

## 7. 구현 시작·완료 Gate

다음 조건을 모두 만족하기 전에는 제품 코드를 변경하지 않는다.

- [x] 필수 문서 18개 존재·내용 확인
- [x] 문서별 Git 상태 확인
- [x] 미추적 필수 기반 문서 3개 목록·내용·hash 확인
- [x] 해당 3개 문서의 커밋 권한 사용자 승인
- [x] Professional System Integration Index 작성
- [x] 회계 Suite 제어 2개와 payload 7개를 필수 입력으로 연결
- [x] D09의 미추적 웹 초안 참조를 D04 final+D05 Addendum v2로 교체
- [x] 요구사항→설계→Task→코드·Schema→테스트 추적표 작성
- [x] 통합 인덱스·참조 수정 자체검토 통과
- [x] 문서 전용 통합 커밋 `6adbfb9c7c33d61f369e0e4a46d504925d1fd414` 완료 및 18개 필수 문서 tracked 확인

제품 구현 완료를 주장하려면 추가로 다음을 모두 만족해야 한다.

- A–P 각 Task에 독립된 실패 테스트, 구현, 복구 테스트, 합격 증거가 있다.
- 기존 Trust Kernel과 전체 회귀 테스트가 통과한다.
- required task 실패, stale revision, 중복 제출, timeout, cancellation, resume가 fail-closed다.
- 순차·병렬 결정적 결과가 동등하고 AI 병렬 profile이 sequential 대비 non-inferiority를 통과한다.
- 모든 중요 Signal Case가 terminal disposition과 Finding 또는 명시적 비결론 상태를 가진다.
- limited completion이 required 실패나 무결성 실패를 우회하지 않는다.
- Finding supersession이 이전 revision을 변경하지 않는다.
- 동일 final revision의 WebReportBundle이 byte-equivalent이고 입력 hash·revision 불일치는 publish 0건이다.
- 변환기와 탭 2가 새 Finding, Grade, 관계, Evidence 또는 전문 결론을 만들지 않는다.
- Account Universe·Coverage 상태 빈칸이 0이고 64 Family 완전성 검사가 통과한다.
- 미지원 법무·노무·세무는 승인 없는 일반 LLM 결론 대신 Boundary로 남는다.
- 제품 표시는 §3의 현재 충족 범위를 넘지 않는다.

## 8. Hard Gate 커밋 범위

문서 전용 Gate 커밋에는 다음만 포함한다.

1. 승인된 미추적 기반 문서 3개
2. 이 Professional System Integration Index
3. D09의 웹 정본·회계 Suite 필수 참조 수정
4. D10의 Norm Catalog·7개 payload 참조 수정

Post-commit 검증 결과는 필수 문서 `18/18 tracked`, 누락 `0`, 통합 커밋 파일 `6개`, 범위 밖 staged 파일 `0개`다. 이 검증을 기록한 후속 커밋이 Hard Gate 증거 커밋이다.

그 밖의 미추적 또는 동시 변경 파일은 사용자 소유로 보존하고 스테이징하지 않는다. 첫 문서 통합 커밋 후에는 그 커밋 ID와 18개 tracked 확인 결과를 이 문서에 기록하고, 이 인덱스만 포함하는 후속 Gate 증거 커밋으로 마지막 시작 체크를 닫는다. 두 커밋 ID는 구현계획과 완료 보고에 기록한다.
