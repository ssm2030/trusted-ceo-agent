# Accounting Multitable JSON Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable, fail-closed Adapter and a snapshot-bound accounting-request preparation path for the approved `accounting-multitable-json/1.0.0` input, without changing any trust boundary or inventing missing accounting judgments.

**Architecture:** A structural intake Adapter flattens the 33 named tables into the existing `ParsedDataset` contract with namespaced fields and JSON-pointer lineage. A shared content-aware selector is used by intake, runtime scan, and evidence preview. A separate accounting builder validates domain relationships and creates the existing seven-field accounting request; a read-only CLI command may create that request only from a verified, HITL-authorized immutable snapshot.

**Tech Stack:** Python 3.11, standard-library `unittest`, `Decimal`, strict JSON and canonical bytes already in the repository, existing ArtifactStore/Source Registry/HITL contracts, `uv` offline test execution.

---

## Scope and non-negotiable boundaries

- Canonical design: `docs/superpowers/specs/2026-07-18-accounting-multitable-json-adapter-design.md`.
- Allowed evaluation fixtures: files explicitly below `evaluation/synthetic/analysis-input/`.
- Forbidden input: do not enumerate, open, hash, copy, import, or otherwise access `evaluation/synthetic/truth/`.
- Do not modify source data, Evidence Lineage schemas, HITL gates, Pack authority, Validators, audit logs, or an existing immutable revision.
- Do not import `tools/synthetic_data/plugin_adapter.py` or any evaluation generator, validation, scoring, or answer module into the Plugin package.
- `prepare-accounting-input` is read-only with respect to ArtifactStore. Its only write is a new user-selected output file, created without overwrite.
- The accounting suite stays `machine_draft` with authority ceiling `Boundary`.
- Missing professional judgments are represented by empty dependent populations so the existing procedures return `not_assessable`. They are never replaced with `0`, `false`, synthetic dates, synthetic IDs, or neutral classifications.

## File responsibility map

### Create

- `plugin/trusted-ceo-agent/trusted_ceo_agent/intake/adapters/accounting_json.py` — structural schema recognition, strict loading, field namespacing, JSON-pointer locators, Adapter metadata.
- `plugin/trusted-ceo-agent/trusted_ceo_agent/intake/adapters/selection.py` — the only content-aware Adapter selection function.
- `plugin/trusted-ceo-agent/trusted_ceo_agent/accounting/input_adapter.py` — accounting-domain validation and deterministic seven-field request construction.
- `tests/support/accounting_multitable.py` — independent minimal valid 33-table test document.
- `tests/unit/intake/test_accounting_json_adapter.py` — structural Adapter tests.
- `tests/unit/intake/test_adapter_selection.py` — selector and fail-closed fallback tests.
- `tests/unit/accounting/test_input_adapter.py` — domain validation, safe mapping, provenance, and missing-data tests.
- `tests/integration/test_cli_prepare_accounting_input.py` — HITL, Source Registry, immutable snapshot, no-side-effect, and run-components handoff tests.

### Modify

- `plugin/trusted-ceo-agent/trusted_ceo_agent/intake/adapters/__init__.py` — export the new Adapter and selector.
- `plugin/trusted-ceo-agent/trusted_ceo_agent/intake/pipeline.py` — delegate supported structured files to the selector after snapshotting.
- `plugin/trusted-ceo-agent/trusted_ceo_agent/runtime_scan.py` — remove duplicate suffix dispatch and use the selector.
- `plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/previews.py` — use the selector when reparsing a root JSON source for Tab 2 evidence preview.
- `plugin/trusted-ceo-agent/trusted_ceo_agent/cli.py` — add the read-only `prepare-accounting-input` command.
- `tests/plugin/test_cli_commands.py` — freeze the new parser contract.
- `tests/integration/test_intake_formats.py` — verify snapshot-first multitable intake.
- `tests/integration/test_cli_scan.py` — verify scan artifact generation for an allowed analysis-input fixture.
- `tests/integration/test_intake_to_evidence.py` — verify namespaced SourceReference lineage.
- `tests/integration/test_cli_accounting_components.py` — keep the existing seven-field run-components contract unchanged.
- `tests/determinism/test_intake_determinism.py` — verify key-order invariance and table-identity sensitivity.
- `tests/unit/web_report/test_previews.py` — verify the Tab 2 reparse path.
- `tests/evaluation/test_synthetic_plugin_integration.py` — prove the allowed nested input reaches the Plugin path without importing evaluation helpers.

## Public interfaces fixed by this plan

- `trusted_ceo_agent.intake.adapters.accounting_json` exports constants
  `ACCOUNTING_MULTITABLE_ADAPTER_ID`, `ACCOUNTING_MULTITABLE_ADAPTER_VERSION`,
  `ACCOUNTING_MULTITABLE_SCHEMA_VERSION`, and `ACCOUNTING_TABLE_NAMES`.
- It exports
  `is_accounting_multitable_candidate(document: object) -> bool`,
  `validate_accounting_multitable_document(document: object) -> dict[str, object]`,
  `load_accounting_multitable_document(path: Path) -> dict[str, object]`, and
  `AccountingMultitableJsonAdapter.parse(path: Path, source_id: str) -> ParsedDataset`.
- `trusted_ceo_agent.intake.adapters.selection` exports the union alias
  `Adapter = CsvAdapter | JsonAdapter | XlsxAdapter | AccountingMultitableJsonAdapter`
  and `select_adapter(display_name: str, immutable_blob: Path) -> Adapter`.
- `trusted_ceo_agent.accounting.input_adapter` exports
  `build_accounting_request(document: Mapping[str, Any], *, run_id: str,
  revision: int, scope_ref: str, source_id: str,
  snapshot_sha256: str) -> dict[str, Any]`.

The request output has exactly these keys:

```python
{
    "scope_ref",
    "suite",
    "tier_zero_input",
    "raw_core_population",
    "revenue_input",
    "cashflow_input",
    "project_cost_inputs",
}
```

### Task 1: Independent fixture and structural accounting Adapter

**Files:**

- Create: `tests/support/accounting_multitable.py`
- Create: `tests/unit/intake/test_accounting_json_adapter.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/intake/adapters/accounting_json.py`
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/intake/adapters/__init__.py`

- [ ] **Step 1: Add an independent 33-table fixture**

Add this table-name literal to `tests/support/accounting_multitable.py`; do not import the production constant so a production omission cannot make the test pass.

```python
from __future__ import annotations

from typing import Any


ACCOUNTING_TABLE_NAMES = (
    "allocation_drivers", "allocation_pools", "allocation_results",
    "bank_accounts", "bank_transactions", "budgets", "cash_receipts",
    "chart_of_accounts", "contract_amendments", "contracts", "credit_notes",
    "customers", "departments", "direct_costs", "employee_assignments",
    "employees", "forecasts", "indirect_costs", "invoices",
    "journal_headers", "journal_lines", "management_kpis", "milestones",
    "payable_aging", "payroll_costs", "performance_obligations", "projects",
    "receivable_aging", "trial_balance", "vendor_costs", "vendor_payments",
    "vendors", "work_logs",
)


