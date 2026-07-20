# Markdown 근거 및 누적 폴더 업로드 설계

- 상태: 사용자 승인 설계
- 기준일: 2026-07-21
- 대상: Trusted CEO Agent localhost 분석 화면과 Python 신뢰 엔진
- 설계 역할: Markdown을 검증된 AI 판단 근거로 사용하고 파일·폴더 업로드를 누적하는 구현 정본

## 1. 결정 요약

분석 자료 입력을 다음 네 형식으로 확장한다.

- CSV
- JSON
- XLSX
- Markdown (`.md`)

Markdown은 단순 첨부나 수치 Fact의 변형으로 취급하지 않는다. 로컬 엔진이
UTF-8 본문을 결정론적으로 구간화하고 각 구간에 원본 Source, 논리 상대경로,
줄 범위, 내용 해시를 연결한 `DocumentEvidence`를 만든다. 모델에는 허용 목록에
포함된 제한된 구간만 비신뢰 데이터로 전달한다. 모델 결과가 문서 근거를
인용하면 로컬 검증기가 허용 ID, 해시, 줄 범위, Source 계보를 다시 검사한다.

웹에는 기존 다중 파일 선택과 별도의 폴더 선택을 제공한다. 폴더 선택은 하위
폴더를 재귀적으로 읽고 지원 형식만 업로드한다. 파일 선택과 폴더 선택을 여러
번 실행하면 같은 분석 실행에 누적된다. 누적 목록의 정본은 Python 서비스의
Source Registry이며, 브라우저 로컬 상태가 아니다.

## 2. 목표와 성공 기준

### 2.1 목표

1. 사용자가 `.md` 파일을 일반 파일 선택과 폴더 선택 모두에서 올릴 수 있다.
2. Markdown 본문이 실제 lens 판단의 근거가 되고 결과의 Evidence Link로
   추적된다.
3. 사용자가 여러 파일과 여러 폴더를 차례로 올려도 이전 자료가 유지된다.
4. 선택 폴더 내부의 논리 상대경로를 보존해 같은 이름의 파일과 폴더별 자료를
   구분한다.
5. 절대경로, 브라우저 실제 로컬 경로, 서비스 staging 경로를 API·AI·로그에
   노출하지 않는다.
6. 기존 CSV·JSON·XLSX 처리, HITL, revision, 최종 보고서 계약을 회귀시키지
   않는다.

### 2.2 성공 기준

- 폴더 하나를 선택하면 모든 하위 지원 파일이 한 배치로 업로드된다.
- 다른 폴더나 파일을 다시 선택하면 분석 시작 전까지 정본 목록에 누적된다.
- 새로고침하거나 저장된 run ID로 복원해도 서버 정본의 누적 목록이 표시된다.
- 동일한 논리 경로와 동일한 내용은 멱등적으로 한 번만 나타난다.
- 동일 내용이 다른 논리 경로에 있으면 blob은 중복 저장하지 않되 모든 경로를
  별칭으로 보존한다.
- 동일 논리 경로에 다른 내용이 다시 들어오면 기존 근거를 바꾸지 않고 새
  배치를 거부한다.
- 모든 Markdown 구간은 한 번 이상 lens Job에 포함되거나, 한계를 넘으면
  `scope_narrowing_required`로 명시적으로 중단된다. 조용한 일부 누락은 없다.
- 모델이 허용되지 않은 문서 근거 ID를 인용하거나 구간이 변조되면 결과를
  정본으로 수용하지 않는다.

## 3. 범위

### 3.1 포함

- `.md` 업로드 정책과 UTF-8 텍스트 검증
- 제목·줄 경계 기반 결정론적 Markdown 구간화
- Document Evidence 스키마, 레지스트리, Evidence Core 연결
- Reasoning Job의 문서 근거 허용 목록과 제한된 본문 컨텍스트
- 모델 초안의 문서 근거 참조 및 Evidence Link 검증
- 기존 파일 다중 선택의 반복 누적
- 재귀 폴더 선택과 반복 폴더 누적
- 지원하지 않는 폴더 파일 제외 및 제외 개수 안내
- 논리 상대경로 검증·저장·그룹 표시
- 서버 정본 업로드 요약을 통한 새로고침 복원
- replay 화면의 동일한 선택·누적 UX와 메타데이터 전용 고지 유지

### 3.2 제외

