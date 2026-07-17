# Trusted CEO Agent 시니어 회계사급 검토 확장 설계

- 상태: 사용자 승인 후속 설계
- 기준일: 2026-07-17
- 적용 시점: 현재 `trusted-ceo-agent` 플러그인 구현과 검증이 완료된 뒤
- 1차 전문 범위: B2B 서비스업의 계약·매출, 현금흐름·운전자본, 프로젝트 원가·원가배분
- 목표 수준: 시니어 회계사와 일부 매니저급의 1차 검토 초안
- 최종 책임: 회계사와 고객 책임자에게 유지

## 0. 이 문서를 사용하는 방법

이 문서는 현재 진행 중인 플러그인 구현을 변경하거나 중단시키는 문서가 아니다. 현재 구현이 끝난 뒤 기존 Trust Kernel과 Pack 구조를 재사용해 전문 분석 깊이를 확장하기 위한 별도 vNext 설계다.

후속 작업자는 다음 순서로 시작한다.

1. `docs/PRD.md`를 읽는다.
2. `docs/ARCHITECTURE_DECISIONS.md`를 읽는다.
3. `docs/superpowers/specs/2026-07-17-trusted-ceo-agent-plugin-design.md`를 읽는다.
4. 현재 코드와 테스트가 위 문서대로 완료됐는지 확인한다.
5. 이 문서를 읽고 기존 구현과의 차이를 Gap 목록으로 만든다.
6. 현재 구현의 검증된 동작은 보존하고, 이 문서의 확장만 별도 구현 계획으로 작성한다.
7. 구현 계획 승인 전에는 코드를 변경하지 않는다.

### 충돌 방지 규칙

- 이 문서는 기존 PRD와 플러그인 상세 설계를 삭제하거나 소급 변경하지 않는다.
- 현재 구현 중인 파일을 이 문서를 이유로 선제 수정하지 않는다.
- 현재 구현의 상태 머신, Artifact Store, Evidence Core, Pack Loader, Reasoning Job, HITL Gate, 최종 Validator는 재사용한다.
- vNext는 가능한 한 신규 모듈·신규 Schema 버전·신규 Pack으로 추가한다.
- 기존 Artifact ID, Pack ID, Schema 의미를 조용히 바꾸지 않는다.
- 기존 계약 변경이 불가피하면 신규 Schema 버전과 명시적 migration을 사용한다.
- 기존 테스트를 수정해 실패를 숨기지 않는다. 기존 동작 변경은 별도 결정 기록과 회귀 테스트가 필요하다.
- 현재 구현 완료 시점의 커밋 또는 불변 snapshot을 vNext 기준선으로 고정한다.
- 다른 작업자의 미커밋 변경이 있으면 덮어쓰지 않고 먼저 작업 경계를 분리한다.

### 문서 간 우선순위

1. 현재 버전 구현과 검증에는 기존 PRD와 기존 상세 설계를 적용한다.
2. 현재 버전 완료 후 회계 전문 확장에는 이 문서를 적용한다.
3. 이 문서와 기존 구현이 충돌하면 기존 동작을 유지하고 vNext migration 결정으로 해결한다.
4. 법령·회계기준·회사 정책과 문서 내용이 충돌하면 최신의 권위 있는 원문과 전문가 승인이 우선한다.

## 1. 목표와 비목표

### 1.1 목표

전처리된 원천 거래와 문서를 전수 계산한 뒤 다음을 수행한다.

- 회계 오류와 통제 이상 후보를 거래·계정·주장 단위로 찾는다.
- 현금흐름과 운전자본의 악화 원인과 회계상 불일치를 찾는다.
- 프로젝트 원가와 원가배분의 왜곡·과다·과소 배부 후보를 찾는다.
- 각 이슈의 영향 계정, 재무제표 주장, 잠재 오류금액, 반대 증거, 추가 검토 절차를 제시한다.
- 조건이 충족될 때 수정분개 후보를 계산 가능한 초안으로 만든다.
- CEO에게는 경영 영향과 의사결정 사항을, 회계사에게는 검토 근거와 미해결 질문을 제공한다.
- 검토하지 못한 중요 계정·주장을 숨기지 않고 Coverage Gap으로 표시한다.

### 1.2 목표 수준의 정의

