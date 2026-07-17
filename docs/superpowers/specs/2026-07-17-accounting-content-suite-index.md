# B2B 서비스업 회계 전문 콘텐츠 설계 Suite Index

- 상태: 사용자 검토용
- 기준일: 2026-07-17
- 최초 기준: 한국 B2B 서비스업, K-IFRS 우선
- 현재 권한: 설계 `machine_draft`; 구현·검증·전문가 승인 전 `Full` 금지

## 1. 목적

이 문서는 전문 회계 콘텐츠 설계 묶음의 필수 읽기 순서와 완료조건을 고정한다. 일부 문서만 구현하고 “시니어 회계사급 전체 검토”라고 표시하지 못하게 한다.

## 2. 상위 설계

1. `2026-07-17-trusted-ceo-agent-plugin-design.md`
2. `2026-07-17-senior-accountant-review-expansion-design.md`
3. `2026-07-17-professional-reasoning-knowledge-foundry-design.md`

## 3. 필수 콘텐츠 설계

1. `2026-07-17-accounting-review-coverage-matrix-design.md`
   - 회계 주장, 데이터 Capability, Tier, Cross-cycle, Release Gate
2. `2026-07-17-accounting-account-universe-gate-design.md`
   - 네 Pack 밖의 중요 계정과 공시영역 누락 차단
3. `2026-07-17-accounting-norm-procedure-seed-catalog.md`
   - 실제 provisional 규범·예외·반증·공통 절차 초안
4. `2026-07-17-accounting-core-journal-integrity-pack-design.md`
   - 원장·시산표·보조원장·분개 무결성
5. `2026-07-17-contract-revenue-pack-design.md`
   - 계약·수행의무·수익·계약잔액·채권
6. `2026-07-17-cash-flow-working-capital-pack-design.md`
   - 현금·현금흐름표·운전자본·유동성
7. `2026-07-17-project-cost-allocation-pack-design.md`
   - 프로젝트원가·배부·WIP·계약원가·손실계약

## 4. 설계 범위

| 영역 | Issue Family 수 | 직접 전문범위 |
|---|---:|---|
| Accounting Core | 16 | 원장 무결성·일반 회계위험 |
| Contract & Revenue | 16 | 계약·수익·채권·계약잔액 |
| Cash & Working Capital | 16 | 현금흐름 분류·현금전환·유동성 |
| Project Cost & Allocation | 16 | 원가귀속·배부·WIP·손실계약 |
| 합계 | 64 | B2B 서비스업 초기 전문범위 |

64개는 품질을 보장하는 마법의 숫자가 아니다. Knowledge Foundry의 합성·POC·전문가 피드백으로 Issue Family를 추가·분할·폐기할 수 있으며 모든 변경은 versioned Patch와 회귀테스트를 요구한다.

## 5. 구현 순서

1. Account Universe와 데이터 Capability
2. Accounting Core Tier 0
3. 세 Cycle의 population·reconciliation
4. Issue Family별 결정적 Procedure
5. Norm·Expectation·Counter-Hypothesis Card
6. Issue Evidence Packet과 Bounded AI Reasoning
7. 합성 Oracle과 회귀평가
8. 전문가 검토와 Knowledge Release 승격

구현 순서가 최종 범위 축소를 뜻하지 않는다.

## 6. 제품 표시 Gate

### `accounting_core_screened`

- Accounting Core의 무결성·대사만 완료
- 전문 회계검토 완료라는 표현 금지

### `three_cycles_boundary`

- 세 Cycle이 구현됐지만 전문가 승격 전
- 조건부 1차 진단으로만 표시

### `senior_accountant_draft_scope`

- 64개 Issue Family가 D1~D12를 충족
- 공식 출처·시행일·관할 연결
- 결정적 계산과 합성 Oracle 통과
- 중요 Account Family 상태 빈칸 0건
- 전문가가 세 Cycle을 검토·승격

이 상태도 최종 회계판단·감사의견을 의미하지 않는다.

### `company_wide_accounting_full`

초기 Suite만으로 사용 금지. Account Universe의 모든 중요 영역에 검증된 전문 Pack이 있어야 한다.

## 7. 자체검토 체크리스트

- AC-01~AC-16
- RV-01~RV-16
- CF-01~CF-16
- CA-01~CA-16
- Issue ID 중복 0건
- 각 Pack에 데이터·절차·가설·정량화·합성사례·Norm seed·Release Gate 존재
- 회계오류와 경영진단 구분
- 실행시점별 K-IFRS Norm Resolver
- IFRS 원문 라이선스 경계
- 중요 범위 밖 계정의 Coverage 상태

## 8. HANDOFF

```text
이 Index를 먼저 읽고 Manifest가 고정한 일곱 콘텐츠 설계서를 모두 확인한다.
Accounting Core만으로 전체 회계검토를 주장하지 않는다.
세 Cycle 구현만으로 회사 전체 회계 Full을 주장하지 않는다.
64개 Issue Family는 초기 seed이며 Knowledge Foundry로 계속 개선한다.
```
