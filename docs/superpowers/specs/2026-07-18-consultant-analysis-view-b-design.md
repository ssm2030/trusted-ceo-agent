# 컨설턴트 분석 View B 설계

작성일: 2026-07-18  
상태: 사용자 선택 승인(B안)  
대상: Trusted CEO Agent 결과 화면의 `컨설턴트 근거 분석`

## 1. 결정

상단 결과 화면은 기존 다섯 개를 유지한다.

1. 최고경영자 의사결정 요약
2. 컨설턴트 근거 분석
3. 실행·신뢰 기록
4. 전문가 검토 패킷
5. 변경 이력

`컨설턴트 근거 분석` 내부에 다음 세 개의 보조 탭을 둔다.

1. `분석 결론`
2. `근거·출처`
3. `검증 계획`

상단에 여섯 번째 화면을 추가하거나 오른쪽 Drawer를 만들지 않는다. 현재 활성 문제는 세 보조 탭과 기존 질문 범위에서 동일하게 유지한다.

## 2. 목표와 비목표

### 목표

- 플러그인이 저장한 분석 결론, 원인 가설, 반대 가설, 미해결 충돌, 조건부 대응과 검증 단계를 사람이 읽기 좋은 순서로 제시한다.
- 현재 `근거·출처` 작업 화면을 보존한다.
- 한 화면에 모든 정보를 쌓지 않고 점진적으로 공개한다.
- 웹은 분석 결과를 투영만 하고 새로운 판단을 만들지 않는다.
- 프로젝터, 노트북, 모바일 폭에서 정보 계층과 가독성을 유지한다.

### 비목표

- 웹에서 새 가설, 결론, 우선순위, 검증 절차 또는 등급을 생성하지 않는다.
- 원인·반대 가설 문자열을 웹이 번역하거나 의미를 보충하지 않는다.
- 현재 `WebReportBundle v1.0.0`에 없는 Finding의 영향 차원, 결론 강도, 절차별 판정 기준을 추측해 표시하지 않는다.
- 보조 탭 전환만으로 분석 리비전이나 질문 대화를 새로 만들지 않는다.

## 3. 정보 구조

### 3.1 공통 머리말

세 보조 탭 위에 현재 문제의 제목과 범위 배지를 한 번만 표시한다. 머리말 아래에 작은 세그먼트형 보조 탭을 배치한다.

- 기본 선택: `분석 결론`
- 차트나 근거 링크를 통해 진입: `근거·출처`
- 보조 탭 전환 시 활성 문제와 질문의 issue scope 유지

### 3.2 분석 결론

위에서 아래 순서로 표시한다.

1. 판단 요약
   - `primary_grade`
   - `title_template`
   - `why_it_matters_template`
   - `secondary_flags`
2. 가설 대조
   - 왼쪽: `cause_hypotheses`
   - 오른쪽: `counter_hypotheses`
3. 미해결 사항
   - `unresolved_conflicts`
4. 조건부 대응
   - 현재 문제의 `conditional_response_refs`에 연결된 `conditional_responses`

가설이 없으면 `등록된 원인 가설 없음`, 반대 가설이 없으면 `등록된 반대 가설 없음`을 표시한다. 빈 값을 숨기거나 웹이 내용을 보충하지 않는다.

### 3.3 근거·출처

기존 `EvidenceWorkbench`의 동작을 보존한다.

- 현재 문제의 `issue_claim_closure`에 포함된 Evidence Link, Fact와 Source만 표시
- 지지·반박, 근거 역할과 독립성 그룹 표시
- 출처 미리보기와 공식 링크 정책 유지
- 근거 또는 출처를 실제 선택할 때만 질문 scope를 `evidence` 또는 `source`로 변경

기존 화면을 별도 상단 화면으로 복제하지 않고 보조 탭 콘텐츠로 재사용한다.

### 3.4 검증 계획

다음 순서로 표시한다.

1. 다음 검증 단계
   - `verification_next_steps`
2. 미해결 충돌
   - `unresolved_conflicts`
3. 전문가 검토 경계
   - `expert_review_refs`에 연결된 패킷의 profession과 질문
4. 현재 자료 제한
   - 현재 문제 closure의 Source와 연결되는 미해결 `data_quality`

현재 계약상 문제와 직접 연결할 수 없는 전역 `monitoring`, `blind_spots`, capability 항목은 억지로 문제별로 배분하지 않는다. 필요한 항목이 없으면 명시적 빈 상태를 표시한다.

## 4. 화면 원칙

