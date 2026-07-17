# Trusted CEO Agent 전문추론 Kernel과 Knowledge Foundry 설계

- 상태: 사용자 승인 후 작성된 검토용 설계
- 기준일: 2026-07-17
- 적용 시점: 현재 플러그인 구현·검증과 시니어 회계사급 검토 확장 구현이 완료된 뒤
- 목적: 전문추론 지식을 일회성으로 작성하지 않고, POC·실사용·전문가 피드백을 통해 안전하게 개선하는 영구 시스템 정의
- 최종 책임: 회계사·변호사·노무사·세무사 등 해당 분야 전문가와 고객 책임자

## 0. 문서의 위치와 적용 순서

이 문서는 다음 문서를 대체하지 않는다.

1. `docs/PRD.md`
2. `docs/ARCHITECTURE_DECISIONS.md`
3. `docs/superpowers/specs/2026-07-17-trusted-ceo-agent-plugin-design.md`
4. `docs/superpowers/specs/2026-07-17-senior-accountant-review-expansion-design.md`

이 문서는 위 설계에 다음 두 하위 시스템을 추가하는 별도 vNext 설계다.

- `Professional Reasoning Kernel`: 여러 도메인에 공통으로 적용하는 안정적인 전문검토 사고 순서
- `Knowledge Foundry`: 지식·절차·반증·테스트를 계속 만들고 검증하며 승인된 버전으로 배포하는 개선 시스템

### 0.1 충돌 방지 규칙

- 현재 구현 중인 코드와 테스트를 이 문서를 이유로 바로 수정하지 않는다.
- 기존 Trust Kernel, Artifact Store, Evidence Core, Pack Loader, Reasoning Job, HITL Gate, Validator를 재사용한다.
- 기존 Artifact ID, Pack ID, Schema를 조용히 변경하지 않는다.
- 변경이 필요하면 새 Schema 버전, migration, compatibility test를 사용한다.
- 기존 Bounded AI Reasoning의 allowlist와 숫자 인용 제한을 약화하지 않는다.
- 기존 Coverage Auditor와 `Full / Boundary / Not Assessable` 판정을 유지한다.
- Knowledge Foundry는 분석 실행 중 활성 Pack을 수정할 수 없다.
- 새 기능은 별도 모듈·Artifact·명령으로 추가하고 기존 구현의 완료 기준선 위에 연결한다.

### 0.2 문서 간 책임 분리

| 문서 | 책임 |
|---|---|
| 기본 플러그인 설계 | 신뢰 경계, Artifact, Pack 실행, Reasoning Job, HITL |
| 시니어 회계사급 확장 설계 | Router, Coverage, Tier 0~3, 전문 Cycle, Issue Evidence Packet |
| 이 문서 | 전문지식의 구성, 깊이 기준, 실패 학습, 검증, 승격, 배포, 회수 |

## 1. 핵심 결정

Knowledge Foundry는 일회성 POC 개선 방법이 아니라 제품 수명 동안 유지되는 시스템이다.

시스템은 두 실행면을 엄격히 분리한다.

### 1.1 Analysis Plane

고객 데이터를 실제로 분석하는 실행면이다.

- 승인된 불변 `Knowledge Release`만 사용한다.
- 실행 시작 시 Release ID, Pack hash, Kernel hash, Prompt hash를 고정한다.
- 실행 중 피드백이나 모델 제안으로 지식을 변경하지 않는다.
- 동일 입력과 동일 Release의 결정적 Fact·Signal·계산은 동일해야 한다.
- 결과에는 사용한 Release와 각 지식 카드의 출처를 기록한다.

### 1.2 Knowledge Plane

지식과 검토능력을 개선하는 별도 실행면이다.

- POC, 합성사례, 전문가 리뷰, 실사용 피드백을 수집한다.
- 실패의 근본 원인을 분류한다.
- LLM이 수정 후보를 제안할 수 있다.
- 출처, 의미 차이, 영향 범위, 회귀테스트를 검증한다.
- 필요한 전문가가 승인한 새 버전만 Release로 승격한다.
- 이전 Release를 보존하고 즉시 rollback할 수 있어야 한다.

### 1.3 두 실행면의 불변조건

```text
Analysis Plane
  immutable Knowledge Release
           |
           v
  data -> facts -> signals -> issue packets -> human draft
           |
           v
  feedback candidate only
           |
           v
Knowledge Plane
  triage -> patch proposal -> grounding -> tests -> approval -> new release
```