def valid_accounting_multitable_document() -> dict[str, Any]:
    tables: dict[str, list[dict[str, Any]]] = {
        name: [] for name in ACCOUNTING_TABLE_NAMES
    }
    tables["chart_of_accounts"] = [
        {
            "account_code": "2000", "account_id": "ACC-AP",
            "account_name": "Accounts payable", "account_type": "liability",
            "active": True, "currency": "KRW", "entity": "E1",
            "normal_balance": "credit",
        },
        {
            "account_code": "5000", "account_id": "ACC-EXP",
            "account_name": "Project expense", "account_type": "expense",
            "active": True, "currency": "KRW", "entity": "E1",
            "normal_balance": "debit",
        },
    ]
    tables["customers"] = [{
        "business_number": "123-45-67890", "country_code": "KR",
        "credit_terms_days": 30, "customer_id": "C1",
        "customer_name": "Customer One", "entity": "E1",
        "industry": None,
    }]
    tables["departments"] = [{
        "cost_center": "CC1", "department_id": "D1",
        "department_name": "Finance", "entity": "E1",
    }]
    tables["employees"] = [
        {
            "active": True, "currency": "KRW", "department_id": "D1",
            "employee_id": "U1", "employee_name": "Creator",
            "entity": "E1", "hire_date": "2025-01-01",
            "job_title": "Accountant", "monthly_salary": "10.00",
        },
        {
            "active": True, "currency": "KRW", "department_id": "D1",
            "employee_id": "U2", "employee_name": "Approver",
            "entity": "E1", "hire_date": "2025-01-01",
            "job_title": "Controller", "monthly_salary": "10.00",
        },
    ]
    tables["projects"] = [{
        "budget_amount": "200.00", "currency": "KRW",
        "customer_id": "C1", "department_id": "D1",
        "end_date": "2026-12-31", "entity": "E1",
        "fixed_price": "200.00", "project_id": "P1",
        "project_manager_employee_id": "U1", "project_name": "Project One",
        "start_date": "2026-01-01", "status": "active",
    }]
    tables["vendors"] = [{
        "business_number": "123-45-67890", "country_code": "KR",
        "entity": "E1", "payment_terms_days": 30,
        "service_category": "cloud", "vendor_id": "V1",
        "vendor_name": "Vendor One",
    }]
    tables["journal_headers"] = [{
        "approved_at": "2026-06-30T10:05:00Z", "approver_id": "U2",
        "counterparty_id": "V1", "creator_id": "U1",
        "creator_role": "accountant", "currency": "KRW",
        "description": "June service", "economic_event_date": "2026-06-29",
        "entered_at": "2026-06-30T10:00:00Z", "entity": "E1",
        "journal_id": "J1", "period": "2026-06",
        "posting_date": "2026-06-30", "project_id": "P1",
        "sequence": 1, "source_id": "ledger", "source_type": "manual",
        "status": "posted",
    }]
    tables["journal_lines"] = [
        {
            "account_id": "ACC-EXP", "credit": "0.00",
            "currency": "KRW", "debit": "100.00", "entity": "E1",
            "journal_id": "J1", "line_id": "L1", "line_number": 1,
            "period": "2026-06", "project_id": "P1",
        },
        {
            "account_id": "ACC-AP", "credit": "100.00",
            "currency": "KRW", "debit": "0.00", "entity": "E1",
            "journal_id": "J1", "line_id": "L2", "line_number": 2,
            "period": "2026-06", "project_id": "P1",
        },
    ]
    tables["trial_balance"] = [
        {
            "account_id": "ACC-EXP", "closing": "100.00",
            "control_subledger": "not_applicable", "credit_turnover": "0.00",
            "currency": "KRW", "debit_turnover": "100.00", "entity": "E1",
            "opening": "0.00", "period": "2026-06",
            "prior_closing": "0.00", "trial_balance_id": "TB-EXP",
        },
        {
            "account_id": "ACC-AP", "closing": "-100.00",
            "control_subledger": "payable_aging", "credit_turnover": "100.00",
            "currency": "KRW", "debit_turnover": "0.00", "entity": "E1",
            "opening": "0.00", "period": "2026-06",
            "prior_closing": "0.00", "trial_balance_id": "TB-AP",
        },
    ]
    tables["vendor_costs"] = [{
        "amount": "100.00", "cost_date": "2026-06-29",
        "currency": "KRW", "direct_flag": True, "entity": "E1",
        "invoice_reference": "INV-V1", "journal_id": "J1",
        "project_id": "P1", "service_category": "cloud",
        "vendor_cost_id": "VC1", "vendor_id": "V1",
    }]
    tables["payable_aging"] = [{
        "aging_bucket": "current", "ap_item_id": "AP1",
        "as_of_date": "2026-06-30", "currency": "KRW", "entity": "E1",
        "original_amount": "100.00", "outstanding_amount": "100.00",
        "vendor_cost_id": "VC1", "vendor_id": "V1",
    }]
    tables["direct_costs"] = [{
        "amount": "80.00", "cost_date": "2026-06-29",
        "cost_type": "vendor", "currency": "KRW",
        "direct_cost_id": "DC1", "entity": "E1", "project_id": "P1",
        "source_row_id": "VC1", "source_table": "vendor_costs",
    }]
    tables["allocation_pools"] = [{
        "account_id": "ACC-EXP", "currency": "KRW",
        "driver_type": "approved_engineer_hours", "entity": "E1",
        "period": "2026-06", "pool_id": "POOL1",
        "pool_name": "Operations", "source_amount": "120.00",
    }]
    tables["allocation_drivers"] = [{
        "driver_id": "DRV1", "driver_quantity": "3.00",
        "driver_share": "1.00", "entity": "E1", "period": "2026-06",
        "pool_id": "POOL1", "project_id": "P1",
    }]
    tables["allocation_results"] = [{
        "allocated_amount": "100.00", "allocation_id": "ALLOC1",
        "currency": "KRW", "driver_id": "DRV1", "entity": "E1",
        "journal_id": "J1", "period": "2026-06",
        "pool_id": "POOL1", "project_id": "P1",
    }]
    return {
        "company_id": "COMP1",
        "company_name": "Company One",
        "currency": "KRW",
        "entity": "E1",
        "generator_version": "1.0.0",
        "reporting_period": {"start": "2026-01-01", "end": "2026-06-30"},
        "scenario_id": "unit-valid",
        "schema_version": "1.0.0",
        "seed": 1,
        "tables": tables,
    }
```

- [ ] **Step 2: Write structural RED tests**

In `tests/unit/intake/test_accounting_json_adapter.py`, create a temporary JSON file with `canonical_bytes`, parse it, and add these exact assertions:

```python
def test_namespaces_fields_and_uses_exact_json_pointer(self) -> None:
    document = valid_accounting_multitable_document()
    document["tables"]["journal_lines"][0]["note"] = None
    dataset = self.parse(document)
    record = next(
        row for row in dataset.records
        if row.locator == {"pointer": "/tables/journal_lines/0"}
    )
    self.assertEqual("json_pointer", record.locator_type)
    self.assertEqual("L1", record.values["journal_lines.line_id"])
    self.assertEqual("100.00", record.values["journal_lines.debit"])
    self.assertIsNone(record.values["journal_lines.note"])
    self.assertEqual(
        "accounting-multitable-json",
        dataset.metadata["adapter_id"],
    )
    self.assertEqual("1.0.0", dataset.metadata["adapter_version"])
    self.assertEqual(33, len(dataset.metadata["table_row_counts"]))