- 서버가 사용자의 로컬 디렉터리를 직접 탐색하는 기능
- 절대경로 또는 드라이브 경로 수집
- 폴더 구조를 실제 서버 디렉터리 구조로 재생성하는 기능
- ZIP 또는 기타 압축 파일 업로드·압축 해제
- Markdown 안의 링크 열기, 이미지 다운로드, HTML 실행, 코드 실행
- PDF·DOCX·TXT 등 추가 문서 형식
- 분석이 시작된 뒤 기존 실행의 근거 파일 교체·삭제
- 모델을 이용한 선행 문서 요약이나 Fact 자동 변환

## 4. 현재 동작과 문제

현재 `DataUploadCard`의 파일 입력은 `multiple`이므로 한 번의 선택에서 여러
파일을 고를 수 있다. BFF와 Python 서비스도 한 multipart 요청의 복수 `files`
항목을 처리한다.

하지만 다음 문제가 있다.

1. `LiveAnalysisCommandCenter`와 `ReplayCommandCenter`가 업로드 성공 후
   `setSelectedFiles(...)`로 화면 목록을 교체한다. 서버 Source Registry가
   누적되어도 화면은 마지막 배치만 보인다.
2. live 브라우저 저장소에는 보안상 run ID만 저장하므로 새로고침하면 로컬
   파일 목록 상태가 사라진다.
3. 폴더 선택 입력과 논리 상대경로 전달 계약이 없다.
4. 웹과 Python 업로드 정책이 `.md`를 거부한다.
5. 활성 서비스의 `runtime_scan.py`는 모든 Source를 구조화 데이터 어댑터로
   보내므로 `.md`는 차단 품질 이슈가 된다.
6. Reasoning Job은 허용 Fact·Signal ID만 전달하며 문서 본문과 문서 근거
   계약이 없다.
7. Evidence Link와 관련 검증기는 Fact·Signal만 근거로 허용한다.

## 5. 업로드 UX와 누적 규칙

### 5.1 입력 제어

`DataUploadCard`는 다음 두 제어를 제공한다.

- **파일 선택**: `.csv,.json,.xlsx,.md`, `multiple`
- **폴더 선택**: 디렉터리 입력, 하위 파일 재귀 선택

폴더 입력은 브라우저가 제공하는 논리 상대경로만 사용한다. 입력 값을 처리한
뒤 초기화해 같은 폴더도 다시 선택 이벤트를 낼 수 있게 한다. 폴더 선택 API를
지원하지 않는 브라우저에서는 파일 다중 선택을 유지하고 폴더 버튼을 사용할 수
없다는 안내를 표시한다.

### 5.2 클라이언트 선택 처리

두 입력은 공통 선택 정규화 함수로 합쳐진다. 각 선택 항목은 다음 값을 가진다.

```text
file: 브라우저 File
logical_path: 선택 루트 기준 NFC 정규화 상대경로
collection_label: logical_path의 첫 구간, 일반 파일은 "개별 파일"
```

지원 확장자는 대소문자를 구분하지 않는다. 폴더에서 미지원 확장자는 제외하고
`지원하지 않는 파일 N개를 제외했습니다`를 표시한다. 지원 파일이 하나도 없으면
서버 요청을 보내지 않는다.

### 5.3 논리 상대경로 정책

논리 상대경로는 표시·출처 구분용 데이터이며 파일 시스템 경로로 해석하지
않는다. 브라우저, BFF, Python 서비스가 각각 다음 조건을 검사한다.

- NFC 정규화 후 `/` 구분자만 사용
- 전체 길이 512자 이하
- 비어 있는 구간, `.` 또는 `..` 구간 금지
- 선행 `/`, 역슬래시, 드라이브 접두사, URI 스킴 금지
- 제어문자와 NUL 금지
- 마지막 구간은 실제 `File.name`과 일치
- 일반 파일 선택은 `File.name`을 논리 상대경로로 사용

검증된 논리 상대경로는 로컬 Source의 `display_name` 또는 `aliases`에 저장한다.
staging 파일은 계속 안전한 basename과 opaque token만 사용한다. 논리 경로는
staging 목적지 생성에 사용하지 않는다.

### 5.4 반복 선택과 정본 누적

하나의 폴더 선택은 한 루트를 고른다. 사용자는 폴더 선택을 반복해 여러 폴더를
같은 실행에 추가할 수 있다. 일반 파일 선택도 반복 누적된다.

