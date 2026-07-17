from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, cast

from trusted_ceo_agent.canonical import strict_loads
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.intake.models import ParsedDataset, ParsedRecord


ACCOUNTING_MULTITABLE_ADAPTER_ID = 'accounting-multitable-json'
ACCOUNTING_MULTITABLE_ADAPTER_VERSION = '1.0.0'
ACCOUNTING_MULTITABLE_SCHEMA_VERSION = '1.0.0'

ACCOUNTING_TABLE_NAMES = (
    'allocation_drivers', 'allocation_pools', 'allocation_results',
    'bank_accounts', 'bank_transactions', 'budgets', 'cash_receipts',
    'chart_of_accounts', 'contract_amendments', 'contracts', 'credit_notes',
    'customers', 'departments', 'direct_costs', 'employee_assignments',
    'employees', 'forecasts', 'indirect_costs', 'invoices',
    'journal_headers', 'journal_lines', 'management_kpis', 'milestones',
    'payable_aging', 'payroll_costs', 'performance_obligations', 'projects',
    'receivable_aging', 'trial_balance', 'vendor_costs', 'vendor_payments',
    'vendors', 'work_logs',
)

_TOP_LEVEL_KEYS = (
    'company_id',
    'company_name',
    'currency',
    'entity',
    'generator_version',
    'reporting_period',
    'scenario_id',
    'schema_version',
    'seed',
    'tables',
)
_REPORTING_PERIOD_KEYS = frozenset({'start', 'end'})


def _escape_pointer(value: str) -> str:
    return value.replace('~', '~0').replace('/', '~1')


def _key_set_description(expected: set[str], actual: set[str]) -> str:
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    return f'missing={missing}, unexpected={unexpected}'


def is_accounting_multitable_candidate(document: object) -> bool:
    return isinstance(document, dict) and 'tables' in document


def validate_accounting_multitable_document(
    document: object,
) -> dict[str, object]:
    if not isinstance(document, dict) or not all(
        isinstance(key, str) for key in document
    ):
        raise ContractError('accounting document top-level must be an object')

    expected_top_level = set(_TOP_LEVEL_KEYS)
    actual_top_level = set(document)
    if actual_top_level != expected_top_level:
        detail = _key_set_description(expected_top_level, actual_top_level)
        raise ContractError(
            f'accounting document top-level key set mismatch: {detail}'
        )

    if document['schema_version'] != ACCOUNTING_MULTITABLE_SCHEMA_VERSION:
        raise ContractError(
            'accounting schema_version must be '
            f'{ACCOUNTING_MULTITABLE_SCHEMA_VERSION}'
        )

    reporting_period = document['reporting_period']
    if not isinstance(reporting_period, dict) or not all(
        isinstance(key, str) for key in reporting_period
    ):
        raise ContractError('reporting period must be an object')
    actual_period_keys = set(reporting_period)
    if actual_period_keys != _REPORTING_PERIOD_KEYS:
        detail = _key_set_description(
            set(_REPORTING_PERIOD_KEYS),
            actual_period_keys,
        )
        raise ContractError(f'reporting period key set mismatch: {detail}')
    start_value = reporting_period['start']
    end_value = reporting_period['end']
    if not isinstance(start_value, str) or not isinstance(end_value, str):
        raise ContractError('reporting period start and end must be ISO dates')
    try:
        start_date = date.fromisoformat(start_value)
        end_date = date.fromisoformat(end_value)
    except ValueError as error:
        raise ContractError(
            f'reporting period start and end must be ISO dates: {error}'
        ) from error
    if start_date > end_date:
        raise ContractError('reporting period start must not follow end')

    tables = document['tables']
    if not isinstance(tables, dict) or not all(
        isinstance(key, str) for key in tables
    ):
        raise ContractError('accounting table set must be an object')
    expected_tables = set(ACCOUNTING_TABLE_NAMES)
    actual_tables = set(tables)
    if actual_tables != expected_tables:
        detail = _key_set_description(expected_tables, actual_tables)
        raise ContractError(f'accounting table set mismatch: {detail}')
    for table_name in ACCOUNTING_TABLE_NAMES:
        rows = tables[table_name]
        if not isinstance(rows, list):
            raise ContractError(f'{table_name} table must be an array')
        for row_index, row in enumerate(rows):
            if not isinstance(row, dict) or not all(
                isinstance(key, str) for key in row
            ):
                raise ContractError(
                    f'{table_name} row {row_index} must be an object '
                    'with string keys'
                )

    return cast(dict[str, object], document)


def load_accounting_multitable_document(path: Path) -> dict[str, object]:
    try:
        document = strict_loads(path.read_bytes())
    except (OSError, UnicodeError, ValueError) as error:
        raise ContractError(f'invalid strict JSON input: {error}') from error
    return validate_accounting_multitable_document(document)


class AccountingMultitableJsonAdapter:
    def parse(self, path: Path, source_id: str) -> ParsedDataset:
        document = load_accounting_multitable_document(path)
        tables = cast(dict[str, list[dict[str, Any]]], document['tables'])
        records: list[ParsedRecord] = []
        all_fields: set[str] = set()
        logical_index = 0
        table_row_counts: dict[str, int] = {}

        for table_name in ACCOUNTING_TABLE_NAMES:
            rows = tables[table_name]
            table_row_counts[table_name] = len(rows)
            for row_index, row in enumerate(rows):
                logical_index += 1
                values = {
                    f'{table_name}.{raw_field}': raw_value
                    for raw_field, raw_value in row.items()
                }
                all_fields.update(values)
                records.append(ParsedRecord(
                    logical_index=logical_index,
                    locator_type='json_pointer',
                    locator={
                        'pointer': (
                            f'/tables/{_escape_pointer(table_name)}/{row_index}'
                        ),
                    },
                    values=values,
                ))

        metadata = {
            'adapter_id': ACCOUNTING_MULTITABLE_ADAPTER_ID,
            'adapter_version': ACCOUNTING_MULTITABLE_ADAPTER_VERSION,
            'input_schema_version': document['schema_version'],
            **{
                key: document[key]
                for key in _TOP_LEVEL_KEYS
                if key != 'tables'
            },
            'table_row_counts': table_row_counts,
        }
        return ParsedDataset(
            source_id=source_id,
            media_type='application/json',
            fields=tuple(sorted(all_fields)),
            records=tuple(records),
            metadata=metadata,
        )