def test_preserves_booleans_nulls_decimal_strings_and_signs(self) -> None:
    dataset = self.parse(valid_accounting_multitable_document())
    values = [record.values for record in dataset.records]
    account = next(value for value in values if "chart_of_accounts.account_id" in value)
    customer = next(value for value in values if "customers.customer_id" in value)
    payable = next(value for value in values if "trial_balance.trial_balance_id" in value
                   and value["trial_balance.trial_balance_id"] == "TB-AP")
    self.assertIs(account["chart_of_accounts.active"], True)
    self.assertIsNone(customer["customers.industry"])
    self.assertEqual("-100.00", payable["trial_balance.closing"])


def test_requires_exact_top_level_and_33_table_set(self) -> None:
    for mutation, message in (
        (lambda value: value.pop("company_id"), "top-level"),
        (lambda value: value.__setitem__("unexpected", True), "top-level"),
        (lambda value: value["tables"].pop("work_logs"), "table set"),
        (lambda value: value["tables"].__setitem__("unknown", []), "table set"),
        (lambda value: value.__setitem__("schema_version", "2.0.0"), "schema_version"),
    ):
        document = valid_accounting_multitable_document()
        mutation(document)
        with self.subTest(message=message), self.assertRaisesRegex(
            ContractError, message
        ):
            self.parse(document)
```

Also test a non-object row, an inverted report period, and raw duplicate JSON keys. The duplicate-key test must write bytes containing two `"company_id"` keys rather than constructing a Python dictionary.

- [ ] **Step 3: Verify RED**

Run:

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.intake.test_accounting_json_adapter
```

Expected: FAIL with `ModuleNotFoundError` for `trusted_ceo_agent.intake.adapters.accounting_json`.

- [ ] **Step 4: Implement strict structural validation**

In `accounting_json.py`, define the exact 33-table tuple from the fixture, require the exact top-level key set, require report-period key set `{"start", "end"}`, validate ISO dates and order, require every table value to be a list, and require every row to be a string-keyed object. Use `strict_loads`; catch `OSError`, `UnicodeError`, and `ValueError` and raise `ContractError(f"invalid strict JSON input: {error}")`.

Candidate recognition is deliberately narrow:

```python
def is_accounting_multitable_candidate(document: object) -> bool:
    return isinstance(document, dict) and "tables" in document
```

Flatten rows in `ACCOUNTING_TABLE_NAMES` order and original row order:

```python
values = {
    f"{table_name}.{raw_field}": raw_value
    for raw_field, raw_value in row.items()
}
record = ParsedRecord(
    logical_index=logical_index,
    locator_type="json_pointer",
    locator={"pointer": f"/tables/{_escape_pointer(table_name)}/{row_index}"},
    values=values,
)
```

The locator object must contain only `pointer`. Metadata must contain Adapter ID/version, input schema version, all non-table top metadata, and `table_row_counts`.

- [ ] **Step 5: Export and verify GREEN**

Export `AccountingMultitableJsonAdapter` from `intake/adapters/__init__.py`, then run:

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.intake.test_accounting_json_adapter tests.unit.intake.test_adapters
```

Expected: PASS, including existing flat JSON tests.

- [ ] **Step 6: Commit Task 1**

```powershell
git add plugin/trusted-ceo-agent/trusted_ceo_agent/intake/adapters tests/support/accounting_multitable.py tests/unit/intake/test_accounting_json_adapter.py
git commit -m "feat: add multitable accounting json adapter"
```

### Task 2: Shared content-aware Adapter selector

**Files:**

- Create: `tests/unit/intake/test_adapter_selection.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/intake/adapters/selection.py`
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/intake/adapters/__init__.py`

- [ ] **Step 1: Write selector RED tests**

Add tests for CSV, XLSX, root-array JSON, valid accounting JSON, malformed accounting candidate, unrelated root-object JSON, and unsupported suffix. The fail-closed case is:

```python
def test_invalid_accounting_candidate_never_falls_back(self) -> None:
    document = valid_accounting_multitable_document()
    document["schema_version"] = "2.0.0"
    path = self.write_json(document)
    with self.assertRaisesRegex(ContractError, "schema_version"):
        select_adapter("dataset.json", path)
```

The root-array case must assert `type(adapter) is JsonAdapter`; the accounting case must assert `type(adapter) is AccountingMultitableJsonAdapter`.

- [ ] **Step 2: Verify RED**

Run:

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.intake.test_adapter_selection
```

Expected: FAIL because `selection.py` does not exist.

- [ ] **Step 3: Implement the selector**

Use this decision order:

```python
def select_adapter(display_name: str, immutable_blob: Path) -> Adapter:
    suffix = Path(display_name).suffix.casefold()
    if suffix == ".csv":
        return CsvAdapter()
    if suffix == ".xlsx":
        return XlsxAdapter()
    if suffix != ".json":
        raise ContractError(
            f"unsupported input format: {suffix or '<none>'}"
        )
    try:
        document = strict_loads(immutable_blob.read_bytes())
    except (OSError, UnicodeError, ValueError) as error:
        raise ContractError(f"invalid strict JSON input: {error}") from error
    if isinstance(document, list):
        return JsonAdapter()
    if is_accounting_multitable_candidate(document):
        validate_accounting_multitable_document(document)
        return AccountingMultitableJsonAdapter()
    raise ContractError(
        "JSON root must be an array or accounting multitable object"
    )
```

Do not inspect the original mutable file. `immutable_blob` is the content-addressed snapshot.

- [ ] **Step 4: Export and verify GREEN**

Export `select_adapter` from `intake/adapters/__init__.py`, then run:

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.intake.test_adapter_selection tests.unit.intake.test_accounting_json_adapter
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```powershell
git add plugin/trusted-ceo-agent/trusted_ceo_agent/intake/adapters tests/unit/intake/test_adapter_selection.py
git commit -m "refactor: centralize intake adapter selection"
```

### Task 3: Intake, runtime scan, lineage, determinism, and Tab 2 preview integration

**Files:**

- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/intake/pipeline.py`
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/runtime_scan.py`
- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/previews.py`
- Modify: `tests/integration/test_intake_formats.py`
- Modify: `tests/integration/test_cli_scan.py`
- Modify: `tests/integration/test_intake_to_evidence.py`
- Modify: `tests/determinism/test_intake_determinism.py`
- Modify: `tests/unit/web_report/test_previews.py`

- [ ] **Step 1: Add pipeline and scan RED tests**

Use `valid_accounting_multitable_document()` for the focused pipeline test. Assert snapshot-first parsing and:

```python
self.assertEqual("accounting-multitable-json", result.dataset.metadata["adapter_id"])
self.assertEqual(
    {"pointer": "/tables/journal_headers/0"},
    next(
        record.locator for record in result.dataset.records
        if record.values.get("journal_headers.journal_id") == "J1"
    ),
)
```

In `test_cli_scan.py`, use only:

```python
ROOT / "evaluation" / "synthetic" / "analysis-input" / "clean-baseline" / "dataset.json"
```

After `start` and `scan`, assert one parsed source, Adapter ID `accounting-multitable-json`, 33 row-count entries, and 360 records. Do not form a path containing the forbidden directory name.

