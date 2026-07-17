import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent.intake.adapters.csv import CsvAdapter


class IntakeDeterminismTests(unittest.TestCase):
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
