# Trusted CEO Agent Web

대회용 `127.0.0.1` 전용 Next.js App Router 웹입니다. 플러그인이 분석과
신뢰의 정본이며, 이 앱은 저장된 시연 흐름과 검증된 결과를 표시합니다.

## 런타임

- Node.js `22.22.0`
- npm
- Next.js 16 / React 19 / TypeScript 5

```powershell
npm --prefix web install
npm --prefix web run dev
```

브라우저에서 `http://127.0.0.1:3000`을 엽니다. 분석 탭의 replay 업로드는
CSV, JSON, XLSX 파일의 메타데이터만 브라우저 세션에 보존하며 파일 내용을
분석하거나 저장하지 않습니다. 실제 승인 작업은 웹이 아닌 플러그인의
interactive Terminal TTY 흐름에서만 수행합니다.

## 결과 리포트 가져오기

[HD-06 운영 계약](../docs/operations/prompts/HD-06-export-web-report.md)이
생성·검증한 다음 파일을 사용합니다.

```text
exports/<run_id>/revision-<revision>/web-report-bundle.json
```

`http://127.0.0.1:3000/report`에서 `웹 리포트 JSON 파일`을 선택하고
`리포트 가져오기`를 누릅니다. 파일명은 정확히
`web-report-bundle.json`이어야 하며 최대 크기는 50 MiB입니다. 검증이
실패하면 현재 표시 중인 결과는 교체되지 않습니다.
파일 가져오기 경로는 bundle의 Schema·hash·참조를 검사한 뒤에도 표시 mode를
의도적으로 `unverified_import`(`출처 미확인 묶음`)로 설정합니다. HD-06의
source viewer mode와 같다고 가정하거나 `trusted_final`로 표시하지 않습니다.
trusted 등록 게시 경로는 artifact store root와 bundle path를 분리하는 별도
계약·구현 전까지 대회 당일 HD-07 절차에 포함하지 않습니다.


결과 리포트는 다섯 상단 화면을 유지합니다.

1. 최고경영자 의사결정 요약
2. 컨설턴트 근거 분석
3. 실행·신뢰 기록
4. 전문가 검토 패킷
5. 변경 이력

`컨설턴트 근거 분석`은 `분석 결론`, `근거·출처`, `검증 계획`으로
나뉩니다. 웹은 WebReportBundle에 저장된 공개 필드만 결정적으로 표시하며
대화 전용 내용이나 비공개 중간 Artifact를 분석·복원하지 않습니다.