- [ ] **Step 2: Add lineage, determinism, and preview RED tests**

Add these behaviors:

```python
def test_table_object_order_does_not_change_semantic_hash(self) -> None:
    left = valid_accounting_multitable_document()
    right = copy.deepcopy(left)
    right["tables"] = dict(reversed(list(right["tables"].items())))
    self.assertEqual(self.parse(left).semantic_rows_hash,
                     self.parse(right).semantic_rows_hash)


def test_moving_same_row_between_tables_changes_semantic_hash(self) -> None:
    left = valid_accounting_multitable_document()
    right = valid_accounting_multitable_document()
    row = right["tables"]["journal_lines"].pop()
    right["tables"]["trial_balance"].append(row)
    self.assertNotEqual(self.parse(left).semantic_rows_hash,
                        self.parse(right).semantic_rows_hash)
```

The SourceReference test must assert selected field `journal_lines.debit`, locator type `json_pointer`, and locator `{"pointer": "/tables/journal_lines/0"}`. The preview test must reparse an accounting JSON source and verify the same locator and value.

- [ ] **Step 3: Verify RED**

Run:

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.integration.test_intake_formats tests.integration.test_cli_scan tests.integration.test_intake_to_evidence tests.determinism.test_intake_determinism tests.unit.web_report.test_previews
```

Expected: accounting cases FAIL because pipeline, scan, and preview still select `JsonAdapter`.

- [ ] **Step 4: Replace duplicate selection paths**

In `pipeline.py`, keep document-like formats unchanged and delegate structured formats:

```python
blob = self.snapshotter.artifact_root / snapshot.source["snapshot_ref"]
if path.suffix.casefold() in {".txt", ".md", ".pdf"}:
    dataset = None
else:
    adapter = select_adapter(path.name, blob)
    dataset = adapter.parse(blob, snapshot.source["source_id"])
```

In `runtime_scan.py`, delete `_adapter()` and its three direct Adapter imports:

```python
adapter = select_adapter(str(source["display_name"]), blob)
dataset = adapter.parse(blob, source_id)
```

In `web_report/previews.py`, preserve an explicit flat JSON `records_pointer` and use the common selector only at the root:

```python
if media_type == "application/json":
    metadata = source.get("metadata")
    pointer = (
        metadata.get("records_pointer", "")
        if isinstance(metadata, Mapping)
        else ""
    )
    if not isinstance(pointer, str):
        raise IntegrityError("JSON records pointer must be a string")
    if pointer:
        return JsonAdapter(records_pointer=pointer).parse(path, source_id)
    return select_adapter("snapshot.json", path).parse(path, source_id)
```

- [ ] **Step 5: Verify GREEN**

Run the Step 3 command again.

Expected: PASS. Existing flat CSV/JSON/XLSX, `.txt/.md/.pdf`, and preview-pointer cases must also pass.

- [ ] **Step 6: Commit Task 3**

```powershell
git add plugin/trusted-ceo-agent/trusted_ceo_agent/intake/pipeline.py plugin/trusted-ceo-agent/trusted_ceo_agent/runtime_scan.py plugin/trusted-ceo-agent/trusted_ceo_agent/web_report/previews.py tests/integration/test_intake_formats.py tests/integration/test_cli_scan.py tests/integration/test_intake_to_evidence.py tests/determinism/test_intake_determinism.py tests/unit/web_report/test_previews.py
git commit -m "feat: route multitable snapshots through intake and preview"
```

### Task 4: Domain validation and safe accounting request builder

**Files:**

- Create: `tests/unit/accounting/test_input_adapter.py`
- Create: `plugin/trusted-ceo-agent/trusted_ceo_agent/accounting/input_adapter.py`

- [ ] **Step 1: Write the closed-contract and provenance RED tests**

Use the support fixture and call:

```python
request = build_accounting_request(
    valid_accounting_multitable_document(),
    run_id="run_fixture",
    revision=4,
    scope_ref="scope_fixture",
    source_id="source_" + "a" * 24,
    snapshot_sha256="a" * 64,
)
```

Assert the exact seven keys, fixed suite release `accounting-suite-2026-07-17`, run/revision binding in all 20 procedure inputs, and this exact local reference:

```python
"source_" + "a" * 24 + "@" + "a" * 64 + "#/tables/vendor_costs/0"
```

Assert no snapshot SHA is used as `suite.release_id`.

- [ ] **Step 2: Write safe-assessability RED tests**

Dispatch the built request through `dispatch_accounting_suite`. Assert:

```python
self.assertEqual(64, len(bundle["execution_manifest"]["family_records"]))
self.assertEqual(30, len(bundle["result_artifacts"]))
```

Tier Zero must consume direct journal/TB data. CA-02 and CA-04 must not be `not_assessable`. AC-06 through AC-16, all RV families, all CF families, and CA families other than CA-02/CA-04 must be `not_assessable`.

Add explicit tests proving:

- CA-02 compares explicit `vendor_costs.direct_flag` classified amount `100` to linked `direct_costs.amount` `80`.
- CA-04 compares recorded allocation `100` to `pool source_amount 120 × driver quantity 3 / pool quantity 3 = 120`.
- Removing a required CA-02 source value empties the CA-02 rows; it does not create a zero.
- Null or missing AC-08 control flags leave `raw_core_population["journals"]` empty, and `raw_core_population["close_timestamp"]` equals the source report-end date without an appended time.
- Revenue and cashflow populations remain empty even though invoice, contract, KPI, and aging source tables exist, because the closed procedure contracts require absent judgments.

- [ ] **Step 3: Write domain failure RED tests**

Create independent subtests for:

- duplicate primary key;
- missing foreign key;
- invalid ISO date or timestamp;
- invalid `YYYY-MM` period;
- non-finite or non-decimal monetary string;
- row currency/entity inconsistent with the top-level document;
- journal line with both debit and credit positive;
- journal whose debit and credit totals differ;
- malformed 64-character lowercase snapshot SHA or a `source_id` not equal to `source_{snapshot_sha256[:24]}`;
- empty run ID, source ID, or scope ref;
- negative or boolean revision.

Each must raise `ContractError` before returning a request.

- [ ] **Step 4: Verify RED**

Run:

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.accounting.test_input_adapter
```

Expected: FAIL because `trusted_ceo_agent.accounting.input_adapter` does not exist.

- [ ] **Step 5: Implement domain contract validation**

The builder first calls `validate_accounting_multitable_document`. It then validates exact row fields against the approved schema. Put this complete field map in production code; production code must not import evaluation modules:

```python
_TABLE_FIELDS = {
    "allocation_drivers": {
        "driver_id", "driver_quantity", "driver_share", "entity", "period",
        "pool_id", "project_id",
    },
    "allocation_pools": {
        "account_id", "currency", "driver_type", "entity", "period",
        "pool_id", "pool_name", "source_amount",
    },
    "allocation_results": {
        "allocated_amount", "allocation_id", "currency", "driver_id",
        "entity", "journal_id", "period", "pool_id", "project_id",
    },
    "bank_accounts": {
        "account_id", "account_number_masked", "bank_account_id",
        "bank_name", "currency", "entity",
    },
    "bank_transactions": {
        "amount", "bank_account_id", "bank_transaction_id", "counterparty_id",
        "currency", "description", "direction", "entity", "journal_id",
        "transaction_date",
    },
    "budgets": {
        "budget_id", "cost_budget", "currency", "entity", "hours_budget",
        "period", "project_id", "revenue_budget",
    },
    "cash_receipts": {
        "amount", "bank_account_id", "currency", "customer_id", "entity",
        "invoice_id", "journal_id", "receipt_date", "receipt_id",
    },
    "chart_of_accounts": {
        "account_code", "account_id", "account_name", "account_type", "active",
        "currency", "entity", "normal_balance",
    },
    "contract_amendments": {
        "amendment_id", "amount_change", "approval_date", "approved_by",
        "contract_id", "currency", "entity", "scope_change",
    },
    "contracts": {
        "billing_method", "contract_id", "contract_value", "currency",
        "customer_id", "end_date", "entity", "project_id", "signed_date",
        "start_date", "status",
    },
    "credit_notes": {
        "amount", "credit_note_id", "currency", "entity", "invoice_id",
        "issue_date", "journal_id", "reason",
    },
    "customers": {
        "business_number", "country_code", "credit_terms_days", "customer_id",
        "customer_name", "entity", "industry",
    },
    "departments": {
        "cost_center", "department_id", "department_name", "entity",
    },
    "direct_costs": {
        "amount", "cost_date", "cost_type", "currency", "direct_cost_id",
        "entity", "project_id", "source_row_id", "source_table",
    },
    "employee_assignments": {
        "allocation_percent", "assignment_id", "employee_id", "end_date",
        "entity", "project_id", "start_date",
    },
    "employees": {
        "active", "currency", "department_id", "employee_id", "employee_name",
        "entity", "hire_date", "job_title", "monthly_salary",
    },
    "forecasts": {
        "as_of_date", "currency", "entity", "forecast_cash_in",
        "forecast_cash_out", "forecast_cost", "forecast_id",
        "forecast_revenue", "project_id",
    },
    "indirect_costs": {
        "amount", "cost_date", "currency", "description", "entity",
        "indirect_cost_id", "journal_id", "pool_id",
    },
    "invoices": {
        "amount", "contract_id", "currency", "customer_id", "due_date",
        "entity", "invoice_id", "issue_date", "journal_id", "milestone_id",
        "project_id", "status", "subtotal", "tax",
    },
    "journal_headers": {
        "approved_at", "approver_id", "counterparty_id", "creator_id",
        "creator_role", "currency", "description", "economic_event_date",
        "entered_at", "entity", "journal_id", "period", "posting_date",
        "project_id", "sequence", "source_id", "source_type", "status",
    },
    "journal_lines": {
        "account_id", "credit", "currency", "debit", "entity", "journal_id",
        "line_id", "line_number", "period", "project_id",
    },
    "management_kpis": {
        "dimension_id", "dimension_type", "entity", "kpi_id", "metric_name",
        "period", "unit", "value",
    },
    "milestones": {
        "billing_amount", "completion_date", "currency", "due_date", "entity",
        "milestone_id", "milestone_name", "obligation_id", "project_id",
        "status",
    },
    "payable_aging": {
        "aging_bucket", "ap_item_id", "as_of_date", "currency", "entity",
        "original_amount", "outstanding_amount", "vendor_cost_id", "vendor_id",
    },
    "payroll_costs": {
        "amount", "currency", "employee_id", "entity", "hours", "journal_id",
        "payroll_cost_id", "payroll_period", "project_id",
    },
    "performance_obligations": {
        "allocated_price", "contract_id", "currency", "end_date", "entity",
        "obligation_id", "obligation_name", "progress_percent", "project_id",
        "satisfaction_method", "start_date",
    },
    "projects": {
        "budget_amount", "currency", "customer_id", "department_id",
        "end_date", "entity", "fixed_price", "project_id",
        "project_manager_employee_id", "project_name", "start_date", "status",
    },
    "receivable_aging": {
        "aging_bucket", "ar_item_id", "as_of_date", "currency", "customer_id",
        "entity", "invoice_id", "original_amount", "outstanding_amount",
    },
    "trial_balance": {
        "account_id", "closing", "control_subledger", "credit_turnover",
        "currency", "debit_turnover", "entity", "opening", "period",
        "prior_closing", "trial_balance_id",
    },
    "vendor_costs": {
        "amount", "cost_date", "currency", "direct_flag", "entity",
        "invoice_reference", "journal_id", "project_id", "service_category",
        "vendor_cost_id", "vendor_id",
    },
    "vendor_payments": {
        "amount", "bank_account_id", "currency", "entity", "journal_id",
        "payment_date", "payment_id", "vendor_cost_id", "vendor_id",
    },
    "vendors": {
        "business_number", "country_code", "entity", "payment_terms_days",
        "service_category", "vendor_id", "vendor_name",
    },
    "work_logs": {
        "approved_by", "currency", "employee_id", "entity", "hourly_cost",
        "hours", "labor_cost", "project_id", "work_date", "work_log_id",
    },
}
```

Use these exact typed-field maps. Every field not listed here is a string; nullable fields may be `None`, while every other string must be non-empty.

```python
_DECIMAL_FIELDS = {
    "employees": {"monthly_salary"},
    "projects": {"fixed_price", "budget_amount"},
    "contracts": {"contract_value"},
    "contract_amendments": {"amount_change"},
    "performance_obligations": {"allocated_price", "progress_percent"},
    "milestones": {"billing_amount"},
    "invoices": {"subtotal", "tax", "amount"},
    "credit_notes": {"amount"},
    "cash_receipts": {"amount"},
    "vendor_payments": {"amount"},
    "bank_transactions": {"amount"},
    "receivable_aging": {"original_amount", "outstanding_amount"},
    "payable_aging": {"original_amount", "outstanding_amount"},
    "employee_assignments": {"allocation_percent"},
    "work_logs": {"hours", "hourly_cost", "labor_cost"},
    "payroll_costs": {"hours", "amount"},
    "vendor_costs": {"amount"},
    "direct_costs": {"amount"},
    "indirect_costs": {"amount"},
    "allocation_pools": {"source_amount"},
    "allocation_drivers": {"driver_quantity", "driver_share"},
    "allocation_results": {"allocated_amount"},
    "budgets": {"revenue_budget", "cost_budget", "hours_budget"},
    "forecasts": {
        "forecast_revenue", "forecast_cost", "forecast_cash_in",
        "forecast_cash_out",
    },
    "management_kpis": {"value"},
    "journal_lines": {"debit", "credit"},
    "trial_balance": {
        "prior_closing", "opening", "debit_turnover", "credit_turnover",
        "closing",
    },
}
_DATE_FIELDS = {
    "employees": {"hire_date"},
    "projects": {"start_date", "end_date"},
    "contracts": {"signed_date", "start_date", "end_date"},
    "contract_amendments": {"approval_date"},
    "performance_obligations": {"start_date", "end_date"},
    "milestones": {"due_date", "completion_date"},
    "invoices": {"issue_date", "due_date"},
    "credit_notes": {"issue_date"},
    "cash_receipts": {"receipt_date"},
    "vendor_payments": {"payment_date"},
    "bank_transactions": {"transaction_date"},
    "receivable_aging": {"as_of_date"},
    "payable_aging": {"as_of_date"},
    "employee_assignments": {"start_date", "end_date"},
    "work_logs": {"work_date"},
    "vendor_costs": {"cost_date"},
    "direct_costs": {"cost_date"},
    "indirect_costs": {"cost_date"},
    "forecasts": {"as_of_date"},
    "journal_headers": {"posting_date", "economic_event_date"},
}
_DATETIME_FIELDS = {
    "journal_headers": {"entered_at", "approved_at"},
}
_PERIOD_FIELDS = {
    "allocation_pools": {"period"},
    "allocation_drivers": {"period"},
    "allocation_results": {"period"},
    "budgets": {"period"},
    "payroll_costs": {"payroll_period"},
    "management_kpis": {"period"},
    "journal_headers": {"period"},
    "journal_lines": {"period"},
    "trial_balance": {"period"},
}
_INTEGER_FIELDS = {
    "customers": {"credit_terms_days"},
    "vendors": {"payment_terms_days"},
    "journal_headers": {"sequence"},
    "journal_lines": {"line_number"},
}
_BOOLEAN_FIELDS = {
    "chart_of_accounts": {"active"},
    "employees": {"active"},
    "vendor_costs": {"direct_flag"},
}
_NULLABLE_FIELDS = {
    ("customers", "industry"),
    ("contract_amendments", "scope_change"),
    ("milestones", "completion_date"),
    ("invoices", "status"),
    ("bank_transactions", "description"),
    ("forecasts", "forecast_cash_out"),
}
```

