# B2B 서비스업 회계 자동검토 Coverage Matrix 설계

- 상태: 사용자 승인 후 작성된 검토용 콘텐츠 설계
- 기준일: 2026-07-17
- 최초 적용대상: 한국 B2B 서비스업, K-IFRS 우선
- 제품 수준: 시니어 회계사와 일부 매니저급 1차 검토 초안
- 지식 권한: 이 문서만으로는 `machine_draft`; 공식 원문 연결·합성검증·전문가 승격 전 `Full` 금지

## 0. 목적

이 문서는 회계 검토를 몇 개의 비율과 이상신호로 축소하지 않도록 전체 검토공간을 고정한다. 실제 내용은 다음 네 Pack 설계서가 담당한다.

1. `2026-07-17-accounting-core-journal-integrity-pack-design.md`
2. `2026-07-17-contract-revenue-pack-design.md`
3. `2026-07-17-cash-flow-working-capital-pack-design.md`
4. `2026-07-17-project-cost-allocation-pack-design.md`

이 문서와 네 Pack 설계서는 다음 상위 설계를 구현하기 위한 콘텐츠 명세다.

- `2026-07-17-senior-accountant-review-expansion-design.md`
- `2026-07-17-professional-reasoning-knowledge-foundry-design.md`

현재 플러그인 코드는 이 문서를 이유로 수정하지 않는다. 구현은 별도 계획과 승인을 거친다.

## 1. 해결하려는 얕음

금지되는 분석 패턴:

```text
매출 급증 -> 매출 이상 가능성
DSO 증가 -> 현금흐름 악화
프로젝트 마진 하락 -> 원가배분 문제 가능성
```

요구되는 분석 패턴:

```text
모집단·Coverage
-> 계정·주장
-> 정상 기대관계
-> 복수 가설
-> 규범·예외
-> 구별 절차
-> 지지·반대 증거
-> 오류금액·현금·운영 영향
-> 회계처리·추가절차
-> 권한·한계
```

Signal 하나는 Issue를 확정하지 못한다. 같은 Signal을 만드는 오류, 정상 사유, 데이터 오류를 분리해야 한다.

## 2. 기준 체계와 버전

### 2.1 최초 규범 Overlay

- 관할: 대한민국
- 재무보고 기준: 한국채택국제회계기준
- 기준시점: 분석 대상 보고기간에 시행 중인 K-IFRS
- 업종: B2B 소프트웨어·클라우드·구축·교육·운영지원 등 서비스업
- 관리회계: 회사 정책과 인과관계 기반 진단을 별도 표시

한국회계기준원은 K-IFRS가 IFRS에 기초하지만 제·개정 시점 차이로 내용이 일치하지 않을 수 있음을 명시한다. 따라서 IFRS 원문만 보고 K-IFRS 적용결론을 자동 확정하지 않는다.

### 2.2 Norm Resolver

각 분석 Run은 다음을 고정한다.

- `reporting_framework`
- `jurisdiction`
- `reporting_period_start`
- `reporting_period_end`
- `early_adoption_flags`
- `company_accounting_policy_version`
- `norm_release_id`

Norm Card는 다음을 가져야 한다.

- 기준서·해석서 ID
- 적용 문단 ref
- K-IFRS 채택·시행 상태
- 시행일
- 조기적용 여부
- 적용범위
- 요건·예외의 구조화된 요약
- 공식 URL
- 라이선스 상태
- 전문가 검토상태

### 2.3 라이선스 경계

- IFRS Foundation은 제품·서비스 통합 등 일부 이용에 별도 라이선스가 필요할 수 있음을 안내한다.
- 제품 저장소에 IFRS·K-IFRS 전문을 무단 복제하지 않는다.
- 초기 Pack은 기준서 ID, 문단 ref, 자체 작성한 짧은 요건 요약, 공식 링크를 저장한다.
- 실제 제품 배포 전 법적·라이선스 검토를 `expert_review_required`로 둔다.
- 라이선스가 확보되기 전 원문 검색 기능이나 장문 인용 기능을 제공하지 않는다.

## 3. 회계 주장과 진단 축

