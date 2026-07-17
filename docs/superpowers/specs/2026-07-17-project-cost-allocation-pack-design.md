# Project Cost & Cost Allocation Cycle Pack 설계

- Pack ID: `kr_b2b.project_cost_allocation.v1`
- 상위 Matrix: `2026-07-17-accounting-review-coverage-matrix-design.md`
- 기준: K-IFRS 관련 계약원가·재고·무형자산·충당부채 Overlay, 관리회계 인과관계 별도
- 권한 상한: 전문가 승격 전 `Boundary`

## 0. 목적

프로젝트 마진 이상을 단순 탐지하는 데서 멈추지 않고, 원가가 완전하게 수집됐는지, 올바른 프로젝트와 기간에 귀속됐는지, 배부기준이 경제적 인과관계를 왜곡하는지, 회계상 자산·비용·충당부채가 잘못됐는지를 구분한다.

다음 결과를 분리한다.

- `accounting_misstatement_candidate`
- `management_cost_distortion`
- `control_weakness`
- `not_assessable`

관리회계상 더 나은 배부기준이 곧 K-IFRS 오류를 의미하지 않는다.

## 1. Cost Event Graph

```text
resource acquisition
-> employee / vendor / infrastructure usage
-> activity
-> cost pool
-> allocation base
-> project / contract / customer
-> WIP / expense / contract cost asset
-> revenue and margin
-> future fulfilment / loss contract
```

원가의 원천, 소비활동, 배부, 회계처리, 경영보고를 분리해 lineage를 보존한다.

## 2. 데이터 역할

| Role | 예시 |
|---|---|
| project_master | 프로젝트, 계약, 고객, 기간, 책임자 |
| cost_gl | 급여·외주·인프라·여비·공통비 원장 |
| payroll | 직원·부서·급여·기간 |
| timesheet | 직원·프로젝트·활동·시간·승인 |
| vendor | 외주계약·청구·작업결과 |
| usage | cloud·license·device·support ticket |
| cost_pool | pool 정의·포함계정·owner |
| allocation | base·rate·driver·run date |
| budget | 예산·baseline·변경 |
| progress | milestone·진척률·예정원가 |
| accounting | WIP·계약원가자산·상각·손상·충당부채 |
| revenue | 프로젝트별 수익·계약잔액 |

timesheet가 없으면 시간기준 재배부를 확정하지 않고 scenario로만 제시한다.

## 3. Issue Family

| ID | Issue | 구분 | 핵심 절차 | 대표 Output |
|---|---|---|---|---|
| CA-01 | GL-프로젝트 원가 불일치 | 회계·통제 | population reconciliation | 누락·orphan 원가 |
| CA-02 | 직접·간접원가 오분류 | 회계·관리 | activity·beneficiary 검사 | 재분류 후보 |
| CA-03 | 원가 pool 비동질 | 관리·통제 | pool composition | 분리 pool 후보 |
| CA-04 | 배부기준 인과관계 부족 | 관리 | driver comparison | 마진 왜곡 |
| CA-05 | 배부율 계산 오류 | 회계·관리 | rate reperformance | 배부차이 |
| CA-06 | 중복·누락·미배부 | 회계·통제 | allocation completeness | 오류금액 |
| CA-07 | 유휴조업도·비정상 낭비 | 회계·관리 | capacity·waste separation | 비용화 후보 |
| CA-08 | 근로시간·인력 원가 귀속 오류 | 회계·관리 | payroll-timesheet-project 대사 | 프로젝트 이동 |
| CA-09 | 외주·인프라·공통서비스 귀속 | 회계·관리 | invoice·usage matching | 원가 재귀속 |
| CA-10 | WIP·진척률·예정원가 오류 | 회계 | roll-forward·ETC backtest | WIP 조정 |
| CA-11 | 계약획득·이행원가 자산화 | 회계 | eligibility·amortisation | 자산·비용 후보 |
| CA-12 | 개발·교육·유지보수 자산화 | 회계 | IAS 38/IFRS 15 scope | 자산조정 후보 |
| CA-13 | 손실·부담계약 누락 | 회계 | unavoidable cost vs benefit | 충당부채 후보 |
| CA-14 | 변경계약·scope creep | 회계·관리 | contract-budget-actual bridge | 미청구·손실 영향 |
| CA-15 | 프로젝트 마진 왜곡 | 관리 | alternate allocation sensitivity | 정상화 마진 |
| CA-16 | 관계회사·부서간 cross-charge | 회계·세무 Trigger | counterparty·policy 검사 | 세무·공시 Trigger |