누적의 정본은 서버 Source Registry다. 서비스의 `RunSnapshot`에 경로 토큰과
snapshot 경로를 제외한 `uploaded_files` 요약을 추가한다. 각 항목은 다음 공개
필드만 가진다.

```text
source_id
logical_path
display_name
media_type
size_bytes
collection_label
```

BFF는 위 필드만 브라우저 계약으로 전달한다. live UI는 별도
`selectedFiles` 누적 상태를 정본으로 삼지 않고 매 mutation·상태 조회 응답의
`uploaded_files`를 렌더링한다. 따라서 새로고침 후에도 run ID로 정본을 다시
불러와 목록을 복원한다. replay 공급자는 같은 계약을 메타데이터 전용 세션
상태로 모사한다.

UI는 `collection_label`로 폴더별 그룹을 만들고 그룹 안에서 `logical_path`를
표시한다. 절대경로나 staging 경로는 표시하지 않는다.

### 5.5 중복과 충돌

- 같은 논리 경로 + 같은 SHA-256: 멱등 성공, 새 항목 없음
- 다른 논리 경로 + 같은 SHA-256: blob은 공유하고 논리 경로 alias 추가
- 같은 논리 경로 + 다른 SHA-256: 불변 근거 충돌로 새 배치 전체 거부
- 같은 basename + 다른 폴더/내용: 서로 다른 논리 경로의 별도 Source 허용

실행당 64개 제한은 고유 blob 수가 아니라 고유 논리 경로 수에 적용한다. 같은
내용의 파일을 여러 경로로 추가해도 각 논리 경로는 파일 수 제한에 포함한다.

### 5.6 업로드 가능 시점

파일과 폴더 입력은 서버 `allowed_actions`에 `attach_data`가 있을 때만 활성화한다.
모델 작업이나 승인 흐름이 시작된 뒤에는 서버가 업로드를 거부하고 UI도 입력을
비활성화한다. 새 자료로 다시 분석하려면 새 실행을 시작한다.

## 6. 업로드 HTTP 계약

기존 multipart `files` 배열을 유지하고, 같은 순서의 반복
`logical_paths` 항목을 추가한다.

```text
expected_revision
idempotency_key
files[]
logical_paths[]
```

BFF와 Python 서비스는 파일 수와 논리 경로 수가 정확히 같은지 검사한다.
일치하지 않으면 정본을 바꾸지 않고 `INPUT_POLICY_FAILURE`로 거부한다. BFF는
브라우저가 보낸 filename과 논리 경로 마지막 구간의 일치도 검사한 뒤 내부
서비스로 전달한다.

기존 클라이언트 호환을 위해 `logical_paths`가 완전히 없으면 각 `File.name`을
논리 경로로 사용한다. 일부 파일에만 논리 경로가 있으면 모호한 배치로 거부한다.

기존 제한을 유지한다.

- 실행당 최대 고유 논리 경로 64개
- 파일당 최대 25 MiB
- 실행당 원본 총합 최대 250 MiB
- BFF 선언 크기 사전 검사와 Python 스트리밍 실측 검사

새 배치는 원자적이다. staging, Markdown 검증, 경로 충돌 검사, Source Registry
결합 중 하나라도 실패하면 새 배치의 staging 파일과 임시 상태를 정리하고 기존
revision과 누적 Source를 유지한다.

## 7. Markdown 파일 정책

### 7.1 확장자와 미디어 타입

`.md`를 허용 확장자와 이중 확장자 검사 집합에 추가한다. 다음 미디어 타입을
허용한다.

- `text/markdown`
- `text/x-markdown`
- `text/plain`
- 브라우저가 타입을 모를 때 사용하는 `application/octet-stream`

미디어 타입은 확장자·본문 검증을 대체하지 않는다.

### 7.2 본문 검증

Markdown은 다음 순서로 검사한다.

1. 빈 파일과 기존 크기 제한 거부
2. UTF-8 또는 UTF-8 BOM 디코딩
3. CRLF·CR을 LF로 정규화
4. NUL과 탭·LF를 제외한 C0 제어문자 거부
5. 빈 본문 거부
6. 원본 bytes SHA-256과 정규화 본문 SHA-256 기록

