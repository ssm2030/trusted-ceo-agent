# Trusted CEO Agent 웹 프로그램 구현 계획 색인

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 승인된 웹 설계를 네 개의 구현 계획으로 안전하게 조정해, 공통 계약 이후 핵심 시연을 병렬 개발하고 선택적인 실시간 분석 연결은 마지막에 추가한다.

**Architecture:** 플러그인이 분석과 신뢰의 정본이며, `contracts/web-report/v1`이 Python과 TypeScript 사이의 유일한 표시 계약이다. `web/`은 `src/`를 쓰는 단일 Next.js localhost 앱이고 저장된 분석 흐름, 결과 리포트, 결과 질문을 분리된 provider와 server boundary로 연결한다. 실시간 분석 제공자는 같은 화면 계약을 사용하지만 핵심 시연이 완성된 뒤에만 켠다.

**Tech Stack:** Python 3.11, uv frozen/offline plugin runtime, Node.js 22.22.0, npm, Next.js 16 App Router, React 19, TypeScript 5, Vitest, Playwright, Apache ECharts core SVG, 로컬 Codex CLI

---

## 정본과 실행 대상

요구사항 정본:

- `docs/superpowers/specs/2026-07-17-trusted-ceo-agent-web-design-final.md`
- `docs/superpowers/specs/2026-07-17-trusted-ceo-agent-web-design-final-addendum-v2.md`

하위 구현 계획:

1. `docs/superpowers/plans/2026-07-17-trusted-ceo-agent-web-contracts.md`
2. `docs/superpowers/plans/2026-07-17-trusted-ceo-agent-web-viewer.md`
3. `docs/superpowers/plans/2026-07-17-trusted-ceo-agent-result-qa.md`
4. `docs/superpowers/plans/2026-07-17-trusted-ceo-agent-live-analysis.md`

이 색인을 먼저 읽고 하위 계획을 실행한다. 하위 계획 사이에 같은 파일, 타입 또는 상태 이름이 다르면 이 색인의 조정 규칙을 적용한다. 요구사항 의미가 충돌하면 final spec과 addendum v2가 최우선이다.

## 단일 웹 경로 규칙

웹은 `create-next-app --src-dir`로 만든 단일 앱이다. production TypeScript와 React는 아래에만 둔다.

```text
web/src/app/**                 Next.js App Router와 Route Handlers
web/src/features/**            브라우저 기능과 화면
web/src/lib/client/**          브라우저 전용 공통 코드
web/src/lib/server/**          server-only 공통 코드
web/src/server/analysis/**     실시간 분석 제공자
web/src/types/**               전역 TypeScript 선언
web/tests/unit/**              단위·서버 통합 테스트
web/tests/component/**         React component 테스트
web/tests/e2e/**               Playwright
web/scripts/**                 로컬 사전 점검
```

결과 Q&A 계획의 경로는 다음 exact 경로로 치환한다.

```text
web/app/...                         -> web/src/app/...
web/lib/client/...                  -> web/src/lib/client/...
web/lib/server/...                  -> web/src/lib/server/...
web/components/questions/...        -> web/src/features/questions/...
web/components/results/ResultWorkspace.tsx
                                    -> web/src/features/report/ReportWorkspace.tsx
web/types/web-speech.d.ts           -> web/src/types/web-speech.d.ts
```

`web/tests/**`, `web/scripts/**`, `contracts/**`, `plugin/**`, `tests/**` 경로는 그대로다. `web/app`, `web/lib`, `web/components`를 별도 production root로 만들지 않는다. Q&A 계획의 `git add` 명령도 위 치환이 끝난 실제 경로만 stage한다.

## 공통 AnalysisProvider 계약

재현 제공자와 실시간 제공자는 `web/src/features/analysis/analysis-provider.ts`의 같은 계약을 사용한다. 웹 뷰어 계획의 `ProviderSnapshot` shape를 정본으로 고정한다.

```ts
export type PendingAction =
  | "human_response"
  | "terminal_approval"
  | "provider_work"
  | "retry"
  | "resume"
  | "request_changes"
  | "terminal";

export type ProviderSnapshot = {
  provider_kind: "replay" | "plugin";
  display_badge: "저장된 시연 흐름" | "실시간 플러그인";
  run_id: string;
  revision: number;
  workflow_status: string;
  ui_phase: 1 | 2 | 3 | 4 | 5 | 6 | 7;
  pending_action: PendingAction;
  pending_approval_request_id: string | null;
  allowed_actions: string[];
  latest_event: string;
  progress: number;
  result_ref: string | null;
  error: null | {
    code:
      | "STALE_REVISION"
      | "HUMAN_RESPONSE_REQUIRED"
      | "TERMINAL_APPROVAL_REQUIRED"
      | "RETRYABLE_PROVIDER_FAILURE"
      | "CONTRACT_FAILURE"
      | "INTEGRITY_FAILURE"
      | "STOPPED"
      | "CANCELLED";
    message: string;
  };
};
```

