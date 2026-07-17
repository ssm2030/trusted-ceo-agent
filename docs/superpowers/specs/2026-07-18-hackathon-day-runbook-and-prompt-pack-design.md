# Trusted CEO Agent 대회 당일 Runbook·Prompt Pack 설계

- 상태: 사용자 승인 설계, 구현 전 검토본
- 기준일: 2026-07-18
- 적용 범위: 대회 데이터 진단, 조건부 Adapter·Pack·Component 변경, 실제 분석, 웹 결과 변환·게시
- 비적용 범위: Trust Kernel 변경, 전문 콘텐츠 승격, 분석 엔진 또는 웹의 신규 기능 설계

## 1. 문제와 목표

현재 대회 운영 프롬프트는 대화에서 “1번”, “3번”, “5번”처럼 서로를
참조한다. 같은 대화에서는 의미를 유추할 수 있지만 새 대화는 이전 대화를
알지 못하므로 번호만으로 다음 작업의 실제 계약을 복원할 수 없다.

이 설계의 목표는 다음과 같다.

1. 대회 운영 절차의 Prompt ID, 순서, 진입·완료 조건을 하나의 Runbook에 고정한다.
2. 각 작업 프롬프트를 독립 파일로 분리해 새 대화에서도 정확히 실행할 수 있게 한다.
3. 라우팅 출력이 숫자가 아니라 Prompt ID와 실제 파일 경로를 가리키게 한다.
4. 기존 전문 시스템 설계와 코드 계약을 반복·대체하지 않고 운영 진입점만 제공한다.
5. 조건부 변경, 분석 HITL, 결과 변환, 웹 게시의 책임을 섞지 않는다.

## 2. 정본과 우선순위

운영 문서는 새로운 제품·전문·신뢰 정본이 아니다. 충돌 시 우선순위는
다음과 같다.

1. 코드가 검증하는 Schema·Trust Kernel·불변 revision·승인·Validator 계약
2. `docs/superpowers/specs/2026-07-17-professional-system-integration-index.md`의
   D01~D18 정본과 충돌 규칙
3. `docs/operations/HACKATHON_DAY_RUNBOOK.md`
4. `docs/operations/prompts/HD-01`~`HD-07`
5. 특정 대화의 임시 지시와 모델의 추정

하위 문서는 상위 계약을 완화할 수 없다. 충돌을 발견한 실행자는 하위 문서를
임의 수정하거나 상위 계약을 우회하지 않고 `BLOCKED_CONTRACT_CONFLICT`로
종료한다.

## 3. 파일 구조

구현은 다음 파일만 새로 만든다.

```text
docs/operations/
├─ HACKATHON_DAY_RUNBOOK.md
└─ prompts/
   ├─ HD-01-diagnose-route.md
   ├─ HD-02-adapter-change.md
   ├─ HD-03-provisional-pack.md
   ├─ HD-04-deterministic-component.md
   ├─ HD-05-analysis-hitl-finalize.md
   ├─ HD-06-export-web-report.md
   └─ HD-07-publish-tab2.md
```

Runbook은 번호 계약, 공통 안전 규칙, 라우팅, handoff 형식, 새 대화
부트스트랩만 가진다. 개별 프롬프트는 자신의 작업 계약만 가지며 다른
프롬프트의 본문을 복제하지 않는다.

## 4. 고정 Prompt ID와 책임

| Prompt ID | 파일 | 단일 책임 | 쓰기 권한 |
|---|---|---|---|
| `HD-01` | `HD-01-diagnose-route.md` | 저장소·데이터 읽기 전용 진단과 다음 경로 결정 | 없음 |
| `HD-02` | `HD-02-adapter-change.md` | 승인된 Adapter·정규화 Gap 구현과 검증 | 승인된 Adapter 관련 파일·테스트 |
| `HD-03` | `HD-03-provisional-pack.md` | 승인된 전문지식 Gap을 Provisional Pack으로 구현·검증 | 승인된 Pack·Registry 후보·테스트 |
| `HD-04` | `HD-04-deterministic-component.md` | 승인된 계산·대사·Signal Gap을 결정적 Component로 구현·검증 | 승인된 Component·계약·테스트 |
| `HD-05` | `HD-05-analysis-hitl-finalize.md` | 실제 데이터 전처리, 분석, HITL, Finding, Completion, 최종화 | 플러그인의 정식 mutation·revision 경계 |
| `HD-06` | `HD-06-export-web-report.md` | finalized revision을 검증된 WebReportBundle로 변환 | workspace의 새 export 파일만 |
| `HD-07` | `HD-07-publish-tab2.md` | 검증 번들을 웹에 업로드하고 탭 2를 확인 | 웹의 검증된 ReportStore 교체만 |

