from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from tests.support_accounting_multitable import valid_accounting_multitable_document
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.intake.adapters.accounting_json import AccountingMultitableJsonAdapter
from trusted_ceo_agent.intake.adapters.csv import CsvAdapter
from trusted_ceo_agent.intake.adapters.json import JsonAdapter
from trusted_ceo_agent.intake.adapters.xlsx import XlsxAdapter
from trusted_ceo_agent.web_report.closure import EvidenceClosure
from trusted_ceo_agent.web_report.previews import build_source_views


ROOT = Path(__file__).resolve().parents[3]
SOURCE_ID = "source_" + "a" * 24
SHA = "a" * 64


def closure_for(
    *,
    source: dict,
    source_ref: dict,
) -> EvidenceClosure:
    return EvidenceClosure(
        facts=(
            {
                "fact_id": "fact_" + "b" * 24,
                "source_refs": [source_ref],
                "derivation": None,
                "quality": [],
            },
        ),
        signals=(),
        evidence_links=(),
        sources=(source,),
        data_quality=(),
        capability_map={"capability_map_id": "capability_map", "capabilities": []},
    )


def source_for(path: Path, *, access_policy: str, display_name: str) -> dict:
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    return {
        "source_id": SOURCE_ID,
        "source_type": "uploaded_file",
        "access_policy": access_policy,
        "evidence_usage": "primary",
        "observation_roles": ["ledger"],
        "display_name": display_name,
        "media_type": {
            ".csv": "text/csv",
            ".json": "application/json",
            ".xlsx": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        }[path.suffix],
        "sha256": digest,
        "size_bytes": len(payload),
        "received_at": "2026-07-17T00:00:00Z",
        "snapshot_ref": f"sources/blobs/{digest}",
        "original_path_token": "path_" + "c" * 24,
        "aliases": [],
        "metadata": {},
    }


def place_blob(snapshot: Path, source_path: Path, source: dict) -> Path:
    blob = snapshot / source["snapshot_ref"]
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(source_path.read_bytes())
    return blob


