# Knowledge Foundry Dual-loop Feedback Intake와 3단계 승인 설계

- 상태: 사용자 승인 후 작성된 검토용 설계
- 기준일: 2026-07-17
- 적용 시점: 현재 플러그인 구현·검증과 Knowledge Foundry 구현계획 승인 후
- 목적: 평가 데이터셋과 실사용 피드백을 안전한 수정·회귀·Release로 연결

## 0. 문서 위치와 충돌 방지

이 문서는 다음 설계를 대체하지 않고 Feedback Intake를 구체화한다.

1. `2026-07-17-trusted-ceo-agent-plugin-design.md`
2. `2026-07-17-senior-accountant-review-expansion-design.md`
3. `2026-07-17-professional-reasoning-knowledge-foundry-design.md`
4. `2026-07-17-accounting-content-suite-manifest.md`

### 재사용 계약

- 기존 immutable Run과 Artifact Store
- Evidence Core와 lineage
- hidden Oracle 격리
- expected revision과 CAS
- HITL Gate
- Pack·Prompt·Release hash
- 직접수정 금지
- Validator와 rollback

### 금지

- 대화 한마디로 시스템 프롬프트 자동 수정
- 사용자 신고를 검증 없이 회계 정답으로 등록
- 원본 Run 결과 덮어쓰기
- 승인 범위를 추정해 확대
- 승인받은 뒤 Patch 내용을 바꾸고 그대로 배포
- 운영 데이터를 동의 없이 평가 데이터셋으로 복사

## 1. 핵심 결정

Knowledge Foundry는 두 입력 Loop를 함께 사용한다.

### Loop A. Controlled Evaluation

정상·오류·경계·반증·누락·복합 합성 데이터와 hidden Oracle로 알려진 실패를 자동 검출한다.

### Loop B. Field Feedback

실사용자·CEO·회계사·관리자가 결과 카드나 대화창에서 예상하지 못한 오류·누락·맥락을 제출한다.

두 Loop는 공통 Feedback Inbox와 Triage 이후 합쳐진다.

```text
Synthetic / Curated Evaluation
        |
        v
Oracle Evaluator -------------------+
                                     |
Issue Card / Chat / Expert Review    |
        |                            |
        v                            v
Feedback Capture ------------> Feedback Inbox
                                     |
                                     v
                         Reproduction and Triage
                                     |
                         +-----------+-----------+
                         |                       |
                      invalid                confirmed
                                                 |
                                                 v
                                        Patch + Regression
                                                 |
                                                 v
                                      Expert / Maintainer Gate
                                                 |
                                                 v
                                      Knowledge Release Deploy
```

## 2. 세 가지 승인

“승인합니다”는 바로 직전에 제시된 정확한 객체·버전·행위에만 적용한다.

| 단계 | 승인 질문 | 승인 결과 | 아직 일어나지 않는 일 |
|---|---|---|---|
| 1. Feedback Submit | 이 내용을 피드백으로 제출할까요? | Feedback Record 생성 | 지식·코드·프롬프트 변경 |
| 2. Patch Approve | 검증된 이 Patch를 승인할까요? | Release Candidate에 포함 가능 | 운영 Release 배포 |
| 3. Release Deploy | 이 Candidate를 새 Release로 배포할까요? | 이후 Run에 새 Release 적용 | 기존 Run 덮어쓰기 |

### 2.1 승인 바인딩

모든 Approval Record는 다음에 묶인다.

- `approval_stage`
- `object_id`
- `object_hash`
- `expected_revision`
- `requested_action`
- `requested_by`
- `approved_by`
- `approver_role`
- `requested_at`
- `approved_at`
- `expires_at`
- `status`

다음이면 승인은 자동 무효화된다.

- 객체 내용 또는 hash 변경
- expected revision 불일치
- 승인권한 만료·회수
- 승인 요청 만료
- 상위 Release Candidate 변경
- 추가 테스트 실패

### 2.2 승인 문구