`시니어 회계사 + 일부 매니저급 1차 검토 초안`은 다음을 뜻한다.

- 주니어 업무: 자료 정리, 전수 대사, 재계산, 예외 목록 생성
- 시니어 업무: 예외의 원인 후보, 반대 가설, 잠재 영향, 다음 검토 절차 작성
- 일부 매니저 업무: 중요성·위험 기반 우선순위, 이슈 간 연결, 전문가 라우팅
- 제외 업무: 최종 회계처리 승인, 감사의견, 법적 책임, 고객과의 최종 논쟁·합의

### 1.3 비목표

- 첫 버전에서 모든 산업과 모든 K-IFRS·IFRS 주제를 다루지 않는다.
- AI가 최종 회계처리나 감사 결론을 확정하지 않는다.
- AI가 설치된 필수 Pack을 제거하거나 검토 범위를 조용히 축소하지 않는다.
- 불투명한 ML 점수 하나로 Pack 실행 여부를 결정하지 않는다.
- 근거가 없는 분개나 오류금액을 생성하지 않는다.
- 회계 관점을 법무·노무·세무의 공통 결론으로 강제하지 않는다.

## 2. 현재 구현과의 관계

현재 구현은 다음 강점을 그대로 유지한다.

- 원본 snapshot 불변
- Fact·Signal과 AI 해석 분리
- Evidence Link와 lineage
- Pack authority와 provisional 경계
- HITL 상태 전이와 revision
- 모델 draft의 비신뢰 처리
- 결과 등급과 전문직 경계
- 최종 검증과 감사 패키지

현재 구현 완료 후 다음 Gap을 먼저 감사한다.

1. 원천 행이 Data Gate 승인 후 실제 Fact Register로 물질화되는가
2. Pack의 `analysis_plan`과 `deep_dive_plan`이 실제 CLI 실행 경로에 연결되는가
3. 필요한 Component parameter와 threshold가 Pack에서 결정적으로 해소되는가
4. 모든 Component 결과가 Evidence Core와 최종 출력까지 연결되는가
5. POC fixture 전용 코드가 실제 실행 경로와 분리되어 있는가
6. 설치 Pack이 전문가 검증 없이 Full authority로 승격되지 않는가

위 Gap이 남아 있으면 신규 회계 Pack을 추가하기 전에 먼저 연결을 완성한다. 단, 현재 구현 완료 전에는 이 문서를 근거로 해당 파일을 동시에 수정하지 않는다.

## 3. 설계 원칙

### 3.1 라우터는 전문가가 아니라 보수적 배차 시스템이다

도메인 판단은 Pack에 두고 라우터는 다음만 책임진다.

- 필수검사 포함
- 사용자 요청 포함
- 존재하는 데이터·계정에 대응하는 검사 포함
- 결정적 신호가 요구하는 심화검사 포함
- AI가 제안한 추가 후보 포함
- 중요 계정·주장의 Coverage Gap 차단

### 3.2 AI는 추가만 하고 제거하지 못한다

- AI 라우터는 후보 Pack을 추가할 수 있다.
- AI 라우터는 필수 Pack, 사용자 요청 Pack, 중요 계정 대응 Pack을 제거할 수 없다.
- AI 라우터의 제안은 Pack 존재, 데이터 capability, 권한, 비용, 금지 결론 검증을 통과해야 한다.
- AI 제안이 실패해도 결정적 라우팅 결과는 유지한다.

### 3.3 전문 깊이는 Pack과 결정적 Component가 담당한다

- 숫자 계산, 대사, 기간 정렬, 오류금액, 분개 후보 계산은 코드가 수행한다.
- AI는 경제적 의미, 원인·반대 가설, 자료 요청, 전문가 질문, 경영 영향 초안을 작성한다.
- 기준서 판단은 자유 생성 문장이 아니라 Pack의 구조화된 판단 트리와 허용된 후보 안에서 수행한다.

### 3.4 미검토는 실패가 아니라 명시적 결과다

모든 중요 계정·주장은 다음 중 하나의 상태를 가져야 한다.

- `completed`
- `deep_review_pending`
- `not_assessable`
- `expert_review_required`
- `not_applicable`
- `excluded_by_approved_scope`

빈 상태와 조용한 생략은 허용하지 않는다.

