# Trusted CEO Agent 웹 최종 설계

- 상태: 사용자 승인 및 독립 재검토 반영 정본
- 기준일: 2026-07-17
- 1차 실행 환경: 대회용 macOS localhost
- 문서 역할: 웹 UX, 플러그인 연결, 표시·질의·보안 계약

이 문서는 독립적으로 구현 가능한 웹 설계 정본이며 이전 웹 초안을 대체한다. 플러그인의 분석·검증 규칙은 플러그인 스키마와 Architecture Decision을 정본으로 삼는다.

## 1. 결정 요약

웹은 플러그인이 완성되기 전부터 병렬로 만들 수 있다. 단, 화면을 현재 내부 JSON에 직접 연결하지 않고 먼저 버전이 있는 계약을 고정한다.

1. 플러그인은 분석, 근거, 등급, 승인, 리비전의 유일한 정본이다.
2. 플러그인은 검증된 full run에서 단일 `web-report-bundle.json`을 결정적으로 내보낸다.
3. 웹은 묶음을 표시 모델로 변환하고 그릴 뿐 새 분석 판단을 하지 않는다.
4. 실제 플러그인과 fixture가 모두 따르는 계약 v1을 먼저 만든 뒤 플러그인과 웹을 병렬 구현한다.

상단 탭은 처음부터 둘 다 구현한다.

1. `분석 작업`: 자료 업로드, 필요한 자료 요청, 사람 확인 질문·답변, 진행·오류·재시도를 담은 지휘센터
2. `결과 리포트`: 저장된 플러그인 실행본의 결론, 차트, 근거, 신뢰 기록, 전문가 패킷, 변경 이력을 보여주는 경영진 대시보드

대회 1차의 `분석 작업`은 `저장된 시연 흐름`이라고 명확히 표시하는 재현 제공자를 사용한다. `결과 리포트`에는 실제 TTY 승인, 최종화, 전체 검증을 거친 플러그인 full run의 대표 묶음을 연결한다. 이후 실시간 플러그인 제공자를 연결해도 화면 구조는 유지한다.

결과 질문은 실제 기능이다. 웹에 별도 OpenAI API 키를 넣지 않고 로그인된 로컬 Codex CLI를 사용한다. Codex CLI도 OpenAI 서비스와 통신하므로 로그인, 이용 권한, 인터넷이 필요하다. 저장 결과 열람은 Codex 실패와 무관하게 작동한다.

## 2. 범위

### 2.1 포함

- 두 상단 탭
- CEO용 최대 3개 요약 문제와 핵심 그래프
- 전체 문제 구조
- 문제별 근거·신뢰·전문가 패킷·변경 이력
- 원본 근거 미리보기, 계산 근거, 플러그인이 기록한 공식 자료 링크
- 결과에 대한 실제 텍스트 질문·답변
- 접이식 질문 말풍선과 대화 유지
- 누르고 말하기 방식의 음성 질문과 답변 읽기
- 전문가에게 보낼 단방향 검토 패킷 렌더링·다운로드
- immutable revision과 이전 리비전 비교
- Stage 3 Pack·매핑 변경을 흡수하는 버전별 어댑터

### 2.2 제외

- 웹의 독자 분석 엔진
- 웹이 만드는 문제 중요도, 수치, 등급, 원인, 결론
- 웹의 TTY 승인 대행
- 전문가 답변 수집·검토·재분석·결과 반영
- 실시간 양방향 음성 스트리밍
- Phase 1의 Vercel, Supabase, 공개 배포, 다중 사용자 인증
- Trust Kernel, HITL, 전문직 경계, `판단 불가` 정책 완화

## 3. 불변 원칙

### 3.1 권한

- Fact, Signal, 계산, 문제, 가설, 등급, 대응, 전문가 라우팅은 플러그인만 생성한다.
- 웹은 플러그인이 생성한 표시 지시와 참조만 렌더링한다.
- 결과 하위 시스템은 읽기 전용이다.
- 향후 분석 작업 실시간 제공자는 최신 `expected_revision`을 포함해 플러그인 CLI 변경 명령을 요청한다.
- 웹 서버는 플러그인 Python 모듈을 직접 import하지 않는다.
- 모든 플러그인 명령은 다음 launcher 경계를 사용한다.

```text
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python plugin/trusted-ceo-agent/scripts/trusted_ceo_agent.py <command>
```

### 3.2 세 산출물 프로필

| 프로필 | 용도 | 웹 처리 |
|---|---|---|
| `full-run` | 불변 스냅샷, Evidence Core, 승인, 감사, 리비전 전체 | 서버가 교차 검증할 때만 읽고 브라우저에는 직접 노출하지 않음 |
| `viewer-bundle` | 허용된 근거, 표시 지시, 검증 영수증, 미리보기, 변경 정보 | 결과 리포트의 정식 입력 |
| `delivery-package` | 현재 `final/` 고객 전달물 | 전체 웹 기능 입력으로 간주하지 않음 |

기존 delivery package만으로는 원본 미리보기, 신뢰 타임라인, 변경 비교, 고품질 차트, 질문 허용 목록이 완전하지 않다.

### 3.3 실패 격리

- 저장 결과는 인터넷과 Codex 없이 열린다.
- Codex 실패는 새 질문만 막는다.
- 음성 실패는 텍스트 질문을 막지 않는다.
- 새 묶음 검증 실패 시 현재 유효 묶음을 유지한다.
- 없는 정보를 추정하지 않고 해당 기능만 `사용 불가`로 축소한다.

### 3.4 정직한 표시

- 재현 실행을 실시간 분석으로 표시하지 않는다.
- fixture를 실제 고객 승인 실행본으로 표시하지 않는다.
- 묶음 안의 자기 진술만으로 신뢰 배지를 주지 않는다.
- 자연어 의미까지 증명하지 못하는 검증을 `완전 검증`이라고 부르지 않는다.
- 모든 제한을 한국어로 보여준다.

### 3.5 한국어