자연어 `승인`, `좋습니다`, `반영하세요`를 허용할 수 있지만 다음을 모두 만족해야 한다.

- 활성 승인 요청이 정확히 하나
- 요청 객체와 행위가 화면에 표시
- 같은 대화·세션의 직전 승인 요청
- 승인자의 인증된 역할이 충분
- expected revision이 현재와 일치

조건이 하나라도 없으면 승인으로 처리하지 않고 대상을 다시 제시한다.

### 2.3 역할분리

| 변경 유형 | Stage 2 승인 | Stage 3 승인 |
|---|---|---|
| Norm·전문 Method | 해당 도메인 전문가 | Release 관리자 |
| Procedure 의미변경 | 도메인 전문가 + Maintainer | Release 관리자 |
| 계산 Component | Maintainer, 의미변경 시 전문가 추가 | Release 관리자 |
| parser·mapping | Maintainer, 회계의미 변경 시 전문가 추가 | Release 관리자 |
| 출력 표현만 변경 | Product owner 또는 Maintainer | Release 관리자 |

POC에서는 한 사람이 여러 역할을 가질 수 있지만 Approval Record는 단계별로 분리한다. 운영에서는 조직 정책에 따라 동일인의 Stage 2·3 겸임을 차단할 수 있다.

## 3. Loop A: 평가 데이터셋

### 3.1 데이터셋 구성

문제가 있는 사례만 만들지 않는다.

- 정상
- 단일 오류
- 복수 오류
- 경계값
- 강한 반대 증거
- 데이터 누락
- mapping 오류
- 같은 Signal·다른 원인
- Cross-cycle 파급
- Cross-domain 충돌
- 판단불가가 정답인 사례

### 3.2 합성 데이터 구조

- 정상 경제적 사건을 먼저 생성
- 오류 Seeder가 별도 변형
- runtime input에는 문제 label 미포함
- Oracle은 별도 경로·권한에 저장
- Generator seed와 version 보존
- 같은 시나리오 재생 가능

### 3.3 Oracle

기존 Oracle 계약을 재사용하고 다음을 보강한다.

- `scenario_id`
- `generator_version`
- `seed`
- `hidden_problem_families`
- `expected_issue_keys`
- `allowed_alternative_issue_keys`
- `expected_amount_or_range`
- `required_evidence_roles`
- `required_counter_checks`
- `expected_not_assessable_reasons`
- `forbidden_claim_codes`
- `forbidden_professional_conclusions`
- `expected_authority_ceiling`
- `oracle_review_status`

### 3.4 자동 평가 결과

Evaluator는 다음을 분리한다.

- false negative
- false positive
- wrong issue family
- wrong amount
- wrong period
- wrong evidence
- missing counter-check
- overconfidence
- unjustified Not Assessable
- forbidden conclusion
- performance regression

Oracle 실패는 `machine_verified_failure` Feedback Record를 자동 생성할 수 있다. 이 자동 제출은 Stage 1에만 해당하며 Patch·배포 승인을 대신하지 않는다.

### 3.5 Oracle 오류

시스템 결과가 아니라 Oracle이 틀릴 수 있다.

- `oracle_dispute` 상태 허용
- runtime 결과와 Oracle을 독립 전문가가 비교
- Oracle 수정도 versioned Patch와 review 필요
- 기존 평가결과를 삭제하지 않고 새 Oracle version으로 재평가

## 4. Loop B: 실사용 피드백

### 4.1 입력 채널

- Issue Card 버튼
- 대화창 자연어
- 전문가 Review Console
- CLI
- API
- 평가·모니터링 시스템

모든 채널은 같은 Feedback Record Schema와 권한검사를 사용한다.

### 4.2 Issue Card 빠른 입력

기본 선택:

- 맞음
- 틀림
- 문제를 놓침
- 금액이 틀림
- 근거가 틀림
- 정상적 설명이 있음
- 필요한 데이터가 부족함
- 표현이 오해를 부름
- 다른 도메인 영향 누락

선택 후 최소 추가정보만 요청한다.

