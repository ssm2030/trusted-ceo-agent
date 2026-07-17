# B2B 서비스업 Accounting Norm & Procedure Seed Catalog

- 상태: 전문 콘텐츠 Suite의 필수 provisional 지식 초안
- 기준일: 2026-07-17
- 권한: `machine_draft`
- 적용: K-IFRS 시행본 원문·문단·전문가 검증 전 결론 확정 금지

## 0. 목적과 저작권 경계

이 문서는 Pack에 넣을 Norm·Method·Procedure Card의 실제 초기 내용을 제공한다. 단순 Card ID 목록이 아니다.

- 아래 내용은 공식 자료를 바탕으로 자체 요약한 설계 초안이다.
- 기준서 전문이나 장문을 제품에 복제하지 않는다.
- 실제 Card 승격 전 분석기간에 시행 중인 K-IFRS 원문과 문단 ref를 다시 확인한다.
- K-IFRS와 IFRS의 제·개정 시점 차이를 Norm Resolver가 처리한다.
- 회계사 검토 전 authority는 `Boundary`를 넘지 않는다.

## 1. 공통 Norm Card

### N-COMMON-ASSERTION-01 거래와 잔액

- 거래: 발생, 완전성, 정확성, 기간귀속, 분류, 표시
- 잔액: 실재성, 권리·의무, 완전성, 정확성·평가·배분, 분류, 표시
- 하나의 이슈가 여러 주장을 침해할 수 있다.
- Signal과 주장 연결이 없으면 전문 Issue로 승격하지 않는다.

### N-COMMON-EVIDENCE-01 증거 강도

검토 순서:

1. 원천 시스템·외부 증거
2. 서로 독립된 내부 증거
3. 통제된 시스템 산출물
4. 담당자 설명

담당자 설명은 필요하지만 독립 증거가 없으면 확정 근거가 아니다. 상충 증거를 삭제하지 않는다.

### N-COMMON-MATERIALITY-01 중요성

- 고객·회계사가 입력한 중요성을 사용한다.
- 중요성 부재 시 시스템이 감사 중요성을 발명하지 않는다.
- 금액이 작아도 부정, 법규, covenant, 반복오류, KPI 조작은 질적으로 중요할 수 있다.
- 중요성은 검토 우선순위에 쓰되 필수 무결성검사를 제거하지 않는다.

## 2. Accounting Core Norm Seed

### N-KR-1008-01 회계정책

판단요소:

- 특정 거래에 직접 적용되는 기준이 존재하는가
- 기준이 선택을 허용하는가
- 회사가 일관된 정책을 적용했는가
- 변경이 기준서 요구인지 더 신뢰성 있고 목적적합한 정보 때문인지
- 소급적용·공시 요구가 있는가

구별 Evidence:

- 정책서
- 변경 승인
- 시행일
- 비교기간 재작성
- 기준서 변경

금지:

- 결과가 유리해졌다는 사실만으로 정책변경을 오류로 확정
- 계정명 변경을 회계정책 변경으로 간주

### N-KR-1008-02 회계추정

판단요소:

- 측정불확실성 때문에 금액을 추정하는가
- 새로운 정보·경험·상황 변화가 있는가
- 변경효과가 현재·미래기간에 반영되는가

반증:

- 과거에 사용 가능했던 신뢰성 있는 정보를 누락·오용했다면 전기오류 후보
- 계산모델 변경이 실제로 정책 변경일 수 있음

### N-KR-1008-03 전기오류

후보:

- 수학적 오류
- 정책 적용 오류
- 사실의 간과·오해
- 부정

구별 Evidence:

- 과거 승인 시점에 정보가 이용 가능했는가
- 합리적으로 입수 가능했는가
- hindsight만으로 생성된 정보인가

### N-AUDIT-240-01 경영진 override Method

필수 관점:

- 분개와 기타 조정
- 추정 편향
- 비정상 중요 거래의 사업목적
- 통제 우회

출력은 `fraud_risk_candidate`이며 부정 확정이 아니다.

## 3. Contract & Revenue Norm Seed

### N-KR-1115-01 고객계약 식별

요건 후보:

- 당사자가 계약을 승인하고 의무 이행을 약속
- 각 당사자의 권리를 식별 가능
- 지급조건 식별 가능
- 상업적 실질 존재
- 대가 회수가능성 평가

Procedure:

- 계약 승인·권리·지급조건·현금흐름 변화·고객 신용 Evidence를 수집
- 기준 미충족 계약의 수금은 별도 부채·환불가능성 검토로 전달

금지:

- 서명문서 존재만으로 모든 요건 충족
- 현금수금만으로 수익 인식

### N-KR-1115-02 계약 결합

