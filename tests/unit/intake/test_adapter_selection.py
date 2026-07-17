from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests.support_accounting_multitable import (
    valid_accounting_multitable_document,
)
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.intake.adapters.accounting_json import (
    AccountingMultitableJsonAdapter,
)
from trusted_ceo_agent.intake.adapters.csv import CsvAdapter
from trusted_ceo_agent.intake.adapters.json import JsonAdapter
from trusted_ceo_agent.intake.adapters.selection import select_adapter
from trusted_ceo_agent.intake.adapters.xlsx import XlsxAdapter


class AdapterSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def write_bytes(self, payload: bytes) -> Path:
        path = self.root / "immutable-blob"
        path.write_bytes(payload)
        return path

    def write_json(self, document: Any) -> Path:
        return self.write_bytes(canonical_bytes(document))

    def test_selects_csv_by_display_name(self) -> None:
        adapter = select_adapter("ledger.CSV", self.write_bytes(b"not inspected"))

        self.assertIs(type(adapter), CsvAdapter)

    def test_selects_xlsx_by_display_name(self) -> None:
        adapter = select_adapter("ledger.XLSX", self.write_bytes(b"not inspected"))

        self.assertIs(type(adapter), XlsxAdapter)

    def test_selects_root_array_json(self) -> None:
        adapter = select_adapter(
            "records.json",
            self.write_json([{"period": "2026-01", "amount": "10.00"}]),
        )

        self.assertIs(type(adapter), JsonAdapter)

    def test_selects_valid_accounting_multitable_json(self) -> None:
        adapter = select_adapter(
            "dataset.json",
            self.write_json(valid_accounting_multitable_document()),
        )

        self.assertIs(type(adapter), AccountingMultitableJsonAdapter)

    def test_invalid_accounting_candidate_never_falls_back(self) -> None:
        document = valid_accounting_multitable_document()
        document["schema_version"] = "2.0.0"

        with self.assertRaisesRegex(ContractError, "schema_version"):
            select_adapter("dataset.json", self.write_json(document))

    def test_rejects_unrelated_root_object_json(self) -> None:
        with self.assertRaisesRegex(
            ContractError,
            "root must be an array or accounting multitable object",
        ):
            select_adapter("records.json", self.write_json({"records": []}))

    def test_json_selection_uses_strict_decoder(self) -> None:
        for payload, message in (
            (b'{"tables":{},"tables":{}}', "duplicate JSON key"),
            (b'[{"amount":NaN}]', "non-finite JSON number"),
            (b"\xff", "invalid strict JSON input"),
        ):
            with self.subTest(payload=payload), self.assertRaisesRegex(
                ContractError,
                message,
            ):
                select_adapter("dataset.json", self.write_bytes(payload))

    def test_rejects_unsupported_or_missing_suffix(self) -> None:
        for display_name, suffix in (
            ("dataset.parquet", ".parquet"),
            ("dataset", "<none>"),
        ):
            with self.subTest(display_name=display_name), self.assertRaisesRegex(
                ContractError,
                f"unsupported input format: {suffix}",
            ):
                select_adapter(display_name, self.write_bytes(b"not inspected"))


if __name__ == "__main__":
    unittest.main()
