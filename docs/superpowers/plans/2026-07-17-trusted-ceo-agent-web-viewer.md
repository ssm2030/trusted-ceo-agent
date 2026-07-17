# Trusted CEO Agent Web Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a macOS-localhost Next.js web application with an honest replay analysis workspace and a read-only, evidence-grounded five-section executive report viewer.

**Architecture:** The standalone `web/` npm application consumes only the versioned `contracts/web-report/v1` contract and never imports the plugin Python package. Server-only modules validate bundles, call the plugin CLI through its frozen offline launcher for registered-run cross-validation, retain source previews, and atomically publish a safe client view; React renders the two tabs without creating analysis judgments. The report workspace exposes a stable `ReportScope` and an empty question-bubble slot, while result Q&A and a live AnalysisProvider remain outside this plan.

**Tech Stack:** Node.js 22.22.0, npm, Next.js 16 App Router, React 19, TypeScript 5, CSS Modules/global CSS without Tailwind, Apache ECharts core with SVG renderer, AJV Draft 2020-12, Vitest, Testing Library, Playwright, axe-core.

---

## Execution boundaries

- Canonical requirements are only:
  - `docs/superpowers/specs/2026-07-17-trusted-ceo-agent-web-design-final.md`
  - `docs/superpowers/specs/2026-07-17-trusted-ceo-agent-web-design-final-addendum-v2.md`
- Do not use the older web drafts or the first addendum as requirements.
- `contracts/web-report/v1/` is a prerequisite owned by the shared Contract 0 workstream. Before Task 2, it must contain the six schemas, generated TypeScript types, and valid/invalid fixtures named in the final design.
- The plugin workstream owns `export-web-report` and `validate-web-report`. This plan owns only the safe Node child-process adapter and its tests.
- Do not import `plugin/trusted-ceo-agent/trusted_ceo_agent` from TypeScript.
- Do not read `final-result.json` or a delivery package directly in the browser.
- Do not implement result Q&A, Codex CLI execution, conversation persistence, voice input/output, or a live plugin AnalysisProvider in this plan.
- Do expose `ReportScope` and `QuestionBubbleSlotProps` so the Q&A workstream can attach without changing report architecture.
- Do not create an expert response form, expert review completion state, or expert-response reanalysis path.
- Every user-facing label and error is Korean. Trace IDs, file names, and stable object IDs may remain technical.
- Every feature follows RED, observed failure, minimal GREEN, focused regression, then commit.
- Run commands from the repository root unless the command explicitly changes directory.
- Because the current worktree contains unrelated untracked files, stage only the exact files listed in each task.

## Required shared contract exports

The Contract 0 workstream must export these exact type names from `contracts/web-report/v1/generated/types.ts`:

```ts
export type WebReportBundleV1 = {};
export type ViewerEligibilityDecisionV1 = {};
export type PresentationManifestV1 = {};
export type SourcePreviewV1 = {};
export type ExpertPacketViewItemV1 = {};
export type RevisionViewV1 = {};
```

The empty bodies above describe export names only; the generated file must contain the full schema-derived shapes. Web code imports the generated definitions and does not duplicate them.

## File map

```text
.gitignore
web/
  .nvmrc
  package.json
  package-lock.json
  next.config.ts
  tsconfig.json
  eslint.config.mjs
  vitest.config.ts
  playwright.config.ts
  README.md
  src/
    app/
      globals.css
      layout.tsx
      page.tsx
      analysis/page.tsx
      report/loading.tsx
      report/page.tsx
      api/report/current/route.ts
      api/report/import/route.ts
      api/report/source-previews/[previewRef]/route.ts
      api/report/expert-packets/[packetId]/route.ts
    config/
      runtime.ts
      __tests__/runtime.test.ts
    contracts/
      v1.ts
    features/
      shell/
        labels.ko.ts
        ProductShell.tsx
        TopTabs.tsx
        RunHeader.tsx
        __tests__/TopTabs.test.tsx
        __tests__/RunHeader.test.tsx
      analysis/
        analysis-model.ts
        analysis-provider.ts
        replay-scenario.ts
        replay-provider.ts
        replay-session-store.ts
        ReplayCommandCenter.tsx
        StageRail.tsx
        CurrentWorkPanel.tsx
        RunDetailsPanel.tsx
        DataUploadCard.tsx
        HumanResponseForm.tsx
        TerminalApprovalNotice.tsx
        __tests__/replay-provider.test.ts
        __tests__/upload-policy.test.ts
        __tests__/ReplayCommandCenter.test.tsx
        __tests__/TerminalApprovalNotice.test.tsx
      report/
        model/
          view-model.ts
          adapter-v1.ts
          report-scope.ts
          eligibility.ts
          chart-option.ts
          expert-packet-markdown.ts
          __tests__/adapter-v1.test.ts
          __tests__/report-scope.test.ts
          __tests__/eligibility.test.ts
          __tests__/chart-option.test.ts
          __tests__/expert-packet-markdown.test.ts
        QuestionBubbleSlot.tsx
        ReportWorkspace.tsx
        ReportSectionNav.tsx
        DecisionBrief.tsx
        IssueSummaryCards.tsx
        FullIssueStructure.tsx
        EvidenceWorkbench.tsx
        TrustManifest.tsx
        ExpertPackets.tsx
        RevisionChanges.tsx
        SourcePreviewDialog.tsx
        __tests__/ReportWorkspace.test.tsx
        __tests__/EvidenceWorkbench.test.tsx
        __tests__/ExpertPackets.test.tsx
        __tests__/RevisionChanges.test.tsx
        __tests__/SourcePreviewDialog.test.tsx
        charts/
          EChartCanvas.tsx
          ChartPanel.tsx
          IssueGraph.tsx
          EvidenceFallbackTable.tsx
          __tests__/EChartCanvas.test.tsx
          __tests__/ChartPanel.test.tsx
    lib/
      server/
        contract-paths.ts
        bundle-validator.ts
        bundle-integrity.ts
        import-policy.ts
        plugin-validator-client.ts
        run-registry.ts
        report-store.ts
        source-preview-repository.ts
        official-url-policy.ts
        expert-packet-export.ts
        __tests__/bundle-validator.test.ts
        __tests__/bundle-integrity.test.ts
        __tests__/import-policy.test.ts
        __tests__/plugin-validator-client.test.ts
        __tests__/run-registry.test.ts
        __tests__/report-store.test.ts
        __tests__/source-preview-repository.test.ts
        __tests__/official-url-policy.test.ts
    test/
      setup.ts
  tests/
    e2e/
      two-tabs.spec.ts
      analysis-replay.spec.ts
      report-navigation.spec.ts
      report-evidence.spec.ts
      expert-revision.spec.ts
      bundle-import.spec.ts
      accessibility.spec.ts
```

## Task 1: Node 22.22.0 and Next.js 16 testable application shell

**Files:**

- Modify: `.gitignore`
- Create: `web/.nvmrc`
- Create: `web/package.json`
- Create: `web/package-lock.json`
- Create: `web/next.config.ts`
- Create: `web/tsconfig.json`
- Create: `web/eslint.config.mjs`
- Create: `web/vitest.config.ts`
- Create: `web/playwright.config.ts`
- Create: `web/src/test/setup.ts`
- Create: `web/src/config/runtime.ts`
- Create: `web/src/config/__tests__/runtime.test.ts`
- Create: `web/src/app/globals.css`
- Create: `web/src/app/layout.tsx`
- Create: `web/src/app/page.tsx`

- [ ] **Step 1: Create the npm project and pin the requested majors**

Run:

```bash
mkdir web
cd web
npm init -y
npm install --save-exact next@16 react@19 react-dom@19 echarts@6 ajv@8 ajv-formats@3 json-canonicalize@2
npm install --save-dev --save-exact typescript@5 @types/node@22 @types/react@19 @types/react-dom@19 eslint@9 eslint-config-next@16 vitest@4 jsdom@27 vite-tsconfig-paths@6 @testing-library/react@16 @testing-library/jest-dom@6 @testing-library/user-event@14 @playwright/test@1 @axe-core/playwright@4
cd ..
```

Expected: `web/package-lock.json` is created and `npm` reports no unresolved dependency.

Set the package metadata and scripts to:

```json
{
  "name": "trusted-ceo-agent-web",
  "version": "0.1.0",
  "private": true,
  "engines": {
    "node": "22.22.0"
  },
  "scripts": {
    "dev": "next dev --hostname 127.0.0.1",
    "build": "next build",
    "start": "next start --hostname 127.0.0.1",
    "lint": "eslint .",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:e2e": "playwright test"
  }
}
```

Keep the exact dependency versions written by `npm install --save-exact` in the same file.

- [ ] **Step 2: Add runtime and test configuration**

Write `web/.nvmrc`:

```text
22.22.0
```

Configure TypeScript with strict mode, `@/* -> ./src/*`, DOM libraries, and `noEmit`. Configure Vitest with `jsdom`, `src/test/setup.ts`, and the same alias. Configure Playwright with Chromium, base URL `http://127.0.0.1:3000`, and a web server command of `npm run dev`.

