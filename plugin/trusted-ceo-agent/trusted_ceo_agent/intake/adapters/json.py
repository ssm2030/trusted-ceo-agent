from __future__ import annotations

from pathlib import Path
from typing import Any

from trusted_ceo_agent.canonical import strict_loads
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.intake.models import ParsedDataset, ParsedRecord


def _escape_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _resolve_pointer(value: Any, pointer: str) -> Any:
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise ContractError("JSON record pointer must be RFC 6901")
    current = value
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        try:
            current = current[int(token)] if isinstance(current, list) else current[token]
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise ContractError(f"JSON pointer does not resolve: {pointer}") from error
    return current


class JsonAdapter:
    def __init__(self, *, records_pointer: str = "") -> None:
        self.records_pointer = records_pointer

    def parse(self, path: Path, source_id: str) -> ParsedDataset:
        try:
            document = strict_loads(path.read_bytes())
        except (OSError, UnicodeError, ValueError) as error:
            raise ContractError(f"invalid strict JSON input: {error}") from error
        rows = _resolve_pointer(document, self.records_pointer)
        if not isinstance(rows, list):
            raise ContractError("JSON record pointer must select an array")
        records: list[ParsedRecord] = []
        all_fields: set[str] = set()
        prefix = self.records_pointer
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or not all(isinstance(key, str) for key in row):
                raise ContractError(f"JSON record {index} must be an object")
            values = dict(row)
            all_fields.update(values)
            pointer = f"{prefix}/{index}" if prefix else f"/{index}"
            records.append(ParsedRecord(index + 1, "json_pointer", {"pointer": pointer}, values))
        return ParsedDataset(source_id, "application/json", tuple(sorted(all_fields)), tuple(records), {"records_pointer": prefix})