- 어떤 주장 또는 금액이 틀렸는가
- 올바른 내용은 무엇인가
- 어떤 Evidence가 있는가
- 영향 범위는 어디인가

### 4.3 대화형 입력

사용자는 자연어로 지적한다.

```text
이 매출 건은 틀렸습니다.
12월 28일 고객 검수가 완료됐고 검수확인서가 있습니다.
```

Feedback Extractor는 다음 Preview를 만든다.

```text
Feedback 후보

대상 Run: RUN-2026-0012
대상 Issue: RV-08 수익 cutoff
유형: false_positive
수정 주장: 12월 28일 고객 검수 완료
Evidence 후보: 검수확인서
영향: 수익인식 시점 재검토
신뢰상태: unverified_feedback

이 내용을 Feedback Record로 제출할까요?
```

사용자의 Stage 1 승인 전에는 저장하지 않는다.

### 4.4 Casual conversation 경계

다음은 Feedback Record가 아니다.

- 결과에 대한 일반 질문
- 가정적 반론
- 사용자가 아직 확신하지 않는 의견
- 단순 감탄·불만
- 승인 대상이 없는 “반영해”

AI가 피드백 의도를 감지하면 Preview를 제안할 수 있지만 자동 제출하지 않는다.

### 4.5 누락 Issue

현재 Issue가 없는 경우:

- Run ID
- 영향 계정·프로젝트·계약
- 놓친 문제 설명
- 사용자 기대결론
- Evidence 후보
- 예상 금액
- 관련 Issue Family 후보

를 담은 `missed_issue` Record를 만든다. Issue Family를 모르면 빈칸이 아니라 `unclassified`로 저장하고 Triage가 분류한다.

## 5. Feedback Record

### 5.1 식별·lineage

- `feedback_id`
- `source_type`
- `run_id`
- `run_revision`
- `knowledge_release_id`
- `issue_id`
- `issue_family_id`
- `fact_refs`
- `signal_refs`
- `evidence_refs`
- `submitted_at`

### 5.2 내용

- `feedback_type`
- `target_claim`
- `original_statement`
- `correction_claim`
- `reason_codes`
- `amount_or_range`
- `period`
- `scope`
- `user_comment`
- `requested_outcome`

### 5.3 제출자·신뢰

- `submitter_id`
- `authenticated_role`
- `domain_credential_ref`
- `trust_state`
- `independence_flags`
- `conflict_of_interest_flags`

사용자가 자연어로 “저는 회계사입니다”라고 쓴 것만으로 인증 역할을 부여하지 않는다.

### 5.4 개인정보·동의

- `contains_personal_data`
- `contains_confidential_data`
- `retention_class`
- `evaluation_reuse_consent`
- `deidentification_status`
- `source_copy_allowed`

### 5.5 상태

- `draft_preview`
- `submitted`
- `withdrawn`
- `duplicate`
- `reproducing`
- `not_reproducible`
- `triaged`
- `needs_evidence`
- `expert_adjudication`
- `confirmed_failure`
- `rejected`
- `converted_to_patch`
- `resolved_in_release`

## 6. 피드백 유형

| Type | 의미 |
|---|---|
| false_positive | 정상인데 문제로 제시 |
| false_negative | 존재하는 문제를 누락 |
| wrong_norm | 규범·예외 오적용 |
| wrong_procedure | 필요한 검토 절차 누락·오류 |
| wrong_amount | 금액·기간 계산 오류 |
| mapping_error | 원천·필드·사건 연결 오류 |
| evidence_error | 근거 누락·잘못된 참조 |
| missing_counter | 정상 대안·반대 증거 누락 |
| overconfidence | 근거보다 강한 결론 |
| underconfidence | 근거가 충분한데 과도한 판단불가 |
| cross_domain_miss | 법·노무·세무 등 Trigger 누락 |
| usability | 설명·우선순위·질문이 실무에 부적합 |
| oracle_error | 평가 정답 자체 오류 |

## 7. 신뢰등급