- Analysis Plane에서 Knowledge Plane으로는 `Feedback Record`만 전달한다.
- Knowledge Plane에서 Analysis Plane으로는 승인·서명된 `Knowledge Release`만 전달한다.
- 모델 출력, 고객 의견, 단일 전문가 의견은 즉시 운영 지식이 되지 않는다.

## 2. 목표와 비목표

### 2.1 목표

- “전문 사고법 + 규범지식 + 절차 + 반증”을 실행 가능한 단위로 만든다.
- 시니어 회계사와 일부 매니저급의 1차 검토 깊이를 측정 가능한 계약으로 정의한다.
- 회계·현금흐름·원가배분을 포함한 전문 Cycle을 같은 깊이 기준으로 구축한다.
- 법·노무·세무 등 다른 도메인을 공통 사고틀에 억지로 끼우지 않고 고유 규범과 절차를 유지한다.
- POC에서 발견된 누락·오탐·오판을 올바른 계층의 수정으로 연결한다.
- 한 문제를 고치면서 기존 정답을 망가뜨리는 회귀를 차단한다.
- 지식의 출처, 관할, 시행일, 검증상태, 승인자를 추적한다.
- 전문가의 시간을 전체 시스템 검토가 아니라 고위험 지식 단위에 집중시킨다.
- 시스템이 무엇을 아는지뿐 아니라 무엇을 아직 검증하지 못했는지 표시한다.

### 2.2 비목표

- 모델이 실시간으로 자기 시스템 프롬프트를 덮어쓰는 자가학습
- 사용자 피드백을 검증 없이 정답으로 등록
- LLM 자유서술을 전문지식 저장소로 사용
- 회계·법·노무·세무의 최종 전문가 결론 자동 확정
- 출처와 적용시점이 없는 규범을 Full authority로 사용
- 테스트 실패 중인 Patch의 운영 반영
- 전문가 승인 없이 `expert_reviewed`나 `full` 상태 부여
- 모든 실패를 프롬프트 문장 추가로 해결

## 3. 전문추론의 기본 구조

전문추론은 큰 시스템 프롬프트 하나가 아니라 다음 자산을 조합해 실행한다.

1. `Economic Event Model`
2. `Professional Method Card`
3. `Norm Card`
4. `Expectation Card`
5. `Procedure Card`
6. `Counter-Hypothesis Card`
7. `Cross-domain Trigger Card`
8. 결정적 Component
9. Issue Evidence Packet
10. Bounded AI Reasoning

### 3.1 Economic Event Model

도메인보다 먼저 경제적 사건을 중립적으로 표현한다.

- 당사자
- 역할
- 권리
- 의무
- 자원과 통제
- 대가
- 조건
- 발생일과 효력일
- 이행·청구·지급·취소 상태
- 관련 문서와 시스템 이벤트
- 금액·수량·통화
- 인센티브와 이해상충

회계·법·노무·세무 Pack은 같은 사건을 각자의 관점으로 해석한다. 한 도메인의 결론을 다른 도메인의 사실로 복사하지 않는다.

### 3.2 Professional Reasoning Kernel

Kernel은 도메인에 공통인 사고 순서를 제공한다.

1. 분석 대상 사건·모집단·기간을 확정한다.
2. 당사자·권리·의무·인센티브를 구조화한다.
3. 사용 가능한 증거와 누락된 증거를 구분한다.
4. 정상이라면 나타나야 할 관계와 수치를 만든다.
5. 실제 관찰과 기대를 비교해 모순과 잔차를 찾는다.
6. 오류·부정·정상적 사업사유를 포함한 복수 가설을 생성한다.
7. 규범의 요건·예외·관할·시행일을 적용한다.
8. 각 가설을 구별하는 검사를 실행하거나 요청한다.
9. 지지 증거와 반대 증거를 함께 평가한다.
10. 금액·기간·현금·운영·법적 영향을 계산한다.
11. 다른 도메인의 Trigger와 결론 충돌을 확인한다.
12. 결론, 조건, 한계, 추가 절차를 구조화한다.

Kernel은 비교적 안정적으로 유지한다. 개별 규정, 업종 관행, 임계치, 예외조건을 Kernel 프롬프트에 누적하지 않는다.

### 3.3 도메인별 Method

각 도메인은 공통 Kernel 위에 별도 Method Pack을 가진다.

#### 회계