### 3.1 거래·사건 주장

- 발생
- 완전성
- 정확성
- 기간귀속
- 분류
- 표시

### 3.2 잔액 주장

- 실재성
- 권리와 의무
- 완전성
- 정확성·평가·배분
- 분류
- 표시

### 3.3 경영진단 축

재무제표 오류와 별개로 다음을 평가한다.

- 수익성의 질
- 현금전환
- 운전자본 부담
- 고객·공급자 집중
- 프로젝트 경제성
- 원가 인과관계
- 통제 우회
- 유동성·계속기업 전조

경영진단 결과를 K-IFRS 위반으로 표현하지 않는다.

## 4. 전체 Coverage Matrix

| Pack | Issue 영역 | 주요 계정 | 핵심 주장 | 주요 Output |
|---|---|---|---|---|
| Accounting Core | 원장 무결성·대사 | 전 계정 | 완전성·정확성·기간·분류 | 대사차이, 비정상분개, 조정후보 |
| Contract & Revenue | 계약·이행·수익 | 매출·채권·계약자산·계약부채 | 발생·정확성·기간·평가 | 수익시기·오류금액·분개후보 |
| Cash & Working Capital | 현금·채권·채무·유동성 | 현금·채권·채무·차입 | 실재·완전성·분류·평가 | 현금흐름분류, bridge, 유동성 이슈 |
| Project Cost & Allocation | 프로젝트 원가·WIP | 원가·재공·계약원가·충당부채 | 완전성·평가·배분·기간 | 재배부, 마진정정, 손실계약 후보 |

## 5. Cross-cycle 연결

### 5.1 계약에서 현금까지

```text
계약
-> 수행의무
-> 서비스 이행
-> 수익
-> 청구
-> 매출채권·계약자산
-> 수금
-> 현금
```

각 단계의 금액과 날짜가 다음 단계와 대사돼야 한다.

### 5.2 계약에서 원가까지

```text
계약 약속
-> 프로젝트·서비스 활동
-> 인력·외주·인프라 사용
-> 직접·간접원가
-> 배부
-> 프로젝트 마진
-> 손실계약·계약원가 판단
```

### 5.3 손익에서 현금까지

```text
영업손익
+ 비현금항목
+ 운전자본 변동
+ 기타 영업조정
= 영업현금흐름
```

잔차는 설명되지 않은 채 최종 보고서에 숨기지 않는다.

## 6. 데이터 Capability

### 6.1 필수 공통 데이터

- 계정과목표
- 분개 헤더·라인
- 전기일·증빙일·입력일·승인일
- 사용자·역할·승인자
- 시산표
- 전기말 잔액
- 고객·공급자·프로젝트 master
- 회계기간·마감일
- 통화와 환율

### 6.2 Cycle 데이터

#### 계약·매출

- 계약·변경계약
- 견적·주문·청구서
- 서비스 시작·개통·검수·접속 로그
- 가격표·독립판매가격
- CRM·이메일 약속
- 수익 스케줄
- 매출채권·계약자산·계약부채

#### 현금·운전자본

- 은행거래·은행잔액
- 은행조정표
- 매출채권·매입채무 open item
- 수금·지급 matching
- 차입·팩토링·공급자금융 계약
- covenant와 현금예측

#### 프로젝트 원가

- 프로젝트·작업·원가센터
- 근로시간표
- 급여·외주·인프라 사용량
- 원가 pool·배부기준·배부율
- 예산·진척률·예정원가
- WIP·계약원가자산

### 6.3 Capability 상태

- `complete`: 모집단과 필수 Evidence role이 모두 존재
- `partial`: 일부 구별 절차 가능
- `missing`: 핵심 절차 실행 불가
- `unreliable`: 대사 또는 lineage 실패

Capability가 부족하면 확정결론 대신 필요한 자료와 영향받는 주장 Coverage를 출력한다.

## 7. 중요성·우선순위

### 7.1 중요성 분리

- `accounting_materiality_input`: 고객 또는 회계사가 입력한 회계 중요성
- `diagnostic_impact`: 경영영향 우선순위
- `control_severity`: 통제우회·부정 위험
- `coverage_priority`: 미검토 중요 계정 우선순위