검토 후보:

- 같은 고객 또는 관련 당사자
- 비슷한 시점
- 하나의 상업적 목적
- 한 계약 가격이 다른 계약에 의존
- 약속이 하나의 수행의무를 구성

Procedure:

- 고객·협상자·승인일·가격연동·교차조건을 graph로 검사

### N-KR-1115-03 계약 변경

분기:

- 추가 재화·용역이 구별되고 가격이 독립판매가격을 반영하면 별도계약 후보
- 남은 재화·용역이 기존과 구별되면 기존 종료·신규계약 효과 후보
- 남은 재화·용역이 구별되지 않고 기존 수행의무 일부면 누적 catch-up 후보

필수 Evidence:

- 변경 승인
- 추가 약속
- 가격 근거
- 변경일 현재 이행상태

### N-KR-1115-04 수행의무

구별되는 재화·용역 판단:

- 고객이 자체적으로 또는 사용 가능한 다른 자원과 함께 효익을 얻을 수 있는가
- 계약의 다른 약속과 별도로 식별되는가

별도 식별 반증:

- 중요한 통합 서비스
- 다른 재화·용역을 중요하게 수정·맞춤화
- 약속들이 상호의존·상호관련

Procedure:

- 별도판매, 타 공급자 수행, 고객 사용가능성, 통합·수정·의존 Evidence

### N-KR-1115-05 거래가격

구성:

- 고정대가
- 변동대가
- 유의적 금융요소
- 비현금대가
- 고객에게 지급할 대가

변동대가:

- 기대값 또는 가장 가능성 높은 금액 중 상황을 더 잘 예측하는 방법
- 중요한 수익 되돌림 가능성을 고려한 제약
- 보고기간마다 갱신

Procedure:

- bonus, penalty, SLA credit, 환불, 할인, price protection과 후속 실제 결과 비교

### N-KR-1115-06 독립판매가격 배분

원칙:

- 계약 개시 시 상대적 독립판매가격에 기초

증거 순서:

- 관측 가능한 독립판매 거래
- 조정시장평가
- 예상원가+마진
- 제한된 상황의 잔여접근

Procedure:

- 고객·지역·수량별 가격분포
- 승인된 할인
- bundle 거래
- 추정방법 일관성

### N-KR-1115-07 기간에 걸친 충족

후보 중 하나:

- 고객이 이행과 동시에 효익을 받고 소비
- 고객이 통제하는 자산을 생성·가치증대
- 대체용도가 없는 자산을 만들고 현재까지 이행에 대한 집행가능한 지급청구권 존재

충족하지 않으면 한 시점 후보로 이동한다.

필수 Evidence:

- 고객 통제
- 대체사용 가능성
- 계약·법률상 지급청구권
- 해지 시 보상

법적 집행가능성은 법률전문가 Trigger가 될 수 있다.

### N-KR-1115-08 한 시점 통제이전

지표 후보:

- 현재 지급청구권
- 법적 소유권
- 물리적 점유
- 유의적 위험·보상
- 고객 검수

어느 지표 하나만으로 자동 확정하지 않는다.

### N-KR-1115-09 진행률

목적:

- 고객에게 이전되는 이행을 충실히 나타내는 단일 방법을 수행의무별 일관 적용

검사:

- output 또는 input method
- 통제이전과 무관한 투입 제외
- 비효율·낭비
- 측정 신뢰성
- 추정 변경

### N-KR-1115-10 본인·대리인

핵심:

- 고객에게 이전되기 전 특정 재화·용역을 통제하는가

지표 후보:

- 주된 이행책임
- 재고위험
- 가격결정 재량

지표는 통제판단을 보조하며 체크 개수로 결론내리지 않는다.

### N-KR-1115-11 계약잔액

- receivable: 대가에 대한 무조건적 권리
- contract asset: 이행했지만 시간 경과 외 조건이 남은 권리
- contract liability: 이행 전 대가 수취 또는 지급기일 도래

Procedure:

- 이행·청구·지급의 사건순서를 재수행

### N-KR-1115-12 계약원가

계약획득원가:

- 계약을 얻지 못했다면 발생하지 않았을 증분원가 후보

이행원가:

- 다른 기준서 적용을 먼저 확인
- 계약과 직접 관련
- 미래 수행에 사용할 자원을 생성·향상
- 회수 예상

비용 후보:

- 일반관리
- 비정상 낭비
- 이미 충족한 수행의무 관련
- 충족·미충족 부분을 구분할 수 없음
- 다른 기준서가 비용처리를 요구하는 교육 등

## 4. Cash Flow & Working Capital Norm Seed

### N-KR-1007-01 현금과 현금성자산

