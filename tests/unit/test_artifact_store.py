import json
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
