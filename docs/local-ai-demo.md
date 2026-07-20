# Local AI 서비스 데모

Trusted CEO Agent의 데모 모드는 브라우저가 같은-origin Web API만 호출하고, Web 서버가 `127.0.0.1`의 Python AI 서비스와 통신하는 단일 사용자 localhost 구성입니다. 브라우저 사용자는 플러그인, Codex CLI, 터미널 승인 흐름을 조작하지 않습니다.

## 실행

저장소 루트에서 다음 한 명령을 실행합니다.

```powershell
npm --prefix web run dev:ai
```

Python 서비스의 인증된 health 확인이 끝난 뒤 Web 서버가 시작됩니다. 브라우저에서 `http://127.0.0.1:3000/analysis`를 엽니다. 두 서버는 IPv4 loopback에만 바인딩되며, 이 모드는 로그인 없는 단일 사용자 데모이므로 포트 포워딩, reverse proxy, 공유 PC 또는 외부 공개에 사용하면 안 됩니다.

OpenAI API 접근이 준비되지 않은 경우에도 UI와 저장된 보고서 열람은 열리지만 새 AI 분석과 결과 질문은 비활성화됩니다. 화면에는 `OpenAI API 키가 필요합니다`가 표시됩니다. 키 생성·복사 방법은 이 문서에 두지 않습니다. 실제 API 사용이 필요하면 별도의 보안 키 설정 흐름을 명시적으로 요청해 로컬 저장 위치를 확인한 뒤 진행합니다.

## 입력 자료

허용 형식과 MIME은 다음으로 제한됩니다.

- CSV: `.csv`, `text/csv`
- JSON: `.json`, `application/json`
- Excel: `.xlsx`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

한 파일은 최대 25 MiB, 한 실행은 최대 64개 파일과 총 250 MiB입니다. 매크로 포함 Excel, 압축 파일, 실행 파일, 확장자와 MIME이 맞지 않는 파일, 손상된 문서는 거부됩니다. 업로드 내용은 명령으로 실행되지 않으며 먼저 localhost에서 정책 검사와 정규화를 거칩니다.

## 분석과 승인

웹 HITL은 두 유형이며 실제 흐름에는 네 개의 revision 고정 체크포인트가 있습니다.

1. `context_data`
   - 분석 미션과 범위를 확인합니다.
   - 업로드 원본, 열 의미, 매핑과 포함 범위를 확인합니다.
2. `diagnostic_final`
   - 진단 이슈와 심화 분석 범위를 확인합니다.
   - 최종 문구와 전달 범위를 확인합니다.

각 승인·수정·재분석은 화면에 표시된 최신 revision을 기준으로 제출됩니다. AI 출력은 승인이나 사실로 바로 저장되지 않으며, 로컬 스키마·참조·값·최종 검증을 통과해야 다음 단계와 공식 보고서에 반영됩니다.

분석이 완료되면 `최종 보고서 열기`로 검증된 보고서를 게시합니다. 보고서의 `결과에 질문하기`는 현재 보고서 범위와 검증된 참조만 사용하며, 비식별 POC 원격 처리 안내에 동의한 뒤 전송됩니다. 지원 근거가 없으면 시스템은 추측하지 않고 `현재 실행본의 근거로는 확인할 수 없습니다`라고 답합니다.

## 실패, 재시도, 재개

- `AI_TRANSIENT_FAILURE`: 일시적인 네트워크·rate limit·서비스 오류입니다. 현재 체크포인트에서 `재시도`합니다.
- `STOPPED`: 사용자가 안전한 체크포인트에서 중단한 상태입니다. `재개`로 계속합니다.
- `STALE_REVISION`: 다른 동작으로 revision이 바뀌었습니다. 최신 상태를 다시 불러온 뒤 제출합니다.
- `AI_AUTH_FAILURE`: API 접근이 준비되지 않았거나 거부됐습니다. 자동 반복하지 않습니다.
- `AI_REFUSAL`, `AI_OUTPUT_INVALID`, `VALIDATION_FAILURE`: 모델 거부 또는 계약·참조 검증 실패입니다. 원본과 기존 승인 상태를 보존하며 자동 우회하지 않습니다.
- `CANCELLED`: 실행이 취소된 terminal 상태입니다.

브라우저 새로고침과 Python 재시작 후에는 저장된 run ID와 Python manifest를 사용해 최신 체크포인트를 복구합니다. 실행 중이던 질문은 재시작 시 실패 상태로 회수되어 새 질문을 영구 차단하지 않습니다.

## 저장 위치와 삭제

기본 저장 위치는 다음과 같습니다.

- Python 실행, 업로드와 revision 산출물: `web/var/ai-service/runs/<run_id>/`
- 검증 후 게시 가능한 보고서 파일: 저장소 루트의 `.trusted-ceo-agent-reports/`
- Web의 현재 보고서와 질문 대화 기록: 운영체제 임시 디렉터리의 `trusted-ceo-agent-web-runtime/` (또는 `TRUSTED_CEO_WEB_RUNTIME_ROOT`로 지정한 절대 경로)
- 브라우저: `sessionStorage`에 현재 run ID만 저장하며 원본 파일이나 내부 토큰은 저장하지 않습니다.

`실행 데이터 삭제`를 확인하면 Python의 해당 실행 디렉터리 전체와 브라우저의 현재 run ID가 삭제됩니다. 따라서 업로드 원본, revision, 중간 AI Job, 실행별 질문 snapshot은 남지 않습니다. 이미 검증해 게시한 보고서 사본과 Web 대화 기록은 별도 표시 기록이므로 이 버튼이 자동 삭제하지 않습니다. 데모 데이터를 완전히 폐기해야 하면 서버를 종료한 뒤 위 두 보고서·Web runtime 위치도 운영 정책에 따라 별도로 제거해야 합니다.

## 분리된 live smoke

자동 테스트는 키 없는 fake 서비스만 사용합니다. 실제 API smoke는 사용자가 API 사용과 합성 fixture를 명시적으로 승인한 경우에만 한 번 실행합니다. 서비스가 이미 보안 설정 흐름으로 준비된 상태에서 다음 harness를 사용하며, stdout에는 계약 통과 여부, 단계 수, 소요 시간, 입력·출력 토큰 수, 최종 검증 결과만 출력됩니다.

```powershell
$env:PYTHONPATH=(Resolve-Path 'plugin/trusted-ceo-agent').Path
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync `
  python plugin/trusted-ceo-agent/scripts/smoke_live_service.py `
  --service-url http://127.0.0.1:8765 `
  --artifact-root web/tests/fixtures `
  --internal-token $env:TRUSTED_CEO_INTERNAL_TOKEN
```

Harness는 SHA-256으로 고정된 `company-diagnostic.json` 합성 fixture만 허용합니다. prompt, 모델 응답 본문, API 키, 원본 자료는 출력하거나 별도 로그 파일에 저장하지 않습니다. API가 준비되지 않았으면 `AI_API_KEY_REQUIRED`로 한 번 종료하며 자동 재시도하지 않습니다.