Add these entries to `.gitignore`:

```gitignore
web/node_modules/
web/.next/
web/coverage/
web/playwright-report/
web/test-results/
web/var/
web/.tmp/
```

- [ ] **Step 3: Write the failing runtime contract test**

```ts
import { describe, expect, it } from "vitest";
import { RUNTIME_CONTRACT } from "@/config/runtime";

describe("RUNTIME_CONTRACT", () => {
  it("pins the tournament runtime and localhost boundary", () => {
    expect(RUNTIME_CONTRACT).toEqual({
      node: "22.22.0",
      nextMajor: 16,
      host: "127.0.0.1",
      packageManager: "npm",
    });
  });
});
```

- [ ] **Step 4: Run the test and observe RED**

Run:

```bash
npm --prefix web run test -- src/config/__tests__/runtime.test.ts
```

Expected: FAIL because `@/config/runtime` does not exist.

- [ ] **Step 5: Implement the minimal runtime contract and base App Router files**

Create `web/src/config/runtime.ts`:

```ts
export const RUNTIME_CONTRACT = Object.freeze({
  node: "22.22.0",
  nextMajor: 16,
  host: "127.0.0.1",
  packageManager: "npm",
} as const);
```

Create a Korean root layout and make `/` redirect to `/analysis`:

```tsx
// web/src/app/layout.tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Trusted CEO Agent",
  description: "근거 기반 최고경영자 의사결정 지원",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
```

```tsx
// web/src/app/page.tsx
import { redirect } from "next/navigation";

export default function HomePage() {
  redirect("/analysis");
}
```

Define CSS variables for navy, white, status colors, focus outline, a 12-column grid, and a Korean system font stack. Do not add Tailwind packages or directives.

- [ ] **Step 6: Verify GREEN and the baseline build**

Run:

```bash
node --version
npm --prefix web run test -- src/config/__tests__/runtime.test.ts
npm --prefix web run typecheck
npm --prefix web run lint
```

Expected: Node prints `v22.22.0`; the focused test, typecheck, and lint pass.

- [ ] **Step 7: Commit**

```bash
git add .gitignore web/.nvmrc web/package.json web/package-lock.json web/next.config.ts web/tsconfig.json web/eslint.config.mjs web/vitest.config.ts web/playwright.config.ts web/src/test web/src/config web/src/app/globals.css web/src/app/layout.tsx web/src/app/page.tsx
git commit -m "chore(web): scaffold local Next viewer"
```

## Task 2: Strict Contract 0 loader and v1 view-model adapter

**Files:**

- Create: `web/src/contracts/v1.ts`
- Create: `web/src/lib/server/contract-paths.ts`
- Create: `web/src/lib/server/bundle-validator.ts`
- Create: `web/src/features/report/model/view-model.ts`
- Create: `web/src/features/report/model/adapter-v1.ts`
- Create: `web/src/lib/server/__tests__/bundle-validator.test.ts`
- Create: `web/src/features/report/model/__tests__/adapter-v1.test.ts`

- [ ] **Step 1: Verify the prerequisite contract files**

Run:

```bash
test -f contracts/web-report/v1/web-report-bundle.schema.json
test -f contracts/web-report/v1/viewer-eligibility-decision.schema.json
test -f contracts/web-report/v1/generated/types.ts
test -f contracts/web-report/v1/fixtures/valid-poc.json
test -f contracts/web-report/v1/fixtures/invalid-reference.json
```

Expected: all commands exit `0`. If one fails, complete the shared Contract 0 plan before continuing this task.

- [ ] **Step 2: Write failing schema and adapter tests**

```ts
// web/src/lib/server/__tests__/bundle-validator.test.ts
// @vitest-environment node
import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";
import { contractFixturePath } from "@/lib/server/contract-paths";
import { validateBundleBytes } from "@/lib/server/bundle-validator";

describe("validateBundleBytes", () => {
  it("accepts the canonical POC fixture", async () => {
    const bytes = await readFile(contractFixturePath("valid-poc.json"));
    const bundle = await validateBundleBytes(bytes);
    expect(bundle.bundle_version).toMatch(/^1\./);
  });

  it("rejects an unsupported major", async () => {
    const bytes = await readFile(contractFixturePath("valid-poc.json"));
    const value = JSON.parse(bytes.toString("utf8"));
    value.bundle_version = "2.0.0";
    await expect(validateBundleBytes(Buffer.from(JSON.stringify(value)))).rejects.toMatchObject({
      code: "UNSUPPORTED_BUNDLE_MAJOR",
    });
  });
});
```

```ts
// web/src/features/report/model/__tests__/adapter-v1.test.ts
// @vitest-environment node
import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";
import { adaptBundleV1, toClientReport } from "@/features/report/model/adapter-v1";
import { contractFixturePath } from "@/lib/server/contract-paths";
import { validateBundleBytes } from "@/lib/server/bundle-validator";

describe("adaptBundleV1", () => {
  it("uses the plugin-provided CEO issue order without ranking", async () => {
    const bundle = await validateBundleBytes(
      await readFile(contractFixturePath("valid-poc.json")),
    );
    const view = adaptBundleV1(bundle, {
      mode: "poc_fixture",
      label: "검증된 POC 시연 실행본",
      trusted: false,
      questionsAllowed: false,
    });
    expect(view.ceoSummary.map((issue) => issue.issue_id)).toEqual(
      bundle.presentation_manifest.ceo_summary_issue_refs,
    );
    expect(view.ceoSummary.length).toBeLessThanOrEqual(3);
  });

  it("does not send embedded preview values to the report page", async () => {
    const bundle = await validateBundleBytes(
      await readFile(contractFixturePath("valid-poc.json")),
    );
    const client = toClientReport(
      adaptBundleV1(bundle, {
        mode: "poc_fixture",
        label: "검증된 POC 시연 실행본",
        trusted: false,
        questionsAllowed: false,
      }),
    );
    expect("sourcePreviewsById" in client).toBe(false);
  });
});
```

- [ ] **Step 3: Run focused tests and observe RED**

Run:

```bash
npm --prefix web run test -- src/lib/server/__tests__/bundle-validator.test.ts src/features/report/model/__tests__/adapter-v1.test.ts
```

Expected: FAIL because the contract bridge, validator, and adapter modules do not exist.

- [ ] **Step 4: Implement the contract bridge and strict validator**

Create `web/src/contracts/v1.ts` as a type-only bridge:

```ts
export type {
  ExpertPacketViewItemV1,
  PresentationManifestV1,
  RevisionViewV1,
  SourcePreviewV1,
  ViewerEligibilityDecisionV1,
  WebReportBundleV1,
} from "../../../contracts/web-report/v1/generated/types";
```

Create `contract-paths.ts` with repository-root resolution that never accepts a browser-supplied path:

```ts
import path from "node:path";

const REPOSITORY_ROOT = path.resolve(process.cwd(), "..");
export const CONTRACT_ROOT = path.join(REPOSITORY_ROOT, "contracts", "web-report", "v1");

export function contractFixturePath(name: string): string {
  if (!/^[a-z0-9-]+\.json$/.test(name)) {
    throw new Error("잘못된 계약 fixture 이름입니다.");
  }
  return path.join(CONTRACT_ROOT, "fixtures", name);
}
```

Create the validator API:

```ts
import type { WebReportBundleV1 } from "@/contracts/v1";

export const MAX_BUNDLE_BYTES = 50 * 1024 * 1024;

export class BundleContractError extends Error {
  constructor(
    public readonly code:
      | "BUNDLE_TOO_LARGE"
      | "INVALID_JSON"
      | "UNSUPPORTED_BUNDLE_MAJOR"
      | "SCHEMA_INVALID",
    message: string,
  ) {
    super(message);
  }
}

export async function validateBundleBytes(bytes: Uint8Array): Promise<WebReportBundleV1>;
```

Implement it with `Ajv2020`, local schemas only, `allErrors: true`, and no remote schema loading. Reject before parsing when `bytes.byteLength > MAX_BUNDLE_BYTES`. Parse UTF-8 JSON, require major `1`, validate the complete schema, and return the typed value.

- [ ] **Step 5: Implement typed server and client view models**

Use schema-derived indexed types rather than duplicated free-form objects:

