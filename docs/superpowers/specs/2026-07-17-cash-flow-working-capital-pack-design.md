# Cash Flow & Working Capital Cycle Pack 설계

- Pack ID: `kr_b2b.cash_working_capital.v1`
- 상위 Matrix: `2026-07-17-accounting-review-coverage-matrix-design.md`
- 기준: K-IFRS 제1007호·제1109호·제1107호 우선, 경영 유동성 진단 별도
- 권한 상한: 전문가 승격 전 `Boundary`

## 0. 목적

현금흐름표 분류 오류, 현금·채권·채무의 회계오류, 손익과 현금의 불일치, 운전자본과 유동성 위험을 분리해 검토한다.

다음 세 질문에 각각 답한다.

1. 현금과 현금흐름표가 회계적으로 맞는가
2. 영업이익이 왜 현금으로 전환되지 않는가
3. 현재 현금구조가 경영적으로 지속 가능한가

세 질문을 하나의 “현금흐름이 나쁨”으로 합치지 않는다.

## 1. 모집단과 데이터 역할

| Role | 예시 |
|---|---|
| bank | 은행계좌, 거래, 잔액, 확인서 |
| cash_gl | 현금·예금·제한현금 GL |
| cashflow | 현금흐름표 line·분류·조정 |
| ar | 청구·채권·수금·credit note |
| ap | 매입·채무·지급 |
| debt | 차입·이자·상환·covenant |
| factoring | 채권양도·상환청구권·수수료 |
| supplier_finance | 금융기관·공급자·지급조건 |
| forecast | 13주 또는 월별 현금예측 |
| payroll_tax | 급여·원천세·부가세·법인세 지급 |
| contract | 지급조건·선수금·환불 |

은행 원천과 GL이 없으면 현금 실재성·완전성은 Not Assessable이다.

## 2. Issue Family

| ID | Issue | 회계·진단 구분 | 핵심 절차 | 대표 Output |
|---|---|---|---|---|
| CF-01 | 은행·GL 대사차이 | 회계 | bank reconciliation | 미기록·미결 차이 |
| CF-02 | 현금·현금성자산·제한현금 분류 | 회계 | 조건·만기·위험 검사 | 재분류 후보 |
| CF-03 | 영업·투자·재무 분류 오류 | 회계 | transaction classification | 현금흐름표 조정 |
| CF-04 | 비현금거래 혼입·누락 | 회계 | GL-cash trace | 비현금 조정 |
| CF-05 | 재무활동 부채 roll-forward 오류 | 회계 | debt bridge | 설명되지 않은 변동 |
| CF-06 | 공급자금융·reverse factoring | 회계·진단 | 계약·지급조건·공시 검사 | 분류·집중위험 |
| CF-07 | 매출채권 회수악화 | 회계·진단 | aging·cohort·subsequent cash | ECL·현금전환 |
| CF-08 | 매입채무 지급지연 | 회계·진단 | DPO·overdue·terms | 현금보전·체납위험 |
| CF-09 | 손익-영업현금흐름 괴리 | 진단 | EBITDA/operating profit bridge | 원인기여도 |
| CF-10 | 고객·공급자 집중 | 진단 | concentration·scenario | 유동성 노출 |
| CF-11 | 팩토링·채권양도 | 회계·진단 | derecognition·recourse 검사 | 차입·매각 후보 |
| CF-12 | covenant·차입 유동성 | 회계·진단 | covenant recompute | 위반·분류 Trigger |
| CF-13 | 세금·급여·필수지급 체납 | 회계·진단 | due-payment matching | 미지급·법적 Trigger |
| CF-14 | 기간말 window dressing | 통제·진단 | pre/post cash pattern | 일시적 개선 후보 |
| CF-15 | 현금예측 편향·runway | 진단 | forecast backtest·scenario | 자금부족 시점 |
| CF-16 | 계속기업 전조 | 전문가 Trigger | liquidity stress synthesis | 추가 평가 Packet |

## 3. 결정적 절차

### P-CF-01 Bank reconciliation

```text
bank_balance
+ deposits_in_transit
- outstanding_payments
+/- verified_reconciling_items
= adjusted_bank_balance

adjusted_bank_balance - cash_gl_balance = unexplained_difference
```

- 계좌·통화·법인별로 수행한다.
- 장기 미결항목과 반복 carry-forward를 분리한다.
- 내부계좌간 이체는 양쪽 계좌와 날짜를 매칭한다.
- bank source 누락을 GL 잔액으로 보완했다고 간주하지 않는다.

### P-CF-02 Cash definition and restriction

검토:

- 요구불예금 여부
- 취득 시점 만기
- 알려진 금액으로 전환 가능성
- 가치변동 위험
- 인출 제한·담보·escrow
- overdraft 조건과 cash management

분류 결론은 계약·은행조건 Evidence 없이는 Boundary다.

