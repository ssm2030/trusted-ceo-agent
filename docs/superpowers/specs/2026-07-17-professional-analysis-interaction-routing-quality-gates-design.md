# 전문분석 상호작용·다중 도메인 라우팅·품질·성능 Gate 설계

- 상태: 사용자 승인 요구를 반영한 검토용 설계
- 기준일: 2026-07-17
- 적용 시점: 현재 플러그인 기준선 이후의 웹 실시간 연결, 전문추론, Knowledge Foundry 구현
- 목적: 사용자 답변을 불변 분석 리비전에 연결하고, 여러 전문 도메인을 빠뜨리지 않으며, 품질을 낮추지 않는 병렬성과 측정 가능한 속도 기준을 구현요건으로 고정

## 0. 문서 위치와 우선순위

이 문서는 다음 정본을 대체하지 않는 교차 구현계약이다.

1. `docs/superpowers/specs/2026-07-17-trusted-ceo-agent-plugin-design.md`
2. `docs/superpowers/specs/2026-07-17-trusted-ceo-agent-web-interface-design.md`
3. `docs/superpowers/specs/2026-07-17-senior-accountant-review-expansion-design.md`
4. `docs/superpowers/specs/2026-07-17-professional-reasoning-knowledge-foundry-design.md`
5. `docs/superpowers/specs/2026-07-17-knowledge-foundry-feedback-intake-design.md`

현재 플러그인 기준선과 기존 리비전·승인·Trust Kernel은 그대로 유지한다. 이 문서는 후속 구현계획이 반드시 포함해야 하는 추가 계약을 고정한다.

충돌 시 다음 순서를 따른다.

1. 원본 불변성, 승인, 권한, 해시, Evidence lineage 등 Trust Kernel
2. 이 문서의 사용자 답변·다중 라우팅·품질·성능 Gate
3. 웹 표시와 편의 기능

### 금지

- 결과 질문과 분석 변경 답변을 같은 경로로 처리
- 웹이 분석 Artifact를 직접 수정
- 사용자 답변을 현재 리비전에 덮어쓰기
- 자연어 답변을 승인으로 간주
- 하나의 경제적 사건을 정확히 하나의 전문 도메인에만 배정
- AI 라우터가 필수 도메인·Pack을 제거
- 속도 목표를 맞추기 위해 필수 절차·반증·Coverage를 생략
- 병렬 실행 실패를 얕은 단일 답변으로 대체
- 근거·테스트·전문가 승인 없는 전문 Pack을 `Full`로 사용
- 기존 기본 플러그인 225초 목표를 미측정 Cross-domain 실행에 그대로 주장

## 1. 확정 요구사항

후속 구현계획은 다음 세 계약을 선택사항이 아닌 필수 작업으로 다룬다.

1. 질문 카드 UX뿐 아니라 `사용자 답변 -> 플러그인 검증 -> 새 불변 리비전`을 실제로 연결한다.
2. 도메인별 실행 깊이, 병렬 품질 Gate, 속도 SLO와 측정방법을 구현한다.
3. 공통 경제적 사건은 회계·노무·법무·세무 중 0개, 1개 또는 여러 개로 동시에 라우팅하며 전문성·품질·속도 설정의 근거를 버전과 승인으로 보존한다.

## 2. 상호작용을 두 경로로 분리

### 2.1 Analysis-affecting Human Response

분석의 의미나 범위를 바꾸는 답변이다.

- Mission과 고객 가설 확인·수정
- 데이터 의미, 열, 단위, 기간, source role 확인
- 데이터 미제공 또는 대체 자료 선택
- 분석 범위 포함·제외
- 문제 후보의 수용·반박·이견
- 심화검사 대상 선택
- 최종 문구·전문가 routing·전달 범위 변경 요청

이 답변은 플러그인의 검증된 mutation을 통해 새 분석 리비전을 만든다.

### 2.2 Result Question and Answer

완료되거나 현재 존재하는 실행본을 설명하는 읽기 전용 질문이다.

- 왜 이 문제가 표시됐는가
- 어떤 근거와 계산을 사용했는가
- 현재 결과로 무엇을 알 수 없는가
- 추가로 어떤 자료가 필요한가