단순 숫자 `1`~`7`은 설명용 별칭일 뿐이다. 기계적·운영적 참조에는 항상
`HD-01` 같은 Prompt ID와 정확한 상대 경로를 함께 사용한다.

## 5. 공통 프롬프트 계약

모든 프롬프트는 다음 순서의 머리말을 가진다.

1. 자신의 Prompt ID와 파일 경로 확인
2. `HACKATHON_DAY_RUNBOOK.md` 전체 읽기
3. Runbook이 지정한 상위 정본과 현재 코드 계약 확인
4. 선행 handoff와 입력 식별자 검증
5. 자신의 허용 쓰기 범위 확인
6. 작업 수행
7. 완료 Gate 검증
8. 표준 Handoff Envelope 출력

모든 프롬프트는 다음 규칙을 공유한다.

- 이전 대화 내용을 기억한다고 가정하지 않는다.
- “앞 단계”, “5번 결과” 같은 비정규 참조를 사용하지 않는다.
- 입력이 없으면 저장소·Artifact에서 결정적으로 발견하거나 질문한다.
- 후보가 여러 개면 최신이라는 이유만으로 선택하지 않는다.
- 원본 데이터, 기존 immutable revision, 승인, authority를 덮어쓰지 않는다.
- 확인되지 않은 능력·Pack·Component를 존재한다고 추정하지 않는다.
- 실패를 약한 성공으로 바꾸지 않는다.
- 완료 상태와 다음 Prompt ID를 명시한다.

## 6. 표준 Handoff Envelope

각 프롬프트의 마지막 출력은 사람이 복사해 새 대화에 붙일 수 있는 다음
형식을 사용한다.

```yaml
HANDOFF:
  handoff_version: "1.0"
  operation_id: "<stable operation identifier>"
  completed_prompt_id: "HD-0X"
  status: "<prompt-specific terminal status>"
  project_root: "<absolute path>"
  data_path: "<absolute path or null>"
  artifact_root: "<absolute path or null>"
  run_id: "<run id or null>"
  revision: "<integer or null>"
  approved_gap_ids: []
  produced_paths: []
  validation_evidence: []
  blocking_questions: []
  limitations: []
  next_prompt_id: "HD-0X | MANUAL_UPLOAD | STOP"
  next_prompt_path: "<repo-relative path or null>"
  prompts_after_success: []
```

Prompt별 추가 필드는 허용하지만 위 필드를 제거하거나 의미를 바꿀 수 없다.
민감한 원본 값과 비밀정보는 Handoff에 넣지 않는다.

`HD-01`은 아직 실행을 만들지 않으므로 `artifact_root`, `run_id`,
`revision`이 `null`일 수 있다. `HD-05` 이후에는 세 필드를 반드시
구체화한다. `HD-06`은 `produced_paths`에 검증된
`web-report-bundle.json` 절대경로를 포함한다.

## 7. 라우팅 규칙

### 7.1 정상 경로

```text
HD-01
  ├─ 기존 기능 충분 ─────────────────────────────→ HD-05
  ├─ Adapter Gap ───────────────────────────────→ HD-02
  ├─ Pack Gap ──────────────────────────────────→ HD-03
  ├─ Component Gap ─────────────────────────────→ HD-04
  ├─ 사용자 의미 확인 필요 ─────────────────────→ USER_RESPONSE
  └─ Red 또는 핵심 능력 부재 ───────────────────→ STOP

승인된 조건부 변경 완료
  → HD-05
  → HD-06
  → MANUAL_UPLOAD 또는 HD-07
```

### 7.2 복합 변경

의존 순서는 번호순이 아니라 Artifact 계약으로 결정한다.

1. 구조적 입력 Gap이 있으면 `HD-02`가 먼저다.
2. Adapter 결과의 Canonical Fact와 Evidence 역할을 확인한다.
3. 새 전문 방법론이 필요하면 `HD-03`에서 Procedure와 계산 요구를 정의한다.
4. 기존 Pack이 계산 계약을 이미 정의했다면 `HD-04`만 실행할 수 있다.
5. 새 Pack이 새 계산을 요구하면 `HD-03` 다음 `HD-04`다.
6. 모든 Yellow 변경은 승인된 Gap ID와 테스트를 가져야 한다.
7. 관련 회귀검증을 통과한 뒤에만 `HD-05`로 간다.