Use one primary-key field per table:

```python
_PRIMARY_KEYS = {
    "allocation_drivers": "driver_id",
    "allocation_pools": "pool_id",
    "allocation_results": "allocation_id",
    "bank_accounts": "bank_account_id",
    "bank_transactions": "bank_transaction_id",
    "budgets": "budget_id",
    "cash_receipts": "receipt_id",
    "chart_of_accounts": "account_id",
    "contract_amendments": "amendment_id",
    "contracts": "contract_id",
    "credit_notes": "credit_note_id",
    "customers": "customer_id",
    "departments": "department_id",
    "direct_costs": "direct_cost_id",
    "employee_assignments": "assignment_id",
    "employees": "employee_id",
    "forecasts": "forecast_id",
    "indirect_costs": "indirect_cost_id",
    "invoices": "invoice_id",
    "journal_headers": "journal_id",
    "journal_lines": "line_id",
    "management_kpis": "kpi_id",
    "milestones": "milestone_id",
    "payable_aging": "ap_item_id",
    "payroll_costs": "payroll_cost_id",
    "performance_obligations": "obligation_id",
    "projects": "project_id",
    "receivable_aging": "ar_item_id",
    "trial_balance": "trial_balance_id",
    "vendor_costs": "vendor_cost_id",
    "vendor_payments": "payment_id",
    "vendors": "vendor_id",
    "work_logs": "work_log_id",
}
```

Foreign keys are validated only when non-null. Put these exact relationships in production code:

```python
_FOREIGN_KEYS = {
    "employees": (("department_id", "departments", "department_id"),),
    "bank_accounts": (("account_id", "chart_of_accounts", "account_id"),),
    "projects": (
        ("customer_id", "customers", "customer_id"),
        ("project_manager_employee_id", "employees", "employee_id"),
        ("department_id", "departments", "department_id"),
    ),
    "contracts": (
        ("customer_id", "customers", "customer_id"),
        ("project_id", "projects", "project_id"),
    ),
    "contract_amendments": (
        ("contract_id", "contracts", "contract_id"),
        ("approved_by", "employees", "employee_id"),
    ),
    "performance_obligations": (
        ("contract_id", "contracts", "contract_id"),
        ("project_id", "projects", "project_id"),
    ),
    "milestones": (
        ("project_id", "projects", "project_id"),
        ("obligation_id", "performance_obligations", "obligation_id"),
    ),
    "invoices": (
        ("customer_id", "customers", "customer_id"),
        ("contract_id", "contracts", "contract_id"),
        ("project_id", "projects", "project_id"),
        ("milestone_id", "milestones", "milestone_id"),
        ("journal_id", "journal_headers", "journal_id"),
    ),
    "credit_notes": (
        ("invoice_id", "invoices", "invoice_id"),
        ("journal_id", "journal_headers", "journal_id"),
    ),
    "cash_receipts": (
        ("customer_id", "customers", "customer_id"),
        ("invoice_id", "invoices", "invoice_id"),
        ("bank_account_id", "bank_accounts", "bank_account_id"),
        ("journal_id", "journal_headers", "journal_id"),
    ),
    "vendor_payments": (
        ("vendor_id", "vendors", "vendor_id"),
        ("vendor_cost_id", "vendor_costs", "vendor_cost_id"),
        ("bank_account_id", "bank_accounts", "bank_account_id"),
        ("journal_id", "journal_headers", "journal_id"),
    ),
    "bank_transactions": (
        ("bank_account_id", "bank_accounts", "bank_account_id"),
        ("journal_id", "journal_headers", "journal_id"),
    ),
    "receivable_aging": (
        ("customer_id", "customers", "customer_id"),
        ("invoice_id", "invoices", "invoice_id"),
    ),
    "payable_aging": (
        ("vendor_id", "vendors", "vendor_id"),
        ("vendor_cost_id", "vendor_costs", "vendor_cost_id"),
    ),
    "employee_assignments": (
        ("employee_id", "employees", "employee_id"),
        ("project_id", "projects", "project_id"),
    ),
    "work_logs": (
        ("employee_id", "employees", "employee_id"),
        ("project_id", "projects", "project_id"),
        ("approved_by", "employees", "employee_id"),
    ),
    "payroll_costs": (
        ("employee_id", "employees", "employee_id"),
        ("project_id", "projects", "project_id"),
        ("journal_id", "journal_headers", "journal_id"),
    ),
    "vendor_costs": (
        ("vendor_id", "vendors", "vendor_id"),
        ("project_id", "projects", "project_id"),
        ("journal_id", "journal_headers", "journal_id"),
    ),
    "direct_costs": (("project_id", "projects", "project_id"),),
    "indirect_costs": (
        ("pool_id", "allocation_pools", "pool_id"),
        ("journal_id", "journal_headers", "journal_id"),
    ),
    "allocation_pools": (
        ("account_id", "chart_of_accounts", "account_id"),
    ),
    "allocation_drivers": (
        ("pool_id", "allocation_pools", "pool_id"),
        ("project_id", "projects", "project_id"),
    ),
    "allocation_results": (
        ("pool_id", "allocation_pools", "pool_id"),
        ("project_id", "projects", "project_id"),
        ("driver_id", "allocation_drivers", "driver_id"),
        ("journal_id", "journal_headers", "journal_id"),
    ),
    "budgets": (("project_id", "projects", "project_id"),),
    "forecasts": (("project_id", "projects", "project_id"),),
    "journal_headers": (
        ("creator_id", "employees", "employee_id"),
        ("approver_id", "employees", "employee_id"),
        ("project_id", "projects", "project_id"),
    ),
    "journal_lines": (
        ("journal_id", "journal_headers", "journal_id"),
        ("account_id", "chart_of_accounts", "account_id"),
        ("project_id", "projects", "project_id"),
    ),
    "trial_balance": (
        ("account_id", "chart_of_accounts", "account_id"),
    ),
}
```