### P-CF-03 Cash flow classification

각 cash transaction에:

- 경제적 사건
- 연결된 자산·부채·수익·비용
- 영업·투자·재무 후보
- 정책 선택·시행기준
- non-cash 여부

를 부여한다.

현금 계정 상대계정만으로 분류하지 않고 원거래와 연결한다.

### P-CF-04 Financing liability bridge

```text
opening_financing_liability
+ cash_proceeds
- cash_repayments
+/- noncash_changes
+/- fx_changes
+/- fair_value_or_other
= closing_financing_liability
```

잔차는 분류누락, 원장누락, 연결범위, 외환, 계약변경 가설로 분리한다.

### P-CF-05 Direct cash map

- 고객수금
- 공급자지급
- 직원지급
- 세금지급
- 이자·차입·투자

을 bank transaction에서 counterparty·invoice·payroll·tax ID로 연결한다. 미매칭률을 Coverage로 표시한다.

### P-CF-06 Profit-to-cash bridge

```text
operating_result
+ noncash_expense
- noncash_income
+/- working_capital_changes
+/- classified_operating_adjustments
= operating_cash_flow_candidate
```

다음 기여도를 별도 계산한다.

- AR
- contract asset/liability
- AP
- payroll·tax liabilities
- provisions
- deferred items
- other working capital

잔차는 `unexplained_bridge`로 남긴다.

### P-CF-07 AR aging and cohort

- invoice due date 기준 aging
- 고객·계약·상품·영업담당자별 분포
- 청구월 cohort의 30/60/90/180일 수금
- 후속수금
- credit note·dispute·write-off
- 신규·기존 고객 분리

단순 평균 DSO만으로 결론을 내리지 않는다.

### P-CF-08 AP aging and stretch

- 계약 지급조건 대비 실제 지급
- overdue 금액과 기간
- 기간말 후 집중지급
- 동일 공급자의 신규조건
- 분쟁·품질문제
- supplier finance 참여

정상 협상에 의한 조건개선과 자금부족에 의한 체납을 구별한다.

### P-CF-09 Supplier finance screen

Signal:

- 지급기한 급증
- 금융기관으로 지급상대 변경
- 공급자는 조기수금, 회사는 장기지급
- AP와 차입 사이 분류 불명확
- 현금흐름 분류 변경
- 프로그램 집중도

계약과 공식 K-IFRS 시행본 검토 없이 분류를 확정하지 않는다.

### P-CF-10 Factoring and receivable transfer

검토:

- 현금 수취
- 상환청구권
- 신용위험·연체위험 보유
- servicing
- repurchase
- 수수료·이자
- 장부상 제거

매출채권 매각과 담보차입 가설을 구별한다.

### P-CF-11 Concentration stress

시나리오:

- Top 고객 수금 지연
- Top 공급자 선지급 요구
- 신용한도 축소
- 환불·SLA credit
- 프로젝트 손실

현금 runway와 covenant headroom에 연결한다.

### P-CF-12 Forecast backtest

- 과거 forecast와 실제를 horizon별 비교
- 수금·매출·지급·채용 가정별 오차
- 낙관 편향과 반복 roll-forward
- downside scenario

예측 오차를 회계오류로 표현하지 않는다.

### P-CF-13 Period-end window

기간 전후:

- 관계회사 임시입금
- 다음 기간 즉시 반환
- 공급자 지급 연기
- 팩토링 집중
- 일회성 선수금
- 미지급세금·급여 증가

를 연결한다. 정상 계절성·계약 milestone을 반대가설로 둔다.

## 4. 회계와 경영진단 분리

| 관찰 | 회계 가능성 | 경영 가능성 |
|---|---|---|
| DSO 상승 | ECL·채권평가 | 영업품질·수금통제 |
| AP 증가 | 부채 완전성·분류 | 공급자 의존·지급지연 |
| 선불수금 | 계약부채 | 자금조달 효과 |
| 팩토링 | 제거·차입 분류 | 구조적 현금부족 |
| 제한현금 | 현금 분류·공시 | 사용가능 유동성 부족 |
| OCF 악화 | 분류·누락 검토 | 성장자금·운전자본 문제 |

## 5. 가설과 반증

### OCF 악화

가설:

- 매출채권 회수악화
- 성장으로 인한 정상 운전자본 투자
- 조기 매출인식
- 공급자 선지급
- 일회성 세금·보너스
- 현금흐름 분류 오류

구별:

- cohort
- 계약·청구·수금
- 후속기간
- 사업량
- 분류 재수행

### AP 증가

가설:

- 구매량 증가
- 협상된 지급조건 연장
- 지급능력 악화
- 공급자분쟁
- supplier finance
- 부채 누락 정정

### 기간말 현금증가

가설:

- 정상 milestone 수금
- 선수금
- 관계회사 일시자금
- 팩토링
- 지급연기
- 계좌간 미매칭