## 4. 전체 구조

```text
Mission + Source Registry
        |
        v
Data Intake / Mapping / Fact Materialization
        |
        v
Tier 0 Mandatory Integrity & Reconciliation
        |
        v
Tier 1 Low-cost Population Screening
        |
        +-------------------------------+
        |                               |
        v                               v
Deterministic Routing              AI Additive Proposals
        |                               |
        +---------------+---------------+
                        v
               Candidate Pack Union
                        |
                        v
                 Coverage Auditor
                        |
                        v
             Tier 2 Authorized Deep Review
                        |
                        v
             Issue Evidence Packet Builder
                        |
                        v
              Bounded AI Issue Reasoning
                        |
                        v
              Cross-domain Stand-back
                        |
                        v
              HITL / Expert Draft Output
```

## 5. 위험 라우터

### 5.1 입력

라우터는 다음의 신뢰된 입력만 사용한다.

- 확인된 Mission Contract
- Source Registry와 Data Capability Map
- 계정·거래·기간·통화·사업 단위 정보
- 중요성 기준과 승인된 분석 범위
- Tier 0·1의 결정적 Fact·Signal
- 설치 Pack manifest와 effective authority
- 현재 실행 예산과 필수 절차 정책
- 과거 실행이 있으면 검증된 이전 이슈와 승인 기록

### 5.2 후보 생성 경로

최종 후보는 다음 다섯 집합의 합집합이다.

```text
Candidate Packs =
    Mandatory Baseline Packs
  UNION Mission-requested Packs
  UNION Data/account-driven Packs
  UNION Deterministic-signal Packs
  UNION Validated AI-proposed Packs
```

#### Mandatory Baseline Packs

지원 도메인 여부와 무관하게 가능한 범위에서 실행한다.

- 데이터 무결성
- 차변·대변 균형
- 회계등식
- 기초·증감·기말 Roll-forward
- 원장·보조부 모집단 대사
- 중복·누락·기간 오류
- 결산일 주변 비정상·수동분개
- 중요 계정의 기본 분석적 절차

#### Mission-requested Packs

사용자가 명시한 질문에 대응한다. 사용자의 원인 설명은 Pack 선택 신호일 뿐 Fact로 승격하지 않는다.

#### Data/account-driven Packs

관련 데이터나 중요 계정이 존재하면 최소 스크리닝을 수행한다.

- 매출·채권·계약자산·계약부채 → 계약·매출 Cycle
- 은행·현금·채권·채무 → 현금흐름·운전자본 Cycle
- 프로젝트·인건비·공통비·원가센터 → 프로젝트 원가·배분 Cycle

#### Deterministic-signal Packs

Tier 0·1에서 코드로 생성된 신호가 심화검사를 요구할 때 선택한다.

#### AI-proposed Packs

AI는 여러 신호의 공통 메커니즘이나 교차 도메인 가능성을 근거와 함께 제안한다. 제안은 다음을 포함해야 한다.

- 제안 Pack ref
- 사용한 Fact·Signal ref
- 제안 이유
- 반대 가능성
- 필요한 추가 데이터
- 예상되는 검토 가치

### 5.3 불투명 점수 금지

초기 버전은 학습된 위험점수나 가중합 하나로 실행 여부를 결정하지 않는다. 다음의 설명 가능한 우선순위를 사용한다.

1. 법정·정책상 또는 Mission상 필수 → 실행
2. 중요 계정과 필수 주장에 대응 → 실행
3. 중요한 결정적 신호와 데이터 충족 → 심화 실행
4. 신호는 있으나 데이터 일부 부족 → 제한 실행 또는 자료 요청
5. AI 제안만 있고 결정적 근거 부족 → 저비용 확인 또는 Monitor
6. 데이터·Pack 부족 → Not Assessable

### 5.4 실행 예산

- Tier 0과 중요 계정 Coverage는 예산 때문에 생략할 수 없다.
- Tier 2 예산이 부족하면 위험·중요성 순서로 실행하되 나머지는 `deep_review_pending`으로 남긴다.
- 미실행 절차와 예상 영향은 최종 사각지대에 포함한다.
- AI 토큰은 원장 전체가 아니라 Issue Evidence Packet에만 사용한다.

## 6. Coverage Auditor

