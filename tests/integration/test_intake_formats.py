import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from tests.support_accounting_multitable import valid_accounting_multitable_document
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.intake.adapters.csv import CsvAdapter
from trusted_ceo_agent.intake.adapters.json import JsonAdapter
from trusted_ceo_agent.intake.adapters.xlsx import XlsxAdapter
from trusted_ceo_agent.intake.pipeline import IntakePipeline
from trusted_ceo_agent.intake.snapshot import Snapshotter


class IntakeFormatsIntegrationTests(unittest.TestCase):
    def test_pipeline_snapshots_accounting_json_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_root = root / "input"
            artifact_root = root / "artifacts"
            input_root.mkdir()
            path = input_root / "accounting.json"
            path.write_bytes(canonical_bytes(valid_accounting_multitable_document()))

            result = IntakePipeline(
                Snapshotter(input_root, artifact_root)
            ).ingest(path)

            self.assertIsNotNone(result.dataset)
            assert result.dataset is not None
            blob = artifact_root / result.snapshot.source["snapshot_ref"]
            self.assertTrue(blob.is_file())
            self.assertEqual(
                result.snapshot.source["source_id"],
                result.dataset.source_id,
            )
            self.assertEqual(
                "accounting-multitable-json",
                result.dataset.metadata["adapter_id"],
            )
            self.assertEqual(
                {"pointer": "/tables/journal_headers/0"},
                next(
                    record.locator for record in result.dataset.records
                    if record.values.get("journal_headers.journal_id") == "J1"
                ),
            )

    def test_document_like_formats_remain_snapshot_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_root = root / "input"
            artifact_root = root / "artifacts"
            input_root.mkdir()
            pipeline = IntakePipeline(Snapshotter(input_root, artifact_root))
            for suffix in (".txt", ".md", ".pdf"):
                path = input_root / f"document{suffix}"
                path.write_bytes(b"document")
                with self.subTest(suffix=suffix):
                    result = pipeline.ingest(path)
                    self.assertIsNone(result.dataset)

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
