from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests.support_accounting_multitable import (
    ACCOUNTING_TABLE_NAMES,
    valid_accounting_multitable_document,
)
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.intake.adapters.accounting_json import (
    AccountingMultitableJsonAdapter,
    is_accounting_multitable_candidate,
)


class AccountingMultitableJsonAdapterTests(unittest.TestCase):
    def parse(self, document: dict[str, Any]):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_bytes(canonical_bytes(document))
            return AccountingMultitableJsonAdapter().parse(path, "source_" + "a" * 24)

    def test_candidate_recognition_is_narrow(self) -> None:
        self.assertTrue(
            is_accounting_multitable_candidate(
                valid_accounting_multitable_document()
            )
        )
        self.assertTrue(is_accounting_multitable_candidate({"tables": None}))
        self.assertFalse(is_accounting_multitable_candidate([]))
        self.assertFalse(is_accounting_multitable_candidate({"rows": []}))

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
        account = next(
            value for value in values if "chart_of_accounts.account_id" in value
        )
        customer = next(value for value in values if "customers.customer_id" in value)
        payable = next(
            value for value in values
            if "trial_balance.trial_balance_id" in value
            and value["trial_balance.trial_balance_id"] == "TB-AP"
        )
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

    def test_rejects_non_object_table_row(self) -> None:
        document = valid_accounting_multitable_document()
        document["tables"]["work_logs"] = ["not-an-object"]
        with self.assertRaisesRegex(ContractError, "work_logs.*row 0.*object"):
            self.parse(document)

    def test_rejects_inverted_reporting_period(self) -> None:
        document = valid_accounting_multitable_document()
        document["reporting_period"] = {
            "start": "2026-07-01",
            "end": "2026-06-30",
        }
        with self.assertRaisesRegex(ContractError, "reporting period"):
            self.parse(document)

    def test_rejects_duplicate_raw_json_keys(self) -> None:
        duplicate_document = canonical_bytes(
            valid_accounting_multitable_document()
        ).decode("utf-8").replace(
            '"company_id":"COMP1",',
            '"company_id":"COMP1","company_id":"COMP2",',
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_bytes(duplicate_document.encode("utf-8"))
            with self.assertRaisesRegex(ContractError, "duplicate JSON key"):
                AccountingMultitableJsonAdapter().parse(
                    path,
                    "source_" + "a" * 24,
                )

    def test_metadata_preserves_all_top_level_values_and_table_counts(self) -> None:
        document = valid_accounting_multitable_document()
        dataset = self.parse(document)
        self.assertEqual("1.0.0", dataset.metadata["schema_version"])
        self.assertEqual("1.0.0", dataset.metadata["input_schema_version"])
        for key, value in document.items():
            if key != "tables" and key != "schema_version":
                self.assertEqual(value, dataset.metadata[key])
        self.assertEqual(
            set(ACCOUNTING_TABLE_NAMES),
            set(dataset.metadata["table_row_counts"]),
        )
        self.assertEqual(2, dataset.metadata["table_row_counts"]["journal_lines"])


if __name__ == "__main__":
    unittest.main()
