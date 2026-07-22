import io
import json
import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent import cli
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from tests.support import confirmed_mission


ROOT = Path(__file__).resolve().parents[2]


class TTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def call(arguments: list[str], input_text: str = "") -> tuple[int, dict]:
    old_in, old_out, old_err = cli.sys.stdin, cli.sys.stdout, cli.sys.stderr
    stdin, stdout, stderr = TTY(input_text), TTY(), TTY()
    try:
        cli.sys.stdin, cli.sys.stdout, cli.sys.stderr = stdin, stdout, stderr
        code = cli.main(arguments)
        return code, json.loads(stdout.getvalue())
    finally:
        cli.sys.stdin, cli.sys.stdout, cli.sys.stderr = old_in, old_out, old_err


def prepare_delivery_approved(root: Path) -> tuple[ArtifactStore, list[str], str]:
    artifacts = root / "artifacts"
    mission = root / "mission.json"
    source = root / "source.json"
    mission.write_text(json.dumps(confirmed_mission()), "utf-8")
    source.write_text('[{"domain":"unmapped"}]', "utf-8")
    code, started = call([
        "start", "--artifact-root", str(artifacts),
        "--mission-contract", str(mission), "--input", str(source),
    ])
    if code != 0:
        raise AssertionError(started)
    run_id = started["run_id"]
    common = ["--artifact-root", str(artifacts), "--run-id", run_id]
    code, scanned = call(["scan", *common, "--expected-revision", "1"])
    if code != 0:
        raise AssertionError(scanned)

    store = ArtifactStore(artifacts)
    store.open_run(run_id)
    snapshot = store.verify_revision(2)
    manifest = json.loads((snapshot / "snapshot-manifest.json").read_text("utf-8"))
    files = {
        item["path"]: (snapshot / item["path"]).read_bytes()
        for item in manifest["files"]
    }
    state = json.loads(files["workflow/state.json"].decode("utf-8"))
    state.update({"revision": 3, "state": "finalization_jobs_ready"})
    files["workflow/state.json"] = canonical_bytes(state)
    files["reasoning/integrated-assessment.json"] = canonical_bytes({
        "integrated_assessment_id": "integrated_" + "e" * 24,
        "payload": {"integrated_issues": []},
    })
    files["workflow/hitl-overlay.json"] = canonical_bytes({})
    store.publish(2, files)

    code, prepared = call(
        ["prepare-finalization", *common, "--expected-revision", "3"]
    )
    if code != 0:
        raise AssertionError(prepared)
    code, writer_jobs = call([
        "prepare-jobs", *common, "--stage", "writer",
        "--expected-revision", "4",
    ])
    if code != 0:
        raise AssertionError(writer_jobs)
    writer = root / "writer.json"
    writer.write_text(json.dumps({
        "structured_output_ref": "final/structured-output.json",
        "claim_templates": [],
        "expert_packet_templates": [],
        "ceo_brief_section_order": [],
    }), "utf-8")
    code, ingested = call([
        "ingest-result", *common,
        "--job-id", writer_jobs["data"]["job_ids"][0],
        "--draft", str(writer), "--expected-revision", "5",
    ])
    if code != 0:
        raise AssertionError(ingested)
    code, reduced = call([
        "reduce-stage", *common, "--stage", "writer",
        "--expected-revision", "6",
    ])
    if code != 0:
        raise AssertionError(reduced)

    overlay = root / "final-overlay.json"
    overlay.write_text(json.dumps({"patch_operations": [{
        "op": "add",
        "path": "/delivery_scope/package",
        "value": "ceo_brief",
    }]}), "utf-8")
    code, requested = call([
        "approval-request", *common, "--gate", "final",
        "--overlay", str(overlay), "--expected-revision", "7",
    ])
    if code != 2:
        raise AssertionError(requested)
    approval_input = (
        f"actor-1\nceo\n{requested['data']['nonce']}\nAPPROVE\n"
    )
    code, approved = call([
        "approve-interactive", *common,
        "--request-id", requested["data"]["approval_request_id"],
        "--expected-revision", "8",
    ], approval_input)
    if code != 0 or approved["state"] != "delivery_approved":
        raise AssertionError(approved)
    return store, common, run_id