## 4. 결정적 절차

### P-CA-01 Cost population reconciliation

```text
GL_cost_population
= directly_assigned_cost
+ allocated_cost
+ unassigned_cost
+ excluded_with_reason
```

- 계정·기간·법인·원가센터별로 대사한다.
- 순액 일치만으로 프로젝트 간 상계를 허용하지 않는다.
- 원가가 없는 프로젝트와 프로젝트가 없는 원가를 모두 찾는다.

### P-CA-02 Directness test

직접원가 후보 요건:

- 특정 프로젝트·계약 때문에 발생
- source에서 직접 추적 가능
- 동일 기준이 일관 적용
- 다른 프로젝트와 공동효익이 아님

직접 표기만 있고 활동·계약 ref가 없으면 반증을 요청한다.

### P-CA-03 Pool homogeneity

각 pool에서:

- 비용 성격
- 원가 발생원인
- 혜택받는 대상
- 변동·고정
- 통제가능성
- 기간

을 비교한다.

서로 다른 driver가 필요한 비용을 한 pool에 섞으면 분리 시나리오를 만든다.

### P-CA-04 Allocation rate reperformance

```text
allocation_rate = eligible_pool_cost / eligible_driver_quantity
allocated_cost_i = allocation_rate * driver_quantity_i
```

검사:

- numerator 포함계정
- denominator 모집단
- 0·음수·누락 driver
- 기간 정합성
- rounding
- 배부 후 합계
- 수동 override

### P-CA-05 Driver causality

후보 driver:

- 실제 작업시간
- headcount
- ticket
- cloud usage
- transaction
- 면적
- 직접원가
- 매출

각 driver가 원가 소비를 설명하는 논리와 데이터 가용성을 기록한다. 상관만으로 인과성을 확정하지 않는다.

### P-CA-06 Alternative allocation sensitivity

최소 세 시나리오:

- 회사 현재 정책
- 가장 직접적인 사용량 driver
- 합리적인 대체 driver

프로젝트별 원가·마진·손실계약 상태 변화와 순위를 비교한다.

이는 관리진단이며 회계오류 금액과 분리한다.

### P-CA-07 Capacity and abnormal cost

- normal capacity
- practical capacity
- actual utilisation
- idle time
- rework
- abnormal waste
- onboarding·training

을 구분한다.

유휴원가를 고마진 프로젝트에 배부해 손실 프로젝트가 숨겨지는지 검사한다.

### P-CA-08 Payroll-timesheet reconciliation

```text
paid_or_accrued_hours
= project_hours
+ internal_hours
+ leave_hours
+ unassigned_hours
```

- 직원별·기간별 합계
- 승인 없는 시간
- 불가능한 동시배정
- 마감 후 대량수정
- 프로젝트 종료 후 시간
- manager override

를 검사한다.

근로시간 데이터는 노무·개인정보 Trigger를 가진다.

### P-CA-09 Vendor and usage matching

- 외주 invoice와 계약·milestone·검수
- cloud bill과 tenant·project usage
- 공통 license와 사용자
- support ticket과 고객·프로젝트

를 연결한다.

invoice 설명만으로 귀속을 확정하지 않는다.

### P-CA-10 WIP and progress roll-forward

```text
opening_WIP
+ eligible_current_cost
- recognised_cost
- write_down
+/- transfer
= closing_WIP
```

진척률, 수익인식, 원가인식, 실제 이행을 서로 대사한다.