class SourcePreviewTests(unittest.TestCase):
    def test_accounting_json_root_reparses_with_exact_pointer(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            path = root / "accounting.json"
            path.write_bytes(canonical_bytes(valid_accounting_multitable_document()))
            source = source_for(
                path,
                access_policy="permitted",
                display_name="Accounting JSON",
            )
            dataset = AccountingMultitableJsonAdapter().parse(path, SOURCE_ID)
            record = next(
                item for item in dataset.records
                if item.values.get("journal_lines.line_id") == "L1"
            )
            source_ref = dataset.source_reference(
                record,
                ["journal_lines.debit"],
                "observe",
                f"lineage/sets/{SHA}.json",
                observation_role="ledger",
            )
            snapshot = root / "snapshot"
            snapshot.mkdir()
            place_blob(snapshot, path, source)

            views = build_source_views(
                snapshot,
                closure_for(source=source, source_ref=source_ref),
            )

            self.assertEqual(
                "/tables/journal_lines/0",
                views.previews[0]["locator"]["json_pointer"],
            )
            self.assertEqual(
                ["journal_lines.debit"],
                views.previews[0]["column_labels"],
            )
            self.assertEqual([["100.00"]], views.previews[0]["rows"])

    def test_explicit_json_records_pointer_remains_supported(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            path = root / "nested.json"
            path.write_bytes(canonical_bytes({"payload": [{"id": "1"}]}))
            source = source_for(
                path,
                access_policy="permitted",
                display_name="Nested JSON",
            )
            source["metadata"] = {"records_pointer": "/payload"}
            dataset = JsonAdapter(records_pointer="/payload").parse(path, SOURCE_ID)
            source_ref = dataset.source_reference(
                dataset.records[0],
                ["id"],
                "observe",
                f"lineage/sets/{SHA}.json",
                observation_role="ledger",
            )
            snapshot = root / "snapshot"
            snapshot.mkdir()
            place_blob(snapshot, path, source)

            preview = build_source_views(
                snapshot,
                closure_for(source=source, source_ref=source_ref),
            ).previews[0]

            self.assertEqual("/payload/0", preview["locator"]["json_pointer"])
            self.assertEqual([["1"]], preview["rows"])

    def test_permitted_csv_contains_only_selected_record_and_fields(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            csv_path = root / "source.csv"
            csv_path.write_text(
                "customer,revenue,secret_note\nA,100,private\nB,200,hidden\n",
                encoding="utf-8",
            )
            source = source_for(
                csv_path,
                access_policy="permitted",
                display_name="매출 원장",
            )
            dataset = CsvAdapter().parse(csv_path, SOURCE_ID)
            source_ref = dataset.source_reference(
                dataset.records[0],
                ["customer", "revenue"],
                "observe",
                f"lineage/sets/{SHA}.json",
                observation_role="ledger",
            )
            snapshot = root / "snapshot"
            snapshot.mkdir()
            place_blob(snapshot, csv_path, source)

            views = build_source_views(
                snapshot,
                closure_for(source=source, source_ref=source_ref),
            )

            preview = views.previews[0]
            self.assertEqual(["customer", "revenue"], preview["column_labels"])
            self.assertEqual([["A", "100"]], preview["rows"])
            self.assertNotIn("secret_note", str(preview))
            self.assertNotIn("private", str(preview))
            self.assertNotIn("hidden", str(preview))

    def test_restricted_and_prohibited_sources_never_embed_values(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            csv_path = root / "source.csv"
            csv_path.write_text("customer,revenue\nA,100\n", encoding="utf-8")
            dataset = CsvAdapter().parse(csv_path, SOURCE_ID)
            source_ref = dataset.source_reference(
                dataset.records[0],
                ["customer", "revenue"],
                "observe",
                f"lineage/sets/{SHA}.json",
                observation_role="ledger",
            )
            snapshot = root / "snapshot"
            snapshot.mkdir()
            for policy in ("restricted", "prohibited"):
                source = source_for(
                    csv_path,
                    access_policy=policy,
                    display_name="매출 원장",
                )
                place_blob(snapshot, csv_path, source)
                preview = build_source_views(
                    snapshot,
                    closure_for(source=source, source_ref=source_ref),
                ).previews[0]
                self.assertEqual([], preview["column_labels"])
                self.assertEqual([], preview["rows"])
                self.assertEqual(policy, preview["masking_status"])

    def test_json_pointer_and_xlsx_formula_are_selected_safely(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            snapshot = root / "snapshot"
            snapshot.mkdir()

            json_path = root / "source.json"
            json_path.write_text(
                '[{"customer":"A","revenue":100,"secret":"hidden"}]',
                encoding="utf-8",
            )
            json_source = source_for(
                json_path,
                access_policy="permitted",
                display_name="JSON 매출",
            )
            json_dataset = JsonAdapter().parse(json_path, SOURCE_ID)
            json_ref = json_dataset.source_reference(
                json_dataset.records[0],
                ["customer", "revenue"],
                "observe",
                f"lineage/sets/{SHA}.json",
                observation_role="ledger",
            )
            place_blob(snapshot, json_path, json_source)
            json_preview = build_source_views(
                snapshot,
                closure_for(source=json_source, source_ref=json_ref),
            ).previews[0]
            self.assertEqual([["A", 100]], json_preview["rows"])
            self.assertNotIn("hidden", str(json_preview))

            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Data"
            sheet.append(["customer", "revenue", "formula"])
            sheet.append(["A", 100, "=B2*2"])
            xlsx_path = root / "source.xlsx"
            workbook.save(xlsx_path)
            workbook.close()
            xlsx_source = source_for(
                xlsx_path,
                access_policy="permitted",
                display_name="XLSX 매출",
            )
            xlsx_dataset = XlsxAdapter().parse(xlsx_path, SOURCE_ID)
            xlsx_ref = xlsx_dataset.source_reference(
                xlsx_dataset.records[0],
                ["customer", "formula", "revenue"],
                "observe",
                f"lineage/sets/{SHA}.json",
                observation_role="ledger",
            )
            place_blob(snapshot, xlsx_path, xlsx_source)
            xlsx_preview = build_source_views(
                snapshot,
                closure_for(source=xlsx_source, source_ref=xlsx_ref),
            ).previews[0]
            self.assertEqual([["A", None, 100]], xlsx_preview["rows"])
            self.assertNotIn("=B2*2", str(xlsx_preview))

    def test_source_blob_and_extraction_hash_are_revalidated(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            csv_path = root / "source.csv"
            csv_path.write_text("customer,revenue\nA,100\n", encoding="utf-8")
            source = source_for(
                csv_path,
                access_policy="permitted",
                display_name="매출 원장",
            )
            dataset = CsvAdapter().parse(csv_path, SOURCE_ID)
            source_ref = dataset.source_reference(
                dataset.records[0],
                ["customer", "revenue"],
                "observe",
                f"lineage/sets/{SHA}.json",
                observation_role="ledger",
            )
            snapshot = root / "snapshot"
            snapshot.mkdir()
            blob = place_blob(snapshot, csv_path, source)
            blob.write_text("tampered", encoding="utf-8")

            with self.assertRaisesRegex(IntegrityError, "hash|size"):
                build_source_views(
                    snapshot,
                    closure_for(source=source, source_ref=source_ref),
                )

            blob.write_bytes(csv_path.read_bytes())
            bad_ref = copy.deepcopy(source_ref)
            bad_ref["extraction_hash"] = "0" * 64
            with self.assertRaisesRegex(IntegrityError, "extraction"):
                build_source_views(
                    snapshot,
                    closure_for(source=source, source_ref=bad_ref),
                )


if __name__ == "__main__":
    unittest.main()