```ts
import type { WebReportBundleV1 } from "@/contracts/v1";

export type BundleIssue = WebReportBundleV1["final_result"]["issues"][number];
export type BundleChart = WebReportBundleV1["presentation_manifest"]["chart_specs"][number];
export type BundleSource = WebReportBundleV1["source_view"][number];
export type BundlePreview = WebReportBundleV1["source_previews"][number];

export type ViewerEligibility = {
  mode: "trusted_final" | "poc_fixture" | "unverified_import" | "limited";
  label:
    | "승인·검증된 실행본"
    | "검증된 POC 시연 실행본"
    | "출처 미확인 묶음"
    | "제한된 결과 — 웹 리포트 묶음 필요";
  trusted: boolean;
  questionsAllowed: boolean;
};

export type WebReportViewModel = {
  runHeader: WebReportBundleV1["run"];
  viewerEligibility: ViewerEligibility;
  ceoSummary: BundleIssue[];
  issuesById: Record<string, BundleIssue>;
  relations: WebReportBundleV1["presentation_manifest"]["issue_graph"];
  evidenceById: Record<string, WebReportBundleV1["evidence_view"][number]>;
  sourcesById: Record<string, BundleSource>;
  sourcePreviewsById: Record<string, BundlePreview>;
  charts: BundleChart[];
  trust: WebReportBundleV1["trust_view"];
  expertPacketsById: Record<
    string,
    WebReportBundleV1["expert_packet_view"][number]
  >;
  revisionDiff: WebReportBundleV1["revision_view"];
  labels: WebReportBundleV1["presentation_manifest"]["korean_labels"];
};

export type ClientReportViewModel = Omit<WebReportViewModel, "sourcePreviewsById">;
```

Implement:

```ts
export function adaptBundleV1(
  bundle: WebReportBundleV1,
  eligibility: ViewerEligibility,
): WebReportViewModel;

export function toClientReport(view: WebReportViewModel): ClientReportViewModel;
```

`adaptBundleV1` must reject duplicate IDs and unresolved required references, map `ceo_summary_issue_refs` exactly in contract order, and never calculate rank, grade, metric, relation, or revision differences.

- [ ] **Step 6: Verify GREEN**

Run:

```bash
npm --prefix web run test -- src/lib/server/__tests__/bundle-validator.test.ts src/features/report/model/__tests__/adapter-v1.test.ts
npm --prefix web run typecheck
```

Expected: focused tests and typecheck pass.

- [ ] **Step 7: Commit**

```bash
git add web/src/contracts web/src/lib/server/contract-paths.ts web/src/lib/server/bundle-validator.ts web/src/lib/server/__tests__/bundle-validator.test.ts web/src/features/report/model/view-model.ts web/src/features/report/model/adapter-v1.ts web/src/features/report/model/__tests__/adapter-v1.test.ts
git commit -m "feat(web): add strict report contract adapter"
```

## Task 3: Korean two-tab shell, ReportScope, and Q&A attachment slot

**Files:**

- Create: `web/src/features/shell/labels.ko.ts`
- Create: `web/src/features/shell/ProductShell.tsx`
- Create: `web/src/features/shell/TopTabs.tsx`
- Create: `web/src/features/shell/RunHeader.tsx`
- Create: `web/src/features/shell/__tests__/TopTabs.test.tsx`
- Create: `web/src/features/shell/__tests__/RunHeader.test.tsx`
- Create: `web/src/features/report/model/report-scope.ts`
- Create: `web/src/features/report/model/__tests__/report-scope.test.ts`
- Create: `web/src/features/report/QuestionBubbleSlot.tsx`
- Create: `web/src/app/analysis/page.tsx`
- Create: `web/src/app/report/page.tsx`
- Create: `web/src/app/report/loading.tsx`

- [ ] **Step 1: Write failing tab and scope tests**

```tsx
// web/src/features/shell/__tests__/TopTabs.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TopTabs } from "@/features/shell/TopTabs";

describe("TopTabs", () => {
  it("renders the two approved Korean tabs", () => {
    render(<TopTabs activePath="/analysis" />);
    expect(screen.getByRole("link", { name: "분석 작업" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "결과 리포트" })).toHaveAttribute(
      "href",
      "/report",
    );
  });
});
```

```ts
// web/src/features/report/model/__tests__/report-scope.test.ts
import { describe, expect, it } from "vitest";
import { makeReportScopeKey } from "@/features/report/model/report-scope";

describe("makeReportScopeKey", () => {
  it("keeps two source starts inside one issue in separate conversations", () => {
    const left = makeReportScopeKey({
      runId: "run_1",
      revision: 7,
      scopeKind: "source",
      scopeInstanceId: "source_a",
      issueId: "issue_1",
    });
    const right = makeReportScopeKey({
      runId: "run_1",
      revision: 7,
      scopeKind: "source",
      scopeInstanceId: "source_b",
      issueId: "issue_1",
    });
    expect(left).not.toBe(right);
  });
});
```

- [ ] **Step 2: Run tests and observe RED**

Run:

```bash
npm --prefix web run test -- src/features/shell/__tests__/TopTabs.test.tsx src/features/report/model/__tests__/report-scope.test.ts
```

Expected: FAIL because `TopTabs` and `report-scope` do not exist.

- [ ] **Step 3: Implement exact labels and scope contract**

```ts
// web/src/features/shell/labels.ko.ts
export const KOREAN_LABELS = Object.freeze({
  analysisTab: "분석 작업",
  reportTab: "결과 리포트",
  sections: [
    "최고경영자 의사결정 요약",
    "컨설턴트 근거 분석",
    "실행·신뢰 기록",
    "전문가 검토 패킷",
    "변경 이력",
  ],
} as const);
```

```ts
// web/src/features/report/model/report-scope.ts
export type ScopeKind =
  | "run"
  | "issue"
  | "section"
  | "claim"
  | "evidence"
  | "source"
  | "expert_packet"
  | "revision_diff";

export type ReportScope = {
  runId: string;
  revision: number;
  scopeKind: ScopeKind;
  scopeInstanceId: string;
  issueId: string | null;
};

export function makeReportScopeKey(scope: ReportScope): string {
  return JSON.stringify([
    scope.runId,
    scope.revision,
    scope.scopeKind,
    scope.scopeInstanceId,
  ]);
}
```

Enforce the addendum rules when constructing a scope: run uses `run`; issue uses the selected issue ID; section uses `section:<section_code>:<active_ref-or-all>`; all other kinds use their selected stable ref.

- [ ] **Step 4: Implement the shell and non-interactive Q&A slot**

`TopTabs` uses Next `Link`, `aria-current`, and no client-side tab state. `ProductShell` renders the product title, optional `RunHeader`, top tabs, and page content.

Define the future attachment contract without implementing a question feature:

```tsx
import type { ReportScope } from "@/features/report/model/report-scope";

export type QuestionBubbleSlotProps = {
  scope: ReportScope;
};

export function QuestionBubbleSlot({ scope }: QuestionBubbleSlotProps) {
  return (
    <div
      id="result-question-slot"
      data-scope-key={JSON.stringify([
        scope.runId,
        scope.revision,
        scope.scopeKind,
        scope.scopeInstanceId,
      ])}
      aria-hidden="true"
    />
  );
}
```

This task must not render a question button, text input, simulated answer, or Codex status.

Create `/analysis` and `/report` pages inside `ProductShell`. Until later tasks supply their content, each page renders a Korean heading and an honest status sentence; `/report/loading.tsx` renders `결과 리포트를 확인하고 있습니다`.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
npm --prefix web run test -- src/features/shell src/features/report/model/__tests__/report-scope.test.ts
npm --prefix web run typecheck
```

Expected: focused tests and typecheck pass.

- [ ] **Step 6: Commit**

```bash
git add web/src/features/shell web/src/features/report/model/report-scope.ts web/src/features/report/model/__tests__/report-scope.test.ts web/src/features/report/QuestionBubbleSlot.tsx web/src/app/analysis web/src/app/report
git commit -m "feat(web): add Korean two-tab product shell"
```

## Task 4: Honest replay AnalysisProvider and command-center UI

**Files:**

- Create: `web/src/features/analysis/analysis-model.ts`
- Create: `web/src/features/analysis/analysis-provider.ts`
- Create: `web/src/features/analysis/replay-scenario.ts`
- Create: `web/src/features/analysis/replay-provider.ts`
- Create: `web/src/features/analysis/replay-session-store.ts`
- Create: `web/src/features/analysis/ReplayCommandCenter.tsx`
- Create: `web/src/features/analysis/StageRail.tsx`
- Create: `web/src/features/analysis/CurrentWorkPanel.tsx`
- Create: `web/src/features/analysis/RunDetailsPanel.tsx`
- Create: `web/src/features/analysis/DataUploadCard.tsx`
- Create: `web/src/features/analysis/HumanResponseForm.tsx`
- Create: `web/src/features/analysis/TerminalApprovalNotice.tsx`
- Create: `web/src/features/analysis/__tests__/replay-provider.test.ts`
- Create: `web/src/features/analysis/__tests__/upload-policy.test.ts`
- Create: `web/src/features/analysis/__tests__/ReplayCommandCenter.test.tsx`
- Create: `web/src/features/analysis/__tests__/TerminalApprovalNotice.test.tsx`
- Modify: `web/src/app/analysis/page.tsx`

- [ ] **Step 1: Write failing provider and upload-policy tests**

```ts
// web/src/features/analysis/__tests__/upload-policy.test.ts
import { describe, expect, it } from "vitest";
import { validateReplayFile } from "@/features/analysis/replay-provider";

