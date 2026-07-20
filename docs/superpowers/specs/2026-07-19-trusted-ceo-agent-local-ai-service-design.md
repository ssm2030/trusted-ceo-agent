# Trusted CEO Agent 로컬 AI 서비스 전환 설계

- 상태: 사용자 승인 설계
- 기준일: 2026-07-19
- 대상: 해커톤 단일 사용자 localhost 시연
- 설계 역할: 플러그인·Codex·터미널 없이 웹에서 실행하는 신뢰형 AI 분석 서비스의 구현 정본

## 1. 결정 요약

Trusted CEO Agent를 다음 구조로 전환한다.

```text
브라우저
  ↓
Next.js 웹/BFF
  ↓
Python 로컬 AI 백엔드
  ├─ 분석 오케스트레이터
  ├─ OpenAI Responses API 클라이언트
  ├─ 기존 신뢰·계산·검증 엔진
  ├─ HITL 상태·리비전 관리자
  └─ 로컬 실행본·리포트 저장소
```

사용자는 브라우저만 사용한다. 새 웹 실행 경로는 플러그인 Skill, 플러그인 CLI,
Codex CLI, 터미널 TTY 승인을 호출하지 않는다. 기존
`trusted_ceo_agent` Python 패키지의 결정론적 분석·검증 코드는 일반 백엔드
엔진으로 직접 재사용한다. 기존 CLI는 회귀 검증과 호환을 위해 남기되 새 서비스의
런타임 의존성은 아니다.

AI는 해석, 가설 구성, 문제 구조화, 조건부 대응안 작성에 사용한다. 파일 파싱,
회계 계산, Fact·Signal 생성, 근거 연결, 스키마 검증, 승인·리비전, 최종화는
결정론적 Python 엔진이 담당한다.

## 2. 목표

1. CSV, JSON, XLSX 업로드부터 최종 리포트까지 브라우저에서 완료한다.
2. 회사 맥락·데이터 확인과 최종 판단 확인을 웹 HITL로 수행한다.
3. OpenAI API 모델 출력은 기존 계약에 맞는 구조화 JSON으로 받고 로컬 엔진이
   수치·참조·근거를 다시 검증한다.
4. 기존 `WebReportBundle`과 결과 질문 계약을 유지해 현재 결과 화면을 재사용한다.
5. 브라우저나 Python 백엔드가 재시작되어도 마지막 승인 체크포인트부터 복구한다.
6. 서버 API 키와 로컬 파일을 브라우저, 로그, Git에 노출하지 않는다.

## 3. 범위

### 3.1 포함

- 단일 사용자, 단일 활성 실행
- `127.0.0.1` 전용 Next.js와 Python 백엔드
- 서버 보유 OpenAI API 키
- 합성·비식별 CSV, JSON, XLSX 입력
- 두 화면으로 통합된 웹 HITL
- 실제 OpenAI 분석
- 기존 신뢰 엔진 기반 검증
- 로컬 체크포인트, 재시도, 재개, 중단, 취소, 삭제
- 기존 결과 리포트와 근거 기반 결과 질문

### 3.2 제외

- 공개 URL
- 회원가입, 로그인, 사용자·회사별 데이터 격리
- 실제 고객의 민감 데이터
- 결제, 사용량 과금, 조직·역할 권한
- 분산 작업 큐, 다중 인스턴스, 외부 데이터베이스
- 모델의 셸, 웹 검색, 코드 실행, 임의 파일 쓰기
- 기존 Python 엔진의 TypeScript 재작성
- 플러그인 패키지와 CLI의 즉시 제거

## 4. 현재 구조와 전환 원칙

현재 웹의 `AnalysisProvider`는 실행 생성, 자료 연결, 사람 응답, 진행, 승인,
재시도, 재개, 중단, 취소, 최종 리포트 열기를 추상화한다. 현재 구현은 저장된
시연 흐름을 재생하고, 결과 질문은 로컬 Codex CLI와 플러그인 CLI를 호출한다.

전환은 다음 원칙을 따른다.

