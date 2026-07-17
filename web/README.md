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