describe("validateReplayFile", () => {
  it.each(["company.csv", "company.json", "company.xlsx"])(
    "accepts %s in the analysis workspace",
    (name) => {
      expect(validateReplayFile({ name, size: 128, type: "" }).accepted).toBe(true);
    },
  );

  it("rejects archives", () => {
    expect(
      validateReplayFile({ name: "company.zip", size: 128, type: "application/zip" }),
    ).toEqual({
      accepted: false,
      message: "분석 자료는 CSV, JSON, XLSX 파일만 선택할 수 있습니다.",
    });
  });
});
```

```ts
// web/src/features/analysis/__tests__/replay-provider.test.ts
import { describe, expect, it } from "vitest";
import { ReplayAnalysisProvider } from "@/features/analysis/replay-provider";

describe("ReplayAnalysisProvider", () => {
  it("identifies every state as a saved replay", async () => {
    const provider = new ReplayAnalysisProvider();
    const created = await provider.createRun();
    expect(created.provider_kind).toBe("replay");
    expect(created.display_badge).toBe("저장된 시연 흐름");
    expect(created.workflow_status).toBe("created");
  });

  it("uses human_response returned by the provider instead of inferring an action", async () => {
    const provider = new ReplayAnalysisProvider();
    const created = await provider.createRun();
    const state = await provider.startOrContinue(created.run_id, created.revision);
    expect(state.pending_action).toBe("human_response");
    expect(state.allowed_actions).toContain("submit_human_response");
  });
});
```

- [ ] **Step 2: Run tests and observe RED**

Run:

```bash
npm --prefix web run test -- src/features/analysis/__tests__/upload-policy.test.ts src/features/analysis/__tests__/replay-provider.test.ts
```

Expected: FAIL because replay modules do not exist.

- [ ] **Step 3: Implement the provider contract**

Define the approved workflow and response shapes:

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

```ts
export interface AnalysisProvider {
  createRun(): Promise<ProviderSnapshot>;
  attachData(runId: string, expectedRevision: number, files: File[]): Promise<ProviderSnapshot>;
  submitHumanResponse(
    runId: string,
    expectedRevision: number,
    response: string,
  ): Promise<ProviderSnapshot>;
  requestChanges(runId: string, expectedRevision: number): Promise<ProviderSnapshot>;
  startOrContinue(runId: string, expectedRevision: number): Promise<ProviderSnapshot>;
  prepareTerminalApprovalRequest(
    runId: string,
    expectedRevision: number,
  ): Promise<ProviderSnapshot>;
  getStatus(runId: string): Promise<ProviderSnapshot>;
  getPendingAction(runId: string): Promise<PendingAction>;
  getTerminalApprovalInstruction(runId: string): Promise<string | null>;
  retry(runId: string, expectedRevision: number): Promise<ProviderSnapshot>;
  resume(runId: string, expectedRevision: number): Promise<ProviderSnapshot>;
  stop(runId: string, expectedRevision: number): Promise<ProviderSnapshot>;
  cancel(runId: string, expectedRevision: number): Promise<ProviderSnapshot>;
  openFinalizedReport(runId: string): Promise<string | null>;
}
```

Create a deterministic seven-phase replay scenario. Each transition checks `expectedRevision`, increments revision only for replayed analysis mutations, returns its explicit `pending_action`, and never claims to have analyzed uploaded bytes.

- [ ] **Step 4: Implement replay persistence and UI**

Persist only this JSON-safe subset in `sessionStorage`:

```ts
export type ReplaySession = {
  snapshot: ProviderSnapshot;
  selectedFiles: Array<{ name: string; size: number; type: string }>;
  humanDraft: string;
};
```

Never persist `File`, file bytes, an approval nonce, or a terminal command containing a nonce.

Build the three-column command center:

- left: seven-stage rail;
- center: current provider-directed work;
- right: selected file metadata, requested-data explanations, latest event, run information.

Place this exact notice above the replay UI:

```text
저장된 시연 흐름 — 이 화면은 준비된 작업 과정을 재현하며 선택한 파일 내용을 새로 분석하지 않습니다.
```

`DataUploadCard` uses `accept=".csv,.json,.xlsx"`. `TerminalApprovalNotice` contains only `터미널 승인 필요`, an instruction summary, and polling status. It has no approve/reject buttons.

- [ ] **Step 5: Write and run component tests**

```tsx
// web/src/features/analysis/__tests__/TerminalApprovalNotice.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TerminalApprovalNotice } from "@/features/analysis/TerminalApprovalNotice";

describe("TerminalApprovalNotice", () => {
  it("never offers a web approval action", () => {
    render(<TerminalApprovalNotice instruction="터미널에서 기존 요청을 확인하세요." />);
    expect(screen.getByText("터미널 승인 필요")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /승인|거절/ })).not.toBeInTheDocument();
  });
});
```

Run:

```bash
npm --prefix web run test -- src/features/analysis
```

Expected: all analysis tests pass.

- [ ] **Step 6: Connect the analysis page and verify**

Render `ReplayCommandCenter` from `/analysis`. The page creates one `ReplayAnalysisProvider` and restores its safe session state.

Run:

```bash
npm --prefix web run typecheck
npm --prefix web run lint
npm --prefix web run test -- src/features/analysis
```

Expected: all commands pass.

- [ ] **Step 7: Commit**

```bash
git add web/src/features/analysis web/src/app/analysis/page.tsx
git commit -m "feat(web): add honest replay analysis workspace"
```

## Task 5: Bundle integrity and separated report-import policy

**Files:**

- Create: `web/src/lib/server/bundle-integrity.ts`
- Create: `web/src/lib/server/import-policy.ts`
- Create: `web/src/lib/server/__tests__/bundle-integrity.test.ts`
- Create: `web/src/lib/server/__tests__/import-policy.test.ts`

- [ ] **Step 1: Write failing integrity and import tests**

```ts
// web/src/lib/server/__tests__/import-policy.test.ts
// @vitest-environment node
import { describe, expect, it } from "vitest";
import { assertReportImport } from "@/lib/server/import-policy";

describe("assertReportImport", () => {
  it("accepts one JSON viewer bundle", () => {
    expect(() =>
      assertReportImport({
        fileName: "web-report-bundle.json",
        contentType: "application/json",
        contentLength: 1024,
      }),
    ).not.toThrow();
  });

  it.each(["data.csv", "data.xlsx", "bundle.zip"])(
    "rejects %s in the report import route",
    (fileName) => {
      expect(() =>
        assertReportImport({
          fileName,
          contentType: "application/octet-stream",
          contentLength: 1024,
        }),
      ).toThrow("결과 리포트에는 web-report-bundle.json 한 파일만 가져올 수 있습니다.");
    },
  );
});
```

```ts
// web/src/lib/server/__tests__/bundle-integrity.test.ts
// @vitest-environment node
import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";
import { validateInternalIntegrity } from "@/lib/server/bundle-integrity";
import { contractFixturePath } from "@/lib/server/contract-paths";
import { validateBundleBytes } from "@/lib/server/bundle-validator";

describe("validateInternalIntegrity", () => {
  it("accepts the canonical fixture hash", async () => {
    const bundle = await validateBundleBytes(
      await readFile(contractFixturePath("valid-unverified-import.json")),
    );
    await expect(validateInternalIntegrity(bundle)).resolves.toBeUndefined();
  });

  it("rejects the invalid hash fixture", async () => {
    const bundle = await validateBundleBytes(
      await readFile(contractFixturePath("invalid-hash.json")),
    );
    await expect(validateInternalIntegrity(bundle)).rejects.toMatchObject({
      code: "HASH_MISMATCH",
    });
  });
});
```

- [ ] **Step 2: Run tests and observe RED**

Run:

```bash
npm --prefix web run test -- src/lib/server/__tests__/bundle-integrity.test.ts src/lib/server/__tests__/import-policy.test.ts
```

Expected: FAIL because the integrity and import-policy modules do not exist.

- [ ] **Step 3: Implement the import boundary**

```ts
export const MAX_REPORT_IMPORT_BYTES = 50 * 1024 * 1024;

export type ReportImportMetadata = {
  fileName: string;
  contentType: string;
  contentLength: number;
};

export function assertReportImport(metadata: ReportImportMetadata): void;
```

Require the basename `web-report-bundle.json`, content type `application/json`, and a positive length no greater than 50 MiB. Reject ZIP and every other extension before reading the body.

- [ ] **Step 4: Implement RFC 8785 JCS SHA-256 checks**

```ts
import { createHash } from "node:crypto";
import { canonicalize } from "json-canonicalize";
import type { WebReportBundleV1 } from "@/contracts/v1";

export class BundleIntegrityError extends Error {
  constructor(
    public readonly code: "HASH_MISMATCH" | "PREVIEW_HASH_MISMATCH",
    message: string,
  ) {
    super(message);
  }
}

function sha256Jcs(value: unknown): string {
  return createHash("sha256").update(canonicalize(value)).digest("hex");
}