사용자에게 보이는 제목, 버튼, 상태, 오류, 등급, AI 답변은 한국어다. 내부 ID와 로그 코드만 기술 세부정보에서 원문을 유지할 수 있다.

| 내부 등급 | 화면 표시 |
|---|---|
| `Decision Required` | 의사결정 필요 |
| `Immediate Verification` | 즉시 검증 필요 |
| `Expert Review Required` | 전문가 검토 필요 |
| `Monitor` | 모니터링 |
| `Appendix Signal` | 부록 신호 |
| `Not Assessable` | 판단 불가 |

## 4. 사용자 경험

### 4.1 공통

상단에는 제품명, 현재 실행본, 리비전, 표시 자격, 검증 상태와 두 탭을 둔다.

- `분석 작업`
- `결과 리포트`

표시 자격은 플러그인의 외부 교차 검증 결과만 사용한다.

- `승인·검증된 실행본`
- `검증된 POC 시연 실행본`
- `출처 미확인 묶음`
- `제한된 결과 — 웹 리포트 묶음 필요`

승인된 시각 방향은 A 지휘센터형 분석 화면과 C 경영진 대시보드형 결과 화면의 결합이다.

- 데스크톱 우선 12열 그리드
- 짙은 남색과 흰색 중심
- 상태마다 한 가지 강조색
- 짧은 문제 카드와 넓은 차트
- 긴 본문은 근거 드릴다운에 배치
- 키보드 탐색과 프로젝터 가독성 보장

오른쪽 아래에는 `결과에 질문하기` 말풍선 버튼을 고정한다.

### 4.2 탭 1 — 분석 작업

화면 구조는 다음과 같다.

- 왼쪽: 전체 단계와 현재 위치
- 가운데: 지금 해야 할 작업
- 오른쪽: 업로드 자료, 요청 자료, 최근 이벤트, 실행 정보

사용자가 보는 단계는 다음 일곱 개다.

1. 목표와 자료 준비
2. 데이터 구조 확인
3. 문제 탐색
4. 사람 확인
5. 심층 분석
6. 보고서 작성
7. 완료

사용 가능한 작업은 다음과 같다.

- 데이터 파일 선택·업로드
- 필요한 추가 자료와 요청 이유 확인
- AI가 보낸 사람 확인 질문에 답변
- 답변 초안 검토 후 제출
- 진행 상태와 최근 이벤트 확인
- 재시도, 재개, 변경 요청, 중지, 취소
- `터미널 승인 필요` 상태 확인
- 완료 결과 열기

재현 제공자는 분석을 새로 수행한 것처럼 보이지 않게 `저장된 시연 흐름` 배지를 붙인다. 실제 실시간 제공자가 TTY 승인을 요구하면 웹은 승인 버튼을 제공하지 않고 명령 안내와 상태 폴링만 한다.

### 4.3 workflow 상태 투영

| 화면 단계 | 플러그인 상태 |
|---|---|
| 목표와 자료 준비 | `created`, `context_confirmation_required`, `context_ready` |
| 데이터 구조 확인 | `schema_mapping_job_ready`, `mapping_proposal_ready`, `data_confirmation_required`, `evidence_ready` |
| 문제 탐색 | `scope_narrowing_required`, `lens_jobs_ready`, `lens_ready`, `integrated_draft` |
| 사람 확인 | `diagnostic_approval_required` |
| 심층 분석 | `deep_dive_authorized`, `deep_dive_jobs_ready`, `deep_dive_ready` |
| 보고서 작성 | `finalization_jobs_ready`, `writer_ready`, `final_approval_required`, `delivery_approved` |
| 완료 | `finalized` |
| 중단·복구 | `blocked`, `stopped_by_human`, `failed`, `cancelled` |

상태만 보고 다음 행동을 추측하지 않는다. Provider가 함께 반환하는 `pending_action`을 사용한다.

- `human_response`
- `terminal_approval`
- `provider_work`
- `retry`
- `resume`
- `request_changes`
- `terminal`

### 4.4 탭 2 — 결과 리포트

하위 화면은 다음 다섯 개다.

1. `최고경영자 의사결정 요약`
2. `컨설턴트 근거 분석`
3. `실행·신뢰 기록`
4. `전문가 검토 패킷`
5. `변경 이력`

항목 이름에는 현재 범위 개수를 붙일 수 있다. 패킷이 하나면 `전문가 검토 패킷 1`로 표시한다.

#### 최고경영자 의사결정 요약

- 플러그인이 지정한 요약 문제를 최대 3개만 보여준다.
- 문제, 의미, 등급, 핵심 수치, 다음 의사결정 또는 확인 사항을 짧게 표시한다.
- 플러그인이 검증해 내보낸 차트 1~2개를 함께 표시한다.
- 문제가 적으면 빈 카드를 만들지 않는다.
- `전체 문제 구조 보기`로 모든 문제와 관계를 연다.

웹은 `가장 중요한 3개`를 고르지 않는다. 기본 표시 순서는 기존 CEO brief와 같은 등급 순서, 동일 등급의 `issue_id` 안정 정렬이다. 이것은 표시 순서일 뿐 동일 등급 안의 중요도 판단이 아니다.

#### 전체 문제 구조

- 모든 문제와 플러그인이 제공한 관계만 표시한다.
- 문제 클릭 시 활성 문제 범위를 변경한다.
- 다섯 하위 화면과 질문 창이 같은 범위를 사용한다.
- 관계가 없으면 웹이 연결선을 만들지 않는다.

#### 컨설턴트 근거 분석

- 관찰 사실
- 문제 정의
- 원인 가설과 반대 가설
- 지지·기각 근거
- 해결되지 않은 충돌
- 추가 필요 자료
- 조건부 대응
- 원본·계산·공식 링크

#### 실행·신뢰 기록

- 실행본과 리비전
- 플러그인·Pack·스키마·검증기 버전
- 표시 자격과 검증 항목
- 승인 게이트 요약
- revision·command·gate 순서의 신뢰 이벤트
- 파일 해시, 원본 보존, 제한, 비식별화

정본 timestamp가 없으면 시간을 추정하지 않고 순서만 표시한다.

