# Contract & Revenue Cycle Pack 설계

- Pack ID: `kr_b2b.contract_revenue.v1`
- 상위 Matrix: `2026-07-17-accounting-review-coverage-matrix-design.md`
- 기준: K-IFRS 제1115호 우선, 관련 제1109호·제1037호 등 Overlay
- 권한 상한: 전문가 승격 전 `Boundary`

## 0. 목적

계약 체결액, 청구액, 현금수금, 회계상 수익을 분리하고 계약의 권리·의무와 실제 이행증거를 연결한다. 기간말 매출 급증 하나가 아니라 계약 모집단 전체에서 인식·측정·기간·분류 오류를 찾는다.

## 1. Economic Event Graph

```text
proposal
-> approval
-> contract
-> modification / side agreement
-> promise
-> performance obligation candidate
-> service activation / delivery / acceptance
-> invoice
-> receivable / contract asset / contract liability
-> collection / refund / credit
```

각 노드는 날짜, 금액, 당사자, 문서, 시스템 이벤트, 취소상태를 가진다.

## 2. 데이터 역할

| Role | 예시 |
|---|---|
| contract | 본계약, 부속합의, 변경계약, 갱신 |
| promise | 라이선스, 구축, 교육, 운영지원, 유지보수 |
| pricing | 정가표, 견적, 할인승인, 독립판매가격 |
| fulfilment | 개통, 접속, 배포, 작업완료, 검수 |
| billing | 청구서, 세금계산서, credit note |
| accounting | 수익분개, AR, 계약자산·부채, 수익스케줄 |
| cash | 입금, 환불, 상계 |
| side_evidence | CRM, 이메일, 메신저, 영업승인 |
| cost | 판매수수료, 구축원가, 계약이행원가 |

계약서 텍스트만 있고 이행·청구·원장 데이터가 없으면 수익 인식 결론을 Full로 내리지 않는다.

## 3. Issue Family

| ID | Issue | 주장 | 핵심 절차 | 대표 Output |
|---|---|---|---|---|
| RV-01 | 계약 식별·회수가능성 | 발생·권리 | 계약요건·승인·회수증거 | 계약 성립 경계 |
| RV-02 | 계약 결합·변경 누락 | 정확성·기간 | 고객·시점·가격·변경 연결 | 재평가 대상 |
| RV-03 | 약속·수행의무 식별 | 분류·정확성 | promise graph·별도효익 검사 | 수행의무 후보 |
| RV-04 | 거래가격·변동대가 | 정확성·평가 | price waterfall·constraint | 가격 조정 |
| RV-05 | 독립판매가격 배분 | 배분·정확성 | SSP 근거·상대배분 재수행 | 배분차이 |
| RV-06 | 기간·시점 인식 | 기간·발생 | 통제이전·기간요건 검사 | 인식방식 후보 |
| RV-07 | 진행률 측정 | 정확성·기간 | input/output 재수행 | 누적수익 차이 |
| RV-08 | 검수·개통·cutoff | 발생·기간 | 계약-로그-검수-분개 정렬 | 조기·지연수익 |
| RV-09 | 본인·대리인 총액·순액 | 분류·정확성 | 통제·재고·가격·책임 검사 | gross/net 후보 |
| RV-10 | 라이선스·접근권·사용권 | 기간·분류 | 권리성격·업데이트·지원 연결 | 인식패턴 후보 |
| RV-11 | 계약잔액 분류 | 분류·완전성 | 이행·청구·지급 순서 재수행 | AR/CA/CL 재분류 |
| RV-12 | 유의적 금융요소 | 측정·분류 | 지급시점·상업적 이유·할인 | 금융효과 후보 |
| RV-13 | 환불·SLA credit·할인 | 완전성·평가 | 후속 credit·클레임·usage 검사 | 환불부채·가격조정 |
| RV-14 | 계약획득·이행원가 | 평가·분류 | 증분성·직접관련·회수성 검사 | 자산화·비용화 |
| RV-15 | 취소·side agreement | 발생·기간 | CRM·이메일·해지·후속행동 연결 | 계약조건 수정 |
| RV-16 | 채권·계약자산 손상 | 평가 | aging·회수·신용정보 | ECL 검토 후보 |

## 4. 전문 절차

### P-RV-01 Contract population reconciliation

- CRM won deal
- 서명계약
- 주문
- 청구
- 수익분개
- 수금

을 양방향 대사한다.

분류:

- 계약 있으나 수익 없음
- 수익 있으나 계약 없음
- 청구 있으나 이행 없음
- 이행 있으나 청구 없음
- 수금 있으나 계약·청구 없음

각 차이는 오류가 아니라 후속 가설의 시작점이다.

### P-RV-02 Contract term extraction

구조화 항목:

