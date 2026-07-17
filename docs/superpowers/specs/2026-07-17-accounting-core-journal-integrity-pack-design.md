# Accounting Core & Journal Integrity Pack 설계

- Pack ID: `kr_b2b.accounting_core.v1`
- 상위 Matrix: `2026-07-17-accounting-review-coverage-matrix-design.md`
- 대상: 한국 B2B 서비스업 K-IFRS 우선
- 권한 상한: 전문가 승격 전 `Boundary`

## 0. 목적

모든 전문 Cycle에 앞서 원장과 기초 회계구조가 신뢰 가능한지 전수검사한다. 비정상분개를 “오류”나 “부정”으로 확정하지 않고, 재무제표 주장별로 위험과 구별 절차를 만든다.

이 Pack이 실패하면 다른 Cycle의 금액 합계는 `unreliable`로 내려간다.

## 1. 모집단

- 전체 분개 헤더와 라인
- 시산표
- 전기말 확정잔액
- 보조원장
- 계정과목표
- 회계기간
- 마감·재개방 기록
- 사용자·권한·승인 기록
- 증빙·문서 ref
- 연결·관계회사 데이터가 있으면 관련 분개

제외된 법인·기간·원장·통화는 Coverage Gap으로 기록한다.

## 2. 필수 데이터 역할

| Role | 필수 필드 |
|---|---|
| journal_header | journal_id, source, entry_date, posting_date, period, creator, approver, status |
| journal_line | journal_id, line_id, account, debit, credit, currency, entity, counterparty, project |
| trial_balance | account, opening, debit_turnover, credit_turnover, closing |
| chart_of_accounts | account, type, normal_balance, active_period |
| close_calendar | period, close_time, reopen_time, authorized_by |
| user_role | user, role, privilege_start, privilege_end |
| subledger_balance | subledger, account, object_id, amount, as_of |

식별자·직원정보는 pseudonymize하되 역할과 권한은 보존한다.

## 3. Issue Family

| ID | Issue | 주요 주장 | 필수 절차 | 대표 Output |
|---|---|---|---|---|
| AC-01 | 원천·원장 모집단 불완전 | 완전성 | 파일·기간·sequence·합계 대사 | 누락 Coverage |
| AC-02 | 차변·대변 불균형 | 정확성 | 분개·기간·원장별 균형검사 | 불균형 금액 |
| AC-03 | 시산표·원장 불일치 | 완전성·정확성 | account roll-up 대사 | 계정별 차이 |
| AC-04 | 기초·기말 roll-forward 오류 | 정확성·기간 | 전기말-당기초, 증감 재수행 | 잔차 |
| AC-05 | 보조원장·총계정원장 불일치 | 완전성·실재 | AR·AP·cash·project 대사 | object별 차이 |
| AC-06 | 중복·분할 중복 분개 | 발생·정확성 | exact·near duplicate 검사 | 중복 후보금액 |
| AC-07 | 기간말·마감후·소급 분개 | 기간·발생 | close timestamp 정렬 | cutoff 후보 |
| AC-08 | 관리자·수동·승인우회 분개 | 발생·통제 | 권한·creator/approver·source 검사 | override 후보 |
| AC-09 | 비정상 계정조합·방향 | 분류·정확성 | account-pair·normal balance 검사 | 재분류 후보 |
| AC-10 | 역분개·취소·대체 누락 | 완전성·기간 | reversal pairing | 미역분개·이중반영 |
| AC-11 | 가수·미결·suspense 장기잔액 | 분류·평가 | aging·movement 분석 | 정리 필요잔액 |
| AC-12 | 미지급·충당부채 누락 | 완전성·평가 | 후속지급·계약·반복비용 search | 미인식 후보 |
| AC-13 | 회계정책·추정·전기오류 혼동 | 표시·기간 | 변경 전후·승인·적용기간 비교 | 처리분류 후보 |
| AC-14 | 자산화·비용화·손상 위험 | 분류·평가 | account/activity/benefit 검사 | 자산조정 후보 |
| AC-15 | 관계회사·특수관계 흔적 | 표시·발생 | master·bank·counterparty 연결 | 전문가 Trigger |
| AC-16 | 경영진 편향·분개 집중 | 발생·평가 | 사용자·시간·계정·KPI 영향 집중도 | fraud-risk 후보 |

## 4. 결정적 절차

### P-AC-01 Population manifest

- 모든 입력 source의 hash, 기간, 행수, 금액합계를 기록한다.
- journal header와 line의 orphan을 양방향 검사한다.
- sequence gap은 누락 확정이 아니라 원천시스템 설명 필요 Signal이다.
- 삭제·취소 상태를 별도 모집단으로 보존한다.

### P-AC-02 Debit-credit balance