#### 전문가 검토 패킷

- 승인된 패킷을 화면, Markdown, 인쇄용 HTML로 렌더링한다.
- `패킷 만들기`는 새 분석을 뜻하지 않고 승인된 내용을 파일로 만드는 동작이다.
- 패킷 내용을 새로 작성·수정하면 새 분석 리비전과 승인이 필요하다.
- 전문가 답변 업로드, 검토 완료, 재분석, 결과 반영 기능은 없다.

#### 변경 이력

- 기준·비교 리비전
- 변경 범주
- 추가·변경·제거된 객체 참조
- 무효화된 승인
- 의미 지문 변화
- 플러그인이 생성한 결론·등급·근거·자료 요청 차이

정식 diff가 없으면 웹이 의미 비교를 만들지 않고 `변경 정보 사용 불가`로 표시한다.

### 4.5 질문 말풍선

- 오른쪽 아래 버튼으로 열고 닫는다.
- 닫아도 컴포넌트를 제거하지 않고 입력 초안을 세션 캐시에 보존한다.
- 제출 질문과 검증 답변은 로컬 상호작용 저장소에 남긴다.
- 대화 키는 `run_id + revision + scope + issue_id`다.
- 문제를 바꾸면 새 대화 범위로 전환하고 이전 대화를 삭제하지 않는다.
- 리비전이 바뀌면 새 대화를 시작하고 이전 대화에는 `이전 리비전` 배지를 붙인다.

답변은 본문, 근거, 출처, 리비전, 확인할 수 없는 부분을 함께 표시한다.

### 4.6 음성

- 마이크를 누르고 말하는 턴 방식이다.
- 인식 문장을 입력창에서 확인한 뒤 전송한다.
- 답변 읽기 버튼으로 브라우저 음성 합성을 실행한다.
- 브라우저 음성 인식 미지원 시 텍스트 입력만 남긴다.
- 브라우저나 OS가 음성을 외부 처리할 수 있음을 사용 전에 알린다.
- 실시간 양방향 음성은 구현하지 않는다.

## 5. 계약 0 — 병렬 구현 전 고정

웹과 플러그인은 다음 계약을 먼저 함께 고정한다. 이 단계가 끝나기 전에는 각자의 데이터 어댑터 구현을 시작하지 않는다.

```text
contracts/web-report/v1/
  web-report-bundle.schema.json
  viewer-eligibility-decision.schema.json
  presentation-manifest.schema.json
  result-question-job.schema.json
  result-answer-draft.schema.json
  result-answer.schema.json
  generated/types.ts
  fixtures/valid-trusted.json
  fixtures/valid-poc.json
  fixtures/valid-unverified-import.json
  fixtures/invalid-hash.json
  fixtures/invalid-reference.json
  fixtures/oversize.json
```

계약 규칙은 다음과 같다.

- JSON Schema draft 2020-12
- 모든 object는 `additionalProperties: false`
- 모든 필드는 required이며 선택값은 명시적으로 `null` 허용
- ID는 빈 문자열을 허용하지 않음
- 배열 ID 중복 금지
- 모든 참조는 같은 묶음에서 해소
- 표시 순서 배열을 제외한 ID 집합은 오름차순 정렬
- 알 수 없는 enum 거부
- JSON 최대 50 MiB
- 문제 최대 500개
- 차트 최대 50개, 차트당 point 최대 5,000개
- source preview 전체 최대 10 MiB
- 답변 블록 최대 12개, 블록 텍스트 최대 800자
- generated TypeScript type은 schema와 함께 갱신하고 CI에서 drift 검사

스키마 major가 바뀌면 새 adapter와 valid·invalid fixture를 함께 추가한다.

## 6. 웹 리포트 묶음

### 6.1 플러그인 명령

플러그인에 다음 결정적 읽기 명령을 추가한다.

- `export-web-report`
- `validate-web-report`

`export-web-report`는 지정 revision에서 먼저 full `validate`를 실행한 뒤 하나의 `web-report-bundle.json`을 만든다. 스냅샷을 변경하지 않는다.

`validate-web-report`는 다음을 입력받는다.

- 서버에 등록된 full-run artifact root
- bundle path
- expected run ID
- expected revision

이 명령은 묶음의 자기 진술을 믿지 않고 full run의 snapshot, 승인 계보, Evidence Core, 최종 결과, manifest와 교차 검증한 `ViewerEligibilityDecision`을 반환한다.

### 6.2 RunRegistry 신뢰 루트

서버 전용 registry는 다음을 보관한다.

```text
registration_id
canonical_artifact_root
expected_run_id
allowed_revision
expected_bundle_hash
```

- registry 파일은 브라우저에 노출하지 않는다.
- artifact root는 시작 시 allowlist된 디렉터리 아래의 해석된 절대 경로만 허용한다.
- 사용자가 업로드한 JSON 경로로 artifact root를 만들지 않는다.
- 신뢰 배지는 `validate-web-report` 성공 결과만 사용한다.
- 독립 업로드는 스키마·내부 해시만 검사하고 `출처 미확인 묶음`으로 연다.
- 출처 미확인 묶음에서는 결과 질문과 신뢰 자격 주장을 비활성화한다.

### 6.3 묶음 최상위 계약

```text
bundle_version
canonicalization_version
run
viewer_eligibility_receipt
final_result
presentation_manifest
evidence_view
source_view
source_previews
official_url_policy
trust_view
expert_packet_view
revision_view
file_manifest
bundle_hash
```

필수 세부 계약은 다음과 같다.

#### `run`

- `run_id`
- `revision`
- `workflow_state`
- `semantic_fingerprint`
- `finalization_event_time`

`finalization_event_time`은 불변 스냅샷에 이미 존재하는 시각만 사용하며 없으면 `null`이다. export 현재 시각을 넣지 않는다.

#### `viewer_eligibility_receipt`

- `receipt_version`
- `claimed_viewer_mode`
- `run_id`
- `approved_revision`
- `finalized_revision`
- `workflow_state`
- `snapshot_manifest_hash`
- `final_result_hash`
- `result_artifact_ref`
- `revision_ancestry_hash`
- `validator_version`
- `completed_checks`
- `final_approval_summary`