- 거래 Cycle과 재무제표 주장
- 인식·측정·표시·공시
- 법적 형식과 경제적 실질
- 기간귀속과 cutoff
- 계정 대사와 roll-forward
- 추정·편향·경영진 override
- 잠재 오류금액과 수정분개
- 감사증거의 충분성·적합성

#### 법

- 관할과 효력 발생시점
- 계약·행위의 법적 성격
- 성립·유효성·집행가능성
- 권리·의무·위반·구제수단
- 책임과 손해 범위
- 증거와 절차적 쟁점

#### 노무

- 근로자성·사용자성
- 지휘·통제·경제적 종속
- 근로시간·임금·수당·복리후생
- 안전·차별·개인정보
- 징계·해고·퇴직
- 집단적 노사관계

#### 세무

- 납세의무자와 과세사건
- 거래 성격과 귀속시기
- 과세표준·세율·공제
- 원천징수·부가가치세
- 손금·필요경비
- 특수관계·이전가격
- 신고·증빙·제척기간

## 4. 전문 깊이 계약

각 Issue Family와 전문 Pack은 다음 `Depth Contract`를 충족해야 한다.

### D1. 사건과 모집단

- 검토 대상 경제적 사건을 정의한다.
- 모집단의 시작·종료·제외조건을 명시한다.
- 건수·금액·기간 Coverage를 계산한다.

### D2. 계정·주장·의사결정 영향

- 관련 계정과 재무제표 주장을 연결한다.
- 현금흐름·운영·고객·계약 영향을 연결한다.
- 경영 의사결정과 전문 검토 필요성을 구분한다.

### D3. 정상 기대관계

- 정상 거래라면 맞아야 하는 문서·시스템·숫자 관계를 정의한다.
- 기대관계의 근거와 적용 제외조건을 기록한다.

### D4. 가설 집합

- 명백한 오류
- 부정 또는 override 가능성
- 정상적 사업사유
- 데이터·매핑 오류
- 둘 이상의 원인이 함께 존재하는 복합가설

### D5. 규범 요소

- 적용 규범과 출처
- 관할과 시행일
- 필수 요건
- 예외와 선택사항
- 상충 규범과 해석 불확실성

### D6. 구별 절차

- 가설들을 구별할 최소 절차를 정의한다.
- 각 절차의 입력, 계산, 판정조건, 실패상태를 명시한다.

### D7. 증거와 반대 증거

- 필수 Evidence role을 정의한다.
- 지지 증거와 반대 증거를 분리한다.
- 증거가 없을 때 결론을 강하게 만들지 않는다.

### D8. 정량화

- 잠재 오류금액
- 확정금액과 범위금액
- 기간별 손익·재무상태 영향
- 현금과 비현금 영향
- 계산 불가 사유

### D9. 회계처리·조치 후보

- 조건부 회계처리 후보
- 수정분개 후보
- 운영·통제 개선 후보
- 사람에게 필요한 추가 질문과 문서

### D10. Cross-domain Trigger

- 다른 도메인 검토가 필요한 조건
- 전달할 공통 사실
- 전달하면 안 되는 미확정 결론
- 도메인 간 충돌 상태

### D11. 한계와 권한

- `Full / Boundary / Not Assessable` 조건
- 전문가 검토가 필수인 상황
- 금지된 결론
- 누락 Coverage

### D12. 정답·반증 사례

최소한 다음 사례 유형을 가져야 한다.

- 정상
- 명백한 오류
- 경계값
- 반대 증거가 있는 오류 후보
- 데이터 누락
- 매핑 오류
- 복합원인
- 서로 다른 원인이 같은 Signal을 만드는 사례
- Cross-domain 충돌

### 4.1 Depth Gate

- D1~D12 중 하나라도 구조적으로 없으면 `machine_draft` 이상으로 승격할 수 없다.
- 규범 출처와 시행일이 없으면 `source_grounded`로 승격할 수 없다.
- 반대 증거·경계사례 테스트가 없으면 `synthetic_tested`로 승격할 수 없다.
- 전문가 검토 전에는 해당 분야의 `Full` 결론을 허용하지 않는다.
- 세 Cycle 중 일부만 Depth Contract를 충족한 상태에서 전체 회계범위를 시니어급이라고 표시하지 않는다.

## 5. Knowledge Artifact

Knowledge Foundry는 장문 위키 대신 작고 형식화된 Artifact를 사용한다.

### 5.1 공통 메타데이터

모든 지식 Artifact는 다음을 가진다.

