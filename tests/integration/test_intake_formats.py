import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from trusted_ceo_agent.intake.adapters.csv import CsvAdapter
from trusted_ceo_agent.intake.adapters.json import JsonAdapter
from trusted_ceo_agent.intake.adapters.xlsx import XlsxAdapter


class IntakeFormatsIntegrationTests(unittest.TestCase):
    def test_three_formats_have_same_normalized_semantic_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [{"id": "1", "amount": "10"}, {"id": "2", "amount": "20"}]
            csv_path = root / "data.csv"
            csv_path.write_text("id,amount\n1,10\n2,20\n", encoding="utf-8")
            json_path = root / "data.json"
            json_path.write_text(json.dumps(rows), encoding="utf-8")
            xlsx_path = root / "data.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(["id", "amount"])
            for row in rows:
                sheet.append([row["id"], row["amount"]])
            workbook.save(xlsx_path)
            workbook.close()

            source_id = "source_" + "a" * 24
            datasets = [
                CsvAdapter().parse(csv_path, source_id),
                JsonAdapter().parse(json_path, source_id),
                XlsxAdapter().parse(xlsx_path, source_id),
            ]
            self.assertEqual(1, len({dataset.semantic_rows_hash for dataset in datasets}))


if __name__ == "__main__":
    unittest.main()