1. 기존 화면을 새로 만들지 않고 공급자 구현을 교체한다.
2. 웹은 분석 정본을 만들지 않는다.
3. Python 백엔드가 상태 전환과 revision의 유일한 권한자다.
4. 모델 응답은 제안이며 로컬 검증을 통과하기 전에는 정본이 아니다.
5. 기존 계약과 golden fixture를 보존해 플러그인 경로와 서비스 경로의 결과
   의미가 달라지지 않게 한다.

## 5. 구성요소

### 5.1 Next.js 웹/BFF

책임:

- 기존 분석 작업과 결과 리포트 UI 유지
- 파일 업로드, 진행 상태, HITL 승인·수정·재분석·중단 표시
- 브라우저 요청을 Python 백엔드에 중계
- Python 응답을 기존 `ProviderSnapshot` UI 계약으로 변환
- 브라우저에 Python 포트, 내부 토큰, API 키를 노출하지 않음

새 실시간 공급자는 `RemoteAnalysisProvider`다. 공급자 표시는
`provider_kind: "service"`, 배지는 `실시간 AI 분석`으로 확장한다. 저장 시연
공급자는 회귀와 오프라인 데모를 위해 유지한다.

### 5.2 Python 로컬 AI 백엔드

책임:

- `127.0.0.1`에만 바인딩
- 파일 접수와 실행별 격리
- 분석 오케스트레이션
- OpenAI API 호출
- 결정론적 엔진 호출
- HITL 승인과 revision 처리
- 체크포인트와 최종 결과 저장
- 결과 질문 준비, 모델 호출, 답변 검증

단일 저장소 실행 명령이 Next.js와 Python 프로세스를 함께 시작한다. 런처는
매번 임의의 내부 토큰을 생성해 두 서버 프로세스에 환경으로 전달한다. 브라우저
사용자는 별도 프로세스나 터미널 승인을 조작하지 않는다.

### 5.3 분석 오케스트레이터

오케스트레이터는 다음 상태를 관리한다.

```text
created
→ data_attached
→ preprocessing
→ context_proposal_ready
→ context_confirmation_required
→ deep_analysis
→ decision_confirmation_required
→ finalizing
→ finalized
```

보조 종결·복구 상태는 다음과 같다.

```text
retryable_failure
stopped_by_human
cancelled
validation_failed
```

모든 변경 요청은 `expected_revision`을 포함한다. 현재 revision과 다르면
`STALE_REVISION`으로 거부하고 정본을 바꾸지 않는다. 승인, 수정, 자료 추가처럼
분석 의미가 바뀌는 변경만 revision을 증가시킨다. 상태 조회와 진행률 갱신은
revision을 증가시키지 않는다.

### 5.4 OpenAI 클라이언트

- OpenAI Responses API를 사용한다.
- 기본 모델은 `gpt-5.6`이다.
- 응답 저장을 끄기 위해 `store: false`를 사용한다.
- 애플리케이션이 관리하는 로컬 비동기 작업 안에서 동기 Responses 요청을
  실행한다. 1차 구현은 OpenAI Background mode를 사용하지 않는다.
- Structured Outputs의 `text.format`과 JSON Schema를 사용한다.
- 셸, 웹 검색, Code Interpreter, MCP, 임의 function tool을 제공하지 않는다.
- API 타임아웃, 429, 5xx만 재시도 가능한 오류로 분류한다.
- 모델 거부와 불완전 응답을 별도 오류로 처리한다.

Structured Outputs는 형식 일치를 보장하는 수단이지 내용의 사실성을 보장하는
수단이 아니다. 모델 결과는 기존 Python validator를 반드시 통과해야 한다.

참고:

