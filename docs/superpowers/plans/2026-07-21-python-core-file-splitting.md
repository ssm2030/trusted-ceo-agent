# Python Core File Splitting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split Python finalization, service-view, and mutation responsibilities into focused internal modules without changing public APIs or behavior.

**Architecture:** Existing public modules remain compatibility facades. Shared document helpers feed finalization and delivery, pure view builders feed the orchestrator, and an explicit mutation session feeds command-family handlers.

**Tech Stack:** Python 3.11, unittest, Pydantic, canonical JSON artifacts, uv

---

## Task 1: Extract runtime document and delivery helpers

**Files:**
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/runtime_finalization.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/runtime_documents.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/runtime_delivery.py`
- Modify: `tests/unit/outputs/test_runtime_finalization.py`

- [ ] Add a RED compatibility test that imports `runtime_delivery.build_delivery_package` and asserts that `runtime_finalization.build_delivery_package` is the same callable.
- [ ] Run `uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.outputs.test_runtime_finalization` and confirm the new module import fails.
- [ ] Move document loading, canonical serialization, and artifact-reference helpers into `runtime_documents.py`; move delivery-package builders into `runtime_delivery.py`; retain re-exports from `runtime_finalization.py`.
- [ ] Run the focused test again, then run `tests.unit.outputs.test_professional_finalization`, `tests.unit.outputs.test_professional_publication_from_files`, and `tests.unit.service.test_orchestrator_finalization`.
- [ ] Review `git diff --check` and stage only the files listed in this task.

## Task 2: Extract orchestrator view construction

**Files:**
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/service/orchestrator.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/service/hitl_views.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/service/snapshot_views.py`
- Modify: `tests/unit/service/test_orchestrator.py`

- [ ] Add RED imports and behavior tests for default/edited operation views, pending-gate views, HITL-card construction, and run-snapshot projection.
- [ ] Run `uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.service.test_orchestrator` and confirm the missing modules cause the expected failure.
- [ ] Move `_default_operations`, `_edited_operations`, `_pending_gate`, and `_hitl_card` logic into pure functions in `hitl_views.py`, using explicit arguments instead of service state.
- [ ] Move snapshot response projection into `snapshot_views.py`; keep `OrchestrationService` methods as thin compatibility delegates.
- [ ] Run service-focused tests: `tests.unit.service.test_orchestrator`, `tests.unit.service.test_orchestrator_hitl`, `tests.unit.service.test_orchestrator_finalization`, and `tests.unit.service.test_source_uploads`.
- [ ] Review `git diff --check` and stage only this slice, including the already-created `source_uploads.py` extraction and its tests when committing the overlapping orchestrator file.

## Task 3: Extract mutation contracts, reasoning, and component helpers

**Files:**
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/application/mutations.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/application/mutation_contracts.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/application/mutation_reasoning.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/application/mutation_components.py`
- Modify: `tests/unit/application/test_mutations.py`

- [ ] Add RED module-import and re-export identity tests for public validation helpers and mutation parameter contracts.
- [ ] Run `uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.application.test_mutations` and confirm the expected import failure.
- [ ] Move parameter validation/contracts to `mutation_contracts.py`, reasoning draft/result helpers to `mutation_reasoning.py`, and component preparation/result helpers to `mutation_components.py` without changing signatures.
- [ ] Re-export existing public names from `mutations.py` and run focused mutation, reasoning, and component tests.
- [ ] Review `git diff --check` and commit only this helper-extraction slice.

## Task 4: Split mutation command families

**Files:**
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/application/mutations.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/application/mutation_session.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/application/mutation_commands/__init__.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/application/mutation_commands/analysis.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/application/mutation_commands/reasoning.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/application/mutation_commands/approvals.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/application/mutation_commands/lifecycle.py`
- Modify: `tests/unit/application/test_mutations.py`

- [ ] Add RED import tests for all four command-family modules and a dispatcher parity test covering one representative command per family.
- [ ] Run the focused application test and confirm the missing modules fail first.
- [ ] Introduce an explicit mutation session carrying store, clock, policy, and current-run data required by handlers.
- [ ] Move `scan`/`run-components`/`prepare-finalization` branches to `analysis.py`; `prepare-jobs`/`ingest-result`/`reduce-stage` to `reasoning.py`; approval request/decision branches to `approvals.py`; resume/stop/cancel/finalize branches to `lifecycle.py`.
- [ ] Keep `MutationExecutor` and `_execute` as the public validation/dispatch facade, with unchanged result and error behavior.
- [ ] Run `tests.unit.application.test_mutations`, application/CLI parity, reasoning, approval, finalization, and safety-focused modules discovered by `rg --files tests`.
- [ ] Review `git diff --check` and commit only this command-dispatch slice.

## Task 5: Python core checkpoint

- [ ] Run the combined focused modules from Tasks 1–4 once.
- [ ] Run `uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m compileall -q plugin/trusted-ceo-agent/trusted_ceo_agent`.
- [ ] Inspect imports with `rg -n runtime_(documents|delivery)|hitl_views|snapshot_views|mutation_ plugin/trusted-ceo-agent tests` and remove accidental duplicate implementations.
- [ ] Record exact commands, exit codes, and any deferred failures for the final report.