export async function validateInternalIntegrity(
  bundle: WebReportBundleV1,
): Promise<void>;
```

For `bundle_hash`, clone the top-level object, remove only `bundle_hash`, canonicalize, and compare. For every preview, clone the preview, remove only `preview_hash`, canonicalize, and compare. Do not normalize, sort, or modify any semantic array in the web layer.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
npm --prefix web run test -- src/lib/server/__tests__/bundle-integrity.test.ts src/lib/server/__tests__/import-policy.test.ts
npm --prefix web run typecheck
```

Expected: focused tests and typecheck pass.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/server/bundle-integrity.ts web/src/lib/server/import-policy.ts web/src/lib/server/__tests__/bundle-integrity.test.ts web/src/lib/server/__tests__/import-policy.test.ts
git commit -m "feat(web): validate report bundle imports"
```

## Task 6: Registered-run cross-validation and atomic current report

**Files:**

- Create: `web/src/lib/server/plugin-validator-client.ts`
- Create: `web/src/lib/server/run-registry.ts`
- Create: `web/src/lib/server/report-store.ts`
- Create: `web/src/lib/server/__tests__/plugin-validator-client.test.ts`
- Create: `web/src/lib/server/__tests__/run-registry.test.ts`
- Create: `web/src/lib/server/__tests__/report-store.test.ts`
- Create: `web/src/app/api/report/current/route.ts`
- Create: `web/src/app/api/report/import/route.ts`

- [ ] **Step 1: Write the failing launcher test**

```ts
// web/src/lib/server/__tests__/plugin-validator-client.test.ts
// @vitest-environment node
import { describe, expect, it } from "vitest";
import { buildValidateWebReportCommand } from "@/lib/server/plugin-validator-client";

describe("buildValidateWebReportCommand", () => {
  it("uses the frozen offline plugin launcher with fixed argv", () => {
    expect(
      buildValidateWebReportCommand({
        artifactRoot: "/approved/runs/run_1",
        bundlePath: "/approved/runs/run_1/web-report-bundle.json",
        runId: "run_1",
        revision: 9,
      }),
    ).toEqual({
      file: "uv",
      args: [
        "run",
        "--project",
        "plugin/trusted-ceo-agent",
        "--frozen",
        "--offline",
        "--no-sync",
        "python",
        "plugin/trusted-ceo-agent/scripts/trusted_ceo_agent.py",
        "validate-web-report",
        "--artifact-root",
        "/approved/runs/run_1",
        "--run-id",
        "run_1",
        "--revision",
        "9",
        "--bundle",
        "/approved/runs/run_1/web-report-bundle.json",
      ],
    });
  });
});
```

```ts
// web/src/lib/server/__tests__/report-store.test.ts
// @vitest-environment node
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { ReportStore } from "@/lib/server/report-store";

describe("ReportStore", () => {
  it("keeps the current report when candidate validation fails", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "trusted-ceo-web-"));
    const store = new ReportStore(root);
    await store.publishVerified(Buffer.from('{"id":"old"}'), { label: "old" });
    await expect(
      store.replaceAfterValidation(Buffer.from('{"id":"bad"}'), async () => {
        throw new Error("invalid");
      }),
    ).rejects.toThrow("invalid");
    expect(await readFile(path.join(root, "current-report.json"), "utf8")).toBe(
      '{"id":"old"}',
    );
  });
});
```

- [ ] **Step 2: Run focused tests and observe RED**

Run:

```bash
npm --prefix web run test -- src/lib/server/__tests__/plugin-validator-client.test.ts src/lib/server/__tests__/report-store.test.ts
```

Expected: FAIL because the launcher and store modules do not exist.

- [ ] **Step 3: Implement registry and child-process contracts**

```ts
export type RunRegistration = {
  registration_id: string;
  canonical_artifact_root: string;
  expected_run_id: string;
  allowed_revision: number;
  expected_bundle_hash: string;
};

export type ValidateWebReportInput = {
  artifactRoot: string;
  bundlePath: string;
  runId: string;
  revision: number;
};

export type FixedCommand = {
  file: "uv";
  args: string[];
};

export function buildValidateWebReportCommand(input: ValidateWebReportInput): FixedCommand;
export async function validateRegisteredReport(
  input: ValidateWebReportInput,
): Promise<ViewerEligibilityDecisionV1>;
```

`validateRegisteredReport` uses `execFile`, never a shell string, a 60-second timeout, a 4 MiB output cap, and an environment allowlist containing only the minimal process variables required to find `uv`, Python, and Codex-independent local runtime files. Parse exactly one JSON object from stdout and reject non-zero exit, extra stdout, run mismatch, revision mismatch, or unknown decision enum.

`RunRegistry` reads only a server-configured registry path. Resolve every artifact root and require it to remain below a startup-configured allowlist root. Browser input can select a `registration_id`; it cannot supply an artifact root.

- [ ] **Step 4: Implement the atomic report store**

```ts
export class ReportStore {
  constructor(private readonly runtimeRoot: string) {}

  async publishVerified(bytes: Uint8Array, decision: unknown): Promise<void>;

  async replaceAfterValidation<T>(
    bytes: Uint8Array,
    validator: () => Promise<T>,
  ): Promise<T>;

  async readCurrent(): Promise<Uint8Array | null>;
  async readCurrentDecision(): Promise<unknown | null>;
}
```

Write candidate bundle and decision into the runtime directory, fsync both, then atomically rename them to `current-report.json` and `current-decision.json`. A failed validation removes only candidate files. Never delete or overwrite a plugin full-run artifact.

- [ ] **Step 5: Implement current and import Route Handlers**

`GET /api/report/current`:

1. reads the current bundle and decision;
2. validates schema and internal hashes;
3. adapts the bundle;
4. returns `toClientReport(view)` with `Cache-Control: no-store`;
5. returns Korean `503` JSON when no bundle is configured.

`POST /api/report/import`:

1. checks exact Host/Origin using a shared localhost check inside the route;
2. validates file name, content type, and content length before body parsing;
3. validates schema and internal hashes;
4. assigns the fixed eligibility:

```ts
{
  mode: "unverified_import",
  label: "출처 미확인 묶음",
  trusted: false,
  questionsAllowed: false
}
```

5. atomically replaces current only after every check succeeds;
6. does not create an analysis revision.

- [ ] **Step 6: Verify GREEN**

Run:

```bash
npm --prefix web run test -- src/lib/server/__tests__/plugin-validator-client.test.ts src/lib/server/__tests__/run-registry.test.ts src/lib/server/__tests__/report-store.test.ts
npm --prefix web run typecheck
```

Expected: focused tests and typecheck pass.

- [ ] **Step 7: Commit**

```bash
git add web/src/lib/server/plugin-validator-client.ts web/src/lib/server/run-registry.ts web/src/lib/server/report-store.ts web/src/lib/server/__tests__/plugin-validator-client.test.ts web/src/lib/server/__tests__/run-registry.test.ts web/src/lib/server/__tests__/report-store.test.ts web/src/app/api/report/current/route.ts web/src/app/api/report/import/route.ts
git commit -m "feat(web): cross-validate and publish reports"
```

## Task 7: Five Korean result screens with one synchronized issue scope

**Files:**

- Create: `web/src/features/report/model/eligibility.ts`
- Create: `web/src/features/report/model/__tests__/eligibility.test.ts`
- Create: `web/src/features/report/ReportWorkspace.tsx`
- Create: `web/src/features/report/ReportSectionNav.tsx`
- Create: `web/src/features/report/DecisionBrief.tsx`
- Create: `web/src/features/report/IssueSummaryCards.tsx`
- Create: `web/src/features/report/FullIssueStructure.tsx`
- Create: `web/src/features/report/EvidenceWorkbench.tsx`
- Create: `web/src/features/report/TrustManifest.tsx`
- Create: `web/src/features/report/ExpertPackets.tsx`
- Create: `web/src/features/report/RevisionChanges.tsx`
- Create: `web/src/features/report/__tests__/ReportWorkspace.test.tsx`
- Create: `web/src/features/report/__tests__/EvidenceWorkbench.test.tsx`
- Modify: `web/src/app/report/page.tsx`

- [ ] **Step 1: Write the failing workspace test**

```tsx
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReportWorkspace } from "@/features/report/ReportWorkspace";
import { makeClientReportFixture } from "@/features/report/__tests__/report-fixture";