Markdown HTML을 실행하거나 렌더링하지 않는다. 링크 대상과 이미지 대상에
네트워크 요청을 하지 않는다. 코드 펜스 안의 텍스트를 실행하지 않는다.

## 8. Document Evidence 계약

### 8.1 구간화

구간화는 모델을 호출하지 않는 결정론적 함수다.

- 코드 펜스 밖의 ATX 제목(`#`부터 `######`)을 섹션 경계로 사용
- 제목이 없는 문서는 문서 루트를 하나의 섹션으로 사용
- 섹션이 2,000자를 넘으면 줄 경계에서 추가 분할
- 한 줄이 2,000자를 넘으면 Unicode 문자 경계에서 분할
- 빈 구간은 생성하지 않음
- 각 구간에 1부터 시작하는 원문 정규화 줄 시작·끝 번호 기록
- `heading_path`는 상위 제목부터 현재 제목까지의 NFC 문자열 배열

### 8.2 구간 스키마

새 `document-evidence.schema.json`은 최소한 다음 필드를 가진다.

```text
document_evidence_id: document_[0-9a-f]{24}
source_id
logical_path
chunk_index
heading_path
line_start
line_end
content
content_sha256
normalized_document_sha256
locator_type: markdown_lines
integrity.payload_hash
```

`document_evidence_id`는 Source ID, 정규화 문서 해시, 구간 인덱스, 줄 범위,
본문 해시의 canonical JSON으로부터 생성한다. 레지스트리는 ID 순으로 정렬하고
`intake/document-evidence/<source_id>.json`에 저장한다.

### 8.3 Evidence Core

Evidence Core에 선택적 `document_evidence_register`를 추가한다. 새 실행은 항상
배열을 생성하고 기존 문서가 없는 실행은 빈 배열을 사용한다. 이전에 생성된
Evidence Core에는 필드가 없어도 빈 배열과 같은 의미로 검증해 저장된 fixture와
snapshot을 읽을 수 있게 한다.

Evidence Core 검증기는 다음을 추가로 확인한다.

- 구간 ID 중복 없음
- 모든 `source_id`가 Source Registry에 존재
- Source 확장자와 media type이 Markdown 정책에 부합
- 줄 범위와 chunk index가 양의 정수이며 한 Source 안에서 결정론적 순서
- `content_sha256`, 문서 해시, payload hash 일치
- Source blob을 다시 정규화·구간화한 결과와 레지스트리가 정확히 일치
- 논리 상대경로가 Source `display_name` 또는 `aliases`에 존재

## 9. Reasoning Job과 모델 경계

### 9.1 Job 계약

Markdown이 있는 lens Job에만 다음 선택 필드를 추가한다.

```text
allowed_document_evidence_ids
document_evidence_context
```

`document_evidence_context`의 각 항목은 ID, Source ID, 제목 경로, 줄 범위,
본문, 본문 해시만 포함한다. 그 ID 집합은
`allowed_document_evidence_ids`와 정확히 일치해야 한다. 정렬, 중복, 본문
해시, 원본 레지스트리 일치 여부를 Job 생성 시와 gateway 호출 직전에 다시
검사한다.

문서 근거가 없는 기존 Job은 두 필드를 생략한다. 따라서 기존 Job canonical
payload와 `job_id`는 바뀌지 않는다. 문서 근거가 있는 Job의 `job_id`에는 전체
컨텍스트와 해시가 포함된다.

### 9.2 분할과 한계

lens의 work item은 Fact와 Document Evidence를 합친다.

- Job 하나당 Fact와 Document Evidence 합계 최대 48개
- Job 하나당 Markdown 본문 합계 최대 96,000 Unicode 문자
- 구간 하나당 최대 2,000 Unicode 문자
- 기존 lens shard 최대 6개 유지

모든 구간을 위 한계 안에서 Job에 넣을 수 없으면 임의로 자르지 않고
`scope_narrowing_required`를 반환한다. 사용자는 파일 수나 문서 범위를 줄인 새
실행을 시작한다.

### 9.3 프롬프트 인젝션 경계

gateway의 시스템 지침은 업로드 본문이 명령이 아닌 비신뢰 데이터임을 계속
선언한다. Markdown 컨텍스트는 정책 필드와 분리된 JSON 데이터 배열로만
전달하고 각 `document_evidence_id`를 `untrusted_text_markers`에 포함한다.