이 질문과 답변은 분석 리비전, 승인, Pack, Grade, Final Result를 변경하지 않는다. 답변이 분석 오류 신고로 전환되면 Knowledge Foundry의 Feedback Preview와 Stage 1 승인으로 별도 라우팅한다.

두 경로의 API, 저장소, 권한, 화면 상태를 공유하지 않는다.

## 3. Human Action Card 계약

사용자에게 답변을 요구하는 모든 분석 단계는 구조화된 `HumanActionCard`를 제공한다.

### 3.1 필수 필드

```text
action_id
schema_version
run_id
base_revision
workflow_state
gate
action_type
title
question
why_asked
current_interpretation
evidence_refs
required
allowed_response_types
options
recommended_option_id
recommendation_reason
unanswered_effect
next_step_by_option
expires_at
content_hash
```

`recommended_option_id`는 추천할 근거가 있을 때만 사용한다. 규범적 선택, 이해상충, 전문 판단이 필요한 경우에는 추천을 비워 두고 구별에 필요한 사실을 제시한다.

### 3.2 화면의 고정 순서

카드는 다음 순서로 표시한다.

1. 왜 묻는가
2. 시스템의 현재 해석
3. 근거 또는 데이터 위치
4. 사용자가 지금 해야 할 일
5. 선택지와 추천 이유
6. 답하지 않거나 자료가 없을 때의 영향
7. 각 선택 후 다음 단계

내부 상태명, JSON Pointer, 해시만 보여주고 사용자의 행동을 설명하지 않는 카드는 허용하지 않는다.

### 3.3 응답 유형

카드별 allowlist에서 다음을 조합한다.

- `confirm`
- `choose_one`
- `choose_many`
- `free_text`
- `provide_data`
- `provide_alternative_evidence`
- `proceed_limited`
- `exclude_scope`
- `request_explanation`
- `request_changes`
- `stop`

`request_explanation`은 읽기 전용이며 새 리비전을 만들지 않는다. 나머지 분석 의미 변경 응답은 제출되면 새 리비전을 만든다.

### 3.4 데이터가 없을 때

데이터 요청 카드는 가능한 경우 다음 선택을 제공한다.

1. 지금 제공
2. 다른 자료로 대체
3. 자료 없이 제한 분석
4. 이번 범위에서 제외
5. 분석 중단

`proceed_limited`는 실패나 묵시적 동의가 아니다. 다음을 명시적으로 기록한다.

- `unavailable_reason`: not_collected, inaccessible, confidential, no_permission, time_limited, other
- 부족한 source role과 capability
- 실행 가능한 Procedure
- 실행 불가능한 Procedure
- 영향받는 Issue Family와 도메인
- 예상되는 `Boundary / Not Assessable / deep_review_pending`
- 사용자가 확인한 제한

같은 데이터 요청을 근거 변화 없이 반복하지 않는다.

회사 데이터가 전혀 없어 실제 문제를 검증할 수 없으면 분석계획과 자료요청만 만들고 문제 발견 결과를 생성하지 않는다.

## 4. 사용자 답변에서 새 리비전까지

### 4.1 Provider 계약

웹 `AnalysisProvider`는 최소 다음 메서드를 제공한다.

```text
getPendingAction(run_id, revision)
previewHumanResponse(run_id, expected_revision, action_id, response)
submitHumanResponse(
  run_id,
  expected_revision,
  action_id,
  action_content_hash,
  response,
  idempotency_key
)
```

`submitHumanResponse`는 웹 상태만 바꾸지 않는다. 실제 플러그인 mutation 명령을 호출한다.

### 4.2 플러그인 명령 경계

후속 구현계획은 현재 CLI 명명 규칙과 충돌을 확인한 뒤 다음 의미의 결정적 명령을 추가한다.

```text
pending-action
preview-human-response
submit-human-response
```

명령 이름은 구현계획에서 조정할 수 있지만 의미와 Gate는 바꿀 수 없다.

`submit-human-response`는 다음 순서로 동작한다.

1. `run_id`, `expected_revision`, `action_id`, `content_hash` 검증
2. Action Card가 현재 상태에서 활성인지 확인
3. response type과 payload Schema 검증
4. 권한과 개인정보 정책 확인
5. 응답을 별도 `HumanResponseRecord`로 생성
6. 응답이 허용하는 overlay 또는 Mission·mapping·scope 변경 계산
7. 영향받는 downstream 승인 목록 계산
8. staging에 완전한 새 snapshot 작성
9. 전체 Validator 실행
10. 새 revision 원자 publish
11. invalidated approval과 다음 pending action 반환