### 6.1 목적

위험 라우터의 정확성을 신뢰하지 않고, 라우터가 실패해도 중요 검토 누락을 막는다.

### 6.2 Coverage 축

- 회사·사업 단위
- 회계 Cycle
- 중요 계정
- 재무제표 주장
- 보고기간
- 데이터 source role
- 실행한 절차
- 사용한 Pack·Component
- 현재 결과 상태

### 6.3 회계 주장

초기 공통 주장은 다음과 같다.

- 실재성·발생
- 완전성
- 정확성
- 기간귀속
- 분류
- 평가·배분
- 권리와 의무
- 표시와 공시

### 6.4 차단 조건

다음 중 하나면 결과를 `시니어 회계사급 초안`으로 표시할 수 없다.

- 중요 계정·주장 Coverage에 빈칸이 있음
- 모집단 완전성을 확인하지 못했으나 확정적 이슈를 제시함
- 중요 오류금액이 근거 없이 모델 추정으로 생성됨
- 필수 반대 증거 절차가 실행되지 않음
- 필요한 전문가 Pack이 provisional인데 Full 수준 결론을 냄
- 미실행 심화검사가 최종 사각지대에서 누락됨

### 6.5 Coverage Artifact

후속 구현은 기존 Artifact 규칙에 맞춰 다음 의미를 보존해야 한다.

```json
{
  "coverage_id": "coverage_...",
  "material_account_ref": "account_revenue",
  "assertion": "cutoff",
  "status": "completed",
  "procedure_refs": ["procedure_revenue_cutoff_population"],
  "pack_refs": ["revenue-accounting@2.0.0"],
  "fact_refs": ["fact_..."],
  "signal_refs": ["signal_..."],
  "reason_codes": []
}
```

정확한 파일 경로와 Schema 이름은 후속 구현 계획에서 현재 코드와 충돌하지 않도록 결정한다. 기존 Schema 의미를 덮어쓰지 않는다.

## 7. 실행 Tier

### Tier 0. 필수 무결성·대사

모든 실행에서 가능한 범위까지 수행한다.

- Source snapshot과 행 수·합계 검증
- 차변·대변 균형
- 회계등식
- 기초·증감·기말
- 원장·보조부·명세 모집단 대사
- 중복·누락·잘못된 기간·통화·단위
- 중요 데이터 역할 부재

### Tier 1. 저비용 전수 스크리닝

- 전기·예산·추세 차이
- 비정상 금액과 희귀 조합
- 결산일 주변 거래
- 수동분개와 승인 이상
- 계정 간 기대 관계 붕괴
- 장기 미회수·미지급
- 거래 취소·역분개·중복 후보
- 고객·공급자·프로젝트 집중

Tier 1은 이슈를 확정하지 않고 후보 모집단과 Signal을 만든다.

### Tier 2. 전문 심화검사

라우터와 Coverage Auditor가 승인한 Pack만 실행한다.

- 거래 단위 대사
- 계약·검수·청구·현금·원장 연결
- 현금흐름 재계산과 분류
- 원가 풀·배부율·배부 결과 재수행
- 잠재 오류금액과 민감도
- 수정분개 후보 계산
- 반대 증거와 구별 절차

### Tier 3. 제한된 AI 추론

Issue Evidence Packet별로 수행한다.

- 경제적 사건 설명
- 회계상 문제 후보
- 원인과 반대 가설
- 적용 가능한 처리 후보와 조건
- 누락자료와 검토 질문
- 경영 영향
- 전문가 초안 문구

## 8. 1차 B2B 서비스업 전문 범위

### 8.1 계약·매출 Cycle

#### 데이터

- 계약과 변경계약
- 수행의무·서비스 기간
- 검수·개통·납품
- 청구·세금계산서
- 현금 수금
- 매출원장
- 매출채권
- 계약자산·계약부채
- 취소·환불·Credit note

#### 검토

- 계약 모집단 완전성
- 계약금액·청구·수금·원장 대사
- 검수·서비스·인식일 Cut-off
- 중복·취소 매출
- 선수금과 계약부채 분류
- 미청구 계약자산과 장기 미회수
- 수동분개·결산 조정
- 수행의무·거래가격·배분·인식 후보 판단 트리

