import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.intake.adapters.csv import CsvAdapter
from trusted_ceo_agent.intake.adapters.json import JsonAdapter
from trusted_ceo_agent.intake.adapters.xlsx import XlsxAdapter


class IntakeAdapterTests(unittest.TestCase):
    def test_csv_uses_logical_record_indices_with_quoted_newlines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.csv"
            path.write_text('id,note\n1,"hello\nworld"\n2,plain\n', encoding="utf-8")
            dataset = CsvAdapter().parse(path, "source_" + "a" * 24)
            self.assertEqual([1, 2], [record.logical_index for record in dataset.records])
            self.assertEqual("hello\nworld", dataset.records[0].values["note"])
            self.assertEqual({"record_indices": [1]}, dataset.records[0].locator)

    def test_cp949_requires_explicit_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.csv"
            path.write_bytes("항목,값\n매출,10\n".encode("cp949"))
            with self.assertRaises(ContractError):
                CsvAdapter().parse(path, "source_" + "a" * 24)
            dataset = CsvAdapter(encoding="cp949").parse(path, "source_" + "a" * 24)
            self.assertEqual("cp949", dataset.metadata["encoding"])

    def test_json_uses_strict_decoder_and_rfc6901_pointers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text('[{"id":"1"},{"id":"2"}]', encoding="utf-8")
            dataset = JsonAdapter().parse(path, "source_" + "a" * 24)
            self.assertEqual({"pointer": "/0"}, dataset.records[0].locator)
            path.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaises(ContractError):
                JsonAdapter().parse(path, "source_" + "a" * 24)

    def test_xlsx_formula_is_quality_issue_and_not_trusted_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Data"
            sheet.append(["id", "amount"])
            sheet.append(["1", "=1+1"])
            workbook.save(path)
            workbook.close()

            dataset = XlsxAdapter().parse(path, "source_" + "a" * 24)
            self.assertIsNone(dataset.records[0].values["amount"])
            self.assertEqual("xlsx_cells", dataset.records[0].locator_type)
            self.assertTrue(any(issue["issue_code"] == "untrusted_formula_value" for issue in dataset.quality_issues))


if __name__ == "__main__":
    unittest.main()