이 receipt는 교차 검증 입력일 뿐 그 자체가 신뢰 자격이 아니다.

#### `presentation_manifest`

- `ceo_summary_issue_refs`: 최대 3개
- `selection_basis`
- `metric_cards`
- `chart_specs`
- `issue_graph`
- `korean_labels`

#### `evidence_view`

- Fact
- Signal
- Evidence Link
- Source Reference
- 계산·공식 설명
- 문제·가설·반대 가설 참조 폐쇄
- 데이터 품질과 능력 제한

#### `source_view`

각 source는 다음을 갖는다.

- 안정적인 `source_ref`
- 한국어 표시 이름
- snapshot locator
- extraction hash
- 시트·테이블·범위
- `access_policy`
- 선택적 `official_url`
- `preview_refs`

#### `source_previews`

단일 JSON 안에서 근거를 볼 수 있도록 분석에 사용된 허용 행·셀만 정제해 내장한다.

- `preview_ref`
- `source_ref`
- 행·열 라벨과 허용 셀 값
- 원본 범위 locator
- 잘림·마스킹 상태
- `access_policy`
- `preview_hash`

전체 원본 파일은 넣지 않는다. `permitted`만 값을 담고 `restricted`와 `prohibited`는 내용 없이 메타데이터만 둔다.

#### `official_url_policy`

- `allowed_schemes`
- `allowed_origins`
- `allow_redirects`

Phase 1 기본 scheme은 `https`다. 필요한 `http`는 정확한 origin만 등록한다. 최초 URL과 redirect 최종 URL을 모두 검사한다.

#### `trust_view`

- 플러그인·Pack·스키마·validator 버전
- 검증 항목
- 승인 요약
- TrustEvent
- 파일 해시
- 제한·비식별화

TrustEvent는 `event_id`, `revision`, `command`, `actor_kind`, `gate`, `sequence`, nullable `timestamp`, `invalidated_approval_refs`를 갖는다.

#### `expert_packet_view`

- 전문 분야
- 대상 문제
- 관찰 사실과 근거 참조
- 원인 가설과 반대 가설
- 해결되지 않은 불확실성
- 필요 문서 참조
- 전문가에게 보낼 질문
- 금지 결론
- source locator

현재 final-result의 간단한 packet만으로는 부족하므로 승인된 내부 후보와 full snapshot에서 결정적으로 구성한다.

#### `revision_view`

- 기준·비교 revision
- 변경 범주
- 추가·변경·제거 객체
- 무효화 승인
- 이전·현재 semantic fingerprint
- 플러그인 생성 표시 문구
- 사용 가능 여부와 불가 이유

#### `file_manifest`

bundle 생성에 사용된 full-run 원본 산출물의 논리 경로, 길이, 해시를 담는다. 절대 경로는 담지 않는다.

### 6.4 정규화와 해시

- `canonicalization_version`은 `rfc8785-jcs-1`
- 객체 해시는 RFC 8785 JCS 바이트의 SHA-256
- `bundle_hash`는 최상위 `bundle_hash` 필드만 제거한 전체 bundle의 JCS 바이트에서 계산
- `file_manifest`는 자신, bundle 컨테이너, `bundle_hash`를 항목으로 포함하지 않음
- `preview_hash`는 해당 preview에서 `preview_hash`만 제거한 JCS 바이트에서 계산
- 같은 full-run revision을 반복 export하면 완전히 같은 바이트와 해시를 반환

### 6.5 표시 자격과 승인 계보

`승인·검증된 실행본` 조건은 다음과 같다.

1. registry에 대응 full run이 있다.
2. workflow가 `finalized`다.
3. run ID와 revision이 일치한다.
4. `validate-web-report`가 성공한다.
5. 내부 full `validate --revision`이 성공한다.
6. `snapshot_manifest`, `evidence_core`, `grade_recomputation`, `final_package` 검증이 포함된다.
7. 존재하는 Pack manifest와 component recomputation도 성공한다.
8. 현재 Final 승인이 있다.
9. 승인 입력 방식이 `interactive_tty`다.
10. `fixture_only`가 참이 아니다.
11. Final 승인 `result_artifact_ref`는 승인된 `delivery_approved` revision 결과를 가리킨다.
12. 표시할 `finalized` revision은 승인 revision에서 단절 없이 이어진 자식이다.
13. 두 revision 사이에 승인을 무효화하는 mutation이 없다.
14. revision ancestry hash와 Final Validator가 일치한다.
15. receipt, manifest, preview, bundle hash가 full run과 일치한다.

`검증된 POC 시연 실행본`은 등록된 POC full run과 같은 교차 검증을 통과하지만 `fixture_only: true`인 경우다. 실제 고객 승인으로 표현하지 않는다.

등록 full run이 없는 독립 JSON은 `출처 미확인 묶음`이다. 내장 preview는 경고와 함께 볼 수 있으나 질문과 신뢰 배지는 없다.

delivery package만 선택하면 `웹 리포트 묶음이 필요합니다`를 표시하고 전체 결과로 열지 않는다.

대회 대표 golden bundle은 `poc.py` 결과가 아니라 실제 TTY 승인, 최종화, full validate, export, cross-validate를 완료한 full run에서 만든다.

### 6.6 버전

- 호환 필드 추가: minor
- 의미, 필수 참조, 신뢰 규칙 변경: major
- 웹은 지원 major별 adapter 등록
- 알 수 없는 major 거부
- 필수 참조 파손 시 전체 거부
- adapter는 단일 `WebReportViewModel`을 반환

`WebReportViewModel`은 schema에서 생성한 타입으로만 구성하며 임의 `unknown` bag을 두지 않는다.

```text
runHeader
viewerEligibility
ceoSummary
issuesById
relations
evidenceById
sourcesById
sourcePreviewsById
charts
trust
expertPacketsById
revisionDiff
labels
```

## 7. 시각화

### 7.1 요약 문제