class CliFinalizationFlowTests(unittest.TestCase):
    def test_runtime_grades_writer_and_tty_final_approval_publish_package(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            artifacts = root / "artifacts"
            mission = root / "mission.json"
            source = root / "source.json"
            mission.write_text(json.dumps(confirmed_mission()), "utf-8")
            source.write_text('[{"domain":"unmapped"}]', "utf-8")
            code, started = call([
                "start", "--artifact-root", str(artifacts),
                "--mission-contract", str(mission), "--input", str(source),
            ])
            self.assertEqual(0, code, started)
            run_id = started["run_id"]
            common = ["--artifact-root", str(artifacts), "--run-id", run_id]
            code, scanned = call(["scan", *common, "--expected-revision", "1"])
            self.assertEqual(0, code, scanned)
            store = ArtifactStore(artifacts)
            store.open_run(run_id)
            snapshot = store.verify_revision(2)
            manifest = json.loads((snapshot / "snapshot-manifest.json").read_text("utf-8"))
            files = {
                item["path"]: (snapshot / item["path"]).read_bytes()
                for item in manifest["files"]
            }
            state = json.loads(files["workflow/state.json"].decode("utf-8"))
            state.update({"revision": 3, "state": "finalization_jobs_ready"})
            files["workflow/state.json"] = canonical_bytes(state)
            files["reasoning/integrated-assessment.json"] = canonical_bytes({
                "integrated_assessment_id": "integrated_" + "e" * 24,
                "payload": {"integrated_issues": []},
            })
            files["workflow/hitl-overlay.json"] = canonical_bytes({})
            store.publish(2, files)

            code, prepared = call(["prepare-finalization", *common, "--expected-revision", "3"])
            self.assertEqual(0, code, prepared)
            self.assertEqual([], prepared["data"]["grade_record_ids"])
            code, writer_jobs = call(["prepare-jobs", *common, "--stage", "writer", "--expected-revision", "4"])
            self.assertEqual(0, code, writer_jobs)
            writer_job_id = writer_jobs["data"]["job_ids"][0]
            writer = root / "writer.json"
            writer.write_text(json.dumps({
                "structured_output_ref": "final/structured-output.json",
                "claim_templates": [], "expert_packet_templates": [],
                "ceo_brief_section_order": [],
            }), "utf-8")
            ingest_code, ingested = call(["ingest-result", *common, "--job-id", writer_job_id, "--draft", str(writer), "--expected-revision", "5"])
            self.assertEqual(0, ingest_code, ingested)
            code, reduced = call(["reduce-stage", *common, "--stage", "writer", "--expected-revision", "6"])
            self.assertEqual(0, code, reduced)
            self.assertEqual("writer_ready", reduced["state"])

            overlay = root / "final-overlay.json"
            overlay.write_text(json.dumps({"patch_operations": [{
                "op": "add", "path": "/delivery_scope/package", "value": "ceo_brief",
            }]}), "utf-8")
            code, requested = call(["approval-request", *common, "--gate", "final", "--overlay", str(overlay), "--expected-revision", "7"])
            self.assertEqual(2, code, requested)
            approval_input = f"actor-1\nceo\n{requested['data']['nonce']}\nAPPROVE\n"
            code, approved = call([
                "approve-interactive", *common,
                "--request-id", requested["data"]["approval_request_id"],
                "--expected-revision", "8",
            ], approval_input)
            self.assertEqual(0, code, approved)
            self.assertEqual("delivery_approved", approved["state"])
            code, finalized = call(["finalize", *common, "--expected-revision", "9"])
            self.assertEqual(0, code, finalized)
            self.assertEqual("finalized", finalized["state"])
            snapshot = store.verify_revision(10)
            self.assertTrue((snapshot / "final" / "result.json").is_file())
            self.assertTrue((snapshot / "final" / "ceo-brief.md").is_file())
            self.assertTrue((snapshot / "final" / "audit-manifest.json").is_file())
            code, validated = call(["validate", *common, "--revision", "10"])
            self.assertEqual(0, code, validated)
            self.assertIn("final_package", validated["data"]["checks"])
            code, rendered = call(["render", *common, "--revision", "10"])
            self.assertEqual(0, code, rendered)
            self.assertTrue(rendered["data"]["files"])

    def test_failed_finalize_leaves_revision_state_and_delivery_files_unchanged(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            store, common, run_id = prepare_delivery_approved(root)
            snapshot = store.verify_revision(9)
            manifest = json.loads(
                (snapshot / "snapshot-manifest.json").read_text("utf-8")
            )
            files = {
                item["path"]: (snapshot / item["path"]).read_bytes()
                for item in manifest["files"]
            }
            approval_paths = [
                path for path in files
                if path.startswith("approvals/records/")
            ]
            self.assertEqual(1, len(approval_paths))
            del files[approval_paths[0]]
            state = json.loads(files["workflow/state.json"].decode("utf-8"))
            state["revision"] = 10
            files["workflow/state.json"] = canonical_bytes(state)
            store.publish(9, files)

            code, rejected = call([
                "finalize", *common, "--expected-revision", "10",
            ])

            self.assertEqual(3, code, rejected)
            self.assertIn(
                "current approved interactive Final approval is required",
                rejected["message"],
            )
            self.assertEqual(10, store.state()["revision"])
            unchanged = store.verify_revision(10)
            unchanged_state = json.loads(
                (unchanged / "workflow" / "state.json").read_text("utf-8")
            )
            self.assertEqual("delivery_approved", unchanged_state["state"])
            self.assertFalse((unchanged / "final" / "result.json").exists())
            self.assertFalse((unchanged / "final" / "ceo-brief.md").exists())
            self.assertFalse(
                (unchanged / "final" / "audit-manifest.json").exists()
            )
            self.assertFalse(
                (
                    root / "artifacts" / run_id / "snapshots" / "r0011"
                ).exists()
            )


if __name__ == "__main__":
    unittest.main()