### 8.2 현금흐름·운전자본 Cycle

#### 데이터

- 은행 거래와 잔액
- 현금·현금성자산 원장
- 매출채권·매입채무
- 수금·지급
- 차입금·이자·리스 지급
- 자산 취득·처분
- 세금 지급
- 예산·Forecast

#### 검토

- 은행–원장–재무상태표 대사
- 현금 및 현금성자산 구성
- 영업·투자·재무활동 분류
- 직접법·간접법 재계산
- 순이익–영업현금흐름 Bridge
- 비현금 항목과 운전자본 조정
- DSO·DPO·현금전환주기
- 연체채권과 회수 집중
- 차입금 변동과 현금흐름 대사
- 단기 유동성·현금 고갈 후보

### 8.3 프로젝트 원가·원가배분 Cycle

#### 데이터

- 프로젝트·계약
- 작업시간·인건비율
- 외주비·직접비
- 공통비·원가센터
- 배부 기준과 사용량
- 청구·매출·프로젝트 마진
- WIP·미청구 원가
- 예산·실제·변경주문

#### 검토

- 직접비·간접비 구분
- 원가 풀 완전성
- 배부 대상과 배부 기준
- 배부율 재계산
- 배부 전후 총원가 보존
- 프로젝트별 과다·과소 배부
- 유휴능력과 가동률
- 표준·예산·실제 차이
- 미청구 추가작업과 승인된 범위변경 구분
- WIP·기간비용 분류 후보
- 다른 배부 기준의 민감도

## 9. 전문 Pack 계약

모든 전문 Pack은 최소한 다음을 선언한다.

- Pack ID, version, authority
- 전문분야와 산업 범위
- 관련 Cycle·계정·주장
- 적용·제외 조건
- 요구 source role과 capability
- 필수검사와 선택검사
- Tier 1 entry Signal
- Tier 2 distinguishing test
- 결정적 Component plan
- 중요성·threshold 출처
- 요구 Evidence role과 독립성
- 반대 증거 조건
- 잠재 오류금액 계산 방식
- 분개 후보 허용 조건
- Not Assessable 조건
- 전문가 trigger와 금지 결론
- 예상 실행 비용
- 정답 사례와 regression ref
- 전문가 검토·승격 기록

### Pack authority

- `boundary`: 공통 검진과 자료 요청만 허용
- `provisional`: 전문 초안 후보는 가능하나 결론 강도와 등급 제한
- `full`: 계약·정답셋·전문가 검토와 회귀 테스트를 통과한 범위만 허용

AI나 코드 작성만으로 `full`에 승격할 수 없다.

## 10. Issue Evidence Packet

AI는 전체 원장이나 전체 문서 묶음을 직접 받지 않는다. 이슈별 Packet을 받는다.

Packet은 다음을 포함한다.

- Issue 후보와 관련 Cycle·계정·주장
- 모집단 정의와 Coverage
- 관련 Fact·Signal
- 계산식과 Component run
- 이상 거래 전체 규모와 대표 예외
- 계약·정책·기준 판단 트리의 허용된 node
- 지지 증거와 반대 증거
- 누락자료와 품질 경고
- 잠재 오류금액과 범위
- 허용된 회계처리 후보
- 금지 결론
- 전문가 trigger

AI는 Packet 밖의 금액, 기준 node, Fact, Signal을 만들 수 없다.

## 11. Cross-domain 확장과 충돌 처리

Evidence Core는 전문분야 중립으로 유지한다. 회계·노무·법무·세무 Pack은 같은 경제적 사건을 서로 다른 전문 주장으로 평가한다.

예: 외주 인력 거래

- 회계: 비용 분류, 기간귀속, 프로젝트 원가
- 노무: 근로자성, 근로시간, 임금·퇴직급여
- 법무: 계약상 책임과 분쟁 노출
- 세무: 원천징수, 부가세, 손금

통합 단계는 전문 의견을 하나로 덮어쓰지 않고 다음을 기록한다.

- 공통 사실
- 전문분야별 판단 후보
- 의견의 일치·충돌
- 한 분야의 결정이 다른 분야에 미치는 영향
- 최종 판단 책임자
- 추가로 필요한 전문가