예:

```text
HD-01 → HD-05 → HD-06 → MANUAL_UPLOAD
HD-01 → HD-02 → HD-05 → HD-06 → HD-07
HD-01 → HD-04 → HD-05 → HD-06 → MANUAL_UPLOAD
HD-01 → HD-03 → HD-04 → HD-05 → HD-06 → HD-07
HD-01 → USER_RESPONSE → HD-02 → HD-03 → HD-05 → HD-06
```

## 8. Prompt별 필수 내용

### 8.1 HD-01 Diagnose and Route

- 최소 필수 입력은 데이터 경로다.
- 회사·업종·기간·기준일·CEO 질문은 선택 입력이며 먼저 추론 후보를 만든다.
- 기본 변경 정책은 Green 허용, Yellow 사전 승인, Red 금지다.
- 현재 Adapter·Pack·Component·Schema·테스트 기준선을 조사한다.
- 출력은 입력 충분성, 기존 기능표, Capability Gap, 변경 등급, 의존 경로,
  Yellow 제안, 최종 판정, Handoff를 포함한다.
- 코드를 수정하거나 Run을 만들지 않는다.

### 8.2 HD-02 Adapter Change

- `HD-01`의 승인된 `ADAPTER` Gap만 처리한다.
- 필드의 경제적 의미가 불명확하면 구현하지 않고 질문한다.
- 원본 불변, 행·셀 locator, semantic hash, canonical mapping, lineage를 보존한다.
- 정상·경계·실패·변형 테스트와 기존 Adapter 회귀를 요구한다.
- 완료 상태는 `ADAPTER_READY`, `NEEDS_USER_CLARIFICATION`,
  `BLOCKED_RED_CHANGE` 중 하나다.

### 8.3 HD-03 Provisional Pack

- 승인된 `PACK` Gap만 처리한다.
- Method, Norm, Expectation, Procedure, Counter-Hypothesis, Evidence,
  판단불가, Cross-domain·Expert Trigger와 authority 상한을 갖춘다.
- 공식 근거 또는 전문가 승격이 없으면 `Provisional`을 넘지 않는다.
- D1~D12, 정상·오류·경계·반증·복합 회귀사례를 요구한다.
- 완료 상태는 `PROVISIONAL_PACK_READY`, `NEEDS_EXPERT_SOURCE`,
  `BLOCKED_RED_CHANGE` 중 하나다.

### 8.4 HD-04 Deterministic Component

- 승인된 `COMPONENT` Gap만 처리한다.
- 입력 Fact, 공식, Decimal·단위·기간·부호, 출력 Fact·Signal, lineage,
  실패 조건을 명시한다.
- LLM 계산이나 자유서술 결과를 계산 Artifact로 사용하지 않는다.
- 정상·경계·실패, 순차·병렬 동등성, 결정성, Pack 계약 회귀를 요구한다.
- 완료 상태는 `COMPONENT_READY`, `NEEDS_CANONICAL_FACT`,
  `BLOCKED_RED_CHANGE` 중 하나다.

### 8.5 HD-05 Analysis, HITL and Finalize

- 승인된 Adapter·Pack·Component Release와 입력 snapshot을 고정한다.
- Intake, Canonical Mapping, Data HITL, Fact·Lineage·Quality,
  결정적 계산, Signal Queue, 사건별 심층화, 반증, Finding,
  Cross-Finding Join, Completion을 실제로 실행한다.
- 질문은 한 건씩 흩뿌리지 않고 현재 결론을 바꾸는 항목을 Action Card로 묶는다.
- 새 답변은 새 revision으로 연결하고 영향받는 downstream만 재실행한다.
- 모든 required 사건은 terminal disposition을 가져야 한다.
- Final HITL과 전체 Validator 없이는 `finalized`가 될 수 없다.
- 완료 상태는 `FINALIZED`, `LIMITED_FINALIZED`, `NEEDS_INPUT`,
  `BLOCKED_REQUIRED_FAILURE` 중 하나다.

### 8.6 HD-06 Export Web Report

- finalized 또는 명시 승인된 limited finalized revision만 입력으로 받는다.
- 출력 경로는
  `exports/<run_id>/revision-<revision>/web-report-bundle.json`이다.
- input manifest, full validate, render byte-equivalence,
  `export-web-report`, `validate-web-report`를 수행한다.
- Converter는 새 Finding, Grade, 관계, 근거 충분성을 만들지 않는다.
- 완료 상태는 `READY_FOR_WEB_IMPORT` 또는 `BLOCKED`다.