### P-CA-11 Estimate-to-complete backtest

- 전기 ETC와 당기 실제 잔여원가
- 일정지연
- scope change
- 인력단가
- 재작업
- 고객 claim

을 비교해 반복 낙관편향을 찾는다.

### P-CA-12 Contract cost asset

구분:

- 계약획득 증분원가
- 미래 수행에 직접 관련
- 자원을 생성·향상
- 회수 예상
- 다른 기준서 적용대상
- 이미 수행한 의무 관련 원가
- 일반관리·낭비
- 교육

자산화 후보는 상각·손상·관련 수익패턴까지 재수행한다.

### P-CA-13 Onerous contract

```text
expected_economic_benefits
vs
unavoidable_costs
```

직접 증분원가와 계약이행에 직접 관련된 기타 배부원가를 검토한다. 종료위약금과 이행원가 중 적절한 비교를 Norm Card로 적용한다.

### P-CA-14 Scope creep bridge

```text
baseline_budget
+ approved_change_orders
+ unapproved_scope_candidate
+ price_and_rate_changes
+ productivity_variance
= expected_total_cost
```

미승인 범위확대가 수익·미청구·손실계약에 미치는 영향을 연결한다.

## 5. 가설과 반증

### 저마진 프로젝트

가설:

- 실제 과다작업
- 가격할인
- 원가 오배부
- scope creep
- 비정상 낭비
- 수익인식 지연
- 데이터 누락

구별:

- 시간·usage
- 계약변경
- 배부 전 직접원가
- 수익스케줄
- ETC
- 고객 claim

### 고마진 프로젝트

가설:

- 효율성
- 원가 누락
- 다른 프로젝트로 원가 이전
- 공통비 미배부
- 수익 조기인식
- 후속원가 지연

### 매출기준 공통비 배부

정상 가설:

- 관리정책상 단순하고 안정적
- 실제 소비량과 합리적으로 비례

문제 가설:

- 지원집약 저매출 프로젝트의 원가를 고매출 프로젝트로 이전
- 가격과 원가소비를 혼동

구별:

- 시간·ticket·usage와의 설명력
- 대체 driver 민감도
- 정책 일관성

## 6. 회계오류와 관리왜곡

| 결과 | 회계오류 후보 | 관리왜곡 |
|---|---|---|
| 배부율 산술오류 | 가능 | 가능 |
| 회사정책대로 매출기준 배부 | 기준·정책에 따라 | 인과성 부족 가능 |
| 원가 누락 | 가능 | 가능 |
| 유휴원가 프로젝트 배부 | 적용기준에 따라 | 수익성 왜곡 가능 |
| 대체 driver에서 마진변화 | 그 자체로 아님 | 핵심 진단 |
| 계약원가 자산화 오류 | 가능 | 투자성과 왜곡 |

보고서는 두 금액을 섞지 않는다.

## 7. 정량화

### Accounting misstatement

- 누락·중복 원가
- 잘못된 기간
- 자산화·비용화 차이
- WIP 차이
- 상각·손상 차이
- 부담계약 충당부채 후보

### Management distortion

```text
distortion_i =
cost_under_current_policy_i - cost_under_alternative_driver_i
```

- 시나리오별 범위
- 프로젝트 순위 변화
- 고객·서비스 마진 변화
- 손실전환 프로젝트
- 의사결정 민감도

## 8. Cross-cycle·Cross-domain

| Trigger | 연결 |
|---|---|
| 진행률·WIP | Revenue Pack |
| 미청구·변경계약 | Revenue Pack |
| 손실 프로젝트 현금소요 | Cash Pack |
| 외주 상시 지휘·통제 | 노무·세무 |
| 관계회사 cross-charge | 세무·법 |
| 자본화한 개발활동 | 세무 |
| 직원별 시간 | 개인정보·노무 |

## 9. 출력 예시 구조