기존 snapshot과 Action Card는 수정하지 않는다.

### 4.3 답변과 승인 분리

웹 답변은 TTY 승인을 대신하지 않는다.

- 답변: 사실, 의미, 맥락, 선택, 변경 요청을 새 revision에 기록
- 승인: 현재 Gate의 정확한 diff·hash·revision을 TTY에서 별도 승인

사용자가 카드에서 `맞습니다`를 선택해도 해당 행동이 승인 Gate라면 플러그인은 `terminal_approval_required` 상태를 반환한다. 웹은 정확한 터미널 안내만 표시하고 Approval Record를 만들지 않는다.

### 4.4 동시성·중복·오류

- 모든 mutation은 `expected_revision`을 요구한다.
- stale revision은 `STALE_REVISION`으로 거부하고 현재 카드와 diff를 다시 가져온다.
- `idempotency_key`가 같은 동일 요청은 같은 receipt를 반환한다.
- 같은 key에 다른 payload가 오면 충돌로 거부한다.
- 만료되거나 hash가 바뀐 카드는 제출할 수 없다.
- 일부 필드만 저장하고 revision 생성에 실패하는 상태는 허용하지 않는다.
- Provider timeout 후에는 idempotency receipt를 먼저 조회한다.

### 4.5 제출 결과

```text
HumanResponseReceipt
  response_id
  run_id
  base_revision
  result_revision
  action_id
  response_hash
  affected_paths
  invalidated_approval_refs
  workflow_state
  pending_action_ref
  created_at
```

## 5. 공통 Economic Event와 다중 도메인 라우팅

### 5.1 단일 선택 금지

라우터는 one-of-four 분류기가 아니다.

```text
route(event) -> set[DomainRoute]
```

하나의 사건은 다음 결과를 가질 수 있다.

```text
event_123
  accounting: selected
  labor: selected
  legal: not_assessable
  tax: selected
```

0개, 1개, 여러 개 또는 모든 도메인이 동시에 선택될 수 있다.

### 5.2 Economic Event 최소 계약

```text
event_id
event_type
party_roles
rights
obligations
resource_and_control
consideration
conditions
event_dates
performance_state
billing_state
payment_state
cancellation_state
amounts
incentives
document_refs
system_event_refs
source_lineage
data_quality_refs
```

도메인별 결론을 Economic Event의 공통 Fact로 역복사하지 않는다.

### 5.3 후보 집합

```text
Candidate Domain Packs =
    Mandatory Baseline Packs
  UNION Mission-requested Packs
  UNION Event/data/account-driven Packs
  UNION Deterministic-signal Packs
  UNION Cross-domain Trigger Packs
  UNION Validated AI-proposed Packs
```

AI는 후보를 추가할 수 있지만 앞의 다섯 결정적 집합에서 선택된 후보를 제거할 수 없다.

### 5.4 전 도메인 저비용 applicability screen

등록되고 현재 관할·시행일에 유효한 각 도메인은 관련 Economic Event에 대해 저비용 applicability screen을 실행한다.

screen 결과:

- `not_applicable`
- `triggered`
- `possible_missing_data`
- `unsupported_pack`
- `expert_review_required`

`triggered`는 해당 도메인의 검증된 Pack을 심화 실행한다. `possible_missing_data`는 필요한 자료를 요청하거나 `Not Assessable`로 남긴다. `unsupported_pack`은 LLM의 일반지식으로 대체하지 않는다.

### 5.5 DomainRoute 필수 필드

```text
route_id
event_id
domain
status
trigger_card_refs
fact_refs
signal_refs
missing_capability_refs
selected_pack_refs
effective_authority
required
routing_reason_codes
estimated_cost_class
expert_role
```

### 5.6 도메인별 상태

선택되거나 applicability가 있는 모든 도메인은 빈칸 없이 다음 중 하나를 갖는다.

- `completed`
- `deep_review_pending`
- `not_assessable`
- `expert_review_required`
- `not_applicable`
- `excluded_by_approved_scope`
- `failed`

`failed`나 `not_assessable`을 다른 도메인의 성공으로 숨기지 않는다.

## 6. 전문 깊이 Gate

### 6.1 적용 단위