### 8.7 HD-07 Publish Tab 2

- `READY_FOR_WEB_IMPORT` Handoff와 실제 bundle을 다시 검증한다.
- 기존 Trusted CEO Agent 웹을 재사용하고 필요할 때만 공식 명령으로 실행한다.
- 지원되는 Browser·Chrome 제어 지침을 따라 `/report`를 연다.
- 공식 파일 입력과 `리포트 가져오기`를 사용한다.
- 성공 메시지, run ID, revision, bundle hash와 다섯 결과 화면을 확인한다.
- 실패 시 기존 웹 결과를 유지하고 검증을 우회하지 않는다.
- 완료 상태는 `WEB_PUBLISHED` 또는 `BLOCKED`다.

## 9. 새 대화 부트스트랩

Runbook에는 다음 두 템플릿을 제공한다.

### 9.1 최초 진단

```text
다음 파일을 순서대로 완전히 읽고 HD-01을 실행하세요.

1. docs/operations/HACKATHON_DAY_RUNBOOK.md
2. docs/operations/prompts/HD-01-diagnose-route.md

데이터 경로:
<absolute data path>
```

### 9.2 후속 작업

```text
다음 파일을 순서대로 완전히 읽고 지정된 Prompt ID를 실행하세요.

1. docs/operations/HACKATHON_DAY_RUNBOOK.md
2. <HANDOFF.next_prompt_path>

이전 단계 HANDOFF:
<paste the complete HANDOFF block>
```

새 대화는 Handoff의 Prompt ID, 경로, Gap ID, run identity가 파일과
일치하지 않으면 실행하지 않는다.

## 10. 검증

구현 후 다음 정적 검증을 수행한다.

1. Runbook에 HD-01~HD-07이 정확히 한 번씩 정의된다.
2. 모든 `next_prompt_path` 후보 파일이 존재한다.
3. 각 프롬프트의 자체 Prompt ID와 파일명이 일치한다.
4. 모든 프롬프트가 Runbook과 통합 인덱스를 먼저 읽도록 요구한다.
5. `HD-01`은 쓰기 금지, `HD-06`은 분석 mutation 금지,
   `HD-07`은 분석 결과 수정 금지를 명시한다.
6. Prompt 2~4는 승인된 Gap ID 없이는 실행하지 않는다.
7. 단순 숫자만으로 다음 프롬프트를 참조하는 문구가 없다.
8. `HD-05` 전처리·HITL·종료와 `HD-06` 변환 책임이 섞이지 않는다.
9. `HD-06`과 `HD-07`의 성공 상태와 실패 보존 규칙이 일치한다.
10. Placeholder는 사용자 입력 블록에만 존재한다.

추가로 문서를 사람이 읽어 다음 경로를 시뮬레이션한다.

- Green: `HD-01 → HD-05 → HD-06 → MANUAL_UPLOAD`
- Adapter only: `HD-01 → HD-02 → HD-05 → HD-06`
- Pack and Component: `HD-01 → HD-03 → HD-04 → HD-05 → HD-06`
- User clarification: `HD-01 → USER_RESPONSE → HD-02 → HD-05`
- Red: `HD-01 → STOP`
- Browser recovery: `HD-06 → HD-07`

## 11. 완료 기준

다음이 모두 충족되면 Prompt Pack 구현을 완료한다.

1. Runbook과 7개 프롬프트 파일이 존재한다.
2. 각 파일은 이전 대화 없이 자신의 진입 조건과 완료 조건을 설명한다.
3. 모든 후속 참조가 Prompt ID와 실제 상대경로를 함께 사용한다.
4. Prompt 1의 출력만으로 다음 작업 파일을 선택할 수 있다.
5. Prompt 6의 출력만으로 사용자가 탭 2에 올릴 파일을 찾을 수 있다.
6. Prompt 7이 파일 선택부터 다섯 화면 확인까지 수행할 수 있다.
7. 기존 D01~D18, Trust Kernel, authority, Validator를 완화하지 않는다.
8. 정적 검증과 여섯 운영 경로 시뮬레이션이 모두 통과한다.

## 12. 비목표

- 운영 프롬프트가 전문지식 정본이 되는 것
- Prompt가 코드 Schema·Validator를 대체하는 것
- Yellow 변경 자동 승인
- Provisional Pack 자동 승격
- 미지원 데이터를 일반 LLM 지식으로 보충
- 실제 전문가 평가 없이 시니어급 품질을 확정
- 결과 번들을 웹에서 다시 분석하거나 수정
