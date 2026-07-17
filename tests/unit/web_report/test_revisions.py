from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from trusted_ceo_agent.web_report.canonical import jcs_sha256
from trusted_ceo_agent.web_report.revisions import build_revision_artifacts


ROOT = Path(__file__).resolve().parents[3]
RUN_ID = "run_20260717T010203Z_0123456789abcdef"


def result(fingerprint: str, *, title: str, include_second: bool) -> dict:
    issues = [{"issue_id": "issue_a", "title_template": title}]
    if include_second:
        issues.append({"issue_id": "issue_b", "title_template": "추가 문제"})
    return {
        "issues": issues,
        "cross_issue_relations": [],
        "conditional_responses": [],
        "monitoring": [],
        "blind_spots": [],
        "expert_review_packets": [],
        "integrity": {"semantic_fingerprint": fingerprint},
    }


class RevisionArtifactsTests(unittest.TestCase):
    def test_ancestry_previous_final_and_stable_id_diff_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            store = ArtifactStore(Path(directory) / "artifacts")
            store.create_run(RUN_ID)
            files = {
                "workflow/state.json": canonical_bytes(
                    {"run_id": RUN_ID, "revision": 1, "state": "created"}
                ),
                "audit/events/r0001-start.json": canonical_bytes(
                    {"command": "start", "from_revision": 0, "to_revision": 1}
                ),
            }
            store.publish(0, files)
            files["workflow/state.json"] = canonical_bytes(
                {"run_id": RUN_ID, "revision": 2, "state": "finalized"}
            )
            files["final/result.json"] = canonical_bytes(
                result("a" * 64, title="기존 문제", include_second=False)
            )
            store.publish(1, files)
            files["workflow/state.json"] = canonical_bytes(
                {"run_id": RUN_ID, "revision": 3, "state": "created"}
            )
            files.pop("final/result.json")
            files["audit/events/r0003-resume.json"] = canonical_bytes(
                {"command": "resume", "from_revision": 2, "to_revision": 3}
            )
            store.publish(2, files)
            files["workflow/state.json"] = canonical_bytes(
                {"run_id": RUN_ID, "revision": 4, "state": "finalized"}
            )
            files["final/result.json"] = canonical_bytes(
                result("b" * 64, title="변경된 문제", include_second=True)
            )
            store.publish(3, files)

            artifacts = build_revision_artifacts(store, current_revision=4)

            manifests = []
            for revision in range(1, 5):
                snapshot = store.verify_revision(revision)
                manifest = strict_loads(
                    (snapshot / "snapshot-manifest.json").read_bytes()
                )
                manifests.append(
                    {
                        "revision": revision,
                        "manifest_hash": manifest["manifest_hash"],
                    }
                )
            self.assertEqual(
                jcs_sha256({"manifests": manifests}),
                artifacts.revision_ancestry_hash,
            )
            self.assertTrue(artifacts.revision_view["available"])
            self.assertEqual(2, artifacts.revision_view["base_revision"])
            self.assertEqual(4, artifacts.revision_view["compare_revision"])
            self.assertIn("issue_a", artifacts.revision_view["changed_refs"])
            self.assertIn("issue_b", artifacts.revision_view["added_refs"])

    def test_no_previous_final_is_explicit_and_not_synthesized(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            store = ArtifactStore(Path(directory) / "artifacts")
            store.create_run(RUN_ID)
            store.publish(
                0,
                {
                    "final/result.json": canonical_bytes(
                        result("c" * 64, title="첫 결과", include_second=False)
                    )
                },
            )

            artifacts = build_revision_artifacts(store, current_revision=1)

            view = artifacts.revision_view
            self.assertFalse(view["available"])
            self.assertEqual("NO_PRIOR_FINAL_RESULT", view["unavailable_reason"])
            self.assertIsNone(view["base_revision"])
            self.assertEqual([], view["changed_refs"])


if __name__ == "__main__":
    unittest.main()
