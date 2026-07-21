# Web File Splitting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the largest Web validator, question UI/route, and launcher/preflight modules into cohesive internal units without changing imports, HTTP behavior, or process semantics.

**Architecture:** Public modules remain facades. Pure policy/model functions are separated from React state, route I/O, filesystem access, and child-process supervision so each concern can be tested independently.

**Tech Stack:** TypeScript, React, Next.js, Vitest, Node.js test runner, Playwright

---

## Task 1: Split bundle document policy and semantics

**Files:**
- Modify: `web/src/lib/server/bundle-validator.ts`
- Create: `web/src/lib/server/bundle-document-policy.ts`
- Create: `web/src/lib/server/bundle-semantics.ts`
- Modify: `web/src/lib/server/__tests__/bundle-validator.test.ts`

- [ ] Add RED imports and parity tests for document-shape policy and cross-document semantic checks.
- [ ] Run `npm --prefix web run test:focused -- src/lib/server/__tests__/bundle-validator.test.ts` and confirm the missing modules fail.
- [ ] Move document-level allowlists/shape checks to `bundle-document-policy.ts` and relationship/order/reference checks to `bundle-semantics.ts`.
- [ ] Keep the existing validator exports and error messages stable through facade delegation.
- [ ] Run focused bundle-validator and report-contract tests, then `npm --prefix contracts/web-report run check` once.
- [ ] Review `git diff --check` and commit only this validator slice.

## Task 2: Split question experience model and hook

**Files:**
- Modify: `web/src/features/questions/QuestionExperience.tsx`
- Create: `web/src/features/questions/question-experience-model.ts`
- Create: `web/src/features/questions/useQuestionExperience.ts`
- Modify: `web/src/features/questions/__tests__/QuestionExperience.test.tsx`

- [ ] Add RED unit coverage for pure state derivation and hook integration imports.
- [ ] Run `npm --prefix web run test:focused -- src/features/questions/__tests__/QuestionExperience.test.tsx` and confirm expected import failure.
- [ ] Move pure display/answer derivation to `question-experience-model.ts` and orchestration state/effects/actions to `useQuestionExperience.ts`.
- [ ] Keep `QuestionExperience` props and rendered accessibility/interaction behavior unchanged.
- [ ] Run the focused question experience and related question-page tests.
- [ ] Run `npm --prefix web run typecheck` once for the completed client boundary.
- [ ] Review `git diff --check` and commit only this UI slice.

## Task 3: Extract question request policy

**Files:**
- Modify: `web/src/lib/server/questions/question-route-handlers.ts`
- Create: `web/src/lib/server/questions/question-request-policy.ts`
- Modify: `web/src/lib/server/questions/__tests__/question-route-handlers.test.ts`

- [ ] Add RED policy-module tests for request parsing, normalization, and rejection cases.
- [ ] Run the route-handler focused test and confirm expected import failure.
- [ ] Move request policy and validation into the new pure module while keeping route I/O and response mapping in `question-route-handlers.ts`.
- [ ] Run focused route, provider, and question-contract tests.
- [ ] Review `git diff --check` and commit only this route slice.

## Task 4: Split AI demo launch planning and supervision

**Files:**
- Modify: `web/scripts/start-ai-demo.mjs`
- Create: `web/scripts/ai-launch-plan.mjs`
- Create: `web/scripts/child-supervisor.mjs`
- Modify: `web/scripts/start-ai-demo.test.mjs`

- [ ] Add RED imports and parity tests for environment/command planning and child lifecycle supervision.
- [ ] Run `node --test web/scripts/start-ai-demo.test.mjs` and confirm expected missing-module failure.
- [ ] Move deterministic environment, command, and URL construction to `ai-launch-plan.mjs`; move spawn, signal, cleanup, and exit forwarding to `child-supervisor.mjs`.
- [ ] Keep `start-ai-demo.mjs` as the executable facade and preserve existing exports used by launcher tests.
- [ ] Run all launcher tests once and verify no child process remains after completion.
- [ ] Review `git diff --check` and commit only this launcher slice.

## Task 5: Split question preflight policy and I/O

**Files:**
- Modify: `web/scripts/question-preflight.mjs`
- Create: `web/scripts/question-preflight-policy.mjs`
- Create: `web/scripts/question-preflight-io.mjs`
- Create: `web/scripts/question-preflight.test.mjs`

- [ ] Add a RED Node test importing both new modules and covering capability policy, timeout classification, and file/result normalization.
- [ ] Run `node --test web/scripts/question-preflight.test.mjs` and confirm expected import failure.
- [ ] Move pure capability/timeout/result policy to `question-preflight-policy.mjs` and filesystem/subprocess adapters to `question-preflight-io.mjs`.
- [ ] Keep executable argument, stdout, stderr, and exit-code behavior unchanged in `question-preflight.mjs`.
- [ ] Run preflight, Codex runner, and capability-focused launcher tests once.
- [ ] Review `git diff --check` and commit only this preflight slice.

## Task 6: Web checkpoint

- [ ] Run all focused Web tests touched above once.
- [ ] Run `npm --prefix web run typecheck`, `npm --prefix web run lint`, and the launcher Node tests one at a time.
- [ ] Inspect imports with `rg -n bundle-(document-policy|semantics)|question-(experience-model|request-policy)|ai-launch-plan|child-supervisor|question-preflight-(policy|io) web` and remove duplicate implementations.
- [ ] Record exact commands, exit codes, and deferred items for the final report.