## 6. 정량화

### Bridge contribution

각 원인의 현금영향을 더해 총 OCF 변화와 대사한다.

### Collection exposure

- overdue principal
- expected collection scenarios
- customer concentration
- credit notes·disputes
- ECL input candidate

### Liquidity

- unrestricted cash
- committed undrawn facilities
- mandatory outflows
- scenario inflows
- covenant headroom
- runway date

현금예측은 가정 기반이며 재무제표 확정금액과 구분한다.

## 7. Cross-domain Trigger

| 사실 | Trigger |
|---|---|
| 원천세·부가세 체납 | 세무 |
| 급여·퇴직금 지급지연 | 노무 |
| covenant 위반 | 법·회계 |
| 금융계약 분류 불명확 | 법 |
| 공급자금융 약정 | 법·공시 |
| 관계회사 임시자금 | 세무·법 |

## 8. 출력 예시 구조

```text
Issue: 이익 증가에도 영업현금흐름 악화
Population: 고객청구 1,284건, 수금 matching 96%
Observed: AR 증가 X, 계약자산 증가 Y, AP 증가 Z
Bridge: AR·계약자산이 총 악화의 74% 설명, 잔차 A
Hypotheses: 회수악화 / 성장투자 / 조기인식 / mapping 누락
Counter evidence: 신규고객 성장분 B, 후속수금 C
Accounting: ECL·수익 cutoff 별도 검토
Management: Top 3 고객 지연 시 13주 내 최소현금 D
Authority: Boundary
```

## 9. 합성 사례

1. 정상 성장으로 AR과 OCF가 함께 악화
2. 조기 매출인식으로 AR 증가
3. 고객분쟁으로 장기연체
4. ECL 누락
5. 정상 지급조건 연장
6. 자금부족으로 AP 체납
7. 공급자금융 분류·공시 문제
8. 제한현금을 가용현금으로 포함
9. 팩토링을 매각으로 잘못 처리
10. 비현금 리스·차입변동을 현금흐름에 포함
11. 기간말 관계회사 입금·다음 기간 반환
12. 세금·급여 지급 지연
13. 정상 milestone 선수금
14. covenant 경계값
15. 현금예측의 반복 낙관편향
16. 여러 원인이 같은 OCF 하락을 만드는 복합사례

## 10. Norm Card Seed

- `N-KR-1007-CASH-DEFINITION`
- `N-KR-1007-CLASSIFICATION`
- `N-KR-1007-NONCASH`
- `N-KR-1007-FINANCING-RECONCILIATION`
- `N-KR-1007-SUPPLIER-FINANCE`
- `N-KR-1109-ECL`
- `N-KR-1109-DERECOGNITION`
- `N-KR-1107-DISCLOSURE`
- `N-AUDIT-GOING-CONCERN`

K-IFRS 시행본과 조기적용 여부를 Run별로 확인한다. IFRS 18과 IAS 7 관련 개정은 시행시점에 따라 별도 Norm Release로 관리한다.

## 11. 공식 출처

- K-IFRS 시행 중 목록: `https://www.kasb.or.kr/front/board/ingAccountingList.do`
- KASB 개정 연혁: `https://www.kasb.or.kr/front/board/List2006.do`
- IAS 7: `https://www.ifrs.org/issued-standards/list-of-standards/ias-7-statement-of-cash-flows.html`
- IAS 7 지원자료: `https://www.ifrs.org/supporting-implementation/supporting-materials-by-ifrs-standards/ias-7/`
- IFRS 9: `https://www.ifrs.org/issued-standards/list-of-standards/ifrs-9-financial-instruments/`
- IFRS 18: `https://www.ifrs.org/issued-standards/list-of-standards/ifrs-18-presentation-and-disclosure-in-financial-statements/`
- ISA 570 Revised 2024: `https://www.iaasb.org/publications/isa-570-revised-2024-going-concern`

ISA 570 Revised 2024는 2026-12-15 이후 시작 기간에 효력이 있으므로 현재 Run에 무조건 적용하지 않는다.

## 12. Release Gate

- CF-01~CF-16 모두 D1~D12 연결
- bank-GL 대사와 cash source Coverage
- 회계분류와 경영유동성 표현 분리
- 평균비율뿐 아니라 cohort·분포·잔차 제공
- OCF bridge가 총변화와 대사
- 제한현금·팩토링·공급자금융의 계약 Evidence
- 계속기업은 전문가 Trigger이며 자동 결론 금지
- 정상·오류·경계·반증·복합사례 통과
- 전문가 검토 전 `Boundary`

## 13. HANDOFF

```text
현금흐름 문제를 하나의 비율로 판단하지 않는다.
현금·현금흐름표 회계오류, 운전자본 원인, 유동성 위험을 분리하고
bank-GL 대사, cohort, bridge, 계약검토, stress scenario로 연결한다.
```