실시간 분석 계획 Task 1은 별도 `AnalysisResponse` shape를 만들지 않고 위 `ProviderSnapshot`을 import한다. plugin `provider-status.next_operation`은 server-only 조정 객체이며 브라우저 공개 `pending_action`과 다르다. `result.pending_action.kind`를 검사하는 예시는 `result.pending_action` enum을 검사하도록 실행한다.

`ui_phase`는 final spec 4.3을 정확히 따른다.

```text
1 목표와 자료 준비:
  created, context_confirmation_required, context_ready
2 데이터 구조 확인:
  schema_mapping_job_ready, mapping_proposal_ready, data_confirmation_required, evidence_ready
3 문제 탐색:
  scope_narrowing_required, lens_jobs_ready, lens_ready, integrated_draft
4 사람 확인:
  diagnostic_approval_required
5 심층 분석:
  deep_dive_authorized, deep_dive_jobs_ready, deep_dive_ready
6 보고서 작성:
  finalization_jobs_ready, writer_ready, final_approval_required, delivery_approved
7 완료:
  finalized
```

브라우저 action에는 `approve`가 없다. `prepareTerminalApprovalRequest`는 request를 만들거나 기존 request를 반환할 뿐이며 실제 승인과 변경 결정은 터미널의 interactive TTY 명령에서만 수행한다.

## 공통 결과·질문 범위

결과 화면과 질문은 다음 exact key를 공유한다.

```ts
export type ConversationKey = {
  runId: string;
  revision: number;
  scopeKind: ScopeKind;
  scopeInstanceId: string;
};

export function serializeConversationKey(key: ConversationKey): string {
  return [
    key.runId,
    String(key.revision),
    key.scopeKind,
    key.scopeInstanceId,
  ].join("\u001f");
}
```

`issueId`는 검색·표시 metadata일 수 있지만 대화 고유 키가 아니다. 같은 문제의 서로 다른 evidence link, source preview, expert packet, revision item은 서로 다른 `scopeInstanceId`를 사용한다.

## 계약과 출력 경계

Contract 0 계획이 다음 여섯 schema와 generated types의 최초 파일을 소유한다.

```text
web-report-bundle.schema.json
viewer-eligibility-decision.schema.json
presentation-manifest.schema.json
result-question-job.schema.json
result-answer-draft.schema.json
result-answer.schema.json
generated/types.ts
```

결과 Q&A 계획의 schema 작업은 같은 파일을 다시 설계하지 않는다. Contract 0 결과를 Q&A validator 요구사항과 대조하고, 변경이 필요하면 schema, generated type, valid fixture, invalid fixture를 같은 commit에서 갱신한다. 웹 뷰어와 Q&A는 손으로 복제한 schema interface 대신 generated type을 import한다.

Contract 계획의 `export-web-report --output` 구현은 다음 안전 조건을 추가한다.

```text
1. output의 resolve된 parent가 현재 workspace 안이다.
2. parent의 모든 기존 경로 요소는 symlink가 아닌 실제 directory다.
3. output은 immutable run, plugin root, logs, web/var 밖이다.
4. output 파일이 이미 있으면 실패하며 덮어쓰지 않는다.
5. 같은 parent의 임시 파일에 fsync한 뒤 신규 파일로 원자 이동한다.
6. CLI response의 절대 경로는 웹 client response에서 제거한다.
```

`rfc8785==0.1.4`를 lock한 뒤 네트워크 없이 다음 명령이 성공해야 Contract 0 gate를 통과한다.

```bash
uv sync --project plugin/trusted-ceo-agent --frozen
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -c "import rfc8785; print(rfc8785.__version__)"
```

Expected: 두 명령 exit 0. 두 번째 출력은 `0.1.4`다.

## 실행 파동

### Task 1: 공통 계약 고정

- [ ] Contract 0 계획의 schema RED tests를 실행한다.
- [ ] 여섯 schema, 타입 생성, valid/invalid fixture를 구현한다.
- [ ] Python validator와 TypeScript drift check를 모두 통과시킨다.
- [ ] `export-web-report`와 `validate-web-report`의 최소 수직 흐름을 통과시킨다.
- [ ] safe output path와 frozen/offline dependency를 검증한다.
- [ ] Contract commit을 만든다.

Gate:

```bash
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.contracts.test_web_report_contracts
npm --prefix contracts/web-report run check
```

Expected: 두 명령 모두 exit 0이며 generated type drift가 없다.

### Task 2: 핵심 시연 병렬 구현

Contract gate 뒤 다음 작업을 병렬 실행한다.