```text
journal_imbalance = sum(debit) - sum(credit)
period_imbalance = sum(journal_imbalance)
```

- 통화별·법인별로 먼저 계산한다.
- 환산원장과 거래통화를 섞지 않는다.
- 기간 합계 0이어도 개별 불균형 상계를 허용하지 않는다.

### P-AC-03 GL-TB roll-up

- 분개라인을 계정·기간·법인·통화로 집계한다.
- 시산표 증감과 대사한다.
- 차이는 mapping, opening, excluded source, late posting 가설로 분리한다.

### P-AC-04 Opening roll-forward

```text
prior_closing + current_movement = current_closing
```

- 전기 수정·재작성·환율·연결조정은 별도 bridge로 설명한다.
- 설명되지 않은 잔차를 다른 조정항목에 합치지 않는다.

### P-AC-05 Subledger reconciliation

- AR·AP·cash·fixed asset·project별 object sum과 GL control account를 대사한다.
- object 미존재 GL, GL 미존재 object, 금액·통화·기간 차이를 분리한다.

### P-AC-06 Duplicate detection

강도별 Signal:

- exact: 동일 source·문서·계정·금액·일자
- reversal-like: 반대 방향 동일금액
- near: 날짜·설명·counterparty 일부 차이
- split: 하나의 금액이 여러 분개로 분할

반복 월분개·정상 accrual·자동 reversal을 반대가설로 요구한다.

### P-AC-07 Close and cutoff

- 경제적 사건일, 증빙일, posting date, 입력 timestamp, 승인 timestamp를 비교한다.
- 마감 후 소급분개, 재개방기간 분개, 다음 기간 즉시 역분개를 묶는다.
- 날짜차이만으로 오류 확정하지 않는다.

### P-AC-08 Access and approval

- creator와 approver 동일 여부
- 역할분리 예외 승인
- 관리자권한 부여기간
- 자동 source를 수동으로 변경한 흔적
- 휴일·심야·마감직전 집중

시간대와 교대근무를 정상 반대가설로 확인한다.

### P-AC-09 Account pair expectation

- 업종·회사별 정상 account pair 분포를 만든다.
- 신규·희귀 pair, 정상잔액 반대방향, 수익-자산·비용-부채의 이상조합을 찾는다.
- 희귀성은 위험순위일 뿐 오류판정이 아니다.

### P-AC-10 Reversal pairing

- 원분개와 reversal의 금액·계정·설명·reference·기간을 매칭한다.
- 미역분개, 중복역분개, 부분역분개, 다른 계정 역분개를 분리한다.

### P-AC-11 Suspense aging

- 최초 발생일
- 마지막 movement
- 반복 clear/repost
- 책임부서
- counterparty·증빙 존재

장기잔액과 결산 직전 임시정리를 우선한다.

### P-AC-12 Subsequent disbursement search

- 보고기간 후 지급·세금계산서·급여·외주비를 이전 기간 서비스와 연결한다.
- 반복 월비용 누락, 미청구 용역, 성과급, 세금·법률비용을 후보화한다.
- 후속지급이 신규기간 서비스인지 반증한다.

### P-AC-13 Policy-estimate-error classification

- 변경 대상
- 변경 승인일
- 적용 시작일
- 비교기간 수정 여부
- 새로운 정보인지 과거 정보의 누락인지

IAS 8/K-IFRS 1008 관련 Norm Card와 전문가 검토 없이는 확정하지 않는다.

### P-AC-14 Capitalization screen

- 자산계정에 입력된 급여·외주·교육·광고·유지보수·연구활동을 activity와 연결한다.
- 미래효익·통제·식별가능성·직접 관련성을 판단할 자료를 요청한다.
- 단순 계정명만으로 자산성을 인정하지 않는다.

### P-AC-15 Management bias stand-back

- KPI를 개선하는 방향의 수동분개 비중
- 이익 증가·부채 감소·현금 분류 개선 방향
- 특정 사용자·마감일 집중
- 다음 기간 reversal
- 추정치 변경

개별 Signal을 합산한 불투명 점수를 금지하고 근거별로 제시한다.

## 5. 가설과 반증

### 공통 오류 가설

- 누락·중복
- 잘못된 기간
- 잘못된 계정·부호·통화
- 승인우회
- 회계정책 오적용
- 추정편향
- 원천시스템 동기화 실패

### 정상 반대가설

- 승인된 마감조정
- 자동 reversal
- 합법적 batch posting
- 회계정책 변경
- 시스템 migration
- 시간대·교대근무
- 외화환산·연결조정

### 구별 Evidence

- 승인문서
- 원천증빙
- 시스템 job log
- 변경관리 기록
- 회계정책 memo
- 후속거래
- 담당자 설명과 독립 증거

설명만 있고 독립 증거가 없으면 `unverified_explanation`으로 둔다.

