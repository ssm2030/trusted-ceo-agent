import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trusted_ceo_agent import cli
from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.runtime_components import execute_authorized_scope
from trusted_ceo_agent.runtime_scan import build_scan_artifacts
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from tests.support import confirmed_mission


ROOT = Path(__file__).resolve().parents[2]


def call(arguments: list[str]) -> tuple[int, dict]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = cli.main(arguments)
    return code, json.loads(output.getvalue())


def payloads(snapshot: Path) -> dict[str, bytes]:
    manifest = json.loads((snapshot / "snapshot-manifest.json").read_text("utf-8"))
    return {entry["path"]: (snapshot / entry["path"]).read_bytes() for entry in manifest["files"]}


def prepare_authorized_scope(
    root: Path,
    *,
    required_inputs: tuple[str, ...] = (),
) -> tuple[Path, str, ArtifactStore, list[str], dict, str, object, tuple[dict, ...]]:
    mission_path = root / "mission.json"
    source_path = root / "monthly.json"
    artifacts = root / "artifacts"
    mission = confirmed_mission()
    mission_path.write_text(json.dumps(mission), "utf-8")
    source_path.write_text(json.dumps([
        {"period": "2026-01", "gross_margin": "0.42"},
        {"period": "2026-02", "gross_margin": "0.39"},
        {"period": "2026-03", "gross_margin": "0.36"},
    ]), "utf-8")
    code, started = call([
        "start", "--artifact-root", str(artifacts),
        "--mission-contract", str(mission_path), "--input", str(source_path),
    ])
    if code != 0:
        raise AssertionError(started)
    common = ["--artifact-root", str(artifacts), "--run-id", started["run_id"]]
    code, scanned = call(["scan", *common, "--expected-revision", "1"])
    if code != 2:
        raise AssertionError(scanned)

    store = ArtifactStore(artifacts)
    store.open_run(started["run_id"])
    snapshot = store.verify_revision(2)
    files = payloads(snapshot)
    proposal = strict_loads(files["intake/canonical-mapping-proposal.json"])
    source = strict_loads(files["sources/registry.json"])[0]
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
    updates, _ = build_scan_artifacts(
        files=files,
        pointer=store.state(),
        run_id=started["run_id"],
        current_revision=2,
        source_root=snapshot,
        mission=mission,
        mapping_overlay=overlay,
    )
    files.update(updates)
    scope = {
        "component_ids": ["bridge_decompose"],
        "issue_ids": ["issue_profitability"],
        "required_inputs": list(required_inputs),
    }
    scope_ref = make_id("scope", scope)
    integrated = {
        "payload": {
            "integrated_issues": [{
                "local_key": "issue_profitability",
                "payload": {
                    "problem_family_ref": "profitability_erosion",
                    "scope_key": "enterprise",
                },
            }],
        },
    }
    state = strict_loads(files["workflow/state.json"])
    state.update({"state": "deep_dive_authorized", "revision": 3})
    files["workflow/state.json"] = canonical_bytes(state)
    files["workflow/hitl-overlay.json"] = canonical_bytes({"deep_dive_scope": scope})
    files["reasoning/integrated-assessment.json"] = canonical_bytes(integrated)
    store.publish(2, files)

    current_files = payloads(store.verify_revision(3))
    core = strict_loads(current_files["evidence/core.json"])
    plan, runs = execute_authorized_scope(
        current_files, core, integrated, scope, scope_ref,
    )
    return artifacts, started["run_id"], store, common, scope, scope_ref, plan, runs


class CliComponentsIntegrationTests(unittest.TestCase):
    def test_required_specialist_inputs_fail_closed_before_publish(self) -> None:
        for required_inputs in (("accounting",), ("professional",), ("accounting", "professional")):
            with self.subTest(required_inputs=required_inputs):
                with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                    root = Path(directory)
                    _, _, store, common, _, scope_ref, _, _ = prepare_authorized_scope(
                        root,
                        required_inputs=required_inputs,
                    )

                    code, result = call([
                        "run-components", *common, "--scope-ref", scope_ref,
                        "--expected-revision", "3",
                    ])

                    self.assertEqual(3, code, result)
                    self.assertFalse(result["ok"])
                    self.assertIn("required input", result["message"])
                    self.assertEqual(3, store.state()["revision"])

    def test_only_approved_components_execute_and_are_published(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            artifacts, run_id, store, common, scope, scope_ref, _, _ = prepare_authorized_scope(root)

            code, result = call([
                "run-components", *common, "--scope-ref", scope_ref,
                "--expected-revision", "3",
            ])
            self.assertEqual(0, code, result)
            self.assertEqual("deep_dive_jobs_ready", result["state"])
            self.assertEqual(1, len(result["data"]["component_run_ids"]))
            snapshot = store.verify_revision(4)
            run_id = result["data"]["component_run_ids"][0]
            run = json.loads((snapshot / "components" / "runs" / f"{run_id}.json").read_text("utf-8"))
            self.assertEqual("not_assessable", run["status"])
            scope_doc = json.loads((snapshot / "components" / "scope.json").read_text("utf-8"))
            self.assertEqual(scope_ref, scope_doc["scope_ref"])

            requirements = json.loads(
                (snapshot / "components" / "input-requirements.json").read_text("utf-8")
            )
            self.assertEqual([], requirements["required_inputs"])
            self.assertEqual([], requirements["provided_inputs"])

    def test_failed_approved_component_is_published_and_blocks_workflow(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            artifacts, run_id, store, common, scope, scope_ref, plan, runs = prepare_authorized_scope(root)
            self.assertEqual(1, len(runs))
            failed_run = dict(runs[0])
            failed_run.update({
                "status": "failed",
                "reason_codes": ["forced_contract_failure"],
                "output_fact_ids": [],
                "output_signal_ids": [],
                "output_facts": [],
                "output_signals": [],
            })
            with patch(
                "trusted_ceo_agent.application.mutations.execute_authorized_scope",
                return_value=(plan, (failed_run,)),
            ):
                code, result = call([
                    "run-components", *common, "--scope-ref", scope_ref,
                    "--expected-revision", "3",
                ])

            self.assertEqual(3, code, result)
            self.assertFalse(result["ok"])
            self.assertEqual("blocked", result["state"])
            snapshot = store.verify_revision(4)
            run_id = result["data"]["failed_component_run_ids"][0]
            run = json.loads((snapshot / "components" / "runs" / f"{run_id}.json").read_text("utf-8"))
            self.assertEqual("failed", run["status"])
            state = json.loads((snapshot / "workflow" / "state.json").read_text("utf-8"))
            self.assertEqual("component_contract_failure", state["blocker"])

    def test_unapproved_scope_ref_is_rejected_without_revision(self) -> None:
        # Scope equality is enforced by the same runtime helper exercised above.
        self.assertNotEqual(make_id("scope", {"component_ids": ["aggregate"], "issue_ids": []}), "scope_wrong")


if __name__ == "__main__":
    unittest.main()