회계의 중요성 기준을 노무·법무 위험에 그대로 적용하지 않는다. 공통 출력은 금액, 긴급성, 법적·인적 영향, 통제 영향 등 복수 차원을 유지한다.

## 12. Fallback과 안전 중단

### Full

검증된 Domain·Problem Pack과 필요한 데이터가 모두 있다.

- 원인·반대 가설
- 오류금액
- 분개 후보
- 조건부 대응
- 시니어 회계사급 초안 가능

### Boundary

전문 Pack은 부족하지만 공통 회계 데이터가 있다.

- 원장 무결성
- 재무제표 관계
- 현금·채권·채무 기본 대사
- 일반 이상분개
- 자료 요청과 전문가 질문

시니어 회계사급 표시는 금지한다.

### Not Assessable

데이터와 Pack이 모두 부족하다.

- 확인하지 못한 계정·주장
- 필요한 자료
- 사람이 수행할 절차
- 적용 가능한 전문가 영역

확정 결론은 생성하지 않는다.

## 13. 결과물

### 회계사 검토 초안

각 이슈에 다음을 제공한다.

- 이슈 제목과 Cycle
- 영향 계정과 재무제표 주장
- 관찰 사실
- 검토한 모집단과 Coverage
- 지지·반대 증거
- 현재 처리 후보와 조건
- 잠재 오류금액과 계산 근거
- 수정분개 후보와 전제
- 미해결 질문
- 다음 검토 절차
- 관련 Pack·Component·기준 ref
- 결과 등급과 승인 상태

### CEO 브리프

- 경영적으로 중요한 사실
- 현금·수익성·통제 영향
- 즉시 결정하거나 확인할 사항
- 회계·노무·법무 등 전문 검토 충돌
- 조건부 대응 방향
- 사각지대와 미실행 심화검사

### Coverage 보고서

- 중요 Cycle·계정·주장별 상태
- 실행·미실행 절차
- 데이터 부족
- provisional Pack 사용 영역
- 전문가 승인 필요 영역

## 14. 검증 전략

### 14.1 Pack별 정답 사례

모든 Pack은 다음 사례를 포함한다.

- 정상 사례
- 명백한 오류
- 경계금액 사례
- 반대 증거가 있는 사례
- 데이터 부족 사례
- 서로 충돌하는 원인 사례
- 오류금액 정답
- 수정분개 후보 정답
- 기대 등급
- 금지 결론

### 14.2 자동 검증

- 단위: 계산식, Decimal, 기간, 통화, 배부율
- 계약: Pack, Router, Coverage, Evidence Packet Schema
- 통합: 원천 행부터 회계사 초안까지
- 순차·병렬 동등성
- 입력 변형 안정성
- 중복·누락·TOCTOU 안전성
- AI가 필수 Pack을 제거하지 못하는지
- Coverage 빈칸이 최종화를 차단하는지
- provisional 권한이 결론 강도를 제한하는지

### 14.3 제품 합격 기준

초기 B2B 세 Cycle의 Full 표시는 다음을 모두 충족해야 한다.

- 합성·검증 정답셋의 중요 삽입 오류 재현율 95% 이상
- Mandatory 무결성·대사 오류 재현율 100%
- 표시된 중요 이슈의 적중률 70% 이상
- 결정적 오류금액 계산의 기대값 일치율 100%
- 출처 없는 중요 주장 0건
- Coverage 상태 없는 중요 계정·주장 0건
- 데이터 부족 상태에서 확정 분개·처리 결론 0건
- 반대 증거 누락으로 강한 등급을 유지한 사례 0건
- 동일 입력 반복 시 Fact·Signal·Coverage·결정적 계산이 동일
- 최소 한 명의 자격 있는 회계사 승인
- 중요·분쟁 Pack은 독립적인 두 번째 회계사 검토 또는 문서화된 이견 해결

이 수치는 회계기준의 요구가 아니라 제품의 내부 품질 기준이다.

## 15. 구현 단계와 활성화 Gate

### Phase 0. 현재 구현 완료 기준선

- 기존 구현 계획 완료
- 기존 전체 테스트 통과
- POC와 실제 실행 경로 분리 확인
- 불변 기준 commit 또는 snapshot 생성
- 현재 미해결 항목 HANDOFF 작성

Phase 0 이전에는 이 문서의 구현을 시작하지 않는다.