## 6. 오류금액

| 유형 | 계산 |
|---|---|
| duplicate | 중복 후보 중 경제적 사건이 하나인 금액 |
| cutoff | 올바른 기간 금액과 현재 기간 금액 차이 |
| classification | 계정 간 재분류 금액, 총자산·손익 영향 별도 |
| omission | 후속증거로 확인된 미인식 의무·자산 |
| opening | 설명되지 않은 기초차이 |
| subledger | object와 control account 차이 |

확정금액, 최대노출, 판단불가를 분리한다.

## 7. 출력 계약

각 Issue:

- Issue ID와 Family
- 모집단·Coverage
- 계정·주장
- 비정상 분개·잔액 목록
- 가설과 반대가설
- 실행한 절차
- 증거·반대증거
- 오류금액 또는 범위
- 조정분개 후보
- 통제개선 후보
- 추가자료
- 전문가 질문
- 권한 상태

“부정입니다”가 아니라 “관리자 우회와 KPI 방향성이 함께 관찰돼 부정위험 검토가 필요합니다”처럼 표현한다.

## 8. Tier와 강제 실행

### Tier 0 Mandatory

- AC-01~AC-05
- 차변·대변
- 기초·기말
- GL-TB
- subledger 대사

### Tier 1 Population

- AC-06~AC-11
- AC-16의 결정적 Signal

### Tier 2 Deep Review

- AC-12~AC-15
- 승인된 중요 AC-06~AC-11 후보

## 9. 합성 사례

최소 Seed:

1. 정상 자동 월말 accrual과 reversal
2. 같은 청구서 exact duplicate
3. 분할 중복
4. 마감 후 소급 매출분개
5. 승인된 정상 audit adjustment
6. 관리자 단독 승인·다음 달 reversal
7. 시산표에는 있으나 GL source 누락
8. AR subledger와 GL 불일치
9. 장기 suspense를 결산일에 임시 clear
10. 후속 지급으로 발견되는 미지급외주비
11. 추정 변경과 전기오류가 혼동된 사례
12. 교육비를 계약원가자산으로 자산화한 사례
13. 환산차이를 오류로 오인할 수 있는 반대사례
14. 여러 오류가 순액으로 0이 되는 사례

각 사례는 기대 Issue, 금지 Issue, 오류금액, Evidence role, 반대검사를 가진다.

## 10. Norm Card Seed

- `N-KR-CONCEPTUAL`: 자산·부채·수익·비용 개념과 인식
- `N-KR-1008`: 회계정책·추정·오류
- `N-KR-1037`: 충당부채·우발사항
- `N-KR-1109`: 금융자산·부채·손상
- `N-AUDIT-315`: 위험평가·주장·통제
- `N-AUDIT-240`: 부정위험·경영진 override
- `N-AUDIT-500`: 증거의 관련성과 신뢰성

Audit Method Card는 감사의견을 만드는 근거가 아니라 검토 질문과 증거 강도를 설계하는 참고다.

## 11. 공식 출처

- K-IFRS 시행 중 목록: `https://www.kasb.or.kr/front/board/ingAccountingList.do`
- IAS 8 공식 자료: `https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2022/issued/part-a/ias-8-accounting-policies-changes-in-accounting-estimates-and-errors.pdf`
- IAS 37: `https://www.ifrs.org/issued-standards/list-of-standards/ias-37-provisions-contingent-liabilities-and-contingent-assets/`
- IFRS 9: `https://www.ifrs.org/issued-standards/list-of-standards/ifrs-9-financial-instruments/`
- IAASB Handbook: `https://www.iaasb.org/publications/2021-handbook-international-quality-control-auditing-review-other-assurance-and-related-services`
- ISA 240 Revised 페이지: `https://www.iaasb.org/publications/isa-240-revised-auditor-s-responsibilities-relating-fraud-audit-financial-statements`

ISA 240 Revised의 시행일은 별도이므로 Run의 기준시점에 맞는 Method 버전을 선택한다.

## 12. Release Gate

- Tier 0 대사 미실행 시 다른 Pack Full 금지
- 모든 AC Family에 정상·오류·반증사례 존재
- 확정·후보·판단불가 금액 분리
- 관리자·기간말 Signal만으로 부정 확정 0건
- 정책·추정·오류 구분에 Norm·Evidence 연결
- 회계사 검토 전 authority `Boundary`

## 13. HANDOFF

```text
이 Pack은 다른 모든 Cycle의 신뢰 기반이다.
먼저 모집단·원장·시산표·보조원장을 대사하고,
이후 비정상분개를 가설·반증·금액·추가절차로 구조화한다.
Tier 0 실패를 다른 분석의 그럴듯한 설명으로 덮지 않는다.
```
