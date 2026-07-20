import copy
import tempfile
import unittest
from pathlib import Path

from tests.support_accounting_multitable import valid_accounting_multitable_document
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.intake.adapters.accounting_json import AccountingMultitableJsonAdapter
from trusted_ceo_agent.intake.adapters.csv import CsvAdapter


class IntakeDeterminismTests(unittest.TestCase):
    def parse_accounting(self, document: dict):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "accounting.json"
            path.write_bytes(canonical_bytes(document))
            return AccountingMultitableJsonAdapter().parse(
                path,
                "source_" + "a" * 24,
            )

    def test_table_object_order_does_not_change_semantic_hash(self) -> None:
        left = valid_accounting_multitable_document()
        right = copy.deepcopy(left)
        right["tables"] = dict(reversed(list(right["tables"].items())))
        self.assertEqual(
            self.parse_accounting(left).semantic_rows_hash,
            self.parse_accounting(right).semantic_rows_hash,
        )

    def test_moving_same_row_between_tables_changes_semantic_hash(self) -> None:
        left = valid_accounting_multitable_document()
        right = valid_accounting_multitable_document()
        row = right["tables"]["journal_lines"].pop()
        right["tables"]["trial_balance"].append(row)
        self.assertNotEqual(
            self.parse_accounting(left).semantic_rows_hash,
            self.parse_accounting(right).semantic_rows_hash,
        )

    def test_row_and_column_order_do_not_change_semantic_rows_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.csv"
            second = root / "second.csv"
            first.write_text("id,amount\n1,10\n2,20\n", encoding="utf-8")
            second.write_text("amount,id\n20,2\n10,1\n", encoding="utf-8")
            source_id = "source_" + "a" * 24
            left = CsvAdapter().parse(first, source_id)
            right = CsvAdapter().parse(second, source_id)
            self.assertEqual(left.semantic_rows_hash, right.semantic_rows_hash)


if __name__ == "__main__":
    unittest.main()