- `artifact_id`
- `artifact_type`
- `domain`
- `issue_family_id`
- `version`
- `status`
- `jurisdiction`
- `effective_from`
- `effective_to`
- `source_refs`
- `author`
- `reviewer_refs`
- `created_at`
- `supersedes`
- `content_hash`
- `test_refs`

### 5.2 주요 Artifact

#### Method Card

전문가가 해당 이슈를 검토하는 사고 순서와 필수 질문을 정의한다.

#### Norm Card

규범의 요건·예외·적용범위·시행일을 원자적인 주장 단위로 저장한다.

#### Expectation Card

정상이라면 성립해야 할 정량·정성 관계와 적용 제외조건을 정의한다.

#### Procedure Card

검토 절차의 입력, 모집단, 계산, 결과, 실패처리, 필요한 증거를 정의한다.

#### Counter-Hypothesis Card

주요 가설에 대한 정상적 대안 설명, 반대 증거, 구별 절차를 정의한다.

#### Cross-domain Trigger Card

공통 경제적 사실이 다른 전문영역 검토를 요구하는 조건을 정의한다.

#### Test Case와 Oracle

분석 입력과 분리된 정답, 금지 결론, 필요한 증거·반증·Coverage를 보유한다.

#### Feedback Record

사용자·전문가·평가 시스템이 발견한 문제를 원본 실행과 연결한다.

#### Patch Proposal

수정 대상, 변경 전후 의미, 근거, 영향 범위, 추가 테스트를 담는다.

#### Knowledge Release

승인된 Kernel·Pack·Card·Component·Prompt template의 정확한 버전 집합이다.

## 6. 지식 신뢰등급

지식은 다음 단계를 순서대로 승격한다.

```text
machine_draft
    -> source_grounded
    -> synthetic_tested
    -> poc_stable
    -> expert_reviewed
    -> full
```

### machine_draft

- LLM 또는 비전문가가 만든 후보
- Analysis Plane 사용 금지

### source_grounded

- 권위 있는 원문과 요건별 연결 완료
- 개발·Boundary 분석에서만 제한적으로 사용

### synthetic_tested

- 정상·오류·경계·반증·누락 사례 통과
- 운영 shadow 평가 가능

### poc_stable

- 반복 POC에서 알려진 실패가 재현되지 않음
- `Full` 전문 결론은 여전히 금지

### expert_reviewed

- 해당 이슈 Family를 검토할 자격과 경험이 있는 전문가가 승인
- 고위험 규범은 독립된 추가 검토를 요구할 수 있음

### full

- Depth Contract, 회귀테스트, 출처, 전문가 승인, 운영 Gate를 모두 통과
- 이 상태도 최종 법적·직업적 판단 권한을 시스템에 부여하지 않는다.

## 7. Knowledge Foundry 영구 루프

### 7.1 입력

- 합성 POC 결과
- Oracle 평가 실패
- 전문가 리뷰
- 실제 사용자의 이의제기
- 새로운 업종·데이터 구조
- 규범 변경
- 반복되는 `Not Assessable`
- 거짓 양성·거짓 음성
- 금액 계산 차이
- 도메인 간 결론 충돌
- 사용자에게 이해되지 않는 출력

### 7.2 단계

1. `Feedback Record`를 원본 Run과 Release에 연결한다.
2. 재현 가능한 실패인지 확인한다.
3. 실패 분류와 심각도를 지정한다.
4. 잘못된 계층을 찾아 `Patch Proposal`을 만든다.
5. 권위 있는 출처와 적용 범위를 확인한다.
6. 실패를 재현하는 Test Case를 먼저 추가한다.
7. 정상 대조군과 반대사례를 함께 추가한다.
8. Patch를 적용한 Release Candidate를 만든다.
9. 대상 Family와 전체 회귀테스트를 실행한다.
10. 구조·출처·동작·안전 Gate를 통과시킨다.
11. 필요한 전문가 승인을 받는다.
12. 새 Knowledge Release를 발행한다.
13. shadow 또는 제한된 범위에서 이전 Release와 비교한다.
14. 문제가 생기면 이전 Release로 rollback한다.

### 7.3 영구 운용

초기에는 합성 POC를 높은 빈도로 실행해 기본 지식을 구축한다. 출시 이후에도 다음 시점에 같은 루프를 계속 실행한다.