- 당사자와 승인
- 계약기간
- 시작·갱신·해지
- 약속된 재화·용역
- 가격·할인·변동대가
- 지급시기
- 검수·환불·SLA
- 지식재산권
- 고객 의존성·맞춤화
- side letter 존재

추출값은 문서 위치와 함께 사람이 검토할 수 있어야 한다.

### P-RV-03 Promise and obligation graph

각 약속에 대해:

- 고객이 자체 또는 다른 자원과 함께 효익을 얻는가
- 다른 약속과 별도로 식별되는가
- 통합·수정·상호의존성이 큰가
- 회사가 별도 판매하는가
- 다른 공급자가 수행 가능한가

를 Evidence 질문으로 만든다. 모델이 답을 발명하지 않는다.

### P-RV-04 Price waterfall

```text
fixed consideration
+ probable variable consideration
- credits / rebates / refunds
+/- approved modifications
= constrained transaction price candidate
```

- 금액별 계약조항 ref
- 변동대가 시나리오와 확률
- 중요한 되돌림 위험
- 후속 실제 credit과 비교

를 보존한다.

### P-RV-05 SSP allocation

```text
allocated_price_i =
transaction_price * observable_or_estimated_ssp_i / total_ssp
```

- observable SSP
- adjusted market assessment
- expected cost plus margin
- residual 접근의 적용근거

를 구분한다. 단순 정가를 SSP로 가정하지 않는다.

### P-RV-06 Satisfaction pattern

각 수행의무에 대해:

- 기간에 걸친 충족 후보
- 한 시점 충족 후보
- 시작 전 준비활동
- 고객 검수의 실질
- stand-ready obligation
- 갱신·옵션의 별도 권리

를 분리한다.

### P-RV-07 Progress reperformance

Input method:

```text
eligible_cost_or_effort_to_date / expected_total_eligible_cost_or_effort
```

Output method:

- milestones
- units delivered
- elapsed time
- service events

비정상 낭비, 조달만 된 중요재화, 재작업, 선행원가를 분리한다. 진행률과 원가인식이 자동으로 동일하다고 가정하지 않는다.

### P-RV-08 Population cutoff

보고기간 전후 window에서:

- 계약일
- 개통·배포일
- 고객 사용일
- 검수일
- 청구일
- 전기일
- 수금일

을 전수 정렬한다.

대표적인 가설:

- 조기인식
- 이행로그 지연
- 검수는 형식적
- 무료 trial
- 청구 선행
- 수동 cutoff 조정
- 다음 기간 취소

### P-RV-09 Contract balance roll-forward

```text
opening contract asset
+ revenue before billing
- billing / reclassification
- impairment
= closing contract asset

opening contract liability
+ consideration before performance
- revenue recognised
+/- refund and modification
= closing contract liability
```

AR은 무조건 계약자산과 같지 않다. 무조건적 권리 여부를 검토한다.

### P-RV-10 Side agreement search

- 무료지원
- 추가 customization
- 환불 약속
- 비공식 검수조건
- 가격보전
- 취소 합의
- 성과보장

을 CRM·이메일·승인기록에서 찾아 계약과 연결한다. 검색 부재를 “side agreement 없음”의 확정증거로 사용하지 않는다.

### P-RV-11 Contract cost

구분:

- 계약을 얻기 위한 증분원가
- 계약 이행에 직접 관련된 원가
- 다른 기준서 적용대상
- 과거 수행의무 관련 원가
- 낭비·일반관리비
- 교육비

자산화 후보는 회수가능성과 상각패턴·손상까지 연결한다.

## 5. 핵심 가설·반증

### 매출 조기인식 후보

지지:

- 이행 전 전기
- 기간 후 최초 사용
- 기간 후 검수
- 다음 기간 credit·취소

반증:

- 고객이 이미 통제를 획득
- 검수조항이 형식적
- 로그 migration 지연
- 별도 증거로 기간 내 이행 확인

구별:

- 계약조항
- 고객 확인
- 시스템 audit log
- 배포·접속 기록
- 후속지원·환불

### 설치·교육 별도 수행의무 후보

지지:

- 별도 판매
- 독립 효익
- 타 공급자 수행 가능

반증:

- 고도의 통합
- 서비스 작동에 필수적이고 독립효익 없음
- 회사가 중요한 수정 서비스를 제공

### 현금수금이 수익을 정당화한다는 가설

반증:

- 선불은 계약부채일 수 있음
- 회수와 이행은 다른 사건
- 환불조건·취소권 존재

## 6. 오류금액과 분개후보

### 누적수익 차이

```text
candidate_misstatement =
recorded_cumulative_revenue - supportable_cumulative_revenue
```

### 계약잔액

- 과대수익: 매출 감소, 계약부채 또는 관련 잔액 증가 후보
- 과소수익: 계약부채 감소 또는 계약자산 증가 후보
- 청구권 무조건성에 따라 AR·계약자산 분류 후보