웹은 상위 3개를 계산하지 않고 `presentation_manifest.ceo_summary_issue_refs`를 사용한다.

기본 결정 규칙은 다음 등급 순서와 `issue_id` 안정 정렬이다.

1. 의사결정 필요
2. 즉시 검증 필요
3. 전문가 검토 필요
4. 모니터링
5. 부록 신호
6. 판단 불가

`selection_basis`에 규칙을 기록한다. 향후 사람이 승인한 표시 순서가 플러그인 결과에 있으면 그 순서를 사용할 수 있다.

### 7.2 ChartSpec

각 차트는 다음을 갖는다.

- `chart_id`
- `chart_type`
- 한국어 제목·설명
- issue·Fact·Signal refs
- x·y축 의미
- metric·scope 한국어 라벨
- unit·currency·scale
- period label·sort key
- point별 `value_ref`·`fact_id`
- display format
- decomposition relation
- `float_safe`

1차 허용 차트는 다음 세 종류다.

- 기간 추세 선 그래프
- 범주 비교 막대그래프
- 문제 관계 그래프

규칙은 다음과 같다.

- unit, currency, scale이 완전히 같은 값만 한 series에 둔다.
- period sort key가 없으면 추세로 그리지 않는다.
- decomposition relation이 없으면 구성비 차트를 만들지 않는다.
- 모든 point가 원래 Fact를 유지한다.
- `float_safe=false`거나 선언 scale을 JS number로 왕복 보존할 수 없으면 표로 축소한다.
- 자료가 부족하면 빈 그래프 대신 근거 표와 한국어 이유를 보여준다.
- 웹은 평균, 비율, 증감률, 합계, 예측을 새로 계산하지 않는다.

## 8. 원본·계산·공식 링크

- 브라우저는 `preview_ref`만 요청한다.
- 서버는 bundle 안의 해시 검증된 `source_previews`만 반환한다.
- UI 요청으로 full-run 원본 파일을 다시 열지 않는다.
- locator는 출처 위치 설명과 `validate-web-report` 교차 검증에만 사용한다.
- `permitted`만 값을 표시한다.
- `restricted`는 메타데이터만 표시한다.
- `prohibited`는 내용과 경로를 마스킹한다.
- 절대 경로는 브라우저, 로그, 다운로드에 노출하지 않는다.
- 공식 URL은 allowlist와 redirect 최종 origin을 검사한다.
- 계산식은 플러그인의 formula/component 설명과 입력 Fact refs를 표시한다.

## 9. 결과 질문

### 9.1 플러그인 계약

플러그인에 다음 schema와 명령을 추가한다.

- `result-question-job.schema.json`
- `result-answer-draft.schema.json`
- `result-answer.schema.json`
- `prepare-result-question`
- `validate-result-answer`

플러그인 Skill에는 `완성된 결과에 질문하기` 읽기 전용 흐름을 추가한다.

### 9.2 범위

범위 enum은 다음과 같다.

- `issue`
- `section`
- `run`
- `claim`
- `evidence`
- `source`
- `expert_packet`
- `revision_diff`

issue 범위는 다음을 ID 순으로 결정적 순회한다.

1. 문제
2. 연결 주장, 가설, 반대 가설, 충돌, 대응, 전문가 패킷
3. Evidence Link
4. Fact·Signal
5. Source Reference·preview

section 시작점은 다음과 같다.

- 최고경영자 요약: 요약 문제 또는 활성 문제
- 컨설턴트 근거 분석: 활성 문제
- 실행·신뢰 기록: 선택 event와 revision
- 전문가 검토 패킷: 선택 packet
- 변경 이력: 선택 diff entry

run 전체 context가 설정 상한을 넘으면 자르지 않고 `SCOPE_REQUIRED`를 반환한다. issue도 크면 가능한 `claim`, `evidence`, `source`, `expert_packet`, `revision_diff` 시작점 목록을 반환해 사용자가 고르게 한다.

모델이 allowlist를 선택하지 않는다.

### 9.3 ResultQuestionJob

필수 필드는 다음과 같다.

- run ID, revision
- 질문
- `response_locale: ko-KR`
- scope와 start refs
- 허용 issue·claim·Fact·Signal·Evidence·Source·value refs
- 금지 결론
- 데이터 품질·판단 불가 조건
- 비식별화 표시
- context cap·제외 요약
- output schema version

사용자 질문과 source text는 untrusted input으로 구분하며 그 안의 지시문을 실행 지시로 취급하지 않는다.

### 9.4 draft 문법

`ResultAnswerDraft.answer_blocks[]`의 각 block은 다음을 갖는다.

- `block_id`
- `support_status`: `supported` 또는 `not_supported`
- `text_template`
- `value_refs`
- `claim_refs`
- `evidence_link_ids`
- `source_refs`

placeholder 문법은 `{{value:<value_ref>}}` 하나만 허용한다. 다른 중괄호 표현과 숫자 literal은 금지한다.

- `supported`인 모든 block은 claim과 evidence ref를 최소 하나씩 갖는다.
- `not_supported`는 refs가 비어 있고 정확한 고정 문구 `현재 실행본의 근거로는 확인할 수 없습니다`만 허용한다.
- 새 Fact, Signal, grade, issue relation, 전문가 결론을 만들 수 없다.
- 법률·세무·노무·재무 확정 판단은 금지 결론을 따른다.

### 9.5 정확한 처리 순서

```text
질문
→ plugin prepare-result-question
→ ResultQuestionJob
→ Codex ResultAnswerDraft
→ plugin validate-result-answer
→ plugin placeholder resolution·formatting
→ canonical ResultAnswer
→ web display
```

`validate-result-answer` 입력은 Job, draft, run ID, revision이다. 이 명령이 한 번에 다음을 수행한다.

1. schema 검증
2. run·revision 검증
3. refs와 allowlist 검증
4. 숫자 literal·placeholder 문법 검증
5. support status 검증
6. 현재 revision Fact에서 value 표시값 조회
7. plugin formatter로 plain-text placeholder 치환
8. canonical `ResultAnswer` 생성

