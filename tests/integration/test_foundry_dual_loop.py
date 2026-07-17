from __future__ import annotations

import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.knowledge.foundry import submit_feedback
from trusted_ceo_agent.knowledge.release import ReleaseRegistry

from tests.foundry_support import make_candidate, make_feedback, make_stage3


class FoundryDualLoopTests(unittest.TestCase):
    def test_feedback_patch_candidate_and_deploy_are_three_distinct_mutations(self):
        _, _, stage1, feedback, receipt = make_feedback()
        self.assertEqual("submitted", feedback["status"])
        self.assertEqual(2, receipt["accepted_revision"])
        self.assertNotIn("patch_id", feedback)

        base, _, patch, _, stage2, candidate = make_candidate()
        self.assertEqual("approved_for_candidate", candidate["status"])
        self.assertEqual(2, len(stage2))
        self.assertNotEqual(base["release_id"], candidate["candidate_id"])

        registry = ReleaseRegistry(base)
        registry.start_run("run_before_deploy")
        self.assertEqual(base["release_id"], registry.active_release_id)

        _, stage3 = make_stage3(candidate)
        release = registry.deploy(candidate, stage3, current_revision=4)
        self.assertEqual(release["release_id"], registry.active_release_id)
        self.assertEqual(
            base["release_id"], registry.release_for_run("run_before_deploy")["release_id"]
        )
        self.assertEqual(
            release["release_id"], registry.start_run("run_after_deploy")["release_id"]
        )
        self.assertEqual("feedback_submit", stage1["approval_stage"])

    def test_same_feedback_submission_is_byte_deterministic(self):
        preview, _, approval, feedback, receipt = make_feedback()
        duplicate_feedback, duplicate_receipt = submit_feedback(
            preview,
            approval,
            current_revision=1,
            submitted_at="2026-07-17T00:05:00Z",
        )
        self.assertEqual(canonical_bytes(feedback), canonical_bytes(duplicate_feedback))
        self.assertEqual(canonical_bytes(receipt), canonical_bytes(duplicate_receipt))

    def test_rerun_uses_new_release_without_rewriting_original_run(self):
        base, _, _, _, _, candidate = make_candidate()
        registry = ReleaseRegistry(base)
        original = registry.start_run("run_original")
        _, stage3 = make_stage3(candidate)
        deployed = registry.deploy(candidate, stage3, current_revision=4)
        relation = registry.rerun("run_original", "run_rerun")
        self.assertEqual(base["release_id"], original["release_id"])
        self.assertEqual(base["release_id"], registry.release_for_run("run_original")["release_id"])
        self.assertEqual(deployed["release_id"], registry.release_for_run("run_rerun")["release_id"])
        self.assertEqual("run_original", relation["rerun_of"])


if __name__ == "__main__":
    unittest.main()