- 새로운 고객 데이터 유형이 들어올 때
- 새로운 업종으로 확장할 때
- 규범이나 회사 정책이 바뀔 때
- 전문가가 결론이나 절차에 이의를 제기할 때
- 특정 거짓 양성·음성이 반복될 때
- Coverage Gap이 반복될 때
- Cross-domain 충돌이 새로 발견될 때

POC는 초기 행사로 끝나지 않고 Knowledge Plane의 상시 검증 도구로 남는다.

## 8. 실패 분류와 수정 라우팅

모든 실패는 먼저 원인을 분류한다. 프롬프트 수정은 기본값이 아니다.

| 실패 유형 | 1차 수정 대상 | 예시 |
|---|---|---|
| ingestion | parser·source adapter | 날짜·금액 파싱 실패 |
| mapping | canonical mapping·event model | 이메일 검수를 이행사건으로 연결하지 못함 |
| fact | deterministic materializer | 계약기간 Fact 오류 |
| calculation | Component | cutoff 오류금액 계산 오류 |
| expectation | Expectation Card | 업종상 정상 계절성을 이상으로 봄 |
| norm | Norm Card | 예외 규정 또는 시행일 누락 |
| procedure | Procedure Card | 필요한 대사·구별검사 미실행 |
| counter | Counter-Hypothesis Card | 정상적 사업사유를 생성하지 못함 |
| routing | Router·Coverage | 중요 계정 Pack 미선택 |
| cross-domain | Trigger Card | 근로자성·원천징수 연계 누락 |
| reasoning | Kernel step·Reasoning contract | 근거는 있으나 가설 비교 실패 |
| presentation | output schema·writer | 확정·추정·판단불가 표현 혼동 |
| evaluation | Oracle·rubric | 정답 정의가 잘못됨 |

### 8.1 Patch 최소요건

모든 Patch Proposal은 다음을 포함한다.

- 재현 가능한 실패 Run
- 실패 유형
- 근본 원인
- 수정 대상 Artifact
- 변경 전후 의미 차이
- 권위 있는 출처 또는 출처 불필요 사유
- 새 Test Case
- 영향받는 Issue Family와 도메인
- 기존 결과에 대한 예상 영향
- rollback 조건
- 필요한 승인자

## 9. 시스템 프롬프트 관리

### 9.1 원칙

- 시스템 프롬프트는 위키가 아니다.
- Kernel 프롬프트는 짧고 안정적인 사고 순서와 신뢰 규칙만 담는다.
- 도메인 지식은 versioned Card와 Pack으로 공급한다.
- Reasoning Job은 필요한 Card만 Issue Evidence Packet과 함께 컴파일한다.
- 실행에는 `prompt_template_hash`와 `knowledge_release_id`를 기록한다.

### 9.2 프롬프트를 수정하는 경우

- 여러 Issue Family에서 같은 사고단계 누락이 반복됨
- 가설과 반증을 구조적으로 비교하지 못함
- 증거 없는 결론을 지속적으로 확정함
- 상태·권한·출력 계약을 반복적으로 위반함

단일 규정, 단일 업종 예외, 단일 데이터 매핑 문제는 프롬프트에 추가하지 않는다.

### 9.3 프롬프트 변경 Gate

- 변경 전후 semantic diff
- 대상 실패 재현 테스트
- 전체 Reasoning regression
- 숫자·Evidence ref·allowlist 보안 테스트
- 거짓 확신 증가 여부 평가
- 승인과 rollback 버전

## 10. 전문가 피드백 루프

전문가에게 시스템 전체를 한 번에 검토하도록 요청하지 않는다. 작은 검토 단위로 나눈다.

### 10.1 검토 단위

- 하나의 Issue Family
- 하나의 Norm Card 집합
- 하나의 Procedure
- 하나의 반대가설 집합
- 하나의 정량화 방식
- 소수의 합성사례와 시스템 결과
- 하나의 Cross-domain 충돌

### 10.2 전문가 피드백 유형

- 놓친 이슈
- 거짓 양성
- 잘못된 규범
- 누락된 예외
- 잘못된 데이터 매핑
- 증거 부족
- 누락된 반대가설
- 금액 계산 오류
- 잘못된 확신 수준
- Cross-domain 영향 누락
- 실무적으로 사용할 수 없는 표현

### 10.3 검토 우선순위

전문가 시간은 다음 순서로 배분한다.

1. 손익·현금·법적 책임 영향이 큰 이슈
2. 서로 다른 Pack 결론이 충돌하는 이슈
3. 규범 적용 경계와 예외
4. 반복되는 거짓 양성·음성
5. 여러 Issue Family가 공유하는 Norm·Method
6. Full 승격을 앞둔 Pack