```text
Issue: 공통 개발인력 원가의 프로젝트 마진 왜곡
Population: 공통인력 원가 X, 24개 프로젝트, 시간 Coverage 91%
Observed: 매출기준 배부와 작업시간 분포가 크게 불일치
Hypotheses: 정책상 단순화 / 시간기록 누락 / 실제 cross-support / 배부왜곡
Counter evidence: 3개 프로젝트는 ticket 기준도 높은 지원사용 확인
Accounting impact: 산술·정책 위반 확정분 A
Management impact: 시간기준 재배부 시 B 프로젝트 원가 +C, A 프로젝트 -D
Limit: 시간 Coverage 9% 누락
Next: 누락시간·정책 승인·driver 적합성 전문가 검토
Authority: Boundary
```

## 10. 합성 사례

1. 정상 직접원가 귀속
2. 동일 외주 invoice 중복
3. 프로젝트 없는 orphan cost
4. 직원시간이 다른 프로젝트로 이동
5. 합리적인 매출기준 배부 정상사례
6. 매출기준이 지원소비를 크게 왜곡
7. 실제시간 누락으로 시간기준도 왜곡
8. 유휴원가를 고마진 프로젝트에 배부
9. 비정상 재작업 원가
10. WIP roll-forward 불일치
11. ETC 반복 낙관편향
12. 계약원가자산 요건 충족
13. 이미 수행한 원가의 부적절한 자산화
14. 교육비 자산화
15. 부담계약 충당부채 누락
16. 변경계약 미승인 scope creep
17. 관계회사 cross-charge
18. 원가배부와 수익 cutoff가 함께 틀린 복합사례

## 11. Norm Card Seed

- `N-KR-1115-CONTRACT-COST`
- `N-KR-1115-PROGRESS`
- `N-KR-1002-INVENTORY-COST` 적용대상일 때
- `N-KR-1037-ONEROUS`
- `N-KR-1038-INTANGIBLE`
- `N-KR-1036-IMPAIRMENT`
- `N-COMPANY-COST-POLICY`
- `N-MGMT-ALLOCATION-CAUSALITY`

`N-MGMT-*`는 K-IFRS Norm이 아니며 관리진단 권한만 가진다.

## 12. 공식 출처

- K-IFRS 시행 중 목록: `https://www.kasb.or.kr/front/board/ingAccountingList.do`
- IFRS 15: `https://www.ifrs.org/issued-standards/list-of-standards/ifrs-15-revenue-from-contracts-with-customers/`
- IAS 2: `https://www.ifrs.org/issued-standards/list-of-standards/ias-2-inventories/`
- IAS 37: `https://www.ifrs.org/issued-standards/list-of-standards/ias-37-provisions-contingent-liabilities-and-contingent-assets/`
- IAS 38 검색·공식 자료: `https://www.ifrs.org/issued-standards/search-results/?lang=en`
- IFRS 15 계약이행원가 agenda decision: `https://www.ifrs.org/content/dam/ifrs/supporting-implementation/agenda-decisions/2019/ifrs-15-costs-to-fulfil-a-contract-june-2019.pdf`
- IFRS 15 교육원가 agenda decision: `https://www.ifrs.org/content/dam/ifrs/supporting-implementation/agenda-decisions/2020/ifrs15-training-costs-to-fulfil-a-contract-mar-20.pdf`

## 13. Release Gate

- CA-01~CA-16 모두 D1~D12 연결
- GL 원가와 프로젝트 원가 전체 대사
- 회계오류와 관리왜곡 금액 분리
- current·alternate driver의 numerator·denominator 재수행
- 미배부·중복·유휴·비정상 원가 별도 표시
- WIP·계약원가·부담계약 Norm 연결
- timesheet 누락 시 확정 재배부 금지
- 정상·오류·경계·반증·복합사례 통과
- 회계사와 관리회계 전문가 검토 전 `Boundary`

## 14. HANDOFF

```text
원가배분 문제를 마진 outlier 하나로 판단하지 않는다.
GL-활동-pool-driver-project-WIP-수익의 lineage를 대사하고,
회계오류와 관리상 인과성 왜곡을 분리해 재배부·민감도·반증을 제시한다.
```
