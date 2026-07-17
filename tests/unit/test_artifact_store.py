import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trusted_ceo_agent.errors import RevisionConflict
from trusted_ceo_agent.trust.artifact_store import ArtifactStore


class ArtifactStoreTests(unittest.TestCase):
    def test_publish_requires_current_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory))
            store.create_run("run_20260717T000000Z_0123456789abcdef")
            store.publish(0, {"evidence/core.json": b"{}"})
            with self.assertRaises(RevisionConflict):
                store.publish(0, {"evidence/core.json": b"{}"})

    def test_manifest_covers_every_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory))
            store.create_run("run_20260717T000000Z_0123456789abcdef")
            revision = store.publish(0, {"b.json": b"{}", "a.txt": b"x"})
            manifest = json.loads((revision / "snapshot-manifest.json").read_text("utf-8"))
            self.assertEqual(["a.txt", "b.json"], [item["path"] for item in manifest["files"]])

    def test_transient_snapshot_replace_denial_retries_without_losing_atomicity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory))
            store.create_run("run_20260717T000000Z_0123456789abcdef")
            real_replace = os.replace
            snapshot_attempts = 0

            def transient_replace(source, target):
                nonlocal snapshot_attempts
                if Path(source).name.startswith(".staging-r"):
                    snapshot_attempts += 1
                    if snapshot_attempts == 1:
                        raise PermissionError(5, "transient snapshot lock")
                return real_replace(source, target)

            with (
                patch(
                    "trusted_ceo_agent.filesystem.os.replace",
                    side_effect=transient_replace,
                ),
                patch("trusted_ceo_agent.filesystem.time.sleep") as sleep,
            ):
                revision = store.publish(0, {"evidence/core.json": b"{}"})

            self.assertEqual("r0001", revision.name)
            self.assertEqual(2, snapshot_attempts)
            sleep.assert_called_once_with(0.01)
            self.assertEqual(1, store.state()["revision"])

    def test_transient_state_replace_denial_uses_common_atomic_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory))
            store.create_run("run_20260717T000000Z_0123456789abcdef")
            real_replace = os.replace
            state_attempts = 0

            def transient_replace(source, target):
                nonlocal state_attempts
                if Path(target).name == "state.json":
                    state_attempts += 1
                    if state_attempts == 1:
                        raise PermissionError(5, "transient state lock")
                return real_replace(source, target)

            with (
                patch(
                    "trusted_ceo_agent.filesystem.os.replace",
                    side_effect=transient_replace,
                ),
                patch("trusted_ceo_agent.filesystem.time.sleep") as sleep,
            ):
                revision = store.publish(0, {"evidence/core.json": b"{}"})

            self.assertEqual("r0001", revision.name)
            self.assertEqual(2, state_attempts)
            sleep.assert_called_once_with(0.01)
            self.assertEqual(1, store.state()["revision"])


if __name__ == "__main__":
    unittest.main()