### 10.4 의견 불일치

- 사실, 규범 해석, 중요성, 추가절차 의견을 분리한다.
- 전문가 의견을 단일 정답으로 덮어쓰지 않는다.
- 관할·회사정책·가정 차이를 기록한다.
- 중요한 불일치는 `expert_disagreement` 상태로 남긴다.
- 합의되지 않은 지식은 Full로 승격하지 않는다.

## 11. 합성 POC와 회귀사례

### 11.1 POC 목적

POC의 목적은 좋은 보고서를 시연하는 것이 아니라 현재 지식의 실패점을 적극적으로 찾는 것이다.

- 숨겨진 오류를 찾는가
- 정상 거래를 문제로 오인하지 않는가
- 반대 증거가 결론을 바꾸는가
- 데이터가 부족하면 멈추는가
- 금액과 기간을 정확히 계산하는가
- 다른 도메인 Trigger를 놓치지 않는가

### 11.2 합성 회사 생성

합성 회사 데이터는 정상적인 경제적 구조를 먼저 가진다.

- 계약과 고객
- 청구와 수금
- 서비스 이행
- 원장과 분개
- 프로젝트와 원가
- 직원과 근로시간
- 세금계산서와 신고 관련 자료

오류는 별도 Seeder가 주입한다.

- 조기·지연 인식
- 중복·누락
- 부적절한 원가배분
- 회수위험
- 현금흐름 분류 오류
- 경영진 override
- 계약 이면합의
- 직원·외주 분류 문제
- 원천징수·부가세 문제
- 복합원인

Oracle은 runtime input과 Reasoning Job에서 물리적으로 분리한다.

### 11.3 실패의 영구 고정

확인된 모든 결함은 다음 둘을 함께 만든다.

1. 해당 계층의 Patch
2. 같은 결함의 재발을 막는 Regression Case

둘 중 하나만 있으면 수정 완료로 보지 않는다.

## 12. 전문 Cycle 적용

회계 분야의 첫 Release 범위는 다음 세 Cycle을 모두 포함한다.

### 12.1 계약·매출

- 계약 식별과 변경
- 수행의무와 이행
- 거래가격과 배분
- 인식시기와 cutoff
- 청구·수금·계약자산·계약부채
- 취소·환불·할인·이면합의
- 세금계산서·부가세·판매수수료 Trigger

### 12.2 현금흐름·운전자본

- 현금·제한현금·차입·팩토링
- 영업·투자·재무 분류
- 매출채권·매입채무·재고·선수금
- aging과 회수·지급 cohort
- EBITDA와 영업현금흐름 bridge
- 고객·공급자 집중
- 지급 지연·세금·급여 체납
- covenant와 유동성 Trigger

### 12.3 프로젝트 원가·원가배분

- 원가 pool과 배부대상
- 직접·간접원가 분류
- 배부기준과 인과관계
- 정상조업도와 유휴원가
- 근로시간·외주·공통비
- WIP·진척률·완료예정원가
- 자본화와 비용화
- 저마진·손실 프로젝트와 변경계약
- 이전가격·노무·세무 Trigger

각 Cycle은 같은 Depth Contract와 승격 Gate를 통과해야 한다. 구현 순서는 달라도 “시니어 회계사급 세 Cycle”이라는 제품 표시는 세 Cycle 모두 기준을 충족한 뒤에만 허용한다.

## 13. Cross-domain 확장

### 13.1 공통 사실과 전문 판단 분리

예를 들어 외주 인력에게 정기적으로 동일 금액을 지급한 사실은 공통 Fact다.

- 회계: 비용 귀속·미지급비용·원가배분
- 노무: 근로자성·근로시간·퇴직급여
- 세무: 원천징수·부가세·손금
- 법: 계약 성격·책임·분쟁 가능성

각 도메인은 같은 Fact를 사용하지만 다른 주장·규범·절차를 가진다.

### 13.2 통합자의 권한

Cross-domain Integrator는 다음만 수행한다.

- 공통 Fact 정렬
- 결론 간 일치·충돌 표시
- 한 도메인 결론이 다른 도메인에 미치는 영향 표시
- 필요한 전문가 조합 제안

Integrator는 전문 Pack의 결론을 임의로 덮어쓰지 않는다.

## 14. 검증 체계

### 14.1 구조 검증