| Source | 초기 Trust |
|---|---|
| hidden Oracle 자동실패 | `machine_verified_failure` |
| 인증된 전문가 판정 | `expert_adjudicated` |
| 일반 사용자 | `unverified_feedback` |
| CEO·담당자의 회사맥락 | `context_provided` |
| 반복 독립 신고 | `high_priority_unverified` |
| 시스템 자체 의심 | `system_candidate` |

반복 신고는 우선순위를 올리지만 정답 authority를 자동 상승시키지 않는다.

## 8. 재현과 Triage

### 8.1 Reproduction

- 동일 Run snapshot
- 동일 Knowledge Release
- 동일 Prompt·Pack·Component hash
- 동일 입력·권한

으로 결과를 재생한다.

재현 불가면:

- 환경차이
- 사용자 추가자료
- UI 렌더링
- 비결정적 모델 출력
- 이미 변경된 Release

를 구분한다.

### 8.2 Triage 질문

1. 시스템 결과가 실제로 틀렸는가
2. 사용자 피드백 또는 Oracle이 틀렸는가
3. 사실·규범·계산·표현 중 어디가 문제인가
4. 하나의 사례인가 공통 실패인가
5. 중요도와 영향범위는 얼마인가
6. 즉시 Release 회수가 필요한가

### 8.3 수정 계층

| 실패 | 수정 대상 |
|---|---|
| 원천 파싱 | parser |
| 필드·경제적 사건 연결 | mapping·Event Model |
| Fact 생성 | materializer |
| 금액 | deterministic Component |
| 정상 기대관계 | Expectation Card |
| 규범·예외 | Norm Card |
| 검토 순서 | Procedure Card |
| 반대가설 | Counter-Hypothesis Card |
| Pack 누락 | Router·Coverage |
| 공통 추론단계 | Kernel·Reasoning contract |
| 표현 | output Schema·writer |
| 정답 오류 | Oracle |

프롬프트 수정은 여러 Issue Family에서 같은 공통 추론 실패가 반복될 때만 후보가 된다.

## 9. Patch와 Regression

확인된 실패는 반드시 둘을 함께 만든다.

1. `Patch Proposal`
2. `Regression Case`

### 9.1 Patch Proposal

- feedback refs
- root cause
- target artifacts
- before/after semantic diff
- source refs
- affected Issue Families
- risk classification
- new tests
- expected behavior change
- forbidden side effects
- rollback condition

### 9.2 Regression Case

운영 원본을 그대로 복사하지 않는다.

우선순위:

1. 기존 합성사례에 재현
2. 최소 비식별 재현사례 생성
3. 동의·정책이 있을 때만 제한된 실제 fixture 사용

정상 대조군과 반대사례를 함께 추가한다.

## 10. Stage 2 Patch 승인

승인 요청에는 다음을 보여준다.

```text
Patch ID와 hash
연결된 Feedback
재현 결과
근본 원인
변경 전후 의미
공식 출처
추가된 Regression Case
대상·전체 테스트 결과
영향받는 Pack과 Issue Family
권한·위험 변화
rollback 조건
```

### 승인 결과

- `approved_for_candidate`
- `changes_requested`
- `rejected`
- `expert_disagreement`
- `needs_more_evidence`

승인 이후 Patch가 바뀌면 Stage 2를 다시 요청한다.

## 11. Stage 3 Release 배포

### 11.1 배포 전 Gate

- 모든 Patch hash 고정
- Stage 2 승인 유효
- required expert approval 충족
- 전체 regression 통과
- Coverage 악화 없음 또는 승인된 예외
- 보안·결정성·성능 Gate
- Norm 시행일·관할
- rollback target

### 11.2 배포

- 새 immutable Knowledge Release 생성
- Release manifest·hash·승인기록 보존
- Analysis Plane resolver에 새 기본 Release 등록
- 이전 Release는 보존
- 기존 Run 결과는 변경하지 않음

### 11.3 기존 Run 재분석

사용자가 원하면:

- 새 Run ID 생성
- `rerun_of`로 이전 Run 연결
- 새 Release ID 사용
- 결과 diff 제공
- 기존 승인·결과 보존

재분석은 기존 결과 수정이 아니다.

## 12. 사용자 통지

피드백 제출 후 상태를 숨기지 않는다.

- 접수됨
- 추가 Evidence 필요
- 중복
- 시스템 결함 확인
- 사용자 맥락 차이
- Oracle 오류
- Patch 생성
- Release 반영
- 기각 사유

Release 반영 시:

- 반영 Release
- 바뀐 동작
- 영향 범위
- 기존 Run 재분석 가능 여부

를 알린다.

## 13. 개인정보·기밀

- Feedback Record는 가능한 한 ID와 ref만 보존
- 원본 계약·직원·고객 데이터를 장문 comment에 복사하지 않음
- 평가 재사용은 별도 동의
- 실제 데이터를 합성 재현으로 변환
- direct identifier 제거
- 회사 간 피드백·사례 분리
- 보존기간·삭제요청·legal hold 정책
- 전문가에게 필요한 최소 Evidence만 제공

철회된 피드백은 감사추적을 위해 내용 접근을 제한하고 `withdrawn` 상태와 철회사유를 보존할 수 있다. 개인정보 삭제 의무와 충돌하면 정책에 따라 원문을 삭제하고 비식별 메타데이터만 남긴다.

## 14. 충돌과 중복

### 중복 피드백

- 같은 Run·Issue·주장
- 같은 원인
- 같은 Evidence

를 cluster하되 개별 제출자를 삭제하지 않는다.

### 사용자 간 충돌

- 공통 Fact
- 각자의 주장
- 다른 가정·관할·정책
- 필요한 구별 Evidence

를 분리하고 다수결로 회계결론을 정하지 않는다.

### 전문가 간 충돌

- `expert_disagreement`
- Full 승격 차단
- 추가 Evidence·독립 전문가·적용범위 명시

## 15. 인터페이스 계약

### 15.1 Chat

1. feedback intent 감지
2. 대상 Run·Issue 확인
3. Preview 생성
4. Stage 1 승인
5. Feedback Record 저장
6. receipt 표시

대상이 불명확하면 가장 최근 Run으로 추정해 저장하지 않고 사용자에게 대상 Preview를 보여준다.

### 15.2 CLI 개념 명령

```text
feedback propose
feedback submit --expected-revision
feedback withdraw --expected-revision
feedback reproduce
feedback triage
patch propose
patch approve --expected-revision
release candidate
release deploy --expected-revision
run rerun --release
```

정확한 CLI 문법은 구현계획에서 기존 CLI 패턴에 맞춘다.

### 15.3 API

모든 mutation은:

- authenticated actor
- authorization
- idempotency key
- expected revision
- object hash
- audit event

를 요구한다.

## 16. 오류 처리

| 상황 | 처리 |
|---|---|
| “반영해”만 말함 | 활성 요청 없으면 대상 재제시 |
| 여러 승인 요청 존재 | 하나를 선택하게 함 |
| stale revision | 승인 거부·새 diff 제시 |
| Patch hash 변경 | 기존 승인 무효 |
| 권한 부족 | 승인 거부·필요 역할 표시 |
| Evidence 없음 | unverified 유지·추가자료 요청 |
| 재현 실패 | not_reproducible·원인 보존 |
| 전체 regression 실패 | Release 차단 |
| 배포 후 문제 | Release revoke·rollback |

## 17. 검증 전략

### 17.1 승인 안전성

- Stage 1 승인으로 Patch가 적용되지 않음
- Stage 2 승인으로 Release가 배포되지 않음
- Stage 3만 새 Release를 기본값으로 활성화
- 대상 없는 “승인”은 mutation 0건
- stale revision 승인 0건
- hash 변경 후 승인 재사용 0건

### 17.2 Chat Feedback

- 자연어에서 올바른 Run·Issue·유형 추출
- Preview와 저장 Record 일치
- 승인 전 저장 0건
- 취소 시 저장 0건
- 애매한 대상 자동추정 저장 0건

