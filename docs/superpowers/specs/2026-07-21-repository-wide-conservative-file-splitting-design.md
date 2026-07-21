# Repository-wide conservative file-splitting design

Status: approved on 2026-07-21

## Context

The repository contains several production files whose size now reflects mixed
responsibilities rather than a single cohesive algorithm or state machine.
The refactor must cover the complete production tree, not only files changed
today, while preserving behavior and all supported public entry points.

The worktree also contains user-owned changes and unrelated untracked
evaluation material. Those files are outside this refactor and must not be
modified, staged, or committed.

## Goals

- Split production files only where responsibility boundaries are clear.
- Preserve public Python imports, TypeScript imports, CLI commands, service
  routes, error types, error messages, deterministic ordering, hashes, and
  serialized payloads.
- Reduce the amount of code that must be read or changed for one concern.
- Introduce directed internal dependencies and avoid circular imports.
- Verify every extraction with RED-GREEN tests and the repository completion
  gates.

## Non-goals

- No product behavior, schema, route, or command changes.
- No redesign of business rules, accounting calculations, workflow states, or
  persistence formats.
- No splitting of generated files, schemas, fixtures, tests, lock files,
  vendor code, or build output.
- No broad renaming or formatting-only rewrite.

## Files deliberately kept cohesive

The following files are long but remain intact because their contents form one
rule suite, algorithm, state machine, or persistence pipeline:

- accounting/revenue_procedures.py
- accounting/cashflow_procedures.py
- accounting/core_procedures.py
- accounting/project_cost_procedures.py
- analysis/runtime.py
- service/questions.py
- service/run_store.py
- web/src/lib/server/questions/conversation-store.ts
- evaluation, knowledge-foundry, export, and publication pipelines

Helper extraction from these files is allowed only if implementation evidence
shows an independent concern with more than one consumer. Procedure functions
must not be fragmented merely to reduce line counts.

## Python module boundaries

### Application mutations

application/mutations.py remains the compatibility facade exporting
MutationExecutor and validate_reasoning_draft.

Internal responsibilities move to:

- application/mutation_contracts.py: supported commands, parameter contracts,
  document payload validation, and request normalization.
- application/mutation_reasoning.py: reasoning context, jobs, attempts, draft
  materialization, and reasoning failure artifacts.
- application/mutation_components.py: accounting and professional component
  artifact construction.
- application/mutation_commands/analysis.py: scan, component execution, and
  finalization preparation commands.
- application/mutation_commands/reasoning.py: prepare-jobs, ingest-result, and
  reduce-stage commands.
- application/mutation_commands/approvals.py: approval request and web
  approval/decision commands.
- application/mutation_commands/lifecycle.py: resume, stop, cancel, and
  finalize commands.

A small mutation session object owns the current artifact store, pointer,
revision, files, workflow state, result data, and final commit operation.
Command handlers may mutate only this explicit session. The facade performs
validation, dispatch, and returns the existing ApplicationResult.

### Runtime finalization

- runtime_documents.py: shared safe document loading, status extraction,
  mission loading, and structured artifact extraction.
- runtime_finalization.py: finalization preparation and professional
  diagnostic assembly.
- runtime_delivery.py: writer application, structured-grade verification,
  publication binding, and delivery package construction.

runtime_finalization.py re-exports build_delivery_package so existing imports
remain valid.

### Service orchestration views

service/orchestrator.py retains lifecycle control, application calls,
checkpointing, and gateway execution.

- service/hitl_views.py: default/edited operations, pending-gate resolution,
  and HITL card construction from explicit inputs.
- service/snapshot_views.py: progress, actions, pending state, errors, and
  RunSnapshot construction.

The view modules are pure with respect to storage. The orchestrator loads files
and manifests, then passes them to the view builders.

### Accounting input adapter

- accounting/input_contracts.py: table fields, type classifications,
  primary/foreign keys, source-table mappings, and population declarations.
- accounting/input_validation.py: scalar normalization, runtime binding, row
  validation, journal reconciliation, and tier-zero input validation.
- accounting/input_adapter.py: domain row builders and
  build_accounting_request.

