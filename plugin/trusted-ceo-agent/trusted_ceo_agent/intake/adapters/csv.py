from __future__ import annotations

import csv
import io
from pathlib import Path

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.intake.models import ParsedDataset, ParsedRecord


class CsvAdapter:
    def __init__(self, *, encoding: str | None = None) -> None:
        if encoding not in (None, "utf-8", "utf-8-sig", "cp949"):
            raise ContractError(f"unsupported CSV encoding: {encoding}")
        self.encoding = encoding

    def _decode(self, payload: bytes) -> tuple[str, str]:
        requested = self.encoding
        candidates = [requested] if requested else (["utf-8-sig"] if payload.startswith(b"\xef\xbb\xbf") else ["utf-8"])
        for encoding in candidates:
            try:
                return payload.decode(encoding, errors="strict"), encoding
            except UnicodeDecodeError:
                continue
        raise ContractError("CSV is not UTF-8; CP949 must be selected explicitly")

    def parse(self, path: Path, source_id: str) -> ParsedDataset:
        try:
            text, encoding = self._decode(path.read_bytes())
        except OSError as error:
            raise ContractError(f"cannot read CSV: {path.name}") from error
        reader = csv.DictReader(io.StringIO(text, newline=""))
        fields = tuple(reader.fieldnames or ())
        if not fields or any(not field for field in fields) or len(fields) != len(set(fields)):
            raise ContractError("CSV requires unique non-empty headers")
        records: list[ParsedRecord] = []
        for logical_index, row in enumerate(reader, start=1):
            if None in row:
                raise ContractError(f"CSV record {logical_index} has extra fields")
            values = {
                field: (row.get(field, "") or "").replace("\r\n", "\n").replace("\r", "\n")
                for field in fields
            }
            records.append(ParsedRecord(logical_index, "csv_records", {"record_indices": [logical_index]}, values))
        return ParsedDataset(source_id, "text/csv", fields, tuple(records), {"encoding": encoding})
