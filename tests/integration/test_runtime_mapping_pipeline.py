import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent import cli
from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.evidence.revalidation import revalidate_component_artifacts
from trusted_ceo_agent.runtime_scan import build_scan_artifacts
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from tests.support import confirmed_mission


ROOT = Path(__file__).resolve().parents[2]


def _call(arguments: list[str]) -> tuple[int, dict]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = cli.main(arguments)
    return code, json.loads(output.getvalue())


def _payloads(snapshot: Path) -> dict[str, bytes]:
    manifest = json.loads((snapshot / "snapshot-manifest.json").read_text("utf-8"))
    return {
        item["path"]: (snapshot / item["path"]).read_bytes()
        for item in manifest["files"]
    }


class RuntimeMappingPipelineTests(unittest.TestCase):
    def test_scan_proposes_then_confirmed_mapping_materializes_facts(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            mission_path = root / "mission.json"
            source_path = root / "monthly.json"
            artifact_root = root / "artifacts"
            mission = confirmed_mission()
            mission_path.write_text(json.dumps(mission), "utf-8")
            source_path.write_text(json.dumps([
                {"period": "2026-01", "gross_margin": "0.40"},
                {"period": "2026-02", "gross_margin": "0.36"},
                {"period": "2026-03", "gross_margin": "0.34"},
            ]), "utf-8")

            code, started = _call([
                "start", "--artifact-root", str(artifact_root),
                "--mission-contract", str(mission_path), "--input", str(source_path),
            ])
            self.assertEqual(0, code)
            code, scanned = _call([
                "scan", "--artifact-root", str(artifact_root),
                "--run-id", started["run_id"], "--expected-revision", "1",
            ])
            self.assertEqual(2, code)
            self.assertEqual("schema_mapping_job_ready", scanned["state"])

            store = ArtifactStore(artifact_root)
            store.open_run(started["run_id"])
            pointer = store.state()
            snapshot = store.verify_revision(2)
            files = _payloads(snapshot)
            proposal = strict_loads(files["intake/canonical-mapping-proposal.json"])
            self.assertEqual(1, len(proposal["mappings"]))
            self.assertEqual([], strict_loads(files["evidence/fact-register.json"]))
            source = strict_loads(files["sources/registry.json"])[0]
            self.assertEqual([], source["observation_roles"])

            question = proposal["mappings"][0]
            candidate = question["candidate_mappings"][0]
            overlay = {
                "mapping": {
                    "sources": {source["source_id"]: {"included": True}},
                    "columns": {
                        question["mapping_question_ref"]: {
                            key: candidate[key]
                            for key in (
                                "observation_role", "unit_code", "scale",
                                "time_role", "dimension_code",
                            )
                        }
                    },
                }
            }
            updates, data = build_scan_artifacts(
                files=files,
                pointer=pointer,
                run_id=started["run_id"],
                current_revision=2,
                source_root=snapshot,
                mission=mission,
                mapping_overlay=overlay,
            )
            facts = strict_loads(updates["evidence/fact-register.json"])
            self.assertEqual(3, len([
                item for item in facts if item["fact_code"] == "gross_margin"
            ]))
            self.assertIn("gross_margin_change_pp", {item["fact_code"] for item in facts})
            self.assertEqual(["calculated"], strict_loads(updates["sources/registry.json"])[0]["observation_roles"])
            self.assertTrue(data["mapping_applied"])
            self.assertEqual(3, data["materialized_fact_count"])
            validation = revalidate_component_artifacts({**files, **updates})
            self.assertGreater(len(validation["component_run_ids"]), 0)
            tampered = {**files, **updates}
            run_path = next(
                path for path, payload in tampered.items()
                if path.startswith("components/runs/")
                and strict_loads(payload).get("output_facts")
            )
            run = strict_loads(tampered[run_path])
            run["output_facts"][0]["value"]["canonical_value"] = "999"
            tampered[run_path] = canonical_bytes(run)
            with self.assertRaises(IntegrityError):
                revalidate_component_artifacts(tampered)


if __name__ == "__main__":
    unittest.main()
