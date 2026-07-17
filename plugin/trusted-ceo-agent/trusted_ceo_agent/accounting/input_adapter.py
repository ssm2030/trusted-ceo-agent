"""Build snapshot-bound accounting requests from multitable JSON inputs."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from typing import Any, cast

from trusted_ceo_agent.accounting.suite import build_machine_draft_suite
from trusted_ceo_agent.canonical import canonical_decimal
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.intake.adapters.accounting_json import (
    ACCOUNTING_TABLE_NAMES,
    validate_accounting_multitable_document,
)


_SUITE_RELEASE_ID = "accounting-suite-2026-07-17"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MONTH = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
_HALF_YEAR = re.compile(r"^\d{4}-H[12]$")
_PLAIN_DECIMAL = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$")
_MIN_CALCULATION_PRECISION = 28

_TABLE_FIELDS = {
    "allocation_drivers": {
        "driver_id",
        "driver_quantity",
        "driver_share",
        "entity",
        "period",
        "pool_id",
        "project_id",
    },
    "allocation_pools": {
        "account_id",
        "currency",
        "driver_type",
        "entity",
        "period",
        "pool_id",
        "pool_name",
        "source_amount",
    },
    "allocation_results": {
        "allocated_amount",
        "allocation_id",
        "currency",
        "driver_id",
        "entity",
        "journal_id",
        "period",
        "pool_id",
        "project_id",
    },
    "bank_accounts": {
        "account_id",
        "account_number_masked",
        "bank_account_id",
        "bank_name",
        "currency",
        "entity",
    },
    "bank_transactions": {
        "amount",
        "bank_account_id",
        "bank_transaction_id",
        "counterparty_id",
        "currency",
        "description",
        "direction",
        "entity",
        "journal_id",
        "transaction_date",
    },
    "budgets": {
        "budget_id",
        "cost_budget",
        "currency",
        "entity",
        "hours_budget",
        "period",
        "project_id",
        "revenue_budget",
    },
    "cash_receipts": {
        "amount",
        "bank_account_id",
        "currency",
        "customer_id",
        "entity",
        "invoice_id",
        "journal_id",
        "receipt_date",
        "receipt_id",
    },
    "chart_of_accounts": {
        "account_code",
        "account_id",
        "account_name",
        "account_type",
        "active",
        "currency",
        "entity",
        "normal_balance",
    },
    "contract_amendments": {
        "amendment_id",
        "amount_change",
        "approval_date",
        "approved_by",
        "contract_id",
        "currency",
        "entity",
        "scope_change",
    },
    "contracts": {
        "billing_method",
        "contract_id",
        "contract_value",
        "currency",
        "customer_id",
        "end_date",
        "entity",
        "project_id",
        "signed_date",
        "start_date",
        "status",
    },
    "credit_notes": {
        "amount",
        "credit_note_id",
        "currency",
        "entity",
        "invoice_id",
        "issue_date",
        "journal_id",
        "reason",
    },
    "customers": {
        "business_number",
        "country_code",
        "credit_terms_days",
        "customer_id",
        "customer_name",
        "entity",
        "industry",
    },
    "departments": {
        "cost_center",
        "department_id",
        "department_name",
        "entity",
    },
    "direct_costs": {
        "amount",
        "cost_date",
        "cost_type",
        "currency",
        "direct_cost_id",
        "entity",
        "project_id",
        "source_row_id",
        "source_table",
    },
    "employee_assignments": {
        "allocation_percent",
        "assignment_id",
        "employee_id",
        "end_date",
        "entity",
        "project_id",
        "start_date",
    },
    "employees": {
        "active",
        "currency",
        "department_id",
        "employee_id",
        "employee_name",
        "entity",
        "hire_date",
        "job_title",
        "monthly_salary",
    },
    "forecasts": {
        "as_of_date",
        "currency",
        "entity",
        "forecast_cash_in",
        "forecast_cash_out",
        "forecast_cost",
        "forecast_id",
        "forecast_revenue",
        "project_id",
    },
    "indirect_costs": {
        "amount",
        "cost_date",
        "currency",
        "description",
        "entity",
        "indirect_cost_id",
        "journal_id",
        "pool_id",
    },
    "invoices": {
        "amount",
        "contract_id",
        "currency",
        "customer_id",
        "due_date",
        "entity",
        "invoice_id",
        "issue_date",
        "journal_id",
        "milestone_id",
        "project_id",
        "status",
        "subtotal",
        "tax",
    },
    "journal_headers": {
        "approved_at",
        "approver_id",
        "counterparty_id",
        "creator_id",
        "creator_role",
        "currency",
        "description",
        "economic_event_date",
        "entered_at",
        "entity",
        "journal_id",
        "period",
        "posting_date",
        "project_id",
        "sequence",
        "source_id",
        "source_type",
        "status",
    },
    "journal_lines": {
        "account_id",
        "credit",
        "currency",
        "debit",
        "entity",
        "journal_id",
        "line_id",
        "line_number",
        "period",
        "project_id",
    },
    "management_kpis": {
        "dimension_id",
        "dimension_type",
        "entity",
        "kpi_id",
        "metric_name",
        "period",
        "unit",
        "value",
    },
    "milestones": {
        "billing_amount",
        "completion_date",
        "currency",
        "due_date",
        "entity",
        "milestone_id",
        "milestone_name",
        "obligation_id",
        "project_id",
        "status",
    },
    "payable_aging": {
        "aging_bucket",
        "ap_item_id",
        "as_of_date",
        "currency",
        "entity",
        "original_amount",
        "outstanding_amount",
        "vendor_cost_id",
        "vendor_id",
    },
    "payroll_costs": {
        "amount",
        "currency",
        "employee_id",
        "entity",
        "hours",
        "journal_id",
        "payroll_cost_id",
        "payroll_period",
        "project_id",
    },
    "performance_obligations": {
        "allocated_price",
        "contract_id",
        "currency",
        "end_date",
        "entity",
        "obligation_id",
        "obligation_name",
        "progress_percent",
        "project_id",
        "satisfaction_method",
        "start_date",
    },
    "projects": {
        "budget_amount",
        "currency",
        "customer_id",
        "department_id",
        "end_date",
        "entity",
        "fixed_price",
        "project_id",
        "project_manager_employee_id",
        "project_name",
        "start_date",
        "status",
    },
    "receivable_aging": {
        "aging_bucket",
        "ar_item_id",
        "as_of_date",
        "currency",
        "customer_id",
        "entity",
        "invoice_id",
        "original_amount",
        "outstanding_amount",
    },
    "trial_balance": {
        "account_id",
        "closing",
        "control_subledger",
        "credit_turnover",
        "currency",
        "debit_turnover",
        "entity",
        "opening",
        "period",
        "prior_closing",
        "trial_balance_id",
    },
    "vendor_costs": {
        "amount",
        "cost_date",
        "currency",
        "direct_flag",
        "entity",
        "invoice_reference",
        "journal_id",
        "project_id",
        "service_category",
        "vendor_cost_id",
        "vendor_id",
    },
    "vendor_payments": {
        "amount",
        "bank_account_id",
        "currency",
        "entity",
        "journal_id",
        "payment_date",
        "payment_id",
        "vendor_cost_id",
        "vendor_id",
    },
    "vendors": {
        "business_number",
        "country_code",
        "entity",
        "payment_terms_days",
        "service_category",
        "vendor_id",
        "vendor_name",
    },
    "work_logs": {
        "approved_by",
        "currency",
        "employee_id",
        "entity",
        "hourly_cost",
        "hours",
        "labor_cost",
        "project_id",
        "work_date",
        "work_log_id",
    },
}

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
        "forecast_revenue",
        "forecast_cost",
        "forecast_cash_in",
        "forecast_cash_out",
    },
    "management_kpis": {"value"},
    "journal_lines": {"debit", "credit"},
    "trial_balance": {
        "prior_closing",
        "opening",
        "debit_turnover",
        "credit_turnover",
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
_DATETIME_FIELDS = {"journal_headers": {"entered_at", "approved_at"}}
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
    "allocation_pools": (("account_id", "chart_of_accounts", "account_id"),),
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
    "trial_balance": (("account_id", "chart_of_accounts", "account_id"),),
}
_DIRECT_SOURCE_TABLES = {
    "payroll_costs",
    "vendor_costs",
    "work_logs",
    "allocation_results",
}
_CASHFLOW_POPULATIONS = (
    "bank_reconciliations",
    "cash_items",
    "cash_transactions",
    "financing_bridges",
    "supplier_finance_programs",
    "receivables",
    "payables",
    "profit_cash_bridges",
    "counterparty_exposures",
    "receivable_transfers",
    "covenants",
    "mandatory_payments",
    "period_end_events",
    "forecasts",
    "liquidity_positions",
)


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must be a non-empty string")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ContractError(f"{label} must be a non-negative integer")
    if isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise ContractError(f"{label} must be a non-negative integer")
        result = int(value)
    elif isinstance(value, int):
        result = value
    else:
        raise ContractError(f"{label} must be a non-negative integer")
    if result < 0:
        raise ContractError(f"{label} must be a non-negative integer")
    return result


def _decimal(value: Any, label: str) -> Decimal:
    if not isinstance(value, str):
        raise ContractError(f"{label} must be an exact decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ContractError(f"{label} must be a valid decimal string") from error
    if not result.is_finite():
        raise ContractError(f"{label} must be finite")
    if _PLAIN_DECIMAL.fullmatch(value) is None:
        raise ContractError(f"{label} must use plain decimal notation")
    return result


def _calculation_precision(document: object) -> int:
    """Size a deterministic context for exact sums and stable ratios."""
    if not isinstance(document, Mapping):
        return _MIN_CALCULATION_PRECISION
    tables = document.get("tables")
    if not isinstance(tables, Mapping):
        return _MIN_CALCULATION_PRECISION
    max_digits = 1
    value_count = 0
    for table_name, fields in _DECIMAL_FIELDS.items():
        rows = tables.get(table_name)
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            for field in fields:
                value = row.get(field)
                if not isinstance(value, str):
                    continue
                if _PLAIN_DECIMAL.fullmatch(value) is None:
                    continue
                max_digits = max(
                    max_digits,
                    sum(character.isdigit() for character in value),
                )
                value_count += 1
    carry_digits = len(str(max(value_count, 1)))
    return max(
        _MIN_CALCULATION_PRECISION,
        (2 * max_digits) + carry_digits + 16,
    )


def _date(value: Any, label: str) -> str:
    text = _text(value, label)
    try:
        date.fromisoformat(text)
    except ValueError as error:
        raise ContractError(f"{label} must be an ISO date") from error
    return text


def _timestamp(value: Any, label: str) -> str:
    text = _text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(f"{label} must be an ISO timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{label} timestamp must include a timezone")
    return text


def _period(table_name: str, value: Any, label: str) -> str:
    text = _text(value, label)
    half_year = table_name in {"management_kpis", "budgets"}
    pattern = _HALF_YEAR if half_year else _MONTH
    if pattern.fullmatch(text) is None:
        expected = "YYYY-H1 or YYYY-H2" if half_year else "YYYY-MM"
        raise ContractError(f"{label} period must be {expected}")
    return text


def _escape_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _source_ref(
    source_id: str,
    snapshot_sha256: str,
    table_name: str,
    row_index: int,
) -> str:
    return (
        f"{source_id}@{snapshot_sha256}"
        f"#/tables/{_escape_pointer(table_name)}/{row_index}"
    )


def _validate_runtime_binding(
    *,
    run_id: Any,
    revision: Any,
    scope_ref: Any,
    source_id: Any,
    snapshot_sha256: Any,
) -> tuple[str, int, str, str, str]:
    normalized_run_id = _text(run_id, "run_id")
    normalized_revision = _integer(revision, "revision")
    normalized_scope_ref = _text(scope_ref, "scope_ref")
    normalized_source_id = _text(source_id, "source_id")
    normalized_hash = _text(snapshot_sha256, "snapshot_sha256")
    if _SHA256.fullmatch(normalized_hash) is None:
        raise ContractError(
            "snapshot_sha256 must be a lowercase 64-character SHA-256"
        )
    expected_source_id = f"source_{normalized_hash[:24]}"
    if normalized_source_id != expected_source_id:
        raise ContractError(
            "source_id must equal source_{snapshot_sha256[:24]}"
        )
    return (
        normalized_run_id,
        normalized_revision,
        normalized_scope_ref,
        normalized_source_id,
        normalized_hash,
    )


def _validate_rows(
    document: Mapping[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    validated = validate_accounting_multitable_document(document)
    for field in (
        "company_id",
        "company_name",
        "currency",
        "entity",
        "generator_version",
        "scenario_id",
        "schema_version",
    ):
        _text(validated[field], field)
    _integer(validated["seed"], "seed")
    entity = cast(str, validated["entity"])
    currency = cast(str, validated["currency"])
    tables = cast(dict[str, list[dict[str, Any]]], validated["tables"])

    primary_indexes: dict[str, set[str]] = {}
    for table_name in ACCOUNTING_TABLE_NAMES:
        expected_fields = _TABLE_FIELDS[table_name]
        rows = tables[table_name]
        primary_key = _PRIMARY_KEYS[table_name]
        seen: set[str] = set()
        for row_index, row in enumerate(rows):
            actual_fields = set(row)
            if actual_fields != expected_fields:
                missing = sorted(expected_fields - actual_fields)
                unknown = sorted(actual_fields - expected_fields)
                raise ContractError(
                    f"{table_name}[{row_index}] field mismatch; "
                    f"missing={missing}; unknown={unknown}"
                )
            for field, value in row.items():
                label = f"{table_name}[{row_index}].{field}"
                if (table_name, field) in _NULLABLE_FIELDS and value is None:
                    continue
                if field in _DECIMAL_FIELDS.get(table_name, set()):
                    _decimal(value, label)
                elif field in _DATE_FIELDS.get(table_name, set()):
                    _date(value, label)
                elif field in _DATETIME_FIELDS.get(table_name, set()):
                    _timestamp(value, label)
                elif field in _PERIOD_FIELDS.get(table_name, set()):
                    _period(table_name, value, label)
                elif field in _INTEGER_FIELDS.get(table_name, set()):
                    _integer(value, label)
                elif field in _BOOLEAN_FIELDS.get(table_name, set()):
                    if not isinstance(value, bool):
                        raise ContractError(f"{label} must be boolean")
                else:
                    _text(value, label)
            if "entity" in row and row["entity"] != entity:
                raise ContractError(
                    f"{table_name}[{row_index}].entity differs from document entity"
                )
            if "currency" in row and row["currency"] != currency:
                raise ContractError(
                    f"{table_name}[{row_index}].currency differs from document currency"
                )
            key = cast(str, row[primary_key])
            if key in seen:
                raise ContractError(
                    f"{table_name} contains duplicate {primary_key}: {key}"
                )
            seen.add(key)
        primary_indexes[table_name] = seen

    trial_balance_dimensions: set[tuple[str, str, str, str]] = set()
    for row in tables["trial_balance"]:
        dimension = (
            cast(str, row["account_id"]),
            cast(str, row["entity"]),
            cast(str, row["currency"]),
            cast(str, row["period"]),
        )
        if dimension in trial_balance_dimensions:
            raise ContractError(
                "trial_balance contains duplicate account/entity/currency/period"
            )
        trial_balance_dimensions.add(dimension)

    for table_name, relationships in _FOREIGN_KEYS.items():
        for row_index, row in enumerate(tables[table_name]):
            for source_field, target_table, _target_field in relationships:
                value = row[source_field]
                if value is None:
                    continue
                if value not in primary_indexes[target_table]:
                    raise ContractError(
                        f"{table_name}[{row_index}].{source_field} "
                        f"foreign key not found in {target_table}"
                    )

    for row_index, row in enumerate(tables["direct_costs"]):
        source_table = row["source_table"]
        if source_table not in _DIRECT_SOURCE_TABLES:
            raise ContractError(
                f"direct_costs[{row_index}].source_table is unsupported"
            )
        if row["source_row_id"] not in primary_indexes[source_table]:
            raise ContractError(
                f"direct_costs[{row_index}].source_row_id "
                f"not found in {source_table}"
            )

    _validate_journals(tables)
    return tables


def _validate_journals(tables: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    lines_by_journal: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for line_index, line in enumerate(tables["journal_lines"]):
        debit = _decimal(line["debit"], f"journal_lines[{line_index}].debit")
        credit = _decimal(line["credit"], f"journal_lines[{line_index}].credit")
        if debit < 0 or credit < 0:
            raise ContractError("journal debit and credit must be non-negative")
        if debit > 0 and credit > 0:
            raise ContractError(
                f"journal line {line['line_id']} has both debit and credit positive"
            )
        lines_by_journal[cast(str, line["journal_id"])].append(line)

    for header in tables["journal_headers"]:
        journal_id = cast(str, header["journal_id"])
        lines = lines_by_journal[journal_id]
        if len(lines) < 2:
            raise ContractError(
                f"journal {journal_id} must contain at least two lines"
            )
        debit_total = sum(
            (_decimal(line["debit"], f"{journal_id}.debit") for line in lines),
            Decimal(0),
        )
        credit_total = sum(
            (_decimal(line["credit"], f"{journal_id}.credit") for line in lines),
            Decimal(0),
        )
        if debit_total != credit_total:
            raise ContractError(f"journal {journal_id} balance mismatch")


def _tier_zero_input(
    document: Mapping[str, Any],
    tables: Mapping[str, list[dict[str, Any]]],
    *,
    run_id: str,
    revision: int,
    source_id: str,
    snapshot_sha256: str,
) -> dict[str, Any]:
    period = cast(Mapping[str, str], document["reporting_period"])
    headers = [
        {
            "journal_id": row["journal_id"],
            "source_id": source_id,
            "sequence": _integer(row["sequence"], "journal sequence"),
            "status": row["status"],
            "entity": row["entity"],
            "currency": row["currency"],
            "period": row["period"],
        }
        for row in tables["journal_headers"]
    ]
    lines = [
        {
            "line_id": row["line_id"],
            "journal_id": row["journal_id"],
            "account_id": row["account_id"],
            "debit": row["debit"],
            "credit": row["credit"],
            "entity": row["entity"],
            "currency": row["currency"],
            "period": row["period"],
        }
        for row in tables["journal_lines"]
    ]
    debit_total = sum(
        (_decimal(row["debit"], "journal debit") for row in tables["journal_lines"]),
        Decimal(0),
    )
    credit_total = sum(
        (_decimal(row["credit"], "journal credit") for row in tables["journal_lines"]),
        Decimal(0),
    )
    trial_balance = [
        {
            "account_id": row["account_id"],
            "entity": row["entity"],
            "currency": row["currency"],
            "period": row["period"],
            "prior_closing": row["prior_closing"],
            "opening": row["opening"],
            "debit_turnover": row["debit_turnover"],
            "credit_turnover": row["credit_turnover"],
            "closing": row["closing"],
            "control_subledger": (
                None
                if row["control_subledger"] == "not_applicable"
                else row["control_subledger"]
            ),
        }
        for row in tables["trial_balance"]
    ]
    subledgers = _subledger_balances(tables)
    return {
        "run_id": run_id,
        "revision": revision,
        "source_manifests": [
            {
                "source_id": source_id,
                "source_sha256": snapshot_sha256,
                "period_start": period["start"],
                "period_end": period["end"],
                "header_count": len(headers),
                "line_count": len(lines),
                "debit_total": canonical_decimal(debit_total),
                "credit_total": canonical_decimal(credit_total),
            }
        ],
        "journal_headers": sorted(headers, key=lambda item: item["journal_id"]),
        "journal_lines": sorted(
            lines,
            key=lambda item: (item["journal_id"], item["line_id"]),
        ),
        "trial_balance": sorted(
            trial_balance,
            key=lambda item: (
                item["entity"],
                item["currency"],
                item["period"],
                item["account_id"],
            ),
        ),
        "subledger_balances": subledgers,
    }


def _subledger_balances(
    tables: Mapping[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    accounts = {
        row["account_id"]: row for row in tables["chart_of_accounts"]
    }
    trial_balance = tables["trial_balance"]
    result: list[dict[str, Any]] = []
    specifications = (
        (
            "receivable_aging",
            "ar_item_id",
            "receivable_aging",
        ),
        (
            "payable_aging",
            "ap_item_id",
            "payable_aging",
        ),
    )
    for table_name, object_field, control_name in specifications:
        for row in tables[table_name]:
            period = cast(str, row["as_of_date"])[:7]
            matches = [
                item
                for item in trial_balance
                if item["control_subledger"] == control_name
                and item["entity"] == row["entity"]
                and item["currency"] == row["currency"]
                and item["period"] == period
            ]
            if len(matches) != 1:
                raise ContractError(
                    f"{table_name} row requires exactly one "
                    "trial balance control account"
                )
            account_id = cast(str, matches[0]["account_id"])
            amount = _decimal(
                row["outstanding_amount"],
                f"{table_name}.outstanding_amount",
            )
            normal_balance = accounts[account_id]["normal_balance"]
            if normal_balance == "credit":
                amount = -amount
            elif normal_balance != "debit":
                raise ContractError(
                    f"unsupported normal_balance for {account_id}"
                )
            result.append(
                {
                    "subledger": control_name,
                    "account_id": account_id,
                    "object_id": row[object_field],
                    "entity": row["entity"],
                    "currency": row["currency"],
                    "period": period,
                    "amount": canonical_decimal(amount),
                }
            )
    return sorted(
        result,
        key=lambda item: (
            item["entity"],
            item["currency"],
            item["period"],
            item["subledger"],
            item["account_id"],
            item["object_id"],
        ),
    )


def _empty_raw_core(
    *,
    run_id: str,
    revision: int,
    period_end: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "revision": revision,
        "close_timestamp": period_end,
        "journals": [],
        "allowed_account_pairs": [],
        "subsequent_disbursements": [],
        "policy_changes": [],
        "capitalization_items": [],
        "counterparties": [],
    }


def _empty_revenue(
    *,
    run_id: str,
    revision: int,
    period_start: str,
    period_end: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "revision": revision,
        "period_start": period_start,
        "period_end": period_end,
        "contracts": [],
        "obligations": [],
        "events": [],
        "balances": [],
        "contract_costs": [],
        "credit_risks": [],
    }


def _empty_cashflow(
    *,
    run_id: str,
    revision: int,
    period_end: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "revision": revision,
        "as_of_date": period_end,
        **{name: [] for name in _CASHFLOW_POPULATIONS},
    }


def _ca02_rows(
    tables: Mapping[str, list[dict[str, Any]]],
    *,
    source_id: str,
    snapshot_sha256: str,
) -> list[dict[str, Any]]:
    vendor_by_id = {
        row["vendor_cost_id"]: (index, row)
        for index, row in enumerate(tables["vendor_costs"])
    }
    groups: dict[
        tuple[str, str, str, str],
        dict[str, list[tuple[int, dict[str, Any]]]],
    ] = {}
    for vendor_index, vendor in enumerate(tables["vendor_costs"]):
        period = cast(str, vendor["cost_date"])[:7]
        key = (
            cast(str, vendor["entity"]),
            cast(str, vendor["currency"]),
            period,
            cast(str, vendor["project_id"]),
        )
        group = groups.setdefault(key, {"vendors": [], "directs": []})
        group["vendors"].append((vendor_index, vendor))

    for direct_index, direct in enumerate(tables["direct_costs"]):
        if direct["source_table"] != "vendor_costs":
            continue
        _vendor_index, vendor = vendor_by_id[direct["source_row_id"]]
        if any(
            direct[field] != vendor[field]
            for field in ("entity", "currency", "project_id")
        ):
            raise ContractError(
                "linked direct_costs and vendor_costs dimensions differ"
            )
        vendor_period = cast(str, vendor["cost_date"])[:7]
        direct_period = cast(str, direct["cost_date"])[:7]
        if direct_period != vendor_period:
            raise ContractError(
                "linked direct_costs and vendor_costs periods differ"
            )
        key = (
            cast(str, vendor["entity"]),
            cast(str, vendor["currency"]),
            vendor_period,
            cast(str, vendor["project_id"]),
        )
        groups[key]["directs"].append((direct_index, direct))

    result = []
    for (entity, currency, period, project_id), group in sorted(groups.items()):
        vendors = group["vendors"]
        directs = group["directs"]
        if not directs:
            continue
        classified = sum(
            (
                _decimal(row["amount"], "vendor cost amount")
                for _index, row in vendors
                if row["direct_flag"] is True
            ),
            Decimal(0),
        )
        traceable = sum(
            (
                _decimal(row["amount"], "direct cost amount")
                for _index, row in directs
            ),
            Decimal(0),
        )
        result.append(
            {
                "row_id": (
                    f"CA-02:{entity}:{currency}:{period}:{project_id}"
                ),
                "entity": entity,
                "currency": currency,
                "period": period,
                "project_id": project_id,
                "metrics": {
                    "classified_direct_cost": canonical_decimal(classified),
                    "traceable_direct_cost": canonical_decimal(traceable),
                },
                "source_refs": sorted(
                    _source_ref(
                        source_id,
                        snapshot_sha256,
                        "vendor_costs",
                        index,
                    )
                    for index, _row in vendors
                ),
                "counter_evidence_refs": sorted(
                    _source_ref(
                        source_id,
                        snapshot_sha256,
                        "direct_costs",
                        index,
                    )
                    for index, _row in directs
                ),
            }
        )
    return result


def _ca04_rows(
    tables: Mapping[str, list[dict[str, Any]]],
    *,
    source_id: str,
    snapshot_sha256: str,
) -> list[dict[str, Any]]:
    pools = {
        row["pool_id"]: (index, row)
        for index, row in enumerate(tables["allocation_pools"])
    }
    drivers_by_pool: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, row in enumerate(tables["allocation_drivers"]):
        drivers_by_pool[cast(str, row["pool_id"])].append((index, row))
    results_by_scope: dict[
        tuple[str, str],
        list[tuple[int, dict[str, Any]]],
    ] = defaultdict(list)
    driver_by_id = {
        row["driver_id"]: row for row in tables["allocation_drivers"]
    }
    for index, row in enumerate(tables["allocation_results"]):
        driver = driver_by_id[row["driver_id"]]
        if (
            driver["pool_id"] != row["pool_id"]
            or driver["project_id"] != row["project_id"]
        ):
            raise ContractError(
                "allocation result driver differs from its pool/project"
            )
        results_by_scope[
            (cast(str, row["pool_id"]), cast(str, row["project_id"]))
        ].append((index, row))

    result = []
    for (pool_id, project_id), allocation_rows in sorted(
        results_by_scope.items()
    ):
        pool_index, pool = pools[pool_id]
        pool_drivers = drivers_by_pool[pool_id]
        project_drivers = [
            item for item in pool_drivers if item[1]["project_id"] == project_id
        ]
        if not project_drivers:
            continue
        dimensions = ("entity", "period")
        if any(
            row[field] != pool[field]
            for _index, row in (*allocation_rows, *pool_drivers)
            for field in dimensions
        ):
            raise ContractError("allocation pool, driver, and result dimensions differ")
        if any(
            row["currency"] != pool["currency"]
            for _index, row in allocation_rows
        ):
            raise ContractError("allocation pool and result currency differ")
        total_quantity = sum(
            (
                _decimal(row["driver_quantity"], "driver quantity")
                for _index, row in pool_drivers
            ),
            Decimal(0),
        )
        project_quantity = sum(
            (
                _decimal(row["driver_quantity"], "driver quantity")
                for _index, row in project_drivers
            ),
            Decimal(0),
        )
        if total_quantity <= 0 or project_quantity < 0:
            continue
        current = sum(
            (
                _decimal(row["allocated_amount"], "allocated amount")
                for _index, row in allocation_rows
            ),
            Decimal(0),
        )
        causal = (
            _decimal(pool["source_amount"], "pool source amount")
            * project_quantity
            / total_quantity
        )
        entity = cast(str, pool["entity"])
        currency = cast(str, pool["currency"])
        period = cast(str, pool["period"])
        result.append(
            {
                "row_id": (
                    f"CA-04:{entity}:{currency}:{period}:{project_id}:{pool_id}"
                ),
                "entity": entity,
                "currency": currency,
                "period": period,
                "project_id": project_id,
                "metrics": {
                    "current_allocated_cost": canonical_decimal(current),
                    "causal_driver_allocated_cost": canonical_decimal(causal),
                },
                "source_refs": sorted(
                    _source_ref(
                        source_id,
                        snapshot_sha256,
                        "allocation_results",
                        index,
                    )
                    for index, _row in allocation_rows
                ),
                "counter_evidence_refs": sorted(
                    {
                        _source_ref(
                            source_id,
                            snapshot_sha256,
                            "allocation_pools",
                            pool_index,
                        ),
                        *(
                            _source_ref(
                                source_id,
                                snapshot_sha256,
                                "allocation_drivers",
                                index,
                            )
                            for index, _row in pool_drivers
                        ),
                    }
                ),
            }
        )
    return result


def _project_cost_inputs(
    tables: Mapping[str, list[dict[str, Any]]],
    *,
    run_id: str,
    revision: int,
    source_id: str,
    snapshot_sha256: str,
) -> dict[str, dict[str, Any]]:
    result = {
        f"CA-{number:02d}": {
            "run_id": run_id,
            "revision": revision,
            "rows": [],
        }
        for number in range(1, 17)
    }
    result["CA-02"]["rows"] = _ca02_rows(
        tables,
        source_id=source_id,
        snapshot_sha256=snapshot_sha256,
    )
    result["CA-04"]["rows"] = _ca04_rows(
        tables,
        source_id=source_id,
        snapshot_sha256=snapshot_sha256,
    )
    return result


def _build_accounting_request_in_context(
    document: Mapping[str, Any],
    *,
    run_id: str,
    revision: int,
    scope_ref: str,
    source_id: str,
    snapshot_sha256: str,
) -> dict[str, Any]:
    """Validate one immutable source and build the closed seven-field request."""
    (
        normalized_run_id,
        normalized_revision,
        normalized_scope_ref,
        normalized_source_id,
        normalized_hash,
    ) = _validate_runtime_binding(
        run_id=run_id,
        revision=revision,
        scope_ref=scope_ref,
        source_id=source_id,
        snapshot_sha256=snapshot_sha256,
    )
    tables = _validate_rows(document)
    period = cast(Mapping[str, str], document["reporting_period"])
    tier_zero = _tier_zero_input(
        document,
        tables,
        run_id=normalized_run_id,
        revision=normalized_revision,
        source_id=normalized_source_id,
        snapshot_sha256=normalized_hash,
    )
    return {
        "scope_ref": normalized_scope_ref,
        "suite": build_machine_draft_suite(
            release_id=_SUITE_RELEASE_ID,
            effective_from=period["start"],
            effective_to=period["end"],
        ),
        "tier_zero_input": tier_zero,
        "raw_core_population": _empty_raw_core(
            run_id=normalized_run_id,
            revision=normalized_revision,
            period_end=period["end"],
        ),
        "revenue_input": _empty_revenue(
            run_id=normalized_run_id,
            revision=normalized_revision,
            period_start=period["start"],
            period_end=period["end"],
        ),
        "cashflow_input": _empty_cashflow(
            run_id=normalized_run_id,
            revision=normalized_revision,
            period_end=period["end"],
        ),
        "project_cost_inputs": _project_cost_inputs(
            tables,
            run_id=normalized_run_id,
            revision=normalized_revision,
            source_id=normalized_source_id,
            snapshot_sha256=normalized_hash,
        ),
    }


def build_accounting_request(
    document: Mapping[str, Any],
    *,
    run_id: str,
    revision: int,
    scope_ref: str,
    source_id: str,
    snapshot_sha256: str,
) -> dict[str, Any]:
    """Build deterministically without inheriting process Decimal context."""
    with localcontext() as context:
        context.prec = _calculation_precision(document)
        context.rounding = ROUND_HALF_EVEN
        return _build_accounting_request_in_context(
            document,
            run_id=run_id,
            revision=revision,
            scope_ref=scope_ref,
            source_id=source_id,
            snapshot_sha256=snapshot_sha256,
        )


__all__ = ["build_accounting_request"]