describe("ReportWorkspace", () => {
  it("renders five Korean sections and synchronizes the selected issue", () => {
    const report = makeClientReportFixture();
    render(<ReportWorkspace report={report} />);

    const navigation = screen.getByRole("navigation", { name: "결과 리포트 화면" });
    for (const label of [
      "최고경영자 의사결정 요약",
      "컨설턴트 근거 분석",
      "실행·신뢰 기록",
      "전문가 검토 패킷 1",
      "변경 이력",
    ]) {
      expect(within(navigation).getByRole("button", { name: label })).toBeInTheDocument();
    }

    fireEvent.click(screen.getByRole("button", { name: "문제 B 선택" }));
    fireEvent.click(
      within(navigation).getByRole("button", { name: "컨설턴트 근거 분석" }),
    );
    expect(screen.getByRole("heading", { name: "문제 B 근거 분석" })).toBeInTheDocument();
  });

  it("never renders more than the plugin-provided three summary issues", () => {
    const report = makeClientReportFixture();
    render(<ReportWorkspace report={report} />);
    expect(screen.getAllByTestId("ceo-summary-issue")).toHaveLength(
      report.ceoSummary.length,
    );
    expect(report.ceoSummary.length).toBeLessThanOrEqual(3);
  });
});
```

Create `web/src/features/report/__tests__/report-fixture.ts` as a typed builder using schema-derived types. It contains two issues, one relation, one chart, one packet, and an available revision diff; it contains no source preview cell values.

- [ ] **Step 2: Run the test and observe RED**

Run:

```bash
npm --prefix web run test -- src/features/report/__tests__/ReportWorkspace.test.tsx
```

Expected: FAIL because the workspace components do not exist.

- [ ] **Step 3: Implement the synchronized workspace state**

```ts
export type ReportSection =
  | "decision"
  | "evidence"
  | "trust"
  | "expert_packets"
  | "revision_changes";

export type ReportWorkspaceState = {
  activeIssueId: string;
  activeSection: ReportSection;
  activeRef: string | null;
};
```

Initialize `activeIssueId` from the first `ceoSummary` issue, falling back to the first issue ID in stable bundle order. Selecting an issue changes only `activeIssueId`; all five screens read that same value. Selecting a source, packet, or diff updates `activeRef` and creates a `ReportScope` according to addendum v2.

Render `QuestionBubbleSlot` with the active scope, but do not render an interactive question control.

- [ ] **Step 4: Implement the five screens without analysis invention**

- `DecisionBrief`: up to three supplied issues, supplied metrics, supplied next action, supplied charts, and an `전체 문제 구조 보기` control.
- `FullIssueStructure`: every supplied issue and only supplied relations.
- `EvidenceWorkbench`: observed facts, definition, hypotheses, counter-hypotheses, support/rejection refs, unresolved conflicts, requested data, conditional response, source/calculation/official-link controls.
- `TrustManifest`: versions, checks, approval summary, trust events, hashes, preservation/privacy limits.
- `ExpertPackets`: approved packets only, with count in navigation.
- `RevisionChanges`: supplied comparison only.

No component sorts issues by importance, calculates metrics, creates relations, calculates diffs, or changes an analysis revision.

- [ ] **Step 5: Connect the report page**

The server page reads the current report through the server store, validates and adapts it, then passes `ClientReportViewModel` to `ReportWorkspace`. If there is no report, render:

```text
웹 리포트 묶음이 필요합니다. 결과 리포트에서 web-report-bundle.json을 가져오세요.
```

- [ ] **Step 6: Verify GREEN**

Run:

```bash
npm --prefix web run test -- src/features/report/__tests__/ReportWorkspace.test.tsx src/features/report/__tests__/EvidenceWorkbench.test.tsx src/features/report/model/__tests__/eligibility.test.ts
npm --prefix web run typecheck
```

Expected: focused tests and typecheck pass.

- [ ] **Step 7: Commit**

```bash
git add web/src/features/report/model/eligibility.ts web/src/features/report/model/__tests__/eligibility.test.ts web/src/features/report/ReportWorkspace.tsx web/src/features/report/ReportSectionNav.tsx web/src/features/report/DecisionBrief.tsx web/src/features/report/IssueSummaryCards.tsx web/src/features/report/FullIssueStructure.tsx web/src/features/report/EvidenceWorkbench.tsx web/src/features/report/TrustManifest.tsx web/src/features/report/ExpertPackets.tsx web/src/features/report/RevisionChanges.tsx web/src/features/report/__tests__/report-fixture.ts web/src/features/report/__tests__/ReportWorkspace.test.tsx web/src/features/report/__tests__/EvidenceWorkbench.test.tsx web/src/app/report/page.tsx
git commit -m "feat(web): add scoped executive report screens"
```

## Task 8: ECharts core SVG rendering with evidence-bound fallback tables

**Files:**

- Create: `web/src/features/report/model/chart-option.ts`
- Create: `web/src/features/report/model/__tests__/chart-option.test.ts`
- Create: `web/src/features/report/charts/EChartCanvas.tsx`
- Create: `web/src/features/report/charts/ChartPanel.tsx`
- Create: `web/src/features/report/charts/IssueGraph.tsx`
- Create: `web/src/features/report/charts/EvidenceFallbackTable.tsx`
- Create: `web/src/features/report/charts/__tests__/EChartCanvas.test.tsx`
- Create: `web/src/features/report/charts/__tests__/ChartPanel.test.tsx`
- Modify: `web/src/features/report/DecisionBrief.tsx`
- Modify: `web/src/features/report/FullIssueStructure.tsx`

- [ ] **Step 1: Write the failing chart-model test**

```ts
import { describe, expect, it } from "vitest";
import { buildChartView } from "@/features/report/model/chart-option";
import { makeChartSpec } from "@/features/report/__tests__/report-fixture";

describe("buildChartView", () => {
  it("maps supplied values without calculating a new metric", () => {
    const spec = makeChartSpec({
      chart_type: "line",
      float_safe: true,
      points: [
        { label: "1월", sort_key: "2026-01", value: "10", value_ref: "v1", fact_id: "f1" },
        { label: "2월", sort_key: "2026-02", value: "12", value_ref: "v2", fact_id: "f2" },
      ],
    });
    const view = buildChartView(spec);
    expect(view.kind).toBe("chart");
    if (view.kind === "chart") {
      expect(view.pointBindings).toEqual([
        { dataIndex: 0, valueRef: "v1", factId: "f1" },
        { dataIndex: 1, valueRef: "v2", factId: "f2" },
      ]);
    }
  });

  it("uses an evidence table when float safety is false", () => {
    const view = buildChartView(makeChartSpec({ float_safe: false }));
    expect(view).toMatchObject({
      kind: "table",
      reason: "수치를 안전하게 그래프로 변환할 수 없어 근거 표로 표시합니다.",
    });
  });
});
```

- [ ] **Step 2: Run tests and observe RED**

Run:

```bash
npm --prefix web run test -- src/features/report/model/__tests__/chart-option.test.ts
```

Expected: FAIL because `chart-option` does not exist.

- [ ] **Step 3: Implement conservative chart conversion**

```ts
export type ChartPointBinding = {
  dataIndex: number;
  valueRef: string;
  factId: string;
};

export type ChartView =
  | {
      kind: "chart";
      option: EChartsCoreOption;
      pointBindings: ChartPointBinding[];
      accessibleRows: Array<{
        label: string;
        formattedValue: string;
        factId: string;
      }>;
    }
  | {
      kind: "table";
      reason: string;
      rows: Array<{
        label: string;
        formattedValue: string;
        factId: string;
      }>;
    };