- cash: 보유현금·요구불예금 후보
- cash equivalent: 단기·고유동성·알려진 금액으로 전환 가능·가치변동 위험이 중요하지 않은 투자 후보
- 투자·자금운용 목적과 현금수요 충족 목적을 구별

Procedure:

- 취득일 만기, 인출조건, 가격위험, 사용목적, 담보·제한 검토

### N-KR-1007-02 영업활동

- 주된 수익창출활동과 투자·재무가 아닌 기타 활동
- 직접법 또는 간접법 관련 데이터 구조를 분리

금지:

- 손익계정 상대분개면 무조건 영업
- 회사가 “운영에 필요”하다고 말하면 자동 영업

### N-KR-1007-03 투자활동

- 장기자산과 현금성자산이 아닌 투자 취득·처분 후보
- 자산으로 인식되는 지출과 연결

Procedure:

- 원거래 자산, 자본화 여부, 처분, 사업결합 여부 확인

### N-KR-1007-04 재무활동

- 납입자본과 차입의 규모·구성을 변화시키는 활동 후보

Procedure:

- 차입·상환·자본·배당·리스부채 등 적용정책과 시행기준 확인

### N-KR-1007-05 비현금 거래

- 현금·현금성자산을 사용하지 않는 투자·재무 거래는 현금흐름에서 제외하고 별도 정보로 전달

Procedure:

- 자산취득-부채인식, 리스, 전환, 현물출자 등을 GL과 cash source로 대사

### N-KR-1007-06 재무부채 변동

- 현금흐름으로 생긴 변동과 비현금 변동을 구별하는 reconciliation

Procedure:

- opening, proceeds, repayment, FX, fair value, acquisition, other, closing bridge

### N-KR-1007-07 공급자금융

검토요소:

- 공급자와 회사의 지급조건 변화
- 금융기관 개입
- 해당 부채와 현금흐름의 분류
- 유동성위험과 집중
- 시행 중 K-IFRS 공시요건

계약과 적용기준 없이 일반 AP 또는 차입으로 자동 분류하지 않는다.

### N-KR-1109-01 매출채권·계약자산 기대신용손실

측정요소 후보:

- 편향되지 않은 확률가중 금액
- 화폐의 시간가치
- 과거사건·현재상황·합리적이고 뒷받침 가능한 미래정보

Procedure:

- aging, default, dispute, subsequent cash, macro·customer outlook, collateral·credit enhancement

경영진 회수의지만으로 손상을 배제하지 않는다.

### N-LIQUIDITY-01 경영 유동성

Norm 유형: management diagnostic

- unrestricted cash
- committed facilities
- mandatory outflows
- plausible collections
- covenant headroom
- downside scenario

이는 K-IFRS 위반 결론이 아니라 CEO 의사결정 정보다.

## 5. Project Cost & Allocation Norm Seed

### N-COST-01 회계원가와 관리배부 분리

- 재무보고상 측정요건
- 회사 회계정책
- 내부 수익성 배부

를 별도 Layer로 관리한다.

대체 driver가 더 인과적이라는 사실만으로 재무제표 오류를 확정하지 않는다.

### N-KR-1002-01 재고원가

적용대상일 때 원가 후보:

- 매입원가
- 전환원가
- 현재 장소와 상태에 이르게 한 기타 원가

검토:

- 직접노무
- 생산간접원가
- 정상조업도
- 비정상 낭비
- 순실현가능가치

서비스업 프로젝트가 실제로 이 기준 적용대상인지 먼저 확인한다.

### N-KR-1115-COST-01 계약획득·이행원가

Revenue Seed의 `N-KR-1115-12`를 재사용한다. 원가를 이중으로 자산화하지 않는다.

### N-KR-1038-01 교육·인력

검토 후보:

- 직원 지식·훈련의 미래효익을 기업이 충분히 통제하는가
- 다른 기준서가 적용되는가
- 교육지출 비용처리 요구가 있는가

교육비를 고객에게 청구할 수 있다는 사실만으로 자산성을 인정하지 않는다.

### N-KR-1038-02 개발활동

검토요소 후보:

- 연구와 개발 단계 구별
- 기술적 실현가능성
- 완성·사용·판매 의도와 능력
- 미래경제효익
- 자원 가용성
- 지출의 신뢰성 있는 측정

계정명이나 프로젝트 승인만으로 요건 충족을 확정하지 않는다.

### N-KR-1037-01 부담계약

후보:

- 의무이행의 불가피한 원가가 기대 경제효익을 초과
- 계약 이행원가와 계약 불이행·해지의 보상·위약 관련 비교
- 이행원가에 증분원가와 계약이행에 직접 관련된 기타 원가 배부 포함 여부

