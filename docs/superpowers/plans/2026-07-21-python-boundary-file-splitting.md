# Python Boundary File Splitting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split large Python accounting, CLI, and report-contract boundary modules while keeping their documented imports and command behavior stable.

**Architecture:** Static contracts, validation, parsing, context assembly, command dispatch, and semantic report checks become internal modules. Existing modules remain compatibility facades and own their public entry points.

**Tech Stack:** Python 3.11, unittest, Pydantic, argparse, uv

---

## Task 1: Split accounting input contracts and validation

**Files:**
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/accounting/input_adapter.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/accounting/input_contracts.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/accounting/input_validation.py`
- Modify: `tests/unit/accounting/test_input_adapter.py`

- [ ] Add RED imports for the two new modules and parity assertions for representative account mappings, journal normalization, and tier-zero validation.
- [ ] Run `uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.accounting.test_input_adapter` and confirm the missing modules fail.
- [ ] Move account/category mappings and immutable contract tables to `input_contracts.py`.
- [ ] Move scalar coercion, journal-line validation, and tier-zero validation helpers to `input_validation.py`.
- [ ] Keep public adapter functions and builders in `input_adapter.py`, re-exporting any previously importable names.
- [ ] Run the focused accounting unit module plus directly related accounting preparation integration tests found with `rg -l input_adapter|prepare.*account tests`.
- [ ] Review `git diff --check` and commit only this accounting slice.

## Task 2: Split CLI parser, context, and command dispatch

**Files:**
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/cli.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/cli_parser.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/cli_context.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/cli_commands.py`
- Modify: `tests/plugin/test_cli_commands.py`

- [ ] Add RED import tests for `build_parser`, execution-context construction, and command dispatch through the new modules.
- [ ] Run `uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.plugin.test_cli_commands` and confirm expected import failure.
- [ ] Move argparse construction to `cli_parser.py`, runtime/application dependency construction to `cli_context.py`, and command handlers plus dispatch mapping to `cli_commands.py`.
- [ ] Keep `cli.main` and established helper imports working through facade imports.
- [ ] Run plugin CLI tests, application/CLI parity tests, and CLI safety tests discovered with `rg -l cli|command tests/unit tests/integration tests/plugin`.
- [ ] Review `git diff --check` and commit only this CLI slice.

## Task 3: Extract report semantic validation

**Files:**
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/contracts.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/contract_semantics.py`
- Modify: `tests/unit/web_report/test_contracts.py`

- [ ] Add a RED import and facade parity test for semantic bundle validation.
- [ ] Run `uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.web_report.test_contracts` and confirm expected import failure.
- [ ] Move `_index`, `_require_refs`, `_validate_sorted_id_sets`, and cross-document semantic checks to `contract_semantics.py`; retain schema models and public validation entry points in `contracts.py`.
- [ ] Run the focused report-contract module and Python contract tests found with `rg -l web_report.*contract|validate_bundle_document tests`.
- [ ] Run `npm --prefix contracts/web-report run check` once because the cross-language contract boundary was touched.
- [ ] Review `git diff --check` and commit only this report-contract slice.

## Task 4: Python boundary checkpoint

- [ ] Run the combined focused tests from Tasks 1–3 once.
- [ ] Run the Python package compile smoke test once.
- [ ] Inspect public import parity and remove duplicate implementations.
- [ ] Record exact commands, exit codes, and deferred items for the final report.