- [ ] 작업자 A: 웹 뷰어 계획의 Next.js 골격, 제품 셸, replay 분석 탭.
- [ ] 작업자 B: Contract 계획의 full exporter, ancestry validator, representative bundle.
- [ ] 작업자 C: 웹 뷰어 계획의 bundle adapter, 결과 저장소, 다섯 결과 화면.

병합 순서는 골격 → generated type 소비 → exporter fixture → 결과 화면이다. 각 작업자는 자신이 맡은 exact 파일만 stage한다.

Gate:

```bash
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest discover -s tests
npm --prefix web run typecheck
npm --prefix web run lint
npm --prefix web run test
npm --prefix web run build
```

Expected: plugin 전체 suite와 웹 정적·단위·build 검사가 모두 PASS.

### Task 3: 실제 결과 질문 추가

- [ ] Q&A plugin scope/job/answer validator를 구현한다.
- [ ] 로컬 Codex one-shot bridge를 fake executable로 검증한다.
- [ ] target Mac Seatbelt outside-canary와 company/POC capability gate를 구현한다.
- [ ] append-only ConversationStore를 exact 범위 key로 구현한다.
- [ ] compact floating drawer와 push-to-talk/TTS fallback을 연결한다.
- [ ] 같은 문제의 서로 다른 두 start ref 대화 복원을 Playwright로 검증한다.

Gate:

```bash
npm --prefix web run test
npm --prefix web run test:e2e -- tests/e2e/result-question.spec.ts
npm --prefix web run question:preflight
```

Expected: 자동 tests PASS. 실제 Mac preflight가 company mode를 통과하지 못하면 `companyDataEnabled=false`이며 저장 결과와 POC 제한 모드는 계속 작동한다.

### Task 4: 대회 대표 실행본 고정

- [ ] 실제 TTY로 context, data, 필요한 경우 scope, diagnostic, final gate를 처리한다.
- [ ] `finalize`, full `validate`, `export-web-report`, `validate-web-report`를 순서대로 실행한다.
- [ ] 등록 full-run과 bundle hash를 run registry에 넣는다.
- [ ] `fixture_only=true`면 `검증된 POC 시연 실행본`, 실제 승인 run이면 `승인·검증된 실행본`으로만 표시한다.
- [ ] 독립 JSON import가 항상 `출처 미확인 묶음`이며 질문이 비활성인지 확인한다.

Gate:

```bash
npm --prefix web run test:e2e
```

Expected: 두 탭, 최대 세 문제, chart→evidence, source preview, 다섯 결과 화면, 한 방향 전문가 패킷, revision, 실제 text question, drawer 복원이 모두 PASS.

### Task 5: 시간이 남을 때 live provider 연결

핵심 시연 gate가 모두 통과한 뒤에만 실시간 분석 계획을 실행한다.

- [ ] plugin `provider-status`와 `attach-data`를 구현한다.
- [ ] server-only coordinator와 stage Codex runner를 구현한다.
- [ ] 실제 TTY 승인 경계를 유지한 채 live routes를 연결한다.
- [ ] `ANALYSIS_PROVIDER=replay|plugin` 명시 설정만 허용한다.
- [ ] live preflight 실패 시 replay로 되돌리고 대표 결과 current를 유지한다.

Gate:

```bash
npm --prefix web run preflight:live
npm --prefix web run test:e2e:live
```

Expected: target Mac에서 preflight와 sanitized POC live flow가 PASS하거나, live mode만 명확히 비활성이고 핵심 replay·report·Q&A 시연은 계속 PASS.

## 대회 중단 기준

아래 중 하나라도 발생하면 live provider 작업을 멈추고 핵심 시연본을 동결한다.

- 대표 viewer-bundle cross-validation 실패
- 실제 결과 질문의 plugin answer validation 실패
- Mac outside-read canary 실패인데 company mode가 활성화됨
- replay 또는 결과 리포트 회귀
- 전체 plugin suite 실패
- production build 실패

시각 polish는 핵심 gate 이후에만 한다. 대회 당일 계약 변경은 major를 덮어쓰지 않고 새 adapter와 fixture를 함께 추가한다.

## 전체 완료 기준

- 모든 사용자 문구는 한국어다.
- 분석 탭은 `저장된 시연 흐름`과 `실시간 플러그인`을 혼동시키지 않는다.
- 결과 탭은 plugin-provided 최대 세 문제와 보수적 chart만 그린다.
- 다섯 결과 화면과 질문이 같은 `ReportScope`를 사용한다.
- 결과 질문은 plugin이 준비하고 검증하며 Codex draft를 직접 보여주지 않는다.
- 전문가 패킷은 화면·Markdown·인쇄 전용이고 전문가 답변 수집 기능이 없다.
- 데이터 또는 분석 변경은 새 revision을 만들고 질문·음성·다운로드는 만들지 않는다.
- 실제 승인 기록은 터미널 TTY에서만 생성된다.
- 저장 결과 열람은 Codex, 음성, live provider 실패와 무관하게 작동한다.