- Schema
- ID와 참조 무결성
- 관할·시행일
- 출처 존재
- Depth Contract 완전성
- supersedes와 dependency cycle

### 14.2 지식 검증

- 출처가 실제 주장과 일치하는지
- 예외와 적용 제외조건이 포함되는지
- 상충 규범이 표시되는지
- 규범 변경 시 영향받는 Pack을 찾는지

### 14.3 동작 검증

- 정상 사례 거짓 양성
- 오류 사례 거짓 음성
- 경계사례의 조건부 결론
- 반대 증거에 따른 결론 변화
- 데이터 누락 시 Not Assessable
- 금액과 분개 후보 계산
- Cross-domain Trigger

### 14.4 회귀 검증

- Patch 대상 Family
- 같은 Norm·Method를 공유하는 Family
- 세 전문 Cycle 전체
- 기존 Trust Kernel과 Reasoning allowlist
- 결정성·병렬성·재실행 동등성

### 14.5 Release 검증

- 이전 Release와 결과 diff
- 새 이슈·사라진 이슈·등급 변화
- Coverage 변화
- 오류금액 변화
- 근거 없는 확신 증가
- 처리시간과 실행예산 변화

## 15. 품질 측정

단일 “전문가 점수”를 사용하지 않는다. Issue Family별로 다음을 측정한다.

- seeded issue recall
- 정상사례 precision
- 중요 오류 누락률
- Evidence role 충족률
- 반대가설·반대증거 Coverage
- 오류금액·기간 계산 정확도
- 정답 상태와 `Full / Boundary / Not Assessable` 일치
- Cross-domain Trigger 재현율
- 전문가 수정 유형과 수정량
- 전문가가 추가한 핵심 이슈 수
- 반복 실패율
- regression escape 수
- Release별 성능 변화

정확한 합격 임계치는 Issue Family와 위험도별로 설정한다. 임계치 변경도 versioned policy와 승인을 요구한다.

## 16. 오류·중단·회수

### 16.1 출처 충돌

- 충돌을 숨기지 않는다.
- 적용 관할·기간·사실관계를 분리한다.
- 해결되지 않으면 Boundary 또는 전문가 검토로 내린다.

### 16.2 규범 만료

- 실행일이 `effective_to` 이후이면 자동으로 Full 사용을 차단한다.
- 대체 Norm이 없으면 관련 Issue Family를 Not Assessable로 표시한다.

### 16.3 테스트 실패

- Release 발행을 차단한다.
- 운영 Release는 그대로 유지한다.

### 16.4 전문가 불일치

- 합의되지 않은 Patch를 활성화하지 않는다.
- 불일치 원인과 필요한 사실·질문을 보존한다.

### 16.5 운영 회수

- Release는 immutable하다.
- 문제 Release를 삭제하지 않고 deprecated·revoked 상태로 바꾼다.
- 신규 실행은 직전 안전 Release로 rollback한다.
- 이미 생성된 결과에는 사용 Release를 그대로 보존한다.

## 17. 권한

| 주체 | 가능 | 불가능 |
|---|---|---|
| LLM | 실패 분류 후보, Card·Patch·Test 초안 | 자기 승인, 운영 Release 변경 |
| 결정적 엔진 | Schema·출처·테스트·hash 검증 | 전문 해석 창작 |
| Maintainer | Release Candidate 구성, 배포 실행 | 전문가 승인 위조 |
| 도메인 전문가 | Norm·Procedure·결론 검토·승인 | 원본 실행기록 변경 |
| 고객 사용자 | 이의제기·추가자료·맥락 제공 | 피드백 즉시 정답 등록 |
| Trust Kernel | 권한·상태·lineage·최종 Gate | 전문 결론 대신 결정 |

## 18. 구현 단계

현재 플러그인 구현과 시니어 회계사급 확장 구현을 먼저 완료·검증한 뒤 다음 순서로 진행한다.

### Phase 0. 기준선 고정

- 현재 구현 전체 테스트
- 기존 Artifact와 Pack snapshot
- 현재 Reasoning output baseline

### Phase 1. Knowledge Artifact와 Registry

- Card Schema
- Feedback·Patch·Release Schema
- trust level과 authority
- lineage·hash·supersedes

### Phase 2. Professional Reasoning Kernel

- 안정적인 12단계 Kernel
- Domain Method 연결
- Reasoning Job compiler
- prompt·knowledge hash

### Phase 3. Knowledge Foundry

