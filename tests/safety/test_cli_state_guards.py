import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent import cli
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.trust.artifact_store import ArtifactStore


ROOT = Path(__file__).resolve().parents[2]


def call(arguments: list[str]) -> tuple[int, dict]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = cli.main(arguments)
    return code, json.loads(output.getvalue())


def payloads(snapshot: Path) -> dict[str, bytes]:
    manifest = json.loads((snapshot / "snapshot-manifest.json").read_text("utf-8"))
    return {entry["path"]: (snapshot / entry["path"]).read_bytes() for entry in manifest["files"]}


class CliStateGuardTests(unittest.TestCase):
    def test_writer_cannot_be_prepared_before_finalization(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            mission, source, artifacts = root / "mission.json", root / "source.json", root / "artifacts"
            mission.write_text('{"confirmed":true}', "utf-8")
            source.write_text('[{"value":"1"}]', "utf-8")
            code, started = call(["start", "--artifact-root", str(artifacts), "--mission-contract", str(mission), "--input", str(source)])
            self.assertEqual(0, code)
            code, rejected = call([
                "prepare-jobs", "--artifact-root", str(artifacts), "--run-id", started["run_id"],
                "--stage", "writer", "--expected-revision", "1",
            ])
            self.assertEqual(3, code)
            self.assertIn("not allowed", rejected["message"])
            pointer = json.loads((artifacts / started["run_id"] / "state.json").read_text("utf-8"))
            self.assertEqual(1, pointer["revision"])

    def test_terminal_run_rejects_further_mutation(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            mission, source, artifacts = root / "mission.json", root / "source.json", root / "artifacts"
            mission.write_text('{"confirmed":true}', "utf-8")
            source.write_text('[{"value":"1"}]', "utf-8")
            _, started = call(["start", "--artifact-root", str(artifacts), "--mission-contract", str(mission), "--input", str(source)])
            common = ["--artifact-root", str(artifacts), "--run-id", started["run_id"]]
            code, stopped = call(["stop", *common, "--expected-revision", "1"])
            self.assertEqual(0, code)
            self.assertEqual("stopped_by_human", stopped["state"])
            code, _ = call(["scan", *common, "--expected-revision", "2"])
            self.assertEqual(3, code)
            pointer = json.loads((artifacts / started["run_id"] / "state.json").read_text("utf-8"))
            self.assertEqual(2, pointer["revision"])

    def test_resume_rejects_unresolved_recorded_blocker(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            mission, source, artifacts = root / "mission.json", root / "source.json", root / "artifacts"
            mission.write_text('{"confirmed":false}', "utf-8")
            source.write_text('[{"value":"1"}]', "utf-8")
            _, started = call([
                "start", "--artifact-root", str(artifacts),
                "--mission-contract", str(mission), "--input", str(source),
            ])
            store = ArtifactStore(artifacts)
            store.open_run(started["run_id"])
            files = payloads(store.verify_revision(1))
            files["workflow/state.json"] = canonical_bytes({
                "run_id": started["run_id"],
                "revision": 2,
                "state": "blocked",
                "resume_state": "deep_dive_jobs_ready",
                "blocker": "component_contract_failure",
                "approvals": [],
            })
            store.publish(1, files)

            code, result = call([
                "resume", "--artifact-root", str(artifacts), "--run-id", started["run_id"],
                "--expected-revision", "2",
            ])
            self.assertEqual(3, code)
            self.assertFalse(result["ok"])
            self.assertIn("unresolved", result["message"])
            pointer = json.loads((artifacts / started["run_id"] / "state.json").read_text("utf-8"))
            self.assertEqual(2, pointer["revision"])


if __name__ == "__main__":
    unittest.main()
