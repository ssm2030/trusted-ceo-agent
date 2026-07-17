from __future__ import annotations

from pathlib import Path

from trusted_ceo_agent.canonical import strict_loads
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.intake.adapters.accounting_json import (
    AccountingMultitableJsonAdapter,
    is_accounting_multitable_candidate,
    validate_accounting_multitable_document,
)
from trusted_ceo_agent.intake.adapters.csv import CsvAdapter
from trusted_ceo_agent.intake.adapters.json import JsonAdapter
from trusted_ceo_agent.intake.adapters.xlsx import XlsxAdapter

Adapter = (
    CsvAdapter | JsonAdapter | XlsxAdapter | AccountingMultitableJsonAdapter
)


def select_adapter(
    display_name: str,
    immutable_blob: Path,
) -> Adapter:
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
