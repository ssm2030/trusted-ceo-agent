from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent import cli
from trusted_ceo_agent.trust.artifact_store import ArtifactStore


ROOT = Path(__file__).resolve().parents[2]


class CliHumanResponseIntegrationTests(unittest.TestCase):
    def call(self, argv: list[str]) -> tuple[int, dict]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main(argv)
        return code, json.loads(output.getvalue())

    def test_pending_preview_submit_and_retry_keep_approval_separate(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = Path(directory)
            mission = workspace / "mission.json"
            source = workspace / "data.json"
            response_path = workspace / "response.json"
            mission.write_text('{"confirmed":false,"objective":"diagnose"}', encoding="utf-8")
            source.write_text('{"revenue":"10"}', encoding="utf-8")
            response_path.write_text(json.dumps({
                "response_type": "confirm",
                "payload": {},
                "actor_id": "ceo-1",
            }), encoding="utf-8")
            artifact_root = workspace / "artifacts"
            _, started = self.call([
                "start", "--artifact-root", str(artifact_root),
                "--mission-contract", str(mission), "--input", str(source),
                "--run-owner-actor-id", "ceo-1",
            ])
            run_id = started["run_id"]
            store = ArtifactStore(artifact_root)
            store.open_run(run_id)
            pointer_before = (artifact_root / run_id / "state.json").read_bytes()

            code, pending = self.call([
                "pending-action", "--artifact-root", str(artifact_root), "--run-id", run_id,
            ])
            self.assertEqual(2, code)
            self.assertEqual(pointer_before, (artifact_root / run_id / "state.json").read_bytes())
            card = pending["data"]["action"]

            code, preview = self.call([
                "preview-human-response", "--artifact-root", str(artifact_root),
                "--run-id", run_id, "--expected-revision", "1",
                "--action-id", card["action_id"],
                "--action-content-hash", card["content_hash"],
                "--response", str(response_path),
            ])
            self.assertEqual(0, code)
            self.assertEqual(1, preview["revision"])
            self.assertEqual(1, store.state()["revision"])

            args = [
                "submit-human-response", "--artifact-root", str(artifact_root),
                "--run-id", run_id, "--expected-revision", "1",
                "--action-id", card["action_id"],
                "--action-content-hash", card["content_hash"],
                "--response", str(response_path), "--idempotency-key", "browser-submit-1",
            ]
            code, submitted = self.call(args)
            self.assertEqual(2, code)
            self.assertEqual(2, submitted["revision"])
            self.assertTrue(submitted["data"]["receipt"]["terminal_approval_required"])
            files = store.verify_revision(2)
            self.assertFalse((files / "approvals" / "records").exists())

            pending_code, after_submit = self.call([
                "pending-action", "--artifact-root", str(artifact_root), "--run-id", run_id,
            ])
            self.assertEqual(0, pending_code, after_submit)
            self.assertIsNone(after_submit["data"]["action"])

            retry_code, retried = self.call(args)
            self.assertEqual(2, retry_code)
            self.assertEqual(submitted["data"], retried["data"])
            self.assertEqual(2, store.state()["revision"])

    def test_production_submit_fails_closed_before_publishing_invalid_overlay(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = Path(directory)
            mission = workspace / "mission.json"
            source = workspace / "data.json"
            response_path = workspace / "response.json"
            mission.write_text('{"confirmed":false,"objective":"diagnose"}', encoding="utf-8")
            source.write_text('{"revenue":"10"}', encoding="utf-8")
            response_path.write_text(json.dumps({
                "response_type": "request_changes",
                "payload": {
                    "text": "Invalid typed overlay",
                    "patch_operations": [{
                        "op": "add",
                        "path": "/mission_contract/business_question",
                        "value": ["must", "be", "a", "string"],
                    }],
                },
                "actor_id": "ceo-1",
            }), encoding="utf-8")
            artifact_root = workspace / "artifacts"
            _, started = self.call([
                "start", "--artifact-root", str(artifact_root),
                "--mission-contract", str(mission), "--input", str(source),
                "--run-owner-actor-id", "ceo-1",
            ])
            run_id = started["run_id"]
            _, pending = self.call([
                "pending-action", "--artifact-root", str(artifact_root), "--run-id", run_id,
            ])
            card = pending["data"]["action"]
            code, rejected = self.call([
                "submit-human-response", "--artifact-root", str(artifact_root),
                "--run-id", run_id, "--expected-revision", "1",
                "--action-id", card["action_id"],
                "--action-content-hash", card["content_hash"],
                "--response", str(response_path), "--idempotency-key", "invalid-overlay-1",
            ])
            self.assertEqual(3, code)
            self.assertFalse(rejected["ok"])
            store = ArtifactStore(artifact_root)
            store.open_run(run_id)
            self.assertEqual(1, store.state()["revision"])
            files = store.verify_revision(1)
            self.assertFalse((files / "workflow" / "human-responses").exists())


if __name__ == "__main__":
    unittest.main()