`ResultAnswer` block은 `text_template` 대신 완성된 plain UTF-8 `text`, resolved value metadata와 refs를 담는다. 웹은 HTML escape 후 그대로 보여주며 Markdown이나 HTML을 실행하지 않는다.

결정적 validator는 자연어 문장이 근거를 의미적으로 정확히 함의하는 것까지 증명하지 못한다. 화면에는 `스키마·참조 검증 통과`라고 표시한다. 공격적 fixture와 사람 평가를 별도로 수행한다.

### 9.6 Codex 최소 문맥과 강제 경계

단순 `--cd`와 `--sandbox read-only`는 동일 사용자에게 읽기 가능한 다른 파일 접근을 막는 OS 보안 경계가 아니다. Phase 1도 이 한계를 숨기지 않는다.

질문마다 다음 구조의 임시 디렉터리를 만든다.

```text
<question-root>/
  question-job.json
  result-answer-draft.schema.json
  .agents/skills/trusted-ceo-agent/SKILL.md
```

이 Skill은 결과 질문 전용 최소 Skill이며 전체 분석 Skill과 다른 references를 복사하지 않는다.

Codex는 다음 의미의 인자 배열로 실행한다.

```text
codex exec
  --json
  --ephemeral
  --sandbox read-only
  --ignore-user-config
  --skip-git-repo-check
  --output-schema <result-answer-draft.schema.json>
  --cd <question-root>
  <prompt>
```

프롬프트는 `$trusted-ceo-agent`를 호출하고 Job만 근거로 답하게 한다. 셸 문자열 보간과 sandbox 우회 플래그를 사용하지 않는다.

추가로 `QuestionSandboxRunner`가 macOS deny-by-default 파일 읽기 profile을 적용해야 한다.

- question root와 Codex 실행에 필요한 최소 시스템 파일만 읽기 허용
- full-run root, 저장소, 다른 사용자 자료, 일반 home 경로 읽기 거부
- 임시 출력 디렉터리만 쓰기 허용
- Codex 통신에 필요한 network만 허용
- 프로세스 timeout과 출력 상한 적용

구현은 대상 Mac에서 사용할 수 있는 macOS Seatbelt 기반 runner를 1차로 사용한다. 시작 전 question root 밖의 무작위 canary 파일을 읽지 못하는지 실제 자식 프로세스로 검사한다. 필요한 Codex 옵션, MCP·connector 비활성, 외부 파일 read denial 중 하나라도 확인되지 않으면 실제 회사자료 질문 기능을 켜지 않는다. 안전하지 않은 plain `read-only` 실행으로 자동 축소하지 않는다.

Codex 인증 자료까지 하위 shell에서 읽지 못하게 하는 runner 구현이 대상 CLI에서 불가능하면 Phase 1 질문에는 직접 식별자를 제거한 대회용 POC bundle만 허용한다. 실제 고객자료 질의는 별도 제한 계정·container 또는 서버형 API로 교체하기 전까지 차단한다.

최초 질문 전에 다음을 알리고 동의를 받는다.

- 질문 Job 내용이 Codex를 통해 OpenAI 서비스로 전송됨
- CLI read-only만으로는 OS read isolation이 되지 않음
- 현재 runner 검증 상태
- 브라우저 음성의 외부 처리 가능성

### 9.7 대화 저장

- 앱 로컬 `var/conversations`의 append-only JSONL
- Git 제외
- OS 사용자 전용 directory, 파일 `0600` 상당
- 기본 보존 30일
- 사용자 즉시 전체 삭제
- run별 10 MiB에서 rotation
- 손상된 마지막 record는 격리하고 앞의 정상 record 복구
- 분석 snapshot과 bundle은 수정하지 않음
- 제출 전 draft와 drawer 상태는 browser session cache

## 10. 전문가 검토 패킷

웹의 전문가 기능은 단방향이다.

각 packet은 다음을 갖는다.

- current final result가 참조하는 packet ID
- profession
- target issue
- fact·evidence·source refs
- hypothesis·counter hypothesis
- unresolved uncertainty
- required document refs
- exact review question
- forbidden conclusions
- run ID, revision, packet hash

웹은 같은 승인 내용을 화면, Markdown, 인쇄용 HTML로 변환한다. 문구를 AI로 다시 쓰거나 근거를 추가하지 않는다.

다음 기능은 없다.

- 전문가 답변 입력·업로드
- 답변 완료 상태
- 전문가 답변 검증
- 답변 기반 재분석
- 결과 반영

## 11. 리비전

### 11.1 새 분석 리비전

- 데이터 파일 추가·교체·삭제
- mapping, 열, 단위, 기간 변경
- 사람 확인 답변 제출·수정
- 목표, 회사, 산업, 사업모델, CEO 질문 변경
- 분석 범위·문제 후보 변경
- Pack 선택·내용 변경
- 계산식, KPI, threshold, component 변경
- expert trigger·packet 내용 변경
- request changes, approve, reject, approval invalidation
- 최종 결과에 영향을 주는 모든 plugin mutation

모든 mutation은 최신 `expected_revision`을 받는다. stale이면 덮어쓰지 않고 상태를 다시 읽는다.

### 11.2 분석 리비전 없음

- 화면 열기
- 문제 선택·필터·검색
- 차트 hover·확대
- 질문·답변
- drawer 열기·닫기
- 음성 입력·읽기
- 승인 packet 렌더링·다운로드
- 결과 다운로드
- UI 설정

이 동작은 interaction log나 cache에만 남는다.

## 12. AnalysisProvider

화면은 다음 provider method만 의존한다.

```text
createRun
attachData
submitHumanResponse
requestChanges
startOrContinue
prepareTerminalApprovalRequest
getStatus
getPendingAction
getTerminalApprovalInstruction
retry
resume
stop
cancel
openFinalizedReport
```

`createRun` 외 mutation은 `run_id`와 `expected_revision`을 받는다.

응답은 다음을 포함한다.

```text
provider_kind
run_id
revision
workflow_status
ui_phase
pending_action
allowed_actions
latest_event
progress
result_ref
error
```