전문 깊이는 모델 전체에 한 번 부여하지 않는다. 다음 키로 평가한다.

```text
domain + issue_family + jurisdiction + effective_period + industry_scope
```

### 6.2 D1~D12 필수

선택된 Issue Family는 Knowledge Foundry 설계의 D1~D12를 모두 가져야 한다.

1. 사건과 모집단
2. 계정·주장·의사결정 영향
3. 정상 기대관계
4. 오류·부정·정상사유·매핑오류·복합가설
5. 규범, 관할, 시행일, 요건, 예외
6. 가설 구별 절차
7. 지지·반대 증거
8. 정량화
9. 처리·조치 후보
10. Cross-domain Trigger
11. 한계와 권한
12. 정상·오류·경계·반증·누락·복합원인 정답 사례

하나라도 구조적으로 없으면 해당 Issue Family는 `machine_draft`를 넘을 수 없다.

### 6.3 전문성의 출처

도메인 지식은 다음을 가져야 한다.

- 권위 있는 1차 출처 또는 회사의 승인된 정책
- 관할과 적용 대상
- 시행 시작일과 종료일
- 요건별 atomic claim
- 예외, 선택사항, 상충 규범
- 출처 locator와 hash
- 작성자와 검토자
- Test Case와 Oracle

LLM의 기억, 일반 웹 요약, 출처 없는 체크리스트는 `Full` 근거가 아니다.

### 6.4 전문가 승인

- 회계 Pack: 해당 Issue Family 경험이 있는 회계 전문가
- 노무 Pack: 해당 관할의 노무 전문가
- 법무 Pack: 해당 관할·분야의 법률 전문가
- 세무 Pack: 해당 관할·세목의 세무 전문가

고위험·분쟁 Pack은 독립된 두 번째 검토 또는 문서화된 이견 해결을 요구한다.

한 도메인의 전문가가 다른 도메인의 Full 승인을 대신하지 않는다.

### 6.5 표시 Gate

`시니어급` 표시는 다음을 모두 만족한 정확한 범위에만 허용한다.

- 해당 scope의 모든 필수 Issue Family가 D1~D12 충족
- 필요한 Pack이 `expert_reviewed` 또는 `full`
- 중요 모집단 Coverage 빈칸 0
- 필수 Procedure 완료 또는 명시적 판단불가
- 필수 Cross-domain screen 완료
- Release 품질 Gate 통과

일부 Cycle만 통과한 상태에서 전체 회계, 전체 법무, 전체 노무, 전체 세무를 시니어급이라고 표시하지 않는다.

## 7. 품질 정책의 설정 근거

### 7.1 규범적 불변 기준

다음은 성능과 trade-off하지 않는다.

- 출처 없는 중요 주장 0건
- 결정적 오류금액 기대값 불일치 0건
- Mandatory 무결성·대사 정답 누락 0건
- 데이터 부족 상태의 확정 전문 결론 0건
- Coverage 상태 없는 중요 범위 0건
- 필수 반대 증거 생략 후 강한 결론 0건
- 승인·권한·관할·시행일 우회 0건
- 필수 Cross-domain Trigger 정답 누락 0건

### 7.2 경험적 기준

탐색형 이슈의 recall·precision과 전문가 수정량은 Issue Family와 위험도별로 정한다. 모든 도메인에 하나의 70% 또는 95%를 일괄 적용하지 않는다.

`QualityPolicy`는 다음을 포함한다.

```text
policy_id
domain
issue_family
risk_class
metric
threshold
sample_definition
oracle_refs
expert_approver_refs
effective_from
content_hash
```

Critical·Mandatory 사례는 누락 0건을 요구한다. High·Medium의 임계치는 대표 정답셋과 거짓 양성의 검토비용을 바탕으로 제안하고 전문가가 Stage 2에서 승인한다.

### 7.3 평가 사례

각 Issue Family는 최소 다음을 포함한다.

- 정상
- 단일 오류
- 복수 오류
- 경계값
- 반대 증거
- 데이터 누락
- mapping 오류
- 같은 Signal·다른 원인
- 복합원인
- Cross-cycle
- Cross-domain 충돌
- 판단불가가 정답인 사례

### 7.4 Release Gate

QualityPolicy와 평가 결과는 Knowledge Foundry의 Patch Approve와 Release Deploy를 우회하지 않는다. 임계치 변경도 versioned Patch다.

