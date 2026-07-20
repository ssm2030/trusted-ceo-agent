import tempfile
import unittest
from pathlib import Path

from tests.support_accounting_multitable import valid_accounting_multitable_document
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.evidence.core import EvidenceCoreValidator, assemble_evidence_core
from trusted_ceo_agent.evidence.facts import build_observed_fact
from trusted_ceo_agent.intake.adapters.csv import CsvAdapter
from trusted_ceo_agent.intake.pipeline import IntakePipeline
from trusted_ceo_agent.intake.snapshot import Snapshotter


SHA = "a" * 64


class IntakeToEvidenceIntegrationTests(unittest.TestCase):
    def test_accounting_source_reference_keeps_table_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_root = root / "input"
            artifact_root = root / "artifacts"
            input_root.mkdir()
            path = input_root / "accounting.json"
            path.write_bytes(canonical_bytes(valid_accounting_multitable_document()))
            result = IntakePipeline(
                Snapshotter(input_root, artifact_root)
            ).ingest(path, observation_roles=("ledger",))
            self.assertIsNotNone(result.dataset)
            assert result.dataset is not None
            record = next(
                item for item in result.dataset.records
                if item.values.get("journal_lines.line_id") == "L1"
            )

            reference = result.dataset.source_reference(
                record,
                ["journal_lines.debit"],
                "observe",
                f"lineage/sets/{SHA}.json",
                observation_role="ledger",
            )

            self.assertEqual(["journal_lines.debit"], reference["selected_fields"])
            self.assertEqual("json_pointer", reference["locator_type"])
            self.assertEqual(
                {"pointer": "/tables/journal_lines/0"},
                reference["locator"],
            )

    def test_observed_fact_traces_to_snapshotted_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_root = root / "input"
            artifact_root = root / "artifacts"
            input_root.mkdir()
            path = input_root / "ledger.csv"
            path.write_text("period,revenue\n2026-01,100\n", encoding="utf-8")
            snap = Snapshotter(input_root, artifact_root).snapshot(path, observation_roles=("ledger",))
            blob_path = artifact_root / snap.source["snapshot_ref"]
            dataset = CsvAdapter().parse(blob_path, snap.source["source_id"])
            reference = dataset.source_reference(dataset.records[0], ["revenue"], "observe", f"lineage/sets/{SHA}.json")
            fact = build_observed_fact(
                fact_code="revenue.observed", metric_code="revenue", semantic_role="observation",
                observation_role="ledger", scope=[], time_context={"period": "2026-01"},
                value={"value_type": "decimal", "canonical_value": "100", "unit_code": "currency", "currency_code": "KRW", "scale": "1"},
                source_refs=[reference],
            )
            core = assemble_evidence_core(
                envelope={"schema_version": "1.0.0", "artifact_id": "artifact_" + "b" * 24, "run_id": "run_20260717T000000Z_0123456789abcdef", "revision": 1, "parent_artifact_hash": None, "stage": "evidence_ready", "created_at": "2026-07-17T00:00:00Z", "semantic_fingerprint": SHA, "artifact_hash": SHA},
                mission_contract_ref="mission_" + "c" * 24,
                pack_manifest={"pack_manifest_hash": SHA, "pack_refs": []},
                component_manifest={"component_refs": []},
                source_registry=[snap.source], data_quality_register=[], fact_register=[fact],
                signal_register=[], evidence_links=[],
                capability_map={"capability_map_id": "capability_map_" + "d" * 24, "capabilities": []},
            )
            EvidenceCoreValidator().validate(core, source_root=artifact_root)


if __name__ == "__main__":
    unittest.main()