### 출력

- 단일 금액
- 시나리오별 범위
- 판단불가 금액
- 기간별 reversal schedule
- 세금효과는 별도 세무 Trigger

회계사가 승인하기 전 자동분개를 실행하지 않는다.

## 7. Cross-cycle·Cross-domain

| Trigger | 연결 |
|---|---|
| 미수 장기화 | Cash Pack·IFRS 9 |
| 계약원가자산 | Cost Pack |
| 손실 프로젝트 | Cost Pack·IAS 37 |
| 무상지원·책임 약속 | 법 |
| 판매수수료·외주인력 | 노무·세무 |
| 세금계산서 시기 차이 | 세무 |
| principal-agent | 법·세무 |

## 8. 출력 예시 구조

```text
Issue: 기간말 SaaS 수익 조기인식 후보
Population: 184건 / 420,000,000원 중 31%
Assertions: 발생, 기간귀속, 정확성
Observed: 7건은 다음 기간 최초 사용, 4건은 검수근거 누락
Hypotheses: 조기인식 / 로그지연 / 형식적 검수 / 자료누락
Counter evidence: 기간 내 배포로그 2건, 고객 이메일 승인 1건
Quantification: 확정 X원, 범위 Y~Z원, 판단불가 A원
Candidate treatment: 조건부 수익감소·계약부채 증가
Next procedures: 계약별 수행의무·검수조항·고객확인
Authority: Boundary
```

## 9. 합성 사례

1. 36개월 SaaS 선불계약의 정상 기간인식
2. 설치가 별도 수행의무인 계약
3. 설치가 통합활동인 반대사례
4. 12월 청구·1월 개통 조기인식
5. 12월 실제 개통·1월 로그 migration
6. 이메일 side agreement 무료지원
7. 변동대가와 SLA credit
8. 계약변경을 신규계약으로 잘못 처리
9. SSP 배분 오류
10. 계약자산과 AR 분류 오류
11. 다음 기간 취소·환불
12. 판매수수료 자산화·상각
13. 교육비 자산화 오류
14. 장기미수와 ECL 누락
15. 본인·대리인 gross/net 경계
16. 여러 오류가 한 계약에 함께 존재

각 사례는 계약 원문, 시스템 이벤트, 원장, Oracle을 분리한다.

## 10. Norm Card Seed

- `N-KR-1115-CONTRACT`
- `N-KR-1115-PO`
- `N-KR-1115-PRICE`
- `N-KR-1115-ALLOCATION`
- `N-KR-1115-SATISFACTION`
- `N-KR-1115-CONTRACT-BALANCE`
- `N-KR-1115-CONTRACT-COST`
- `N-KR-1109-ECL`
- `N-KR-1037-ONEROUS`
- `N-KR-1038-TRAINING`

각 Card는 K-IFRS 시행본 문단 ref를 별도로 확인해야 한다.

## 11. 공식 출처

- K-IFRS 시행 중 목록: `https://www.kasb.or.kr/front/board/ingAccountingList.do`
- IFRS 15 공식 페이지: `https://www.ifrs.org/issued-standards/list-of-standards/ifrs-15-revenue-from-contracts-with-customers/`
- IFRS 15 지원자료: `https://www.ifrs.org/supporting-implementation/supporting-materials-by-ifrs-standards/ifrs-15/`
- IFRS 9: `https://www.ifrs.org/issued-standards/list-of-standards/ifrs-9-financial-instruments/`
- IAS 37: `https://www.ifrs.org/issued-standards/list-of-standards/ias-37-provisions-contingent-liabilities-and-contingent-assets/`
- 계약이행 교육원가 agenda decision: `https://www.ifrs.org/content/dam/ifrs/supporting-implementation/agenda-decisions/2020/ifrs15-training-costs-to-fulfil-a-contract-mar-20.pdf`
- 계약이행원가 agenda decision: `https://www.ifrs.org/content/dam/ifrs/supporting-implementation/agenda-decisions/2019/ifrs-15-costs-to-fulfil-a-contract-june-2019.pdf`

## 12. Release Gate

- RV-01~RV-16 모두 D1~D12 충족
- 계약·수익·청구·수금 모집단 대사
- cutoff를 단일 최신일자로 검사하지 않고 전수 population 검사
- 수행의무·SSP·진행률에 필요한 Evidence role 명시
- 확정·범위·판단불가 금액 분리
- side agreement 검색 한계 표시
- 정상·오류·경계·반증·복합사례 통과
- 회계사 검토 전 `Boundary`

## 13. HANDOFF

```text
매출 Signal을 바로 회계오류로 쓰지 않는다.
계약-약속-이행-청구-수금-분개의 전체 사건그래프를 만들고,
복수 가설과 반대증거를 검토한 뒤 오류금액과 조건부 분개를 제시한다.
```
