import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent import cli
from trusted_ceo_agent.evidence.core import EvidenceCoreValidator
from tests.support import confirmed_mission


ROOT = Path(__file__).resolve().parents[2]


def call(arguments: list[str]) -> tuple[int, dict]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = cli.main(arguments)
    return code, json.loads(output.getvalue())


class CliScanIntegrationTests(unittest.TestCase):
    def test_scan_parses_accounting_multitable_snapshot(self) -> None:
        source = (
            ROOT
            / "evaluation"
            / "synthetic"
            / "analysis-input"
            / "clean-baseline"
            / "dataset.json"
        )
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            mission = root / "mission.json"
            artifacts = root / "artifacts"
            mission.write_text(json.dumps(confirmed_mission()), "utf-8")

            code, started = call([
                "start", "--artifact-root", str(artifacts),
                "--mission-contract", str(mission), "--input", str(source),
            ])
            self.assertEqual(0, code, started)
            code, scanned = call([
                "scan", "--artifact-root", str(artifacts),
                "--run-id", started["run_id"], "--expected-revision", "1",
            ])

            self.assertEqual(0, code, scanned)
            self.assertEqual("evidence_ready", scanned["state"])
            self.assertEqual(1, scanned["data"]["parsed_source_count"])
            snapshot = artifacts / started["run_id"] / "snapshots" / "r0002"
            core = json.loads(
                (snapshot / "evidence" / "core.json").read_text("utf-8")
            )
            source_id = core["source_registry"][0]["source_id"]
            dataset = json.loads(
                (snapshot / "intake" / "datasets" / f"{source_id}.json")
                .read_text("utf-8")
            )
            self.assertEqual(
                "accounting-multitable-json",
                dataset["metadata"]["adapter_id"],
            )
            self.assertEqual(33, len(dataset["metadata"]["table_row_counts"]))
            self.assertEqual(360, len(dataset["records"]))

    def test_scan_parses_snapshot_and_stops_at_mapping_gate_before_facts(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            mission = root / "mission.json"
            source = root / "monthly.json"
            artifacts = root / "artifacts"
            mission.write_text(json.dumps(confirmed_mission()), "utf-8")
            source.write_text(json.dumps([
                {"period": "2026-01", "gross_margin": "0.40"},
                {"period": "2026-02", "gross_margin": "0.36"},
                {"period": "2026-03", "gross_margin": "0.34"},
            ]), "utf-8")

            code, started = call([
                "start", "--artifact-root", str(artifacts),
                "--mission-contract", str(mission), "--input", str(source),
            ])
            self.assertEqual(0, code)
            code, scanned = call([
                "scan", "--artifact-root", str(artifacts),
                "--run-id", started["run_id"], "--expected-revision", "1",
            ])

            self.assertEqual(2, code, scanned)
            self.assertEqual("schema_mapping_job_ready", scanned["state"])
            self.assertEqual("b2b-services@1.0.0", scanned["data"]["domain_pack_ref"])
            self.assertEqual("provisional", scanned["data"]["domain_pack_authority"])
            snapshot = artifacts / started["run_id"] / "snapshots" / "r0002"
            self.assertTrue((snapshot / "intake" / "datasets").is_dir())
            self.assertTrue((snapshot / "packs" / "manifest.json").is_file())
            core = json.loads((snapshot / "evidence" / "core.json").read_text("utf-8"))
            EvidenceCoreValidator().validate(core, source_root=snapshot)
            self.assertEqual(1, len(core["source_registry"]))
            self.assertEqual([], core["fact_register"])
            proposal = json.loads((snapshot / "intake" / "canonical-mapping-proposal.json").read_text("utf-8"))
            self.assertEqual(1, len(proposal["mappings"]))


if __name__ == "__main__":
    unittest.main()