export function buildChartView(spec: BundleChart): ChartView;
```

Allow only line, bar, and issue graph. Return a table when a trend lacks sort keys, units/currency/scales conflict, `float_safe` is false, or the declared scale cannot round-trip through JavaScript number. Use only supplied point values and display formats. Do not calculate sums, percentages, averages, changes, forecasts, or ranking.

- [ ] **Step 4: Implement tree-shaken ECharts SVG**

Register only:

```ts
import { BarChart, GraphChart, LineChart } from "echarts/charts";
import {
  DatasetComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import { init, use } from "echarts/core";
import { SVGRenderer } from "echarts/renderers";

use([
  BarChart,
  GraphChart,
  LineChart,
  DatasetComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  SVGRenderer,
]);
```

`EChartCanvas` initializes with `{ renderer: "svg" }`, calls `setOption(option, { notMerge: true })`, maps ECharts click `dataIndex` through `pointBindings`, observes container resize, and disposes on unmount. Render an HTML data-point list with `근거 보기` links for keyboard and screen-reader users.

- [ ] **Step 5: Run component and model tests**

Run:

```bash
npm --prefix web run test -- src/features/report/model/__tests__/chart-option.test.ts src/features/report/charts
npm --prefix web run typecheck
```

Expected: chart tests and typecheck pass.

- [ ] **Step 6: Commit**

```bash
git add web/src/features/report/model/chart-option.ts web/src/features/report/model/__tests__/chart-option.test.ts web/src/features/report/charts web/src/features/report/DecisionBrief.tsx web/src/features/report/FullIssueStructure.tsx
git commit -m "feat(web): render evidence-bound SVG charts"
```

## Task 9: Hash-verified source previews and official-link policy

**Files:**

- Create: `web/src/lib/server/source-preview-repository.ts`
- Create: `web/src/lib/server/official-url-policy.ts`
- Create: `web/src/lib/server/__tests__/source-preview-repository.test.ts`
- Create: `web/src/lib/server/__tests__/official-url-policy.test.ts`
- Create: `web/src/app/api/report/source-previews/[previewRef]/route.ts`
- Create: `web/src/features/report/SourcePreviewDialog.tsx`
- Create: `web/src/features/report/__tests__/SourcePreviewDialog.test.tsx`
- Modify: `web/src/features/report/EvidenceWorkbench.tsx`

- [ ] **Step 1: Write failing preview-policy tests**

```ts
// web/src/lib/server/__tests__/source-preview-repository.test.ts
// @vitest-environment node
import { describe, expect, it } from "vitest";
import { SourcePreviewRepository } from "@/lib/server/source-preview-repository";
import { makeServerReportFixture } from "@/features/report/__tests__/report-fixture";

describe("SourcePreviewRepository", () => {
  it("returns values only for permitted previews", () => {
    const repository = new SourcePreviewRepository(makeServerReportFixture());
    expect(repository.get("preview_permitted")).toMatchObject({
      access_policy: "permitted",
      cells: expect.any(Array),
    });
  });

  it("masks prohibited preview values and locators", () => {
    const repository = new SourcePreviewRepository(makeServerReportFixture());
    const result = repository.get("preview_prohibited");
    expect(result).toEqual({
      preview_ref: "preview_prohibited",
      source_ref: "source_private",
      access_policy: "prohibited",
      message: "이 출처의 내용은 표시할 수 없습니다.",
    });
    expect(JSON.stringify(result)).not.toContain("/");
  });

  it("rejects path-shaped refs", () => {
    const repository = new SourcePreviewRepository(makeServerReportFixture());
    expect(() => repository.get("../source.csv")).toThrow("잘못된 미리보기 참조입니다.");
  });
});
```

```ts
// web/src/lib/server/__tests__/official-url-policy.test.ts
// @vitest-environment node
import { describe, expect, it } from "vitest";
import { assertOfficialUrl } from "@/lib/server/official-url-policy";

describe("assertOfficialUrl", () => {
  it("allows an HTTPS URL whose initial and final origins are registered", () => {
    expect(() =>
      assertOfficialUrl(
        "https://official.example/a",
        "https://official.example/b",
        {
          allowed_schemes: ["https"],
          allowed_origins: ["https://official.example"],
          allow_redirects: true,
        },
      ),
    ).not.toThrow();
  });

  it("rejects a redirect to another origin", () => {
    expect(() =>
      assertOfficialUrl(
        "https://official.example/a",
        "https://evil.example/b",
        {
          allowed_schemes: ["https"],
          allowed_origins: ["https://official.example"],
          allow_redirects: true,
        },
      ),
    ).toThrow("허용되지 않은 공식 자료 링크입니다.");
  });
});
```

- [ ] **Step 2: Run tests and observe RED**

Run:

```bash
npm --prefix web run test -- src/lib/server/__tests__/source-preview-repository.test.ts src/lib/server/__tests__/official-url-policy.test.ts
```

Expected: FAIL because the repository and URL-policy modules do not exist.

- [ ] **Step 3: Implement the server-only preview repository**

```ts
export class SourcePreviewRepository {
  constructor(private readonly report: WebReportViewModel) {}

  get(previewRef: string): SourcePreviewResponse;
}
```

Require `previewRef` to match the contract ID pattern. Resolve only `report.sourcePreviewsById`; never open `snapshot_locator`, `canonical_artifact_root`, or a full-run raw file. Return:

- permitted: approved rows, columns, cells, sanitized locator, truncation/masking state;
- restricted: metadata and restriction explanation, no cell values;
- prohibited: stable refs and the fixed Korean message only.

The Route Handler returns `Cache-Control: no-store`, `404` for unknown refs, and never serializes an absolute path.

- [ ] **Step 4: Implement the accessible preview dialog**

`SourcePreviewDialog` opens from a preview ref, fetches only the preview route, renders permitted cells as a table, renders metadata-only restriction messages, closes with Escape, and returns focus to the opening control. It does not accept a path or source file upload.

Use official links only after `assertOfficialUrl` verifies both initial and redirect-final origins.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
npm --prefix web run test -- src/lib/server/__tests__/source-preview-repository.test.ts src/lib/server/__tests__/official-url-policy.test.ts src/features/report/__tests__/SourcePreviewDialog.test.tsx
npm --prefix web run typecheck
```

Expected: focused tests and typecheck pass.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/server/source-preview-repository.ts web/src/lib/server/official-url-policy.ts web/src/lib/server/__tests__/source-preview-repository.test.ts web/src/lib/server/__tests__/official-url-policy.test.ts web/src/app/api/report/source-previews web/src/features/report/SourcePreviewDialog.tsx web/src/features/report/__tests__/SourcePreviewDialog.test.tsx web/src/features/report/EvidenceWorkbench.tsx
git commit -m "feat(web): add bounded source previews"
```

## Task 10: Trust manifest, one-way expert packets, and supplied revision changes

**Files:**

- Create: `web/src/features/report/model/expert-packet-markdown.ts`
- Create: `web/src/features/report/model/__tests__/expert-packet-markdown.test.ts`
- Create: `web/src/lib/server/expert-packet-export.ts`
- Create: `web/src/app/api/report/expert-packets/[packetId]/route.ts`
- Create: `web/src/features/report/__tests__/ExpertPackets.test.tsx`
- Create: `web/src/features/report/__tests__/RevisionChanges.test.tsx`
- Modify: `web/src/features/report/TrustManifest.tsx`
- Modify: `web/src/features/report/ExpertPackets.tsx`
- Modify: `web/src/features/report/RevisionChanges.tsx`
- Modify: `web/src/app/globals.css`

- [ ] **Step 1: Write failing expert and revision tests**

```ts
// web/src/features/report/model/__tests__/expert-packet-markdown.test.ts
import { describe, expect, it } from "vitest";
import { renderExpertPacketMarkdown } from "@/features/report/model/expert-packet-markdown";
import { makeExpertPacket } from "@/features/report/__tests__/report-fixture";

describe("renderExpertPacketMarkdown", () => {
  it("renders only the approved packet and is byte-stable", () => {
    const packet = makeExpertPacket();
    const first = renderExpertPacketMarkdown(packet);
    const second = renderExpertPacketMarkdown(packet);
    expect(first).toBe(second);
    expect(first).toContain("# 전문가 검토 패킷");
    expect(first).toContain(packet.packet_id);
    expect(first).toContain("금지 결론");
  });
});
```

```tsx
// web/src/features/report/__tests__/ExpertPackets.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ExpertPackets } from "@/features/report/ExpertPackets";
import { makeExpertPacket } from "@/features/report/__tests__/report-fixture";

describe("ExpertPackets", () => {
  it("offers one-way render and download without an answer workflow", () => {
    render(<ExpertPackets packets={[makeExpertPacket()]} activeIssueId="issue_a" />);
    expect(screen.getByRole("link", { name: "Markdown 내려받기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "인쇄 보기" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByText(/검토 완료|답변 업로드|결과 반영/)).not.toBeInTheDocument();
  });
});
```

```tsx
// web/src/features/report/__tests__/RevisionChanges.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RevisionChanges } from "@/features/report/RevisionChanges";

describe("RevisionChanges", () => {
  it("does not invent a semantic diff when the plugin supplied none", () => {
    render(
      <RevisionChanges
        revisionView={{
          available: false,
          unavailable_reason: "비교 리비전이 없습니다.",
        }}
        activeIssueId="issue_a"
      />,
    );
    expect(screen.getByText("변경 정보 사용 불가")).toBeInTheDocument();
    expect(screen.getByText("비교 리비전이 없습니다.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests and observe RED**

Run:

```bash
npm --prefix web run test -- src/features/report/model/__tests__/expert-packet-markdown.test.ts src/features/report/__tests__/ExpertPackets.test.tsx src/features/report/__tests__/RevisionChanges.test.tsx
```

Expected: FAIL because export and completed view behaviors do not exist.

- [ ] **Step 3: Implement deterministic one-way packet rendering**

```ts
export function renderExpertPacketMarkdown(
  packet: ExpertPacketViewItemV1,
): string;
```

Render these supplied sections in fixed order:

1. run, revision, packet hash;
2. profession and target issue;
3. observed facts and evidence refs;
4. hypotheses and counter-hypotheses;
5. unresolved uncertainty;
6. required document refs;
7. exact expert question;
8. forbidden conclusions;
9. sanitized source locators.

Do not add current time, generated prose, inferred evidence, or an expert answer area. The download route resolves a packet from the server-held report and returns UTF-8 Markdown with a sanitized `<packet_id>.md` filename.

- [ ] **Step 4: Implement trust and revision display rules**

`TrustManifest` shows supplied plugin, Pack, schema, and validator versions; completed checks; approval summaries; hashes; privacy/preservation limits; and trust events ordered by supplied sequence. If a timestamp is null, show `순서 <sequence>` and no invented date.

`RevisionChanges` renders only supplied added, changed, removed, invalidated approval, semantic fingerprint, and plugin wording entries. When unavailable, render `변경 정보 사용 불가` and the supplied reason.

Add print CSS that hides application navigation and prints only the selected expert packet. It must not expose source values that are absent from the packet.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
npm --prefix web run test -- src/features/report/model/__tests__/expert-packet-markdown.test.ts src/features/report/__tests__/ExpertPackets.test.tsx src/features/report/__tests__/RevisionChanges.test.tsx
npm --prefix web run typecheck
```

Expected: focused tests and typecheck pass.

- [ ] **Step 6: Commit**

```bash
git add web/src/features/report/model/expert-packet-markdown.ts web/src/features/report/model/__tests__/expert-packet-markdown.test.ts web/src/lib/server/expert-packet-export.ts web/src/app/api/report/expert-packets web/src/features/report/TrustManifest.tsx web/src/features/report/ExpertPackets.tsx web/src/features/report/RevisionChanges.tsx web/src/features/report/__tests__/ExpertPackets.test.tsx web/src/features/report/__tests__/RevisionChanges.test.tsx web/src/app/globals.css
git commit -m "feat(web): add trust revision and expert exports"
```

## Task 11: Browser acceptance, accessibility, and Mac-local verification

**Files:**

- Create: `web/tests/e2e/two-tabs.spec.ts`
- Create: `web/tests/e2e/analysis-replay.spec.ts`
- Create: `web/tests/e2e/report-navigation.spec.ts`
- Create: `web/tests/e2e/report-evidence.spec.ts`
- Create: `web/tests/e2e/expert-revision.spec.ts`
- Create: `web/tests/e2e/bundle-import.spec.ts`
- Create: `web/tests/e2e/accessibility.spec.ts`
- Modify: `web/playwright.config.ts`
- Modify: `web/README.md`

- [ ] **Step 1: Write failing two-tab and replay browser tests**

```ts
// web/tests/e2e/two-tabs.spec.ts
import { expect, test } from "@playwright/test";

test("두 상단 탭을 왕복한다", async ({ page }) => {
  await page.goto("/analysis");
  await expect(page.getByRole("link", { name: "분석 작업" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await page.getByRole("link", { name: "결과 리포트" }).click();
  await expect(page).toHaveURL(/\/report$/);
  await expect(page.getByRole("link", { name: "결과 리포트" })).toHaveAttribute(
    "aria-current",
    "page",
  );
});
```

```ts
// web/tests/e2e/analysis-replay.spec.ts
import { expect, test } from "@playwright/test";

test("replay 자료 선택과 사람 확인 흐름을 완료한다", async ({ page }) => {
  await page.goto("/analysis");
  await expect(page.getByText("저장된 시연 흐름", { exact: false })).toBeVisible();
  await page.getByLabel("분석 자료 선택").setInputFiles({
    name: "company.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("period,revenue\n2026-01,10\n"),
  });
  await expect(page.getByText("company.csv")).toBeVisible();
  await page.getByRole("button", { name: "다음 단계 재현" }).click();
  await page.getByLabel("사람 확인 답변").fill("현재 범위로 진행합니다.");
  await page.getByRole("button", { name: "답변 제출" }).click();
  await expect(page.getByText("심층 분석")).toBeVisible();
});
```

- [ ] **Step 2: Run browser tests and observe RED**

Run:

```bash
npm --prefix web exec -- playwright install chromium
npm --prefix web run test:e2e -- tests/e2e/two-tabs.spec.ts tests/e2e/analysis-replay.spec.ts
```

Expected: at least one assertion fails until the completed UI and Playwright fixture configuration are connected.

- [ ] **Step 3: Add the full report acceptance suite**

Implement exact Playwright cases:

- `report-navigation.spec.ts`
  - CEO summary has at most three supplied issue cards;
  - full issue structure contains every issue;
  - selecting an issue changes all five sections to the same issue;
  - all visible labels are Korean.
- `report-evidence.spec.ts`
  - a chart or accessible point link opens its bound evidence;
  - permitted preview shows cells;
  - restricted preview shows metadata only;
  - prohibited preview shows no values or path;
  - missing chart metadata renders a Korean evidence-table reason.
- `expert-revision.spec.ts`
  - packet downloads as Markdown;
  - print view contains the packet;
  - no expert answer input exists;
  - supplied revision changes render;
  - unavailable diff renders `변경 정보 사용 불가`.
- `bundle-import.spec.ts`
  - valid independent JSON receives `출처 미확인 묶음`;
  - CSV, XLSX, ZIP, oversize, invalid hash, and invalid reference are rejected;
  - failed replacement leaves the previous report visible.

- [ ] **Step 4: Add accessibility and responsive checks**

```ts
// web/tests/e2e/accessibility.spec.ts
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("핵심 두 화면에 심각한 접근성 위반이 없다", async ({ page }) => {
  for (const path of ["/analysis", "/report"]) {
    await page.goto(path);
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations.filter((item) => item.impact === "critical")).toEqual([]);
  }
});

test("모바일에서도 결과 화면과 예약 슬롯이 레이아웃을 밀지 않는다", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/report");
  await expect(page.getByRole("main")).toBeVisible();
  await expect(page.locator("#result-question-slot")).toHaveCount(1);
  await expect(page.locator("#result-question-slot")).toHaveCSS("position", "fixed");
});
```

The reserved slot is 52 by 52 pixels on desktop and mobile, fixed at the lower right, visually empty, `aria-hidden`, and non-interactive. It must not cover the main issue card or chart center.

- [ ] **Step 5: Document exact local commands**

Write `web/README.md` with:

```bash
nvm use
npm ci
npm run dev
```

Document:

- local URL `http://127.0.0.1:3000`;
- runtime registry path configuration;
- representative bundle path configuration;
- the exact frozen plugin validation launcher;
- the distinction between analysis CSV/JSON/XLSX selection and result JSON import;
- Q&A and live provider are not present in this build;
- an imported standalone bundle is always labeled `출처 미확인 묶음`.

- [ ] **Step 6: Run full verification**

Run:

```bash
node --version
npm --prefix web ci
npm --prefix web run typecheck
npm --prefix web run lint
npm --prefix web run test
npm --prefix web run build
npm --prefix web run test:e2e
```

Expected:

- Node prints `v22.22.0`;
- typecheck and lint pass;
- all Vitest suites pass;
- Next.js production build succeeds;
- all Playwright suites pass in Chromium;
- axe reports zero critical violations;
- no test writes to a plugin full-run directory.

On the target Mac, run the representative registered bundle three times through:

```text
full validate → export-web-report → validate-web-report → web result page
```

Require:

- representative result first display within 2 seconds;
- issue and chart selection response within 200 milliseconds;
- three consecutive demo flows succeed;
- network or plugin validation failure never removes the already stored valid report.

- [ ] **Step 7: Inspect scope and commit**

Run:

```bash
git status --short
git diff --check
```

Expected: only intended web plan implementation files are staged or modified; no secrets, absolute company paths, runtime bundles, `web/var`, or unrelated user files are included.

Commit:

```bash
git add web/tests/e2e web/playwright.config.ts web/README.md
git commit -m "test(web): verify executive report viewer"
```

## Final acceptance checklist

- [ ] Node is exactly 22.22.0 and the application uses Next.js 16 App Router with npm.
- [ ] There is no Tailwind dependency or directive.
- [ ] Both `분석 작업` and `결과 리포트` tabs exist.
- [ ] The analysis tab is visibly and consistently identified as `저장된 시연 흐름`.
- [ ] CSV, JSON, and XLSX are accepted only in the analysis file selector.
- [ ] Result import accepts one `web-report-bundle.json` no larger than 50 MiB.
- [ ] Registered reports receive a trust label only after plugin cross-validation.
- [ ] Standalone imports are labeled `출처 미확인 묶음`.
- [ ] Failed bundle replacement preserves the previous valid report.
- [ ] The CEO screen uses at most three plugin-selected issues and plugin-provided chart specifications.
- [ ] All issues remain available in the full issue structure.
- [ ] The five Korean report screens share one active issue scope.
- [ ] ECharts uses core modules and SVG renderer.
- [ ] Unsafe or incomplete chart specifications fall back to evidence tables.
- [ ] Source preview APIs return only hash-verified embedded preview content.
- [ ] Restricted and prohibited source policies do not expose values or absolute paths.
- [ ] Expert packets are one-way screen, Markdown, and print outputs only.
- [ ] Revision changes are shown only when supplied by the plugin.
- [ ] Trust events with no timestamp show sequence only.
- [ ] `ReportScope` follows addendum v2’s `run_id + revision + scope_kind + scope_instance_id`.
- [ ] The question-bubble attachment slot exists without Q&A controls or simulated answers.
- [ ] No live AnalysisProvider, Codex call, conversation store, or voice feature is present.
- [ ] Stored result viewing remains independent of network and Q&A availability.