## 8. 병렬 품질 Gate

### 8.1 병렬 허용 단위

다음 조건을 모두 만족한 작업만 병렬 실행한다.

- 같은 불변 Economic Event·Fact·Signal·Pack Release를 사용
- 서로의 중간 출력을 입력으로 사용하지 않음
- 고유 fragment만 작성
- 독립된 도메인 또는 Issue Family
- required Evidence Packet이 동결됨

Cross-domain 충돌 해소, 전사 중요도, 최종 Grade, CEO 문구는 병렬 실행하지 않고 Join 이후 단일 Integrator에서 수행한다.

### 8.2 품질 대조군

새 concurrency profile은 순차 실행을 대조군으로 사용한다.

```text
sequential
parallel_2
parallel_3
parallel_4
```

실제 모델 평가는 같은 사례·Release·모델 profile을 각 조건에서 반복 실행한다. 입력 순서와 완료 순서 변형도 포함한다.

### 8.3 non-inferiority Gate

병렬 profile은 다음을 모두 만족해야 활성화할 수 있다.

- 7.1의 불변 기준 위반 0건
- Critical·Mandatory recall이 순차 실행보다 낮아지지 않음
- Cross-domain Trigger recall이 낮아지지 않음
- 출처 없는 주장과 금지 결론 증가 0건
- Evidence role과 반대증거 Coverage가 승인 기준 아래로 내려가지 않음
- `Full / Boundary / Not Assessable` 상태 정확도가 낮아지지 않음
- blinded 전문가 비교에서 핵심 이슈·추가 절차의 실무 품질 열화가 없음

가장 빠른 profile이 아니라 위 Gate를 통과한 profile 중 가장 빠른 것을 선택한다.

### 8.4 실패 처리

- required Lens 실패: 통합 완료 차단
- 비필수 탐색 Lens 실패: Coverage Gap과 실패 원인 표시
- timeout: 약한 답변 생성 금지, `deep_review_pending` 또는 `failed`
- 일부 도메인 실패: 나머지 결과는 보존하되 전체 Cross-domain 완료 표시 금지
- writer fallback: 표현만 대체하며 실패한 전문추론을 대체하지 않음

## 9. 속도 SLO

### 9.1 원칙

SLO는 품질 Gate를 통과한 실행만 측정한다. 필수검사 생략, 도메인 단일화, 반증 삭제, 더 약한 결론 생성으로 SLO를 맞추지 않는다.

### 9.2 즉시 고정하는 사용자 체감 SLO

대상 Mac과 warm local server 기준:

| 동작 | SLO |
|---|---:|
| 카드 선택·입력의 로컬 UI 반응 | p95 200ms 이하 |
| 답변 제출 후 처리 중 상태 표시 | 150ms 이하 |
| `submitHumanResponse` receipt 또는 진행 접수 | p95 2초 이하 |
| stale revision 감지와 새 카드 안내 | p95 2초 이하 |
| 저장된 검증 리포트 첫 표시 | p95 2초 이하 |
| 결과 질문 | timeout 90초, 재시도 최대 1회 |

2초 안에 분석이 끝나야 한다는 뜻이 아니다. mutation 접수와 새 revision receipt를 반환한 뒤 후속 분석 상태를 폴링할 수 있다.

### 9.3 현재 기준선 SLO

현재 기본 플러그인의 기존 예산은 해당 범위에만 유지한다.

- 사람 대기 제외 전체 목표: 225초
- 평가 hard limit: 300초
- 저장된 pre-HITL 기반 live branch 목표: 50초
- live branch 평가 hard limit: 75초

이 수치를 다중 전문 도메인 Full 실행의 검증 결과처럼 재사용하지 않는다.

### 9.4 Cross-domain SLO 확정 절차

후속 구현계획은 숫자를 임의로 고정하지 않고 다음 benchmark task를 필수로 포함한다.

1. 대표 workload class 정의
2. 대상 Mac, 모델 profile, cold/warm 조건 고정
3. 이벤트 수, 선택 도메인 수, Issue Family 수, 데이터 행 수 기록
4. 순차와 승인 후보 병렬 profile 비교
5. 품질 Gate 통과 실행만 p50·p95·최대값 계산
6. 최소 4개 대표 시나리오, 조건별 최소 10회 실행
7. 병목을 intake, deterministic, domain reasoning, integration, render로 분해
8. 목표 SLO와 rollback profile을 `PerformancePolicy`로 제안
9. Patch Approve와 Release Deploy 승인