- feedback capture
- failure triage
- patch proposal
- source grounding
- test generation과 oracle
- release candidate와 promotion
- rollback

### Phase 4. 세 회계 Cycle 심화

- 계약·매출
- 현금흐름·운전자본
- 프로젝트 원가·원가배분
- 각 Cycle의 D1~D12
- 세 Cycle 통합 회귀와 Cross-cycle Stand-back

### Phase 5. 전문가 검토와 Full 승격

- 작은 검토 단위 패킷
- 의견 불일치 처리
- Pack별 승인
- Full Release Gate

### Phase 6. 법·노무·세무 확장

- 공통 Economic Event Model 재사용
- 도메인 고유 Method·Norm·Procedure
- Cross-domain Trigger와 Integrator
- 도메인별 별도 전문가 승인

## 19. 완료 조건

다음 조건을 모두 충족해야 이 설계를 구현한 것으로 본다.

1. Analysis Plane과 Knowledge Plane이 코드·권한·Artifact로 분리된다.
2. 분석 실행 중 활성 Knowledge Release가 변경되지 않는다.
3. 모든 결과가 정확한 Release·Pack·Prompt hash를 기록한다.
4. POC·전문가·사용자 피드백이 구조화된 Feedback Record가 된다.
5. 모든 수정은 실패 분류에 따라 올바른 계층으로 라우팅된다.
6. 모든 Patch가 의미 diff, 출처, 영향범위, 새 테스트, rollback 조건을 가진다.
7. 모든 확인된 결함이 Patch와 Regression Case를 함께 남긴다.
8. D1~D12를 충족하지 못한 Pack은 시니어급 또는 Full로 승격되지 않는다.
9. 전문가 승인 없는 지식은 전문 Full 결론에 사용되지 않는다.
10. 시스템 프롬프트가 규범·예외의 장문 위키로 사용되지 않는다.
11. 세 회계 Cycle 모두 같은 깊이 계약과 회귀 Gate를 통과한다.
12. 새 Release가 실패하면 이전 Release로 복귀할 수 있다.
13. 법·노무·세무 결론은 각 도메인의 관할·시행일·전문가 권한을 유지한다.
14. 기존 Trust Kernel, Evidence lineage, HITL, 최종 Validator를 약화하지 않는다.

## 20. 후속 작업자를 위한 HANDOFF

```text
HANDOFF

목표:
Trusted CEO Agent의 전문추론 지식을 일회성 프롬프트나 수동 POC 수정으로
관리하지 않고, 제품 수명 동안 검증·승격되는 영구 Knowledge Foundry로 구현한다.

먼저 읽을 문서:
1. docs/PRD.md
2. docs/ARCHITECTURE_DECISIONS.md
3. docs/superpowers/specs/2026-07-17-trusted-ceo-agent-plugin-design.md
4. docs/superpowers/specs/2026-07-17-senior-accountant-review-expansion-design.md
5. docs/superpowers/specs/2026-07-17-professional-reasoning-knowledge-foundry-design.md

확정 원칙:
- Analysis Plane은 승인된 불변 Release만 사용한다.
- Knowledge Plane만 Patch를 만들고 검증하며 새 Release를 발행한다.
- POC는 초기 행사가 아니라 상시 지식 검증 수단이다.
- LLM은 Patch를 제안하지만 승인하거나 자기 프롬프트를 수정하지 못한다.
- 프롬프트는 위키가 아니며 지식은 typed Card와 Pack으로 관리한다.
- 모든 결함은 Patch와 Regression Case를 함께 남긴다.
- 전문 깊이는 D1~D12 Depth Contract로 판단한다.
- 회계 세 Cycle은 모두 같은 깊이 기준을 통과해야 한다.
- Full은 출처·테스트·전문가 승인 없이 부여하지 않는다.
- 기존 Trust Kernel, Router, Coverage, HITL을 재사용한다.

첫 구현 작업:
1. 현재 구현과 시니어 확장 구현의 완료 기준선을 검증한다.
2. 새 Artifact가 기존 Schema와 충돌하지 않는 Gap 분석을 작성한다.
3. Knowledge Artifact와 Release Registry의 구현 계획을 작성한다.
4. 계획을 사용자에게 승인받은 뒤 구현한다.

금지:
- 런타임 자기수정
- 사용자 피드백 즉시 학습
- 시스템 프롬프트에 규정·예외 계속 누적
- 테스트 없는 Patch
- 전문가 승인 없는 Full
- 기존 Artifact·Schema의 무버전 변경
```