Procedure:

- 최신 ETC
- 직접·간접원가
- 해지권·위약금
- 고객 대가·변동대가
- 관련 자산 손상

### N-MGMT-ALLOC-01 배부 인과관계

Norm 유형: management diagnostic

좋은 배부기준 후보:

- 원가 소비와 논리적으로 연결
- 측정 가능
- 일관 적용
- 조작에 강함
- 비용 대비 유용

검증:

- current driver
- 직접 사용량 driver
- 합리적 대체 driver
- 프로젝트 마진 민감도

### N-MGMT-ALLOC-02 Pool 동질성

하나의 pool은 유사한 발생원인과 수혜대상을 가져야 한다. 서로 다른 driver가 필요한 원가는 분리 후보로 표시한다.

## 6. 공통 Procedure Card

### P-COMMON-01 Population-first

- 모집단 정의
- 포함·제외
- 건수·금액
- source hash
- Coverage

를 계산하기 전 표본이나 대표계약을 고르지 않는다.

### P-COMMON-02 Hypothesis set

각 Issue는 최소 다음을 가진다.

- accounting error
- fraud/control override
- normal business explanation
- data/mapping error
- multi-cause

적용 불가한 가설은 이유를 기록한다.

### P-COMMON-03 Distinguishing test

각 가설 쌍에 대해:

- 서로 다른 예상 증거
- 실행 가능한 검사
- 필요한 데이터
- 판정불가 조건

을 작성한다.

### P-COMMON-04 Quantification

- confirmed
- likely range
- maximum exposure
- not quantifiable

을 구분한다. 관리왜곡과 회계오류를 같은 금액으로 합산하지 않는다.

### P-COMMON-05 Stand-back

Issue별 검토 후:

- 같은 원인이 여러 Issue를 설명하는가
- 서로 모순되는 결론이 있는가
- 중요 계정 Coverage가 비었는가
- 경영진 편향 방향이 반복되는가
- 회계·현금·원가 결과가 대사되는가

를 다시 확인한다.

## 7. 필수 반증 규칙

- 수금은 수익 이행의 증거가 아닐 수 있다.
- 청구는 수익 인식시점의 증거가 아닐 수 있다.
- 검수서는 실제 통제이전과 다를 수 있다.
- 로그 부재는 서비스 부재와 같지 않을 수 있다.
- DSO 상승은 회수악화 외 성장·mix 변화일 수 있다.
- AP 증가는 체납 외 구매증가·조건개선일 수 있다.
- 저마진은 원가과다 외 원가오배부·수익지연일 수 있다.
- 고마진은 효율 외 원가누락·수익조기인식일 수 있다.
- 수동분개는 정상 결산조정일 수 있다.
- 자동분개도 잘못된 설정이면 오류일 수 있다.

## 8. 승격 전 검증

각 Seed Card마다:

1. K-IFRS 시행본 문단 ref 확인
2. 관할·시행일
3. 적용범위와 예외
4. 정상·오류·경계·반증사례
5. 계산 Oracle
6. 상충 Card
7. 회계사 승인

을 요구한다.

## 9. 공식 출처

- 한국회계기준원 시행 중 K-IFRS: `https://www.kasb.or.kr/front/board/ingAccountingList.do`
- 한국회계기준원 K-IFRS 연혁: `https://www.kasb.or.kr/front/board/List2006.do`
- IFRS Standards Navigator: `https://www.ifrs.org/issued-standards/list-of-standards/`
- IFRS 15: `https://www.ifrs.org/issued-standards/list-of-standards/ifrs-15-revenue-from-contracts-with-customers/`
- IAS 7: `https://www.ifrs.org/issued-standards/list-of-standards/ias-7-statement-of-cash-flows.html`
- IFRS 9: `https://www.ifrs.org/issued-standards/list-of-standards/ifrs-9-financial-instruments/`
- IAS 2: `https://www.ifrs.org/issued-standards/list-of-standards/ias-2-inventories/`
- IAS 37: `https://www.ifrs.org/issued-standards/list-of-standards/ias-37-provisions-contingent-liabilities-and-contingent-assets/`
- IAASB Handbook: `https://www.iaasb.org/publications/2021-handbook-international-quality-control-auditing-review-other-assurance-and-related-services`

## 10. HANDOFF

```text
이 Catalog의 내용은 비어 있는 Card 이름이 아니라 provisional 지식 초안이다.
그러나 아직 K-IFRS 문단 검증과 전문가 승격 전이므로 Full authority가 아니다.
구현자는 원문을 복제하지 말고 요건·예외·문단 ref·시행일을 versioned Card로 만든다.
```