Cross-domain Full SLO가 승인되기 전에는 사용자에게 예상 범위와 측정 중 상태를 표시하고 확정 처리시간을 주장하지 않는다.

### 9.5 허용되는 성능 개선

- 독립 Component와 도메인 Lens의 검증된 제한 병렬화
- 동일 hash의 결정적 Artifact 재사용
- 변경된 event·domain만 증분 재실행
- Issue Evidence Packet의 필요한 Card만 컴파일
- 사전 계산된 Fact·Signal 재사용
- Join 전 결과 스트리밍이 아닌 진행 상태 표시

### 9.6 금지되는 성능 개선

- 필수 Pack·Procedure 생략
- 회계 Lens 하나로 법·노무·세무 대체
- Counter-Hypothesis나 반대 증거 제거
- Coverage Gap 숨김
- required Lens 실패를 writer가 메움
- 미검증 concurrency를 운영 기본값으로 적용
- 결과를 먼저 표시하고 나중에 근거를 맞춤

## 10. Cross-domain Integrator와 CEO 출력

Cross-domain Integrator는 모든 required DomainRoute가 terminal 상태가 된 뒤 한 번 실행한다.

입력:

- 공통 Economic Event
- 도메인별 Assessment와 authority
- 지지·반대 증거
- 미해결 충돌
- domain-specific materiality·urgency·human impact
- 추가자료와 전문가 역할

출력:

- 공통으로 확인된 Fact
- 도메인별 판단 후보와 상태
- 일치·충돌
- 한 도메인의 선택이 다른 도메인에 미치는 영향
- 최종 판단 책임자
- CEO가 결정하거나 확인할 선택지
- 필요한 추가자료·절차

CEO Integrator는 별도의 전문 도메인이 아니다. 전문 결론을 평균하거나 다수결로 결정하지 않는다.

회계 중요성 기준을 법적 책임, 근로자 영향, 세무 위험에 복사하지 않는다. 공통 출력은 금액, 긴급성, 법적 영향, 인적 영향, 운영 영향, 통제 영향을 분리한다.

## 11. 구현계획 필수 작업 묶음

후속 구현계획은 최소 다음 작업을 별도 Task와 테스트로 분해한다.

### A. Human Action Contract

- `human-action-card.schema.json`
- `human-response.schema.json`
- `human-response-receipt.schema.json`
- card compiler와 renderer
- 데이터 미제공 상태·선택지

### B. Response-to-Revision

- pending·preview·submit CLI
- CAS·idempotency·hash 검증
- response record와 overlay materialization
- approval invalidation
- `AnalysisProvider` 실제 plugin 연결
- TTY 승인 분리

### C. Economic Event

- `economic-event.schema.json`
- 원천 Fact에서 Event materialization
- event lineage와 quality
- 같은 사건의 도메인 공유

### D. Multi-domain Router

- `domain-route.schema.json`
- 결정적 applicability screen
- Candidate union
- AI additive proposal
- domain status와 Coverage
- Cross-domain Trigger Card

### E. Professional Depth

- D1~D12 machine gate
- Method·Norm·Expectation·Procedure·Counter·Trigger Card compiler
- jurisdiction·effective-date resolver
- expert approval와 authority

### F. Cross-domain Integration

- Domain Assessment contract
- required domain Join Barrier
- conflict preservation
- CEO decision view

### G. Parallel Quality

- sequential baseline runner
- concurrency profile runner
- paired evaluation
- non-inferiority report
- approved profile registry와 rollback

### H. Performance

- workload classes
- stage timing telemetry
- p50·p95 benchmark
- `PerformancePolicy`
- SLO failure 표시와 safe fallback

### I. Knowledge Foundry

- 실패를 Feedback Record에 연결
- routing·depth·quality·performance Patch 분류
- Regression Case
- Stage 2 Patch Approve
- Stage 3 Release Deploy

## 12. 테스트 인수 기준

### 12.1 질문과 리비전