### 17.3 Evaluation

- Oracle runtime 접근 차단
- 정상사례 false positive 측정
- 오류·경계·반증·누락·복합사례
- Oracle dispute 처리
- generator seed 재현

### 17.4 Release

- Patch와 Regression Case 쌍
- 전체 회귀
- 기존 Run 불변
- 새 Run diff
- rollback
- 권한·감사기록

### 17.5 Privacy

- 동의 없는 평가 재사용 0건
- direct identifier 노출 0건
- 회사 간 Evidence 교차 0건

## 18. 품질지표

- feedback submission confirmation rate
- duplicate rate
- reproducibility rate
- median triage time
- confirmed failure rate
- expert disagreement rate
- patch acceptance rate
- regression escape rate
- recurrent failure rate
- time to safe Release
- unauthorized approval attempts
- approval bypass count
- production-data reuse violations

지표가 높거나 낮다는 사실만으로 자동 Release하지 않는다.

## 19. 구현 단계

### Phase 0. 기존 계약 확인

- Run·Issue·Release ID
- expected revision
- Approval Record
- Oracle 격리

### Phase 1. Feedback Record와 Inbox

- Schema
- Artifact Store
- 상태·권한
- Issue Card 입력

### Phase 2. Chat Capture

- intent 감지
- Preview
- Stage 1 승인
- receipt

### Phase 3. Evaluation Loop

- generator·Seeder
- hidden Oracle
- evaluator
- automatic Stage 1 failure

### Phase 4. Triage·Patch·Regression

- reproduction
- root cause
- Patch Proposal
- Regression Case

### Phase 5. Stage 2·3

- role-based approval
- Release Candidate
- deploy·rollback
- rerun diff

### Phase 6. Expert Console와 운영지표

- micro-review
- disagreement
- notification
- metrics

## 20. 완료 조건

1. 평가와 실사용 두 Loop가 같은 Feedback Schema로 연결된다.
2. 대화 피드백은 Preview와 Stage 1 승인 전 저장되지 않는다.
3. Stage 1·2·3의 효과가 코드와 권한으로 분리된다.
4. 승인 객체·hash·revision·행위가 고정된다.
5. 사용자 피드백이 정답 authority를 자동 획득하지 않는다.
6. Oracle 실패도 Patch·배포 승인을 우회하지 않는다.
7. 확인된 실패마다 Patch와 Regression Case가 존재한다.
8. 운영 원본은 동의 없이 평가 fixture가 되지 않는다.
9. 새 Release는 이후 Run에만 적용된다.
10. 기존 Run은 immutable하며 재분석은 새 Run이다.
11. 규범 변경은 해당 전문가 승인 없이는 배포되지 않는다.
12. rollback과 사용자 통지가 가능하다.

## 21. HANDOFF

```text
HANDOFF

목표:
Knowledge Foundry에 Controlled Evaluation과 Field Feedback의 Dual-loop를 연결하고,
Feedback Submit -> Patch Approve -> Release Deploy의 3단계 승인을 구현한다.

확정:
- 대화창은 피드백 입력창이지 자동학습 통로가 아니다.
- Stage 1은 Feedback Record만 만든다.
- Stage 2는 검증된 Patch를 Candidate에 승인한다.
- Stage 3만 새 Knowledge Release를 배포한다.
- “승인”은 직전의 정확한 객체·hash·revision·행위에만 유효하다.
- Oracle과 사용자 의견 모두 틀릴 수 있어 재현·Triage가 필요하다.
- 모든 확인된 실패는 Patch + Regression Case를 남긴다.
- 기존 Run은 덮어쓰지 않고 새 Release로 rerun한다.
- 운영 데이터의 평가 재사용은 동의·비식별화가 필요하다.

먼저:
1. 현재 플러그인 구현을 완료·검증한다.
2. 이 문서와 Knowledge Foundry 설계의 Gap 분석을 작성한다.
3. 사용자 승인 후 구현계획을 작성한다.
```