모델에는 셸, 웹 검색, URL fetch, 코드 실행, 파일 쓰기, MCP, function tool을
제공하지 않는다. Markdown 안의 `system`, `assistant`, 지시문, 링크, 코드가
어떤 형태이든 권한이나 허용 ID를 바꾸지 못한다.

## 10. 모델 결과와 Evidence Link 검증

문서 근거는 Fact나 Signal로 위장하지 않는다. 관련 초안·정본 계약을 다음처럼
확장한다.

- lens 관찰에 선택적 `document_evidence_ids` 허용
- `evidence_proposals[].evidence_ref`가 문서 근거 ID를 참조할 수 있음
- 정규화 카드에 `used_document_evidence_ids` 추가
- Evidence Link의 `evidence_ref` 패턴에 `document_` 추가
- Evidence Link의 `evidence_kind`에 `document` 추가
- value reference는 계속 Fact·Signal만 허용하여 문서 문장을 수치 치환에 쓰지 않음

초안·정본 검증기는 모든 문서 참조가 해당 Job의
`allowed_document_evidence_ids`에 있고 Job 컨텍스트 및 Evidence Core
레지스트리와 일치하는지 확인한다. 문서 근거는 material claim의 지원·반박·경계
근거가 될 수 있지만, 문서만으로 수치 계산 Fact를 만들거나 데이터 가용성
capability를 충족시키지 않는다.

Evidence Core 검증기는 `evidence_kind=document`인 모든 Link가 등록된 문서
구간을 가리키고, 그 구간이 다시 실제 Source blob에 도달하는지 검사한다.
통합·deep-dive·writer 단계는 검증된 claim과 Evidence Link를 사용하며 원문
Markdown 전체를 반복 전송하지 않는다.

## 11. 오류 처리

| 조건 | 처리 |
|---|---|
| 폴더의 미지원 파일 | 제외 후 개수 안내 |
| 지원 파일이 0개 | 서버 요청 없이 화면 오류 |
| 파일·경로 배열 수 불일치 | 배치 전체 거부 |
| 잘못된 상대경로 | 배치 전체 거부 |
| Markdown 인코딩·제어문자 실패 | 배치 전체 거부 |
| 파일·총량·개수 제한 초과 | 배치 전체 거부 |
| 기존 논리 경로와 다른 내용 충돌 | 기존 정본 유지, 새 배치 거부 |
| 분석 시작 뒤 업로드 | `INPUT_POLICY_FAILURE` |
| 문서 구간 처리 한계 초과 | `scope_narrowing_required`, 원문 누락 없음 |
| Job 허용 목록·컨텍스트 불일치 | Job 생성 또는 gateway 호출 거부 |
| 모델이 미허용 문서 ID 인용 | `AI_OUTPUT_INVALID`, 정본 미변경 |
| 구간·Source 해시 변조 | `VALIDATION_FAILURE`, 정본 미변경 |

오류 메시지는 사용자에게 한국어로 파일명 또는 논리 상대경로와 해결 방법을
알리되 절대경로, staging 경로, 내부 토큰, 본문을 포함하지 않는다.

## 12. 테스트 전략

기능 구현은 RED focused 테스트, 예상 실패 확인, 최소 구현, focused GREEN 순서로
진행한다.

### 12.1 Web focused 테스트

- `.md`가 파일 입력 accept와 replay 정책에서 허용됨
- 일반 파일 선택을 여러 번 하면 목록이 누적됨
- 폴더 선택이 하위 파일의 `webkitRelativePath`를 논리 경로로 변환함
- 여러 폴더를 차례로 선택하면 폴더 그룹과 파일이 누적됨
- 미지원 폴더 파일을 제외하고 제외 개수를 표시함
- 지원 파일이 없는 폴더는 provider를 호출하지 않음
- 같은 폴더 재선택을 위해 input 값이 초기화됨
- 서버 `uploaded_files`가 live 화면의 정본이며 새로고침 복원에 사용됨
- 분석 시작 후 두 입력이 비활성화됨
- BFF가 파일·논리 경로 순서와 크기 제한을 검증해 내부 서비스로 전달함

### 12.2 Python 업로드 정책 테스트

