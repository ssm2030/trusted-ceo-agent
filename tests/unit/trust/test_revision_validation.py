from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from trusted_ceo_agent.trust.revision_validation import (
    RevisionValidation,
    validate_revision,
)


ROOT = Path(__file__).resolve().parents[3]
RUN_ID = "run_20260717T010203Z_0123456789abcdef"


class RevisionValidationTests(unittest.TestCase):
    def test_grading_revalidation_receives_native_integral_numbers(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            store = ArtifactStore(Path(directory) / "artifacts")
            store.create_run(RUN_ID)
            store.publish(
                0,
                {
                    "grading/inputs.json": b'[{"issue_id":"issue_1","threshold":2}]',
                    "grading/records/issue_1.json": (
                        b'{"issue_id":"issue_1","threshold":2}'
                    ),
                },
            )

            def regrade(value: dict) -> dict:
                self.assertIsInstance(value["threshold"], int)
                return dict(value)

            with (
                patch(
                    "trusted_ceo_agent.trust.revision_validation.validate_snapshot_files"
                ),
                patch(
                    "trusted_ceo_agent.trust.revision_validation.grade",
                    side_effect=regrade,
                ),
            ):
                validate_revision(store, 1)

    def test_verified_revision_returns_manifest_files_and_checks(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            store = ArtifactStore(Path(directory) / "artifacts")
            store.create_run(RUN_ID)
            store.publish(0, {"notes/readme.txt": b"immutable"})

            with patch(
                "trusted_ceo_agent.trust.revision_validation.validate_snapshot_files"
            ):
                result = validate_revision(store, 1)

            self.assertIsInstance(result, RevisionValidation)
            self.assertEqual(1, result.revision)
            self.assertEqual(b"immutable", result.files["notes/readme.txt"])
            self.assertEqual(1, result.snapshot_manifest["revision"])
            self.assertIn("snapshot_manifest", result.checks)
            self.assertIn("full_snapshot_contracts", result.checks)


if __name__ == "__main__":
    unittest.main()