### Phase 1. 데이터→Fact→Component 연결 완성

- 승인된 mapping의 Fact 물질화
- Pack plan의 결정적 parameter 해소
- CLI와 Component plan 연결
- Evidence Core 병합과 lineage
- 실제 행 기반 통합 테스트

### Phase 2. 보수적 Router와 Coverage Auditor

- Mandatory baseline
- Mission·Data·Signal 기반 라우팅
- AI additive proposal 계약
- Candidate union
- Coverage matrix와 최종화 차단
- Full·Boundary·Not Assessable fallback

### Phase 3. B2B 세 전문 Cycle

- 계약·매출
- 현금흐름·운전자본
- 프로젝트 원가·원가배분
- 오류금액과 분개 후보 Component

### Phase 4. 제한된 AI 추론과 Stand-back

- Issue Evidence Packet
- 이슈별 시니어 초안
- 반대 가설과 추가 절차
- Cross-domain 충돌 보존
- CEO·회계사 출력 분리

### Phase 5. 정답셋·전문가 검증·승격

- 합성 오류 시나리오
- 회계사 독립 평가
- 임계값 보정
- regression 고정
- Pack Registry 승격

## 16. 완료 조건

다음이 모두 충족되면 이 확장을 완료한 것으로 본다.

1. 전처리된 원천 행에서 실제 Fact와 Signal이 생성된다.
2. Tier 0·1은 중요 모집단 전체에 결정적으로 실행된다.
3. 라우터 후보가 다섯 경로의 합집합으로 생성된다.
4. AI가 필수검사를 제거할 수 없다.
5. Coverage Auditor가 중요 계정·주장의 빈칸을 차단한다.
6. B2B 세 Cycle이 거래 단위로 심화검사를 수행한다.
7. 현금흐름과 원가배분을 재계산한다.
8. 각 이슈가 오류금액·반대 증거·추가 절차를 포함한다.
9. 분개는 근거 있는 후보로만 생성된다.
10. Full·Boundary·Not Assessable가 실제 권한과 데이터에 따라 구분된다.
11. 합격 기준과 전문가 검토를 통과한 Pack만 Full로 승격된다.
12. 기존 Trust Kernel과 현재 버전 회귀 테스트가 유지된다.

## 17. 후속 작업자를 위한 HANDOFF

```text
HANDOFF

목표:
현재 Trusted CEO Agent 구현을 보존하면서 B2B 서비스업의 계약·매출,
현금흐름·운전자본, 프로젝트 원가·원가배분에 대해 시니어 회계사와
일부 매니저급의 1차 검토 초안을 생성하도록 확장한다.

먼저 읽을 문서:
1. docs/PRD.md
2. docs/ARCHITECTURE_DECISIONS.md
3. docs/superpowers/specs/2026-07-17-trusted-ceo-agent-plugin-design.md
4. docs/superpowers/specs/2026-07-17-senior-accountant-review-expansion-design.md

확정 원칙:
- 현재 구현 완료 전에는 확장 구현을 시작하지 않는다.
- 라우터는 전문 판단을 발명하지 않는다.
- 후보 Pack은 Mandatory, Mission, Data, Signal, AI 제안의 합집합이다.
- AI는 Pack을 추가할 수 있지만 필수검사를 제거할 수 없다.
- Coverage Auditor가 중요 계정·주장의 공백을 차단한다.
- 전문 깊이는 검증된 Pack과 결정적 Component가 담당한다.
- AI는 Issue Evidence Packet 안에서만 추론한다.
- Full·Boundary·Not Assessable를 구분한다.
- 기존 Trust Kernel과 HITL을 재사용한다.

시작 작업:
1. 현재 구현 완료 상태와 전체 테스트를 검증한다.
2. 이 문서 2장의 여섯 Gap을 코드 증거로 감사한다.
3. 기존 동작을 보존하는 구현 계획을 작성한다.
4. 계획을 사용자에게 승인받은 뒤 구현한다.

금지:
- 기존 미커밋 변경 덮어쓰기
- 기존 Schema 의미의 무버전 변경
- AI 단독 라우팅
- 필수검사 예산 생략
- 전문가 검토 없는 Full Pack 승격
- 최종 회계처리·감사의견 자동 확정
```