시스템은 임의의 감사 중요성을 발명하지 않는다. 중요성이 없으면 금액 순위와 질적 위험을 제공하지만 의무검사를 생략하지 않는다.

### 7.2 질적 중요성

금액이 작아도 다음은 우선한다.

- 경영진 override
- 규제·세금·법적 영향
- covenant 위반
- 반복 오류
- 핵심 KPI 조작 가능성
- 관계회사·임직원 관련
- 개인정보·노무 Trigger
- 손실 은폐 또는 계속기업 전조

## 8. Tier와 Pack 실행

### Tier 0

- 원장·시산표·보조원장 대사
- 차변·대변·기초·기말 무결성
- 현금·은행 대사
- 중복·누락·기간오류
- 필수 Coverage

### Tier 1

- 전수 시계열·비율·aging·집중도
- 기간말·수동·희귀 분개
- 계약·이행·청구·수금 시간정렬
- 원가·배부·마진 분포

### Tier 2

- 선택된 Issue Family의 가설 구별 절차
- 규범 요건·예외
- 오류금액 재수행
- 반대 증거

### Tier 3

- Issue Evidence Packet 안에서만 전문 추론
- 복수 가설 비교
- 조건부 결론·질문·메모 초안

## 9. Issue Family 최소계약

모든 Issue Family는 다음 필드를 가진다.

- `issue_family_id`
- `cycle_id`
- `economic_event_types`
- `accounts`
- `assertions`
- `population_definition`
- `mandatory_data_roles`
- `optional_data_roles`
- `expectation_card_refs`
- `norm_card_refs`
- `procedure_card_refs`
- `counter_hypothesis_refs`
- `calculation_refs`
- `cross_domain_trigger_refs`
- `required_test_case_types`
- `authority_ceiling`
- `not_assessable_conditions`

상위 Knowledge Foundry의 D1~D12가 모두 연결되지 않으면 Pack을 활성화하지 않는다.

## 10. 공통 검토 절차

### 10.1 Reconcile

- 두 모집단의 건수·금액·키를 대사한다.
- 일치·한쪽만 존재·금액차이·기간차이를 분리한다.
- 순액 일치만으로 개별 오류를 상계하지 않는다.

### 10.2 Roll-forward

```text
기초 + 증가 - 감소 +/- 기타 = 기말
```

- 계정별·고객별·프로젝트별로 계산한다.
- 잔차와 원천 거래를 연결한다.

### 10.3 Temporal alignment

- 계약일
- 이행일
- 검수일
- 청구일
- 전기일
- 수금일

날짜 하나를 “진실”로 선택하지 않고 사건별 의미와 우선순위를 적용한다.

### 10.4 Cohort

- 청구월·계약월·프로젝트 시작월 cohort
- 후속 수금·취소·원가 발생을 추적한다.
- 평균만 사용하지 않고 분포와 tail을 보존한다.

### 10.5 Reperformance

- 수익 스케줄
- 현금흐름 분류
- 기대신용손실 입력
- 배부율·원가배부
- WIP·진척률

입력과 계산식을 Evidence로 남긴다.

### 10.6 Counterfactual

- 정상적 대안 가설별 예상 증거를 만든다.
- 실제 증거와 비교한다.
- 대안 배부기준·수익시기·회수시나리오 민감도를 계산한다.

## 11. 공통 Issue Evidence Packet

- 모집단과 Coverage
- 관련 계정·주장
- 관찰 Fact
- 정상 기대관계
- Signal
- 오류·부정·정상·데이터오류 가설
- 실행한 구별 절차
- 지지 증거
- 반대 증거
- 적용 Norm과 시행상태
- 확정금액·범위금액·계산불가
- 회계처리·조정 후보
- 현금·운영 영향
- Cross-domain Trigger
- 미해결 질문
- `Full / Boundary / Not Assessable`
- 사용한 Knowledge Release

## 12. Cross-domain Trigger