- [Structured model outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Background mode](https://developers.openai.com/api/docs/guides/background)
- [Data controls in the OpenAI platform](https://developers.openai.com/api/docs/guides/your-data#v1responses)

### 5.5 결정론적 신뢰 엔진

기존 `trusted_ceo_agent` 모듈에서 다음 기능을 재사용한다.

- 입력 어댑터와 정규화
- 회계·운영 계산과 Fact·Signal 생성
- Evidence Link와 lineage
- 등급과 신뢰 경계
- 승인, revision, snapshot 검증
- WebReportBundle 생성·검증
- 결과 질문 Job 생성과 답변 검증

백엔드는 `trusted_ceo_agent.cli`를 호출하지 않고 Python 서비스 인터페이스를
통해 모듈을 직접 호출한다. CLI에만 있는 조정 로직은 얇은 서비스 함수로
추출하고 CLI와 백엔드가 같은 함수를 공유하게 한다.

### 5.6 로컬 실행 저장소

각 실행은 전용 디렉터리를 갖는다.

```text
runtime/
  runs/
    <run_id>/
      manifest.json
      input/
      revisions/
      model-jobs/
      report/
      conversations/
```

- `run_id`는 추측하기 어려운 임의 ID다.
- manifest와 revision snapshot은 임시 파일 작성 후 원자적 rename으로 교체한다.
- 저장된 파일에는 무결성 해시를 기록한다.
- 원본 경로는 API와 브라우저에 반환하지 않는다.
- 한 번에 하나의 실행만 활성 작업을 수행한다.
- `실행 데이터 삭제`는 실행 디렉터리 전체를 안전하게 삭제한다.
- 백엔드 시작 시 완료되지 않은 임시 파일을 정리한다.

## 6. 로컬 HTTP 계약

브라우저는 Next.js의 같은-origin Route Handler만 호출한다. Next.js BFF가 아래
Python API를 호출하고 `X-Trusted-Ceo-Internal-Token`을 추가한다.

| 메서드 | 경로 | 역할 |
|---|---|---|
| `GET` | `/health` | 프로세스와 엔진 준비 상태 |
| `POST` | `/v1/runs` | 새 실행 생성 |
| `POST` | `/v1/runs/{run_id}/files` | 검증된 입력 연결 |
| `GET` | `/v1/runs/{run_id}` | 현재 상태 조회 |
| `POST` | `/v1/runs/{run_id}/actions/continue` | 다음 자동 단계 시작 |
| `POST` | `/v1/runs/{run_id}/human-responses` | HITL 승인·수정 제출 |
| `POST` | `/v1/runs/{run_id}/actions/retry` | 재시도 가능한 단계 재실행 |
| `POST` | `/v1/runs/{run_id}/actions/resume` | 중단 지점에서 재개 |
| `POST` | `/v1/runs/{run_id}/actions/stop` | 체크포인트를 보존하고 중지 |
| `POST` | `/v1/runs/{run_id}/actions/cancel` | 실행 취소 |
| `GET` | `/v1/runs/{run_id}/report` | 최종 WebReportBundle 조회 |
| `POST` | `/v1/runs/{run_id}/questions` | 검증된 결과 질문 시작 |
| `GET` | `/v1/runs/{run_id}/questions/{request_id}` | 질문 상태·답변 조회 |
| `DELETE` | `/v1/runs/{run_id}` | 실행 데이터 삭제 |

모든 mutation은 다음 공통 필드를 받는다.

```json
{
  "expected_revision": 3,
  "idempotency_key": "client-generated-opaque-value"
}
```

같은 `idempotency_key`와 같은 본문은 동일 결과를 반환한다. 같은 키에 다른
본문이 오면 `IDEMPOTENCY_CONFLICT`로 거부한다.

## 7. 분석 데이터 흐름

### 7.1 실행 생성과 업로드

1. 사용자가 `새 분석`을 선택한다.
2. 백엔드는 revision 0 실행과 전용 저장소를 만든다.
3. 사용자가 CSV, JSON, XLSX 자료를 업로드한다.
4. 백엔드는 파일 정책, 실제 구조, 크기, 개수, 경로를 검사한다.
5. 통과한 파일만 실행 입력으로 등록한다.

### 7.2 결정론적 전처리

기존 엔진이 원본을 정규화하고 표준 테이블, Fact, 계산값, 데이터 품질 문제,
lineage를 생성한다. AI는 파일을 실행하거나 계산식을 확정하지 않는다. 필수
입력이 부족하면 모델 호출 전에 `HUMAN_RESPONSE_REQUIRED`와 필요한 자료 목록을
반환한다.

### 7.3 AI 맥락 해석과 웹 HITL 1

백엔드는 원본 전체가 아니라 다음 최소 패킷을 모델에 전달한다.

- 확인된 파일·테이블 목록
- 컬럼 스키마와 제한된 표본
- 결정론적 프로파일과 품질 경고
- 계산된 Fact 요약
- 허용된 회사 맥락

모델은 회사 상황, 분석 범위, 데이터 매핑 초안을 구조화 JSON으로 반환한다.
로컬 검증 통과 후 웹은 다음 선택을 제공한다.

- 승인
- 수정 후 승인
- 다시 분석
- 중단

사용자 수정은 별도 untrusted 입력으로 기록하고 기존 사실을 자동으로
덮어쓰지 않는다. 승인된 응답만 다음 단계 입력이 된다.

### 7.4 심층 분석과 웹 HITL 2

결정론적 엔진이 지표, 이상 신호, Evidence Link를 만든다. 모델은 허용된
Fact·Signal·Evidence만 사용해 다음을 제안한다.

- 핵심 문제
- 원인 가설과 반대 가설
- 미해결 충돌
- 중요도와 우선순위
- 조건부 대응안
- 추가 검증 계획

모든 주장에는 허용된 참조가 필요하다. 로컬 엔진이 참조, 수치, 기간, 단위,
근거 수준을 검증한 뒤 웹은 항목별 승인·수정·제외를 제공한다. 두 화면의 HITL은
기존 내부 승인 결정을 묶어 보여주지만 실제 revision과 승인 기록은 개별
결정으로 보존한다.

### 7.5 최종화

최종화는 다음을 모두 검사한다.

- 현재 revision과 승인 참조 일치
- Fact·Signal·Evidence 참조 무결성
- 수치·기간·단위 일치
- 검증되지 않은 주장 부재
- WebReportBundle 계약
- 실행본과 결과 묶음 해시

통과한 결과만 `finalized`가 되고 기존 결과 리포트 화면에 표시한다.

### 7.6 결과 질문

결과 질문은 finalized revision을 바꾸지 않는 읽기 전용 흐름이다.

1. 질문 범위에 해당하는 검증된 근거 Job을 만든다.
2. Job과 사용자 질문만 모델에 전달한다.
3. 구조화 답변 초안을 받는다.
4. 기존 답변 validator가 run, revision, 허용 참조, 수치, 문구를 검사한다.
5. canonical answer만 화면과 대화 기록에 저장한다.

## 8. 웹 HITL 의미

웹 HITL은 기존 터미널 승인을 브라우저의 결정 카드로 옮긴 것이다. AI가 작업을
수행하지만 회사의 공식 분석 결과로 확정할 권한은 사람에게 남긴다.

HITL 1은 회사 맥락과 데이터 해석을 확인한다. HITL 2는 문제 정의, 우선순위,
조건부 대응안을 확인한다. 두 화면 모두 다음 공통 동작을 제공한다.

- 전체 또는 항목별 승인
- 사용자 수정
- 근거 보기
- 재분석
- 중단

승인은 사용자 결정 원문, 대상 ID, revision, 시간, 입력 해시를 기록한다.

## 9. 보안

### 9.1 네트워크와 프로세스

- Next.js와 Python은 `127.0.0.1`에만 바인딩한다.
- Host와 Origin을 localhost allowlist로 제한한다.
- Python API는 내부 토큰이 없는 요청을 거부한다.
- 내부 토큰은 프로세스 시작마다 바뀌며 파일과 브라우저 저장소에 기록하지 않는다.
- 외부 호출은 OpenAI API만 허용한다.

### 9.2 API 키

- `OPENAI_API_KEY`는 Python 백엔드 환경에서만 읽는다.
- 클라이언트 번들, Next.js 공개 환경 변수, 응답, 로그, fixture에 포함하지 않는다.
- 키가 없으면 분석 기능을 비활성화하고 저장 리포트 열람은 유지한다.
- 인증 오류는 자동 재시도하지 않는다.

### 9.3 파일 정책

- 허용 형식: `.csv`, `.json`, `.xlsx`
- 금지 형식: `.xlsm`, 압축 파일, 실행 파일, 스크립트
- 최대 64개
- 파일당 최대 25MB
- 실행당 전체 최대 250MB
- 확장자와 실제 구조를 함께 검사
- 심볼릭 링크와 작업 루트 밖 경로 거부
- 업로드 콘텐츠의 지시문을 명령으로 취급하지 않음

### 9.4 모델 격리

- 업로드 데이터와 사용자 문장은 항상 untrusted content로 구분한다.
- 데이터 안의 프롬프트나 명령을 실행하지 않는다.
- 모델에 로컬 도구와 네트워크 도구를 제공하지 않는다.
- 모델 출력은 허용된 JSON Schema 밖의 동작을 요청할 수 없다.
- 모델이 만든 참조는 실행본 allowlist와 대조한다.

## 10. 오류와 복구

| 오류 | 코드 | 재시도 | 정본 처리 |
|---|---|---:|---|
| 파일 형식·용량 | `INPUT_POLICY_FAILURE` | 아니요 | 입력 미등록 |
| 필수 자료 부족 | `HUMAN_RESPONSE_REQUIRED` | 자료 추가 후 | 현재 revision 보존 |
| API 인증 실패 | `AI_AUTH_FAILURE` | 아니요 | 마지막 승인본 보존 |
| API timeout·429·5xx | `AI_TRANSIENT_FAILURE` | 제한적으로 | 마지막 체크포인트 보존 |
| 모델 거부 | `AI_REFUSAL` | 사용자 판단 | 정본 미반영 |
| 구조화 출력 실패 | `AI_OUTPUT_INVALID` | 1회 | 계속 실패하면 단계 중단 |
| 근거·수치 불일치 | `VALIDATION_FAILURE` | 재분석 가능 | 실패 항목 미반영 |
| 오래된 revision | `STALE_REVISION` | 새 상태 조회 후 | HTTP 409, 변경 없음 |
| 엔진 내부 실패 | `ENGINE_FAILURE` | 수동 | 마지막 승인본 보존 |
| 사용자 중지 | `STOPPED` | 재개 가능 | 체크포인트 보존 |
| 사용자 취소 | `CANCELLED` | 아니요 | 종결 상태 |

재시도 가능한 OpenAI 오류는 짧은 지수 backoff와 jitter를 적용해 최대 2회
재시도한다. 동일 모델 출력의 구조 검증 실패는 교정 피드백을 포함해 한 번만
재생성한다. 그 뒤에는 자동 반복하지 않고 사용자에게 실패를 표시한다.

백엔드 재시작 시 manifest를 검사한다. 완료되지 않은 로컬 작업은
`retryable_failure`로 전환하고 마지막 원자적 체크포인트에서 사용자가 재시도한다.
승인된 HITL 결과는 자동으로 다시 실행하지 않는다.

## 11. 테스트 전략

### 11.1 RED/GREEN 순서

각 기능 단위는 다음 순서를 따른다.

1. 실패하는 focused 테스트 추가
2. 해당 테스트만 실행해 RED 확인
3. 최소 구현
4. 해당 테스트만 실행해 GREEN 확인
5. 기능 단위 종료 시 관련 계약·타입 검사

### 11.2 Python 단위 테스트

- 상태 머신과 revision
- HITL 승인·수정·반려
- 파일 정책과 경로 격리
- OpenAI 응답 파싱과 오류 분류
- 근거·수치·참조 검증
- idempotency
- 체크포인트와 재시작 복구
- 데이터 삭제와 로그 redaction

### 11.3 AI 계약 테스트

실제 API 대신 고정된 다음 응답을 사용한다.

- 정상 Structured Output
- 모델 거부
- 불완전 출력
- 잘못된 enum과 누락 필드
- 존재하지 않는 Fact·Signal·Evidence ID
- 변조된 수치·기간·단위
- 근거 없는 주장

CI와 기본 전체 테스트는 실제 OpenAI API를 호출하지 않는다.

### 11.4 Web 테스트

- `RemoteAnalysisProvider`
- BFF 응답·오류 매핑
- 업로드와 진행 상태
- HITL 두 화면
- 승인·수정·재분석·중단
- stale revision 갱신
- 최종 리포트와 결과 질문
- 삭제 후 빈 상태

### 11.5 통합·E2E

통합 테스트는 Next.js, 실제 Python 백엔드, 가짜 OpenAI transport, 실제
결정론적 엔진을 연결한다. Playwright는 다음 전체 흐름을 검증한다.

```text
합성 데이터 업로드
→ HITL 1 승인
→ 심층 분석
→ HITL 2 승인
→ 최종 리포트
→ 근거 기반 질문
→ 실행 데이터 삭제
```

추가 실패 시나리오는 브라우저 새로고침, Python 재시작, API 일시 실패,
검증 실패, stale revision, 중단·재개다.

### 11.6 실제 API 스모크

실제 API 스모크는 자동 테스트와 분리한다. 승인된 합성 데이터로 1회 실행하며
다음만 기록한다.

- 응답 계약 통과 여부
- 입력·출력·전체 토큰 수
- 단계별·전체 소요 시간
- 최종 검증 결과

API 키와 실제 응답 본문은 로그에 기록하지 않는다.

## 12. 전체 완료 게이트

구현 범위가 끝나면 저장소 규칙에 따라 다음을 각각 한 번 실행한다.

```powershell
npm --prefix contracts/web-report run check

$env:PYTHONPATH=(Resolve-Path 'plugin/trusted-ceo-agent').Path
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync `
  python -m unittest discover -s tests -q

npm --prefix web run typecheck
npm --prefix web run lint
npm --prefix web run test
npm --prefix web run build
npm --prefix web run test:e2e
```

완료 게이트 뒤 동작 코드나 설정이 바뀌면 영향받은 게이트만 다시 실행한다.

## 13. 인수 기준

다음을 모두 만족해야 완료다.

1. 사용자가 플러그인, Codex, 터미널을 조작하지 않는다.
2. 업로드부터 최종 리포트까지 웹에서 완료한다.
3. 두 HITL 화면이 실제 승인 기록과 revision을 만든다.
4. 오래된 화면의 변경 요청이 차단된다.
5. 검증 실패 AI 결과가 공식 화면에 표시되지 않는다.
6. 기존 WebReportBundle과 결과 질문 계약을 유지한다.
7. 브라우저 새로고침 후 현재 상태가 복원된다.
8. Python 재시작 후 마지막 승인 체크포인트에서 재시도할 수 있다.
9. API 키가 브라우저 번들, 응답, 로그, Git에 없다.
10. 두 서버가 localhost에만 바인딩된다.
11. 실행 데이터 삭제 후 원본과 중간 산출물이 남지 않는다.
12. 계약, Python 전체 테스트, Web typecheck·lint·unit·build, Playwright가
    통과한다.
13. 합성 데이터 실제 AI 시연이 수동 검토 시간을 제외하고 목표 5분 이내
    완료된다.

## 14. 후속 확장 경계

파일럿 또는 공개 SaaS 전환 때는 이 설계를 유지하고 다음 계층을 교체·추가한다.

- localhost 내부 토큰 → 사용자 인증과 조직 권한
- 실행별 로컬 디렉터리 → 암호화 객체 저장소와 데이터베이스
- 단일 로컬 작업 → durable queue와 worker
- 단일 사용자 상태 → 조직별 tenant 경계
- 수동 삭제 → 보존 기간과 자동 삭제 정책
- 단일 API 프로젝트 → 사용자·조직별 비용·사용량 정책

분석 오케스트레이터, 신뢰 엔진, HITL 계약, WebReportBundle, 결과 질문 validator는
그대로 재사용한다.