The existing build_accounting_request import path remains unchanged.

### CLI

- cli_parser.py: parser construction and command argument declarations.
- cli_context.py: stable reads, artifact-store lookup, workflow-state and
  mission helpers.
- cli_commands.py: command handlers and dispatch table.
- cli.py: compatibility exports and main.

All current subcommands, flags, exit codes, stdout JSON shapes, and argparse
errors remain unchanged.

### Python web-report contracts

- web_report/contract_semantics.py: indexes, reference closure, sorting, hash,
  and cross-document semantic checks.
- web_report/contracts.py: schema-compatible loading, schema validation,
  eligibility validation, public exception, and public entry points.

## Web module boundaries

### Bundle validation

- bundle-document-policy.ts: depth, array-size, absolute-path, JSON pointer,
  and source-preview bounds.
- bundle-semantics.ts: indexes, reference closure, graph, hash, packet, and
  presentation semantic checks.
- bundle-validator.ts: schema loading, validation orchestration, eligibility
  validation, compatibility exports, and public error type.

### Question experience

- question-experience-model.ts: status labels, terminal-state rules, draft
  defaults, and latest-answer selection.
- useQuestionExperience.ts: network requests, polling, storage, cancellation,
  consent, voice control, and action callbacks.
- QuestionExperience.tsx: component composition and rendering only.

QuestionExperience and QuestionReferenceKind stay available from the existing
module.

### Question route handlers

- question-request-policy.ts: bounded JSON parsing, exact body keys, request
  identifiers, reference validation, rate keys, and conversation URL parsing.
- question-route-handlers.ts: response mapping and capability, submit, read,
  cancel, and conversation handlers.

Route modules keep importing the existing handler path.

### AI demo launcher

- ai-launch-plan.mjs: environment loading, browser-safe environment filtering,
  npm invocation, and launch-plan construction.
- child-supervisor.mjs: child spawning, health waiting, signal handling, and
  termination.
- start-ai-demo.mjs: compatibility exports and executable main.

### Question preflight

- question-preflight-policy.mjs: argument parsing, canonicalization, receipt
  hashes, bounded command rules, and seatbelt profile construction.
- question-preflight-io.mjs: private writes, atomic receipts, authentication
  checks, and bounded child execution.
- question-preflight.mjs: orchestration and executable entry point.

## Dependency rules

- Compatibility facades may import internal modules; internal modules must not
  import their facade.
- Pure policy, model, or view modules must not read the filesystem or mutate
  process-global state.
- Storage and process-control modules may depend on pure policy modules, never
  the reverse.
- Python application modules may depend on domain/runtime modules, but runtime
  and domain modules must not depend on application mutation modules.
- Client-safe Web helpers must not import server-only modules.

## Error and data compatibility

- Preserve exception and error class identities exposed by current facades.
- Preserve exact user-facing and contract error messages unless tests prove a
  message is private.
- Preserve canonical byte generation, SHA-256 inputs, sorting keys, identifier
  generation, Decimal handling, and JSON field presence.
- Preserve idempotency, revision, approval nonce, cancellation, and deletion
  behavior.
- Preserve public source sanitization and never introduce absolute paths into
  browser or model payloads.

## Test strategy

For each extraction slice:

1. Add a focused test requiring the new internal boundary or facade re-export.
2. Run it and confirm a failure caused by the missing boundary.
3. Move the minimum code needed without changing behavior.
4. Run the focused module tests and direct consumer tests.
5. Run static checks appropriate to the changed language boundary.

At completion run, once each:

- Web-report contract check.
- Python full unittest discovery.
- Web TypeScript typecheck.
- Web lint.
- Web unit and launcher tests.
- Next.js production build.
- Playwright end-to-end tests.
- git diff --check and a final worktree ownership audit.

## Acceptance criteria

- The eleven target facades are materially smaller and expose the same public
  API.
- No new circular dependency is introduced.
- No unrelated user-owned file is changed, staged, or committed.
- Focused RED-GREEN evidence exists for every extraction slice.
- All repository completion gates pass.