| 사실 | 회계 | 추가 도메인 |
|---|---|---|
| 계약서 밖 무상지원 약속 | 거래가격·수행의무 | 법 |
| 외주 인력이 상시 지휘·통제됨 | 원가·미지급비용 | 노무·세무 |
| 장기 미수·특수관계자 거래 | 손상·공시 | 세무·법 |
| 세금·급여 지급 지연 | 부채 완전성·현금 | 세무·노무 |
| 공급자 지급구조 급변 | 현금흐름·채무 분류 | 법 |
| 프로젝트 간 원가 이전 | 원가·마진 | 세무 |

전달하는 것은 공통 Fact와 질문이며 다른 도메인의 결론이 아니다.

## 13. 합성 POC Coverage

각 Issue Family는 다음 사례를 가진다.

- 정상
- 명백한 오류
- 경계값
- 반대 증거
- 데이터 누락
- 매핑 오류
- 복합원인
- 동일 Signal·상이한 원인
- Cross-cycle 파급
- Cross-domain 충돌

Oracle은 다음을 검증한다.

- 찾아야 할 Issue
- 찾으면 안 되는 Issue
- 필요한 Evidence role
- 필요한 반대검사
- 오류금액 또는 범위
- 허용 가능한 권한
- 필요한 추가자료
- 금지된 전문 결론

## 14. 공식 출처 Registry

초기 설계 근거:

- 한국회계기준원 시행 중 K-IFRS 목록: `https://www.kasb.or.kr/front/board/ingAccountingList.do`
- 한국회계기준원 K-IFRS 연혁: `https://www.kasb.or.kr/front/board/List2006.do`
- IFRS Standards Navigator와 라이선스 안내: `https://www.ifrs.org/issued-standards/list-of-standards/`
- IFRS 15: `https://www.ifrs.org/issued-standards/list-of-standards/ifrs-15-revenue-from-contracts-with-customers/`
- IAS 7: `https://www.ifrs.org/issued-standards/list-of-standards/ias-7-statement-of-cash-flows.html`
- IFRS 9: `https://www.ifrs.org/issued-standards/list-of-standards/ifrs-9-financial-instruments/`
- IAS 2: `https://www.ifrs.org/issued-standards/list-of-standards/ias-2-inventories/`
- IAS 37: `https://www.ifrs.org/issued-standards/list-of-standards/ias-37-provisions-contingent-liabilities-and-contingent-assets/`
- IAASB 2021 Handbook: `https://www.iaasb.org/publications/2021-handbook-international-quality-control-auditing-review-other-assurance-and-related-services`

Audit Method는 위험평가와 증거 관점을 참고하는 것이며, 이 제품이 감사를 수행하거나 감사의견을 제시한다는 의미가 아니다.

## 15. Release Gate

네 Pack 모두 다음을 충족하기 전 “시니어 회계사급 세 Cycle”로 표시하지 않는다.

1. Issue Family 목록과 Coverage Matrix가 완전하다.
2. D1~D12가 모두 연결된다.
3. 공식 출처·시행일·관할이 연결된다.
4. 결정적 절차와 계산이 구현된다.
5. 정상·오류·경계·반증·복합사례를 통과한다.
6. 누락된 중요 Issue가 Coverage Gap으로 차단된다.
7. 회계오류와 경영진단 표현이 분리된다.
8. 숨겨진 Oracle 평가를 통과한다.
9. 회계사가 Issue Family 단위로 검토한다.
10. Knowledge Foundry Release로 승인된다.

## 16. HANDOFF

```text
HANDOFF

이 문서는 회계 자동검토 전체 Coverage를 고정하는 상위 Matrix다.
실제 콘텐츠는 Accounting Core, Revenue, Cash, Cost Allocation 네 Pack 문서를 따른다.

핵심:
- K-IFRS 시행 버전을 Run별로 고정한다.
- IFRS 전문을 무단 내장하지 않는다.
- 회계오류와 관리진단을 분리한다.
- Signal만으로 Issue를 확정하지 않는다.
- 네 Pack 모두 D1~D12를 충족해야 시니어급 범위를 주장한다.
- POC는 모든 Issue Family에 정상·오류·경계·반증·복합사례를 가진다.
```