For `direct_costs`, separately require `source_table` to name one of
`payroll_costs`, `vendor_costs`, `work_logs`, or `allocation_results`, and
require `source_row_id` in that table's primary-key index.

Parse exact decimals with `Decimal`, reject booleans and non-finite values, validate dates with `date.fromisoformat`, timestamps with a timezone-aware ISO parser, and periods with `YYYY-MM`. Because `strict_loads` represents JSON integers as `Decimal`, integer fields accept either Python `int` or a finite integral `Decimal`, reject booleans/fractions, and normalize to `int` only in the procedure request. Preserve original source values in the intake Adapter. The request builder may emit canonical decimal strings only for calculated procedure inputs.

For each journal, require at least two lines, nonnegative debit/credit, no line with both sides positive, and equal debit/credit sums.

- [ ] **Step 6: Implement the deterministic request**

Use these construction rules:

```python
source_ref = (
    f"{source_id}@{snapshot_sha256}"
    f"#/tables/{_escape_pointer(table_name)}/{row_index}"
)
```

- Tier Zero: direct-map headers, lines, and trial balance. Bind every header `source_id` to the registered snapshot source ID. Build one source manifest with full SHA, report period, counts, and debit/credit totals.
- Subledger: map `receivable_aging` and `payable_aging` only when the trial-balance row explicitly names that control subledger. Convert `not_applicable` to `None`. Apply AP sign using the linked chart-of-accounts `normal_balance`; do not mirror a trial-balance closing balance into a subledger.
- Raw core: emit the exact closed root with empty `journals`, `allowed_account_pairs`, `subsequent_disbursements`, `policy_changes`, `capitalization_items`, and `counterparties`. Set `close_timestamp` to the source `reporting_period.end` string unchanged; the existing parser accepts an ISO date, no time is invented, and the empty journal population guarantees the value is not used by a control calculation.
- Revenue: emit the exact closed root with report-period dates and empty `contracts`, `obligations`, `events`, `balances`, `contract_costs`, and `credit_risks`.
- Cashflow: emit the exact closed root with `as_of_date=reporting_period.end` and all 16 list populations empty.
- CA-02: group by entity/currency/period/project. `classified_direct_cost` is the sum of vendor cost amounts whose explicit `direct_flag` is true. `traceable_direct_cost` is the sum of `direct_costs.amount` joined through `source_table="vendor_costs"` and `source_row_id=vendor_cost_id`. Put vendor rows in `source_refs` and linked direct-cost rows in `counter_evidence_refs`.
- CA-04: `current_allocated_cost` is the sum of recorded allocation results. `causal_driver_allocated_cost` is `pool.source_amount × project driver quantity / total pool driver quantity`. Put allocation-result rows in `source_refs` and pool/driver rows in `counter_evidence_refs`.
- Every other CA input is `{"run_id": run_id, "revision": revision, "rows": []}`.
- Build the suite with `build_machine_draft_suite(release_id="accounting-suite-2026-07-17", effective_from=period_start, effective_to=period_end)`.

If any dependent required value for CA-02 or CA-04 is missing or null, omit the whole affected procedure row. Do not emit a partial row.

- [ ] **Step 7: Verify GREEN and adjacent regressions**

Run:

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.unit.accounting.test_input_adapter tests.unit.accounting.test_tier_zero tests.unit.accounting.test_core_population_adapter tests.unit.accounting.test_revenue_procedures tests.unit.accounting.test_cashflow_procedures tests.unit.accounting.test_project_cost_procedures tests.integration.test_accounting_dispatcher
```

Expected: PASS. The new request must dispatch 64 families and 30 result artifacts without raising a contract error.

- [ ] **Step 8: Commit Task 4**

```powershell
git add plugin/trusted-ceo-agent/trusted_ceo_agent/accounting/input_adapter.py tests/unit/accounting/test_input_adapter.py
git commit -m "feat: build snapshot-bound accounting requests"
```

### Task 5: Read-only `prepare-accounting-input` CLI

**Files:**

- Modify: `plugin/trusted-ceo-agent/trusted_ceo_agent/cli.py`
- Modify: `tests/plugin/test_cli_commands.py`
- Create: `tests/integration/test_cli_prepare_accounting_input.py`
- Modify: `tests/integration/test_cli_accounting_components.py`

- [ ] **Step 1: Freeze the parser contract**

Add:

```python
prepare_accounting = commands.add_parser("prepare-accounting-input")
_add_run(prepare_accounting)
prepare_accounting.add_argument("--revision", type=int, required=True)
prepare_accounting.add_argument("--source-id", required=True)
prepare_accounting.add_argument("--scope-ref", required=True)
prepare_accounting.add_argument("--output", type=Path, required=True)
```

The parser test must prove `--expected-revision` is not accepted and all four command-specific arguments are required.

- [ ] **Step 2: Write successful handoff and no-side-effect RED test**

Create an authorized fixture with `required_inputs=("accounting",)`, register the canonical test document as a source, and record before-state bytes:

```python
state_before = state_path.read_bytes()
snapshot_names_before = sorted(
    path.name for path in (artifacts / run_id / "snapshots").iterdir()
)
manifest_before = (
    store.verify_revision(revision) / "snapshot-manifest.json"
).read_bytes()
```

Call `prepare-accounting-input`. Assert:

- exit code 0;
- response revision remains the current revision;
- `target_revision` is current + 1;
- state bytes, snapshot names, and current manifest bytes are unchanged;
- output bytes are canonical and contain exactly the seven request keys;
- a subsequent existing `run-components --accounting-input` call publishes current + 1 with 64 family records and 30 result artifacts.

- [ ] **Step 3: Write failure/no-write RED tests**

Each failure must assert no output file and unchanged ArtifactStore state:

- stale `--revision` returns conflict exit 6;
- state other than `deep_dive_authorized` returns contract exit 3;
- wrong scope ref returns 3;
- approved scope without required input `accounting` returns 3;
- missing or duplicate source ID returns 3;
- non-permitted or non-primary source returns 3;
- source ID, snapshot ref, size, or hash mismatch returns integrity exit 4;
- pre-existing output returns 3 and preserves the original bytes;
- output under the artifact run or Plugin root returns 3;
- unsafe symlink/reparse parent returns 3.

- [ ] **Step 4: Verify RED**

Run:

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.plugin.test_cli_commands tests.integration.test_cli_prepare_accounting_input tests.integration.test_cli_accounting_components
```

Expected: parser and preparation tests FAIL because the command is absent.

- [ ] **Step 5: Implement validation before output creation**

Dispatch the command outside `_mutation`:

```python
if args.command == "prepare-accounting-input":
    return _prepare_accounting_input(args)
```

In `_prepare_accounting_input`, perform this exact order:

1. Open store and require `args.revision == current`.
2. `store.verify_revision(current)`.
3. Load snapshot files and require workflow state `deep_dive_authorized`.
4. Load and normalize `workflow/hitl-overlay.json` deep-dive scope.
5. Recompute `make_id("scope", normalized_scope)` and require exact scope-ref equality.
6. Require `"accounting"` in `normalized_scope["required_inputs"]`.
7. Load `sources/registry.json`; require exactly one matching source.
8. Validate it with `source.schema.json`; require `access_policy="permitted"` and `evidence_usage="primary"`.
9. Require source ID, `snapshot_ref`, `size_bytes`, and SHA to bind to the immutable blob.
10. Strict-load the blob, call `build_accounting_request` for `current + 1`, and canonicalize bytes.
11. Publish only the new external output.

Reuse `publish_web_report_output` for its existing safe-parent, no-clobber, reparse-point, and exclusive-publication behavior. Do not call ArtifactStore publish, RevisionManager commit, or an operational-once audit writer.

- [ ] **Step 6: Return a bounded response**

Return current revision and:

```python
{
    "source_id": args.source_id,
    "source_sha256": digest,
    "scope_ref": args.scope_ref,
    "target_revision": current + 1,
    "request_hash": hashlib.sha256(payload).hexdigest(),
}
```

Do not include raw rows or the request in stdout.

- [ ] **Step 7: Verify GREEN and publisher regressions**

Run:

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.plugin.test_cli_commands tests.integration.test_cli_prepare_accounting_input tests.integration.test_cli_accounting_components tests.integration.test_cli_web_report
```

Expected: PASS and no existing `run-components` behavior changes.

- [ ] **Step 8: Commit Task 5**

```powershell
git add plugin/trusted-ceo-agent/trusted_ceo_agent/cli.py tests/plugin/test_cli_commands.py tests/integration/test_cli_prepare_accounting_input.py tests/integration/test_cli_accounting_components.py
git commit -m "feat: prepare authorized accounting inputs"
```

### Task 6: Allowed synthetic integration and trust-boundary regression

**Files:**

- Modify: `tests/evaluation/test_synthetic_plugin_integration.py`
- Modify: `tests/integration/test_cli_scan.py`
- Modify: `tests/integration/test_cli_prepare_accounting_input.py`

- [ ] **Step 1: Add explicit allowed-input cases**

Use this literal and join each name directly to `evaluation/synthetic/analysis-input/`; never traverse its parent:

```python
_ALLOWED_SCENARIOS = (
    "boundary-adversarial",
    "boundary-degraded",
    "boundary-expert-trigger",
    "boundary-realistic-missing",
    "clean-baseline",
    "integrated-case",
    "single-ac-08-approved-control",
    "single-ac-08-manual-override",
    "single-ca-02-direct-cost-misclassification",
    "single-ca-04-driver-control",
    "single-cf-07-collection-deterioration",
    "single-cf-10-concentration-control",
    "single-rv-08-early-billing",
    "single-rv-13-sla-control",
)
```

For every file, assert:

- 33 tables and 360 raw records;
- structural Adapter success;
- deterministic request creation;
- fixed seven-key request;
- 64 dispatched issue families and 30 result artifacts;
- authority `machine_draft` and ceiling `Boundary`;
- incomplete boundary data becomes `not_assessable`, not a weak pass.

The test must also prove scenario name and path do not influence Adapter selection or suite release.

- [ ] **Step 2: Add anti-helper and anti-default assertions**

Use source inspection limited to the Plugin production package and assert it contains no import of:

```text
tools.synthetic_data
tests.evaluation
evaluation.synthetic
```

For the generated request, assert raw-core journal arrays are empty and no absent control field was synthesized. Assert RV and CF populations remain empty under current contracts. These are trust-boundary assertions, not expected scenario-answer assertions.

- [ ] **Step 3: Run focused evaluation tests**

Run:

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest tests.evaluation.test_synthetic_plugin_integration tests.integration.test_cli_scan tests.integration.test_cli_prepare_accounting_input
```

Expected: PASS for all explicitly allowed analysis-input scenarios.

- [ ] **Step 4: Commit Task 6**

```powershell
git add tests/evaluation/test_synthetic_plugin_integration.py tests/integration/test_cli_scan.py tests/integration/test_cli_prepare_accounting_input.py
git commit -m "test: cover multitable accounting plugin path"
```

### Task 7: Completion gates and Prompt 5 handoff

**Files:**

- Verify only; update the approved design or plan only if implementation evidence requires a factual correction.

- [ ] **Step 1: Inspect the final diff for forbidden changes**

Run:

```powershell
git diff --check
git diff --name-only 523aa35
git status --short
```

Expected: no whitespace errors; no modified file below source input, trust schemas, Pack registry, Validators, audit-log implementation, or immutable artifact output. Pre-existing unrelated dirty files remain untouched.

- [ ] **Step 2: Run contract checks**

```powershell
npm --prefix contracts/web-report run check
```

Expected: exit 0.

- [ ] **Step 3: Run the Python gate once**

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest discover -s tests -q
```

Expected: exit 0.

- [ ] **Step 4: Run WebReport-specific Python tests**

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest discover -s tests/unit/web_report -p "test_*.py" -q
```

Expected: exit 0.

- [ ] **Step 5: Run Web gates once**

```powershell
npm --prefix web run typecheck
npm --prefix web run lint
npm --prefix web run test
npm --prefix web run build
npm --prefix web run test:e2e
```

Expected: every command exits 0. If a gate changes source or configuration, rerun only the gates affected by that change.

- [ ] **Step 6: Record Adapter readiness**

The handoff must state:

```text
ADAPTER_READY
adapter_id: accounting-multitable-json
adapter_version: 1.0.0
suite_release: accounting-suite-2026-07-17
authority: machine_draft
authority_ceiling: Boundary
assessable_from_current_contract: AC-01..AC-05, CA-02, CA-04
explicitly_not_assessable_without_more_evidence: AC-06..AC-16, RV-01..RV-16, CF-01..CF-16, CA-01, CA-03, CA-05..CA-16
next_prompt: 5
final_target: analysis execution and Tab 2 validation
```

This record is a handoff/report, not a Pack promotion and not a revision mutation.

- [ ] **Step 7: Stop at the existing HITL boundary**

Prompt 5 may start the existing analysis workflow and may proceed to Diagnostic HITL. It must not call `prepare-accounting-input` until the approved deep-dive scope explicitly requires `accounting`; it must not call `run-components` until that authorization exists. Any later Final HITL and Validator remain unchanged.

- [ ] **Step 8: Keep rollback bounded to the Yellow implementation**

If rollback is required, revert the Task 6 through Task 1 commits in reverse order. Remove only the new Adapter, selector, builder, CLI command, and their tests; restore the three former selection call sites. Do not alter source snapshots, Source Registry entries, Evidence Core, HITL records, audit records, Pack revisions, Validators, or any published immutable revision.

## Expected implementation outcome

- One reusable Adapter remains registered for future inputs that satisfy the same schema/version; each new task still runs content-aware selection and does not force this Adapter onto unrelated JSON.
- Existing CSV, root-array JSON, XLSX, document intake, Evidence Lineage, and Tab 2 preview behavior remain intact.
- The nested accounting source is snapshot-bound and traceable to exact JSON pointers.
- The builder exposes only computations supported by source columns and closed procedure contracts.
- Dispatch completeness (64 families) is kept distinct from assessability; unsupported judgments produce explicit `not_assessable`.
- The next workflow after successful gates is Prompt 5, not a Pack or Component implementation prompt.