오류 enum은 다음과 같다.

- `STALE_REVISION`
- `HUMAN_RESPONSE_REQUIRED`
- `TERMINAL_APPROVAL_REQUIRED`
- `RETRYABLE_PROVIDER_FAILURE`
- `CONTRACT_FAILURE`
- `INTEGRITY_FAILURE`
- `STOPPED`
- `CANCELLED`

`prepareTerminalApprovalRequest`는 plugin `approval-request --gate data|diagnostic|final`을 최신 revision으로 호출하고 plugin이 만든 request ID, gate, base artifact ref, 안내를 반환한다.

nonce와 approval record는 실제 TTY plugin 흐름만 만든다. 웹에는 `approve` method가 없다.

재현 provider와 plugin provider는 같은 응답 계약을 사용한다. 재현 provider는 `provider_kind=replay`와 `저장된 시연 흐름`을 표시한다.

## 13. 기술 구조

### 13.1 선택

- Next.js App Router
- React
- TypeScript
- Apache ECharts
- Vitest
- Playwright
- 선택적 Web Speech API

Phase 1은 한 개의 Next.js localhost process로 실행한다. Route Handler가 registry, bundle import, conversation, plugin CLI, Codex CLI를 중개한다.

```text
Browser
  ├─ 분석 작업 ───── AnalysisProvider
  ├─ 결과 리포트 ─── RunRegistry ─ BundleAdapter
  ├─ 차트·근거 ───── PresentationRenderer / SourcePreviewResolver
  └─ 질문 drawer ─── ConversationStore / QuestionBridge
                                     ├─ plugin CLI
                                     └─ QuestionSandboxRunner ─ Codex CLI
```

### 13.2 구성요소

`RunRegistry`

- representative registered full run과 bundle을 연다.
- `validate-web-report` 성공 후 원자적으로 current run을 바꾼다.
- 실패하면 기존 결과를 유지한다.

`BundleAdapter`

- bundle major별 adapter
- generated schema type만 사용
- 누락값 추정 금지

`PresentationRenderer`

- plugin issue·chart·graph instruction만 렌더링
- 새 계산·ranking 금지

`SourcePreviewResolver`

- `preview_ref`로 bundle 내부 hash-verified preview만 반환
- full-run raw file 재조회 금지

`QuestionBridge`

- Job 준비
- sandboxed Codex 실행
- plugin validate·render
- verified answer 저장

`ConversationStore`

- run·revision·scope별 append-only interaction
- analysis snapshot과 분리

### 13.3 localhost 보안

- `127.0.0.1` bind
- launch마다 random session secret
- HttpOnly, SameSite=Strict cookie
- exact Host·Origin 검사
- CORS 금지
- mutation CSRF token
- strict CSP
- JSON 한 파일만 import, archive import 없음
- bundle 50 MiB·JSON depth·array·request size limit
- path traversal과 임의 local path 거부
- child process는 고정 executable과 argv array
- 질문 concurrency 1, rate limit, queue, timeout
- 최소 환경변수
- token, Codex auth, absolute path, secret을 client에 보내지 않음
- raw 질문·원본은 기본 log에서 제외

## 14. 오류와 축소

### 14.1 전체 거부

- unsupported major
- hash mismatch
- run·revision·result ref mismatch
- non-finalized
- required validation missing
- broken required ref
- absolute path leak
- registry full-run cross-validation failure

### 14.2 기능 축소

- chart metadata 부족 → 근거 표
- revision diff 없음 → 변경 정보 사용 불가
- trust timestamp 없음 → 순서만 표시
- official URL 없음 → link 숨김
- restricted source → metadata만 표시
- packet 없음 → 해당 packet 없음
- voice 없음 → text
- Codex 없음 → 저장 결과 유지, 새 질문 비활성
- OS read denial 불확인 → 실제 자료 질문 비활성

### 14.3 질문 오류

- context 초과 → `SCOPE_REQUIRED`
- Codex timeout → 자동 retry 최대 1회
- schema·ref·numeric 검증 실패 → answer 미표시
- revision 변경 → 이전 request 취소
- concurrency 초과 → queue 또는 중복 거부

같은 실패를 무한 반복하지 않는다.

## 15. Stage 3

분류는 AD-10을 그대로 따른다.

### Green

- 입력 파일·열·단위 mapping
- 회사·산업·사업모델·기간·CEO 질문
- 검증된 Pack 선택
- 등록 component 조합
- 출력 강조점

Green도 plugin mutation, 새 revision, full validation을 거친다. 새 입력 재계산으로 Fact·Signal 값이 바뀌는 것은 정상이나 직접 수정은 Green이 아니다.

### Yellow

- Provisional Domain/Problem Pack
- 새 KPI·threshold
- 새 formula·component
- 새 expert trigger
- Pack 내용·field 의미 변경

사람 승인, 입출력 계약, 최소 테스트, version 기록, 결론 강도 제한이 필요하다. bundle 계약이 바뀌면 adapter와 fixtures를 함께 추가한다.

### Red

- 원본 보존
- Evidence Chain과 사실·해석 분리
- HITL gate
- 전문직 경계
- 판단 불가 정책
- Final Validator·audit
- Fact·Signal 직접 수정
- approval·revision 우회

웹이 Red 변경을 흡수하지 않고 실행을 중단한다.

## 16. 구현 순서

### C0 — 공동 계약

1. v1 JSON Schemas
2. generated TypeScript types
3. valid·invalid fixtures
4. canonical hash vectors
5. provider interface

### A — 웹

1. 두 탭과 한국어 design system
2. replay provider
3. 다섯 결과 화면과 전체 문제 구조
4. conservative chart 1~2종
5. source preview
6. 질문 drawer와 cache

### B — 플러그인

1. `export-web-report`
2. `validate-web-report`
3. presentation·evidence·preview·trust·revision·packet export
4. question schemas
5. `prepare-result-question`
6. `validate-result-answer`
7. result Q&A minimum Skill
8. actual TTY full-run golden bundle

### 통합