- Markdown 허용 media type 네 종류
- UTF-8, UTF-8 BOM, CRLF 정규화
- 잘못된 인코딩, NUL, 제어문자, 빈 본문 거부
- 논리 상대경로 traversal·절대경로·드라이브·URI·basename 불일치 거부
- 고유 논리 경로 기준 64개 제한
- 동일 경로·동일 내용 멱등성
- 다른 경로·동일 내용 alias와 blob dedup
- 동일 경로·다른 내용 충돌과 원자적 rollback
- 기존 CSV·JSON·XLSX 정책 회귀

### 12.3 Markdown와 Evidence 테스트

- 제목 계층, 제목 없는 문서, 긴 섹션, 긴 단일 줄, 코드 펜스 처리
- LF·CRLF 입력의 동일한 정규화 구간과 안정적인 ID
- 같은 입력의 반복 처리 결과 byte-for-byte 결정성
- Document Evidence ID·본문 해시·문서 해시·줄 범위 변조 거부
- Source Registry에 없는 Source와 논리 경로 참조 거부
- Markdown Source가 차단 품질 이슈 없이 문서 레지스트리에 등록됨
- Markdown이 데이터 mapping 질문이나 수치 capability를 만들지 않음

### 12.4 Reasoning과 모델 경계 테스트

- 문서 구간이 lens Job의 허용 ID와 컨텍스트에 포함됨
- 빈 문서 근거가 있는 기존 Job의 canonical payload와 job ID가 유지됨
- 48개 work item, 구간당 2,000자, Job당 96,000자, shard 6개 제한
- 한계 초과 시 조용한 누락 없이 `scope_narrowing_required`
- gateway가 문서 본문을 비신뢰 JSON 데이터로만 전달하고 도구를 제공하지 않음
- 허용 문서 ID 인용 통과
- 미등록·다른 shard·변조 문서 ID 인용 거부
- 문서 Evidence Link가 Source까지 도달함
- 문서 참조를 value reference로 사용하면 거부

### 12.5 완료 게이트

변경 범위 focused GREEN 후 구현 단위가 끝나면 저장소 규칙의 전체 완료 게이트를
한 번 실행한다.

- 계약 검사와 관련 Python 계약 테스트
- Python 전체 테스트
- Web typecheck, lint, unit test, production build
- launcher 테스트
- Playwright

완료 게이트 뒤 동작 코드나 설정이 바뀐 경우에만 영향받은 게이트를 다시
실행한다.

## 13. 구현 경계

구현은 다음 책임 단위로 나눈다.

1. Web 선택 정규화·폴더 입력·누적 표시
2. BFF·서비스 multipart 논리 경로 계약
3. Python 업로드 정책과 Source 누적 충돌 규칙
4. Markdown 결정론적 구간화와 Document Evidence 스키마
5. Evidence Core·Reasoning Job·Evidence Link 검증기 확장
6. 모델 gateway 비신뢰 컨텍스트 전달
7. 서버 정본 업로드 요약과 replay 호환
8. focused 회귀와 전체 완료 게이트

각 단위는 기존 사용자 변경인 `.gitignore`, `AGENTS.md`, `web/next-env.d.ts`와
관련 없는 미추적 문서·평가 자료를 수정하거나 커밋하지 않는다.

## 14. 보안 불변조건

- `.env.local`과 `OPENAI_API_KEY` 값은 읽거나 출력하거나 커밋하지 않는다.
- 절대경로와 staging 경로는 브라우저 응답, 모델 Job, 오류, 로그에 포함하지
  않는다.
- 논리 상대경로는 표시 데이터이며 파일 시스템 연산에 사용하지 않는다.
- 업로드 본문은 명령이 아니라 비신뢰 데이터다.
- 모델 출력은 제안이며 로컬 계약·참조·해시 검증 전에는 정본이 아니다.
- 모델은 허용 목록 밖의 근거를 만들거나 참조할 수 없다.
- 분석 시작 뒤 Source 집합은 불변이다.
- 새 배치 실패는 기존 revision과 누적 Source를 바꾸지 않는다.

## 15. 독립 자문 상태

읽기 전용 Claude 아키텍처 자문을 승인받아 시도했으나 Claude Code OAuth 토큰이
만료되어 모델 실행 전에 두 번 모두 중단됐다. 입력·출력 토큰은 0이었고 자문
결과는 이 설계에 사용되지 않았다. 본 설계는 현재 Codex가 저장소 코드, 계약,
테스트 구조에 대조해 작성했다.