- Action Card의 이유·현재 해석·행동·옵션·미응답 영향·다음 단계가 모두 표시
- 데이터 미제공 선택 가능
- `request_explanation`은 revision 변화 0
- 분석 의미 답변은 정확히 새 revision 1개 생성
- 이전 revision byte 불변
- stale card 제출 mutation 0
- 중복 idempotency 요청 revision 중복 0
- 웹 답변으로 Approval Record 생성 0

### 12.2 다중 도메인

- 0개, 1개, 2개 이상, 4개 도메인 Trigger 사례
- 같은 event ID가 모든 선택 도메인에 유지
- AI가 필수 route를 제거하는 사례 0
- 미지원 도메인은 일반 LLM 결론 대신 `unsupported_pack`
- 한 도메인 실패가 전체 완료로 표시되는 사례 0
- 회계 중요성이 법·노무·세무의 우선순위를 덮는 사례 0

### 12.3 전문 품질

- D1~D12 누락 Pack의 `Full` 승격 0
- 만료 Norm의 Full 사용 0
- 전문가 승인 없는 Full 0
- Critical·Mandatory Oracle 누락 0
- 출처 없는 중요 주장 0
- 데이터 부족 시 확정 결론 0

### 12.4 병렬과 성능

- 순차·병렬 결정적 Artifact 동등
- 병렬 완료 순서 변형에도 참조·Coverage 동일
- non-inferiority 실패 profile 활성화 0
- required timeout을 약한 결과로 대체 0
- 사용자 체감 SLO 자동 측정
- Cross-domain SLO는 승인된 PerformancePolicy 없이는 Release 기본값이 되지 않음

## 13. 완료 조건

다음이 모두 충족되어야 이 설계가 구현된 것으로 본다.

1. 질문 카드와 사용자 답변이 실제 플러그인 mutation을 통해 새 리비전으로 연결된다.
2. 결과 질문은 분석 리비전을 변경하지 않는다.
3. 데이터 없이 제한 진행할 수 있고 한계가 Coverage와 결과에 남는다.
4. Economic Event가 전문 도메인보다 먼저 생성된다.
5. 라우터가 one-of가 아니라 multi-label union으로 동작한다.
6. 모든 등록 도메인의 applicability screen 결과가 남는다.
7. 선택 도메인의 D1~D12와 authority를 machine gate가 검사한다.
8. 도메인별 전문 승인 없이는 Full을 사용할 수 없다.
9. 필수 도메인 실패를 숨긴 Cross-domain 결과를 만들 수 없다.
10. 병렬 profile은 순차 대조군 대비 non-inferiority를 통과한다.
11. 속도 최적화가 필수 Procedure·반증·Coverage를 줄이지 않는다.
12. 사용자 체감 SLO와 분석 SLO가 서로 분리된다.
13. Cross-domain SLO는 대표 workload benchmark와 승인된 PerformancePolicy를 가진다.
14. 실패와 개선이 Dual-loop와 3단계 승인모델로 연결된다.

## 14. HANDOFF

```text
HANDOFF

목표:
사용자가 답하기 쉬운 Human Action Card를 실제 immutable revision mutation에 연결하고,
공통 Economic Event를 회계·노무·법무·세무의 다중 도메인으로 라우팅하며,
전문 깊이·병렬 품질·속도를 검증·승인 가능한 Gate로 구현한다.

고정:
- 결과 질문과 분석 변경 답변은 다른 경로다.
- 분석 의미 답변은 새 revision을 만든다.
- 웹 답변은 TTY 승인을 대신하지 않는다.
- 데이터 미제공 제한 실행을 지원한다.
- 라우터는 one-of가 아니라 set-valued union이다.
- AI는 route를 추가할 수 있지만 필수 route를 제거하지 못한다.
- D1~D12, 출처, 관할, 시행일, 전문가 승인 없이 Full은 없다.
- 순차 대조군보다 품질이 낮은 병렬 profile은 활성화하지 않는다.
- SLO를 위해 필수 절차·반증·Coverage를 생략하지 않는다.
- Cross-domain SLO는 실제 benchmark와 PerformancePolicy 승인 후 확정한다.
- 모든 실패 수정은 Feedback -> Patch -> Release의 3단계 승인을 따른다.

후속 구현계획:
이 문서 11장의 A~I를 테스트 우선 Task로 분해한다.
기존 기본 플러그인 계획을 소급 수정하지 않고 vNext 계획을 새로 작성한다.
```
