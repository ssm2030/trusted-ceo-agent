# Trusted CEO Agent 웹 최종 설계 보정문 v2

- 상태: 최종 정본의 필수 구성요소
- 기준 문서: `2026-07-17-trusted-ceo-agent-web-design-final.md`
- 계약 보정 버전: 1.0.2

이 보정문 v2와 기준 문서를 함께 웹 설계 정본으로 사용한다. 다른 웹 초안과 이전 보정문은 정본이 아니다. 충돌하는 문장은 이 보정문 v2가 우선한다. 아래 네 항목 외의 결정은 기준 문서를 그대로 유지한다.

## 1. 대화 식별자

기준 문서의 `run_id + revision + scope + issue_id` 키를 다음으로 대체한다.

```text
run_id + revision + scope_kind + scope_instance_id
```

`scope_kind`는 ResultQuestionJob의 scope enum이다. `scope_instance_id`는 다음 규칙으로 결정한다.

| scope_kind | scope_instance_id |
|---|---|
| `run` | 고정값 `run` |
| `issue` | 선택한 `issue_id` |
| `section` | `section:<section_code>:<active_ref-or-all>` |
| `claim` | 선택한 `claim_ref` |
| `evidence` | 선택한 `evidence_link_id` |
| `source` | 선택한 `source_ref` |
| `expert_packet` | 선택한 `expert_packet_id` |
| `revision_diff` | 선택한 `diff_entry_id` |

- `scope_instance_id`는 플러그인이 확정한 기존 ID 또는 위 고정 조합만 사용한다.
- 같은 문제 안의 서로 다른 근거·출처·전문가 패킷·변경 항목 대화는 서로 덮어쓰지 않는다.
- 현재 `issue_id`는 검색·표시용 메타데이터로 별도 보존할 수 있으나 대화 고유 키를 대신하지 않는다.
- Playwright에서 같은 issue의 서로 다른 두 start ref가 별도 대화로 복원되는지 검증한다.

## 2. 터미널 승인 요청과 대기 상태

`prepareTerminalApprovalRequest`가 지원하는 gate enum은 다음 다섯 개로 고정한다.

```text
context
data
scope_narrowing
diagnostic
final
```

승인 요청을 처음 만드는 상태와 TTY 결정을 기다리는 상태를 구분한다.

| gate | 요청 준비 상태 | 요청 생성 후 대기·폴링 상태 |
|---|---|---|
| `context` | `context_confirmation_required`이면서 pending request 없음 | `context_confirmation_required`이면서 pending request 있음 |
| `data` | `mapping_proposal_ready` | `data_confirmation_required` |
| `scope_narrowing` | `scope_narrowing_required`이면서 pending request 없음 | `scope_narrowing_required`이면서 pending request 있음 |
| `diagnostic` | `integrated_draft` | `diagnostic_approval_required` |
| `final` | `writer_ready` | `final_approval_required` |

- Provider는 요청 준비 상태에서만 `approval-request`를 새로 호출한다.
- context와 scope_narrowing은 상태 이름이 요청 전후에 같으므로 `pending_approval_request_id` 존재 여부로 구분한다.
- 대기 상태에서는 새 request를 만들지 않고 기존 request ID를 폴링한다.
- data의 기존 `data_confirmation_required` request가 이미 있으면 새 request를 만들지 않는다.
- 모든 호출은 최신 `expected_revision`을 포함한다.
- plugin이 request ID, base artifact ref, allowed roles, nonce와 안내를 생성한다.
- 웹은 nonce를 저장·재생성하거나 approval record·TTY fingerprint를 만들지 않는다.
- nonce는 사용자에게 복사 가능한 터미널 명령을 구성하는 데만 사용하고 브라우저 영속 저장소와 일반 로그에 남기지 않는다.
- 실제 결정은 plugin의 interactive TTY 흐름만 수행한다.
- 다섯 gate 모두에 대해 request 준비, 대기 polling, stale revision, 승인·변경 요청 후 다음 상태 이동을 통합 테스트한다.

## 3. 질문 말풍선 크기

질문 UI는 결과 화면의 절반을 차지하지 않는 compact floating panel로 고정한다.

### 데스크톱 — viewport 1,024px 이상

- 오른쪽 아래 고정
- 폭: `clamp(360px, 30vw, 440px)`
- 최대 높이: `min(640px, 72vh)`
- viewport 폭의 40%를 넘지 않음
- 배경 결과 화면을 resize하거나 옆으로 밀지 않고 overlay
- 열린 상태에서도 현재 문제 카드와 핵심 차트의 중심 영역을 가리지 않도록 오른쪽 여백 조정

### 태블릿 — viewport 768~1,023px

- 폭 최대 380px
- 높이 최대 70vh
- 오른쪽 아래 overlay

### 모바일 — viewport 767px 이하

- 하단 sheet
- 폭 100%
- 높이 최대 85vh
- 닫으면 원래 scroll 위치와 대화 초안을 복원

닫힌 버튼은 52px 원형 말풍선으로 표시한다. panel을 닫아도 대화와 입력 초안은 유지한다. Playwright에서 데스크톱 panel이 viewport 폭의 40%를 넘지 않고 닫은 뒤 대화가 복원되는지 검증한다.

## 4. 두 업로드 정책의 분리

`JSON 한 파일만 import` 규칙은 결과 리포트의 viewer bundle 가져오기에만 적용한다.

### 분석 작업 탭

- 분석 제공자가 지원하는 CSV, JSON, XLSX 자료를 업로드할 수 있다.
- MIME, 확장자, 크기, workbook 구조, formula 안전성은 plugin intake 계약과 서버 정책으로 검증한다.
- 자료 추가·교체는 plugin mutation이며 새 immutable revision을 만든다.
- replay provider는 같은 UI를 사용하되 실제 분석 산출물을 만들었다고 표시하지 않는다.

### 결과 리포트 탭

- `web-report-bundle.json` 한 파일만 가져온다.
- 최대 크기는 기준 문서대로 50 MiB다.
- ZIP과 다른 archive는 Phase 1에서 받지 않는다.
- 등록 full run이 없는 독립 bundle은 `출처 미확인 묶음`으로만 연다.
- viewer bundle import는 분석 자료 업로드가 아니며 분석 revision을 만들지 않는다.

파일 선택기의 제목, 허용 확장자, 안내 문구와 API route를 두 탭에서 분리한다. 계약 테스트에서 CSV·XLSX가 분석 업로드에는 허용되고 결과 bundle import에는 거부되는지 확인한다.
