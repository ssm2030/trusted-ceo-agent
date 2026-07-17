from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.errors import ContractError, RevisionConflict
from trusted_ceo_agent.knowledge.foundry import build_release_candidate
from trusted_ceo_agent.knowledge.foundry import submit_feedback
from trusted_ceo_agent.knowledge.release import (
    build_knowledge_approval_request,
    record_knowledge_approval,
)

from tests.foundry_support import (
    T0,
    all_green_gates,
    make_candidate,
    make_initial_release,
    make_patch,
    make_preview,
)


class FoundryApprovalBoundaryTests(unittest.TestCase):
    def test_approval_is_bound_to_hash_revision_role_nonce_and_expiry(self):
        preview = make_preview()
        request = build_knowledge_approval_request(
            approval_stage="feedback_submit",
            object_id=preview["preview_id"],
            object_hash=preview["preview_hash"],
            expected_revision=3,
            requested_action="submit_feedback",
            requested_by="user_001",
            required_role="feedback_submitter",
            requested_at=T0,
            expires_at="2026-07-17T00:10:00Z",
            nonce="nonce-one",
        )
        cases = (
            ({"object_hash": "f" * 64}, ContractError, "object hash"),
            ({"current_revision": 4}, RevisionConflict, "stale"),
            ({"approver_role": "viewer"}, ContractError, "role"),
            ({"nonce": "wrong"}, ContractError, "nonce"),
            ({"approved_at": "2026-07-17T00:11:00Z"}, ContractError, "expired"),
        )
        defaults = {
            "object_id": preview["preview_id"],
            "object_hash": preview["preview_hash"],
            "current_revision": 3,
            "approved_by": "user_001",
            "approver_role": "feedback_submitter",
            "nonce": "nonce-one",
            "approved_at": "2026-07-17T00:05:00Z",
        }
        for overrides, error, message in cases:
            with self.subTest(message=message):
                kwargs = {**defaults, **overrides}
                with self.assertRaisesRegex(error, message):
                    record_knowledge_approval(request, **kwargs)

    def test_stage_and_action_cannot_be_mixed(self):
        preview = make_preview()
        with self.assertRaisesRegex(ContractError, "stage.*action"):
            build_knowledge_approval_request(
                approval_stage="feedback_submit",
                object_id=preview["preview_id"],
                object_hash=preview["preview_hash"],
                expected_revision=1,
                requested_action="deploy_release",
                requested_by="user_001",
                required_role="feedback_submitter",
                requested_at=T0,
                expires_at="2026-07-17T01:00:00Z",
                nonce="nonce-two",
            )

    def test_unreproduced_failure_cannot_become_patch(self):
        with self.assertRaisesRegex(ContractError, "reproduced"):
            make_patch(reproduction_result="not_reproducible")

    def test_stage1_approval_cannot_fork_feedback_with_another_timestamp(self):
        from tests.foundry_support import make_feedback

        preview, _, approval, _, _ = make_feedback()
        with self.assertRaisesRegex(ContractError, "approval time"):
            submit_feedback(
                preview,
                approval,
                current_revision=1,
                submitted_at="2026-07-17T00:06:00Z",
            )

    def test_professional_patch_cannot_downgrade_required_roles(self):
        from trusted_ceo_agent.knowledge.foundry import build_patch_proposal
        from tests.foundry_support import make_feedback, make_regression, reproduction, structured_content

        _, _, _, feedback, _ = make_feedback()
        regression = make_regression(feedback)
        with self.assertRaisesRegex(ContractError, "required Stage 2 roles"):
            build_patch_proposal(
                feedback_records=[feedback],
                reproduction=reproduction(),
                failure_type="procedure",
                root_cause="A professional procedure omitted a required check.",
                target_artifacts=[{
                    "artifact_ref": "procedure/professional@1",
                    "artifact_hash": "d" * 64,
                    "artifact_type": "procedure",
                }],
                before_semantics=structured_content(),
                after_semantics=structured_content(),
                source_refs=["official_source_001"],
                affected_issue_family_ids=["AC-REV-01"],
                affected_domains=["accounting"],
                risk_classification="high",
                regression_cases=[regression],
                expected_behavior_changes=["Add the required check."],
                forbidden_side_effects=["No unrelated behavior changes."],
                rollback_conditions=["Regression escape."],
                required_stage2_roles=["maintainer"],
                created_at="2026-07-17T00:05:00Z",
            )

    def test_failed_release_gate_and_missing_stage2_approval_block_candidate(self):
        base, regression, patch, _, approvals, _ = make_candidate()
        with self.assertRaisesRegex(ContractError, "full_regression"):
            build_release_candidate(
                base_release=base,
                patches=[patch],
                regression_cases=[regression],
                stage2_approvals=approvals,
                expected_revision=3,
                artifact_manifest=copy.deepcopy(base["artifact_manifest"]),
                gate_results=all_green_gates(full_regression_passed=False),
                coverage_exception_approval_ref=None,
                rollback_release_id=base["release_id"],
                rollback_release_hash=base["release_hash"],
                created_at="2026-07-17T00:05:00Z",
            )
        with self.assertRaisesRegex(ContractError, "Stage 2"):
            build_release_candidate(
                base_release=make_initial_release(),
                patches=[patch],
                regression_cases=[regression],
                stage2_approvals=[],
                expected_revision=3,
                artifact_manifest=copy.deepcopy(base["artifact_manifest"]),
                gate_results=all_green_gates(),
                coverage_exception_approval_ref=None,
                rollback_release_id=base["release_id"],
                rollback_release_hash=base["release_hash"],
                created_at="2026-07-17T00:05:00Z",
            )


if __name__ == "__main__":
    unittest.main()
