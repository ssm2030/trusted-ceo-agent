from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from trusted_ceo_agent.accounting.input_contracts import (
    _BOOLEAN_FIELDS,
    _DATE_FIELDS,
    _DATETIME_FIELDS,
    _DECIMAL_FIELDS,
    _DIRECT_SOURCE_TABLES,
    _FOREIGN_KEYS,
    _HALF_YEAR,
    _INTEGER_FIELDS,
    _MIN_CALCULATION_PRECISION,
    _MONTH,
    _NULLABLE_FIELDS,
    _PERIOD_FIELDS,
    _PLAIN_DECIMAL,
    _PRIMARY_KEYS,
    _SHA256,
    _TABLE_FIELDS,
)
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.intake.adapters.accounting_json import (
    ACCOUNTING_TABLE_NAMES,
    validate_accounting_multitable_document,
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
calculation_precision = _calculation_precision
decimal_value = _decimal
integer_value = _integer
source_ref = _source_ref
text_value = _text
validate_rows = _validate_rows
validate_runtime_binding = _validate_runtime_binding