- 보조 탭은 상단 내비게이션보다 시각적 위계를 낮춘다.
- 분석 결론의 판단 요약은 한 개의 주 카드로 제한한다.
- 원인과 반대 가설은 넓은 화면에서 2열, 좁은 화면에서 1열로 쌓는다.
- 미해결 충돌은 호박색, 반대 가설은 중립 회색·청록 계열을 사용하고 위험도를 색만으로 전달하지 않는다.
- 중첩 카드 깊이는 최대 2단으로 제한한다.
- 긴 ID나 참조값은 줄바꿈하며 원문을 훼손하지 않는다.
- 보조 탭은 키보드로 접근 가능하고 활성 상태를 `aria-selected`로 노출한다.
- 빈 상태도 화면 제목과 범위는 유지한다.

## 5. 데이터·신뢰 경계

첫 구현은 `WebReportBundle v1.0.0`의 기존 필드만 사용하며 계약을 변경하지 않는다.

| 표시 영역 | 정본 필드 |
|---|---|
| 판단 요약 | `final_result.issues[]` |
| 원인·반대 가설 | `cause_hypotheses`, `counter_hypotheses` |
| 미해결 충돌 | `unresolved_conflicts` |
| 조건부 대응 | `conditional_response_refs` → `conditional_responses` |
| 검증 단계 | `verification_next_steps` |
| 전문가 경계 | `expert_review_refs` → `expert_review_packets` / `expert_packet_view` |
| 근거·출처 | `evidence_view.issue_claim_closure`, `evidence_links`, `facts`, `source_view` |
| 자료 제한 | closure의 `source_refs`와 일치하는 미해결 `data_quality` |

웹은 필터링, 정렬, 그룹화와 빈 상태 표현만 수행한다. 새 문장, 관계, 점수, 인과 또는 절차를 만들지 않는다. Source 접근 정책과 절대경로 비노출 규칙을 그대로 유지한다.

현재 계약으로는 Finding의 `conclusion_strength`, `impact_dimensions`, `uncertainty`, 구조화된 절차 결과를 모두 표시할 수 없다. 이후 심층 계약을 추가할 때는 raw 전문 산출물을 브라우저가 직접 읽게 하지 않고, 플러그인이 결정적으로 내보내는 별도 issue별 분석 View를 WebReportBundle에 추가한다.

## 6. 상태와 상호작용

- 보조 탭 상태는 `컨설턴트 근거 분석` 내부의 UI 상태다.
- 활성 문제를 바꿔도 같은 보조 탭을 유지한다.
- 다른 상단 화면을 갔다가 돌아오면 같은 브라우저 세션에서는 마지막 보조 탭을 유지한다.
- 차트 또는 근거 링크로 이동하면 `컨설턴트 근거 분석 > 근거·출처`를 연다.
- 보조 탭 전환은 질문 대화 키나 분석 리비전을 바꾸지 않는다.

## 7. 구현 경계

예상 변경:

- `web/src/features/report/ConsultantAnalysisView.tsx` 추가
- `web/src/features/report/AnalysisConclusionPanel.tsx` 추가
- `web/src/features/report/VerificationPlanPanel.tsx` 추가
- `web/src/features/report/EvidenceWorkbench.tsx`는 재사용에 필요한 머리말 중복만 정리
- `web/src/features/report/ReportWorkspace.tsx`에서 evidence 분기를 새 View로 교체
- `web/src/features/report/ReportWorkspace.module.css`에 보조 탭과 패널 스타일 추가
- 관련 focused test와 fixture 보강

변경하지 않는 경계:

- `ReportSectionNav.tsx`의 다섯 상단 화면
- WebReportBundle 스키마와 생성 타입
- 플러그인 분석·변환기
- Source preview 보안 정책
- 질문 저장 계약

## 8. 검증

RED 테스트에서 다음을 먼저 고정한다.

- 상단 화면은 정확히 다섯 개다.
- `컨설턴트 근거 분석` 안에 보조 탭 세 개가 있다.
- 기본 보조 탭은 `분석 결론`이다.
- 결론, 원인·반대 가설, 충돌, 조건부 대응이 정본 문자열 그대로 표시된다.
- 빈 배열은 명시적 빈 상태로 표시된다.
- `근거·출처`는 기존 Evidence·Fact·Source 폐쇄를 유지한다.
- 검증 계획은 현재 문제의 단계·패킷·연결된 자료 제한만 표시한다.
- 문제 변경 시 세 보조 탭 어디에서도 다른 문제 자료가 섞이지 않는다.
- 차트 근거 이동은 `근거·출처`를 열고 대상 근거를 활성화한다.
- 보조 탭 전환은 질문 scope를 바꾸지 않는다.
- 좁은 화면에서 가설 대조가 한 열로 쌓이고 수평 본문 스크롤이 생기지 않는다.

focused 테스트, typecheck와 build를 통과한 뒤 브라우저에서 다섯 상단 화면, 세 보조 탭, 문제 전환, 출처 미리보기와 빈 상태를 확인한다.