1. golden bundle result tab
2. evidence·trust·packet·revision
3. one-shot text question
4. persistent conversation
5. voice
6. arbitrary bundle import
7. live AnalysisProvider

시간이 부족하면 두 탭, actual representative result, 차트, one-shot text question까지를 대회 기준선으로 삼는다.

## 17. 검증

### 17.1 계약

- schema valid·invalid fixtures
- generated type drift
- RFC 8785 canonical hash
- same revision repeat export byte equivalence
- registered full run cross-validation
- TTY vs fixture vs unverified import
- approval revision ancestry
- source preview hash·access policy
- question closure·sorting·caps
- placeholder grammar·numeric literal ban
- expert packet required refs

### 17.2 통합

- full run → validate → export → cross-validate → web
- problem click → all five views same scope
- preview ref → embedded permitted rows
- question → Job → sandbox Codex → plugin final ResultAnswer
- Codex disconnected → stored result intact
- invalid new bundle → old result intact
- stale revision conflict
- terminal approval state → no web approval record

### 17.3 Playwright

1. 대표 실행본과 자격 배지가 보인다.
2. 두 탭을 왕복한다.
3. replay upload·HITL flow를 완료한다.
4. CEO 문제는 최대 3개다.
5. 전체 문제 구조에 모든 문제가 있다.
6. 문제 선택 시 다섯 화면 범위가 바뀐다.
7. chart point에서 evidence로 이동한다.
8. 실제 text 질문을 보낸다.
9. schema·ref validated answer와 sources가 보인다.
10. drawer 재개방 후 대화가 남는다.
11. 다른 문제는 별도 conversation이다.
12. packet을 Markdown·print로 만든다.
13. expert answer input이 없다.
14. revision changes가 보인다.
15. Codex를 끊어도 stored result를 본다.
16. fixture와 unverified bundle badge가 정확하다.
17. 사용자 문구가 한국어다.

### 17.4 보안·품질

- Host·Origin·CSRF denial
- path traversal·oversize JSON denial
- restricted·prohibited masking
- external read canary denial
- MCP·connector 비활성 확인
- prompt injection이 allowlist를 확장하지 못함
- 무관 ID 부착·숫자 literal·unsupported claim 공격 fixture
- keyboard, focus return, contrast, screen reader

### 17.5 시연 목표

- target Mac representative bundle first display 2초 이내
- chart·issue switch 200ms 이내
- question progress 150ms 이내 표시
- Codex timeout 90초
- question concurrency 1
- 전체 demo 3회 연속 성공

## 18. 대회 사전 점검

- Mac disk, Node, uv, Python, Codex CLI
- Codex login과 one-shot result
- `--json`, `--ephemeral`, `--sandbox`, `--ignore-user-config`, `--output-schema`, `--cd`
- QuestionSandboxRunner와 outside-file canary
- actual TTY finalized golden full run
- full validate, export, cross-validate
- fixture와 unverified badge
- frozen/offline plugin launcher
- chart·preview·official link
- 질문 context 비식별화
- voice disclosure
- network·Codex·invalid bundle fallback
- projector resolution·Korean font

## 19. 인수 기준

1. 두 탭이 실제로 존재한다.
2. 결과는 actual TTY 승인 full run의 cross-validated bundle을 연다.
3. fixture와 독립 import가 실제 승인으로 보이지 않는다.
4. CEO 화면은 최대 3개 문제와 plugin-generated charts를 보여준다.
5. 전체 문제 구조에서 모든 문제를 선택한다.
6. 다섯 결과 화면과 질문이 활성 문제에 동기화된다.
7. 원본·계산·공식 링크는 허용된 refs만 연다.
8. 질문은 로그인된 로컬 Codex를 실제 호출한다.
9. OS read-denial canary 실패 시 실제 자료 질문을 켜지 않는다.
10. 답변은 plugin의 schema·ref·value 검증과 rendering을 통과해야 보인다.
11. drawer를 닫아도 대화가 유지된다.
12. voice 미지원 시 text 질문이 작동한다.
13. expert packet은 단방향 render·download만 제공한다.
14. 분석 변경은 새 immutable revision을 만든다.
15. 질문·화면·다운로드는 분석 revision을 만들지 않는다.
16. Codex와 internet이 없어도 stored result를 연다.
17. 웹은 plugin CLI와 TTY approval 경계를 우회하지 않는다.
18. 사용자 문구와 AI 답변은 한국어다.

## 20. 확정 선택

| 항목 | 결정 |
|---|---|
| 1차 배포 | macOS localhost |
| 탭 | 분석 작업 + 결과 리포트 |
| 분석 작업 1차 | 정직한 replay provider |
| 결과 입력 | registered full run에서 내보낸 viewer bundle |
| 분석 정본 | plugin |
| web 역할 | thin display·query UI |
| frontend | Next.js App Router + TypeScript |
| chart | Apache ECharts |
| question | sandboxed local Codex CLI one-shot |
| 별도 API key | web에 없음 |
| question output | plugin validates and renders canonical ResultAnswer |
| question UI | bottom-right collapsible drawer |
| voice | push-to-talk + answer readout |
| expert | approved packet one-way export |
| expert reply | 수집·검토·재분석 없음 |
| analysis mutation | new immutable revision |
| UI·question action | no analysis revision |
| terminal approval | web bypass 금지 |
| public deployment | Phase 1 제외 |

## 21. 구현 계획 경계

구현 계획은 파일, 작업 순서, 테스트, 담당을 구체화하되 다음 결정을 다시 열지 않는다.

- 두 탭과 다섯 결과 화면
- A 지휘센터 + C 경영진 대시보드
- plugin 정본과 thin web
- Contract 0 선행
- full-run cross-validation
- deterministic viewer bundle
- plugin-provided summary·chart
- embedded source previews
- plugin-owned Q&A validation·rendering
- OS read-denial 실패 시 실제 자료 Q&A 차단
- one-way expert packet
- immutable revision
- TTY approval 비우회
- localhost 우선

이 경계를 바꾸는 요구는 구현 편의가 아니라 설계 변경으로 처리한다.
