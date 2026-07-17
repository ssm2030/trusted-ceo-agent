from __future__ import annotations

import unittest

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.knowledge.foundry import build_patch_proposal, build_regression_case

from tests.foundry_support import (
    HASH_C,
    T1,
    make_feedback,
    make_preview,
    privacy,
    reproduction,
    structured_content,
)


class FeedbackPrivacyTests(unittest.TestCase):
    def test_direct_identifier_and_hidden_reasoning_are_rejected_before_preview(self):
        with self.assertRaisesRegex(ContractError, "direct identifier"):
            make_preview(content=structured_content(facts=["Email jane@example.com complained."]))
        with self.assertRaisesRegex(ContractError, "structured_content"):
            make_preview(content=structured_content(chain_of_thought=["secret reasoning"]))

    def test_personal_data_must_be_deidentified(self):
        with self.assertRaisesRegex(ContractError, "deidentified"):
            make_preview(privacy_value=privacy(
                contains_personal_data=True,
                deidentification_status="raw",
            ))

    def test_real_regression_fixture_requires_consent_and_deidentification(self):
        _, _, _, feedback, _ = make_feedback()
        with self.assertRaisesRegex(ContractError, "consent"):
            build_regression_case(
                source_feedback_refs=[{
                    "feedback_id": feedback["feedback_id"],
                    "feedback_hash": feedback["feedback_hash"],
                }],
                fixture_kind="deidentified_real",
                fixture_ref="fixtures/restricted.json",
                fixture_hash=HASH_C,
                consent_ref=None,
                expected=structured_content(),
                negative_control_refs=["normal_001"],
                counterexample_refs=["counter_001"],
                created_at=T1,
            )

        with self.assertRaisesRegex(ContractError, "trusted consent"):
            build_regression_case(
                source_feedback_refs=[{
                    "feedback_id": feedback["feedback_id"],
                    "feedback_hash": feedback["feedback_hash"],
                }],
                fixture_kind="deidentified_real",
                fixture_ref="fixtures/restricted.json",
                fixture_hash=HASH_C,
                consent_ref="consent_unverified_001",
                expected=structured_content(),
                negative_control_refs=["normal_001"],
                counterexample_refs=["counter_001"],
                created_at=T1,
            )

    def test_feedback_from_different_tenants_cannot_share_a_patch(self):
        _, _, _, feedback_a, _ = make_feedback(tenant_id="tenant_alpha")
        _, _, _, feedback_b, _ = make_feedback(tenant_id="tenant_beta")
        regression = build_regression_case(
            source_feedback_refs=[{
                "feedback_id": feedback_a["feedback_id"],
                "feedback_hash": feedback_a["feedback_hash"],
            }],
            fixture_kind="synthetic",
            fixture_ref="fixtures/synthetic.json",
            fixture_hash=HASH_C,
            consent_ref=None,
            expected=structured_content(),
            negative_control_refs=["normal_001"],
            counterexample_refs=["counter_001"],
            created_at=T1,
        )
        with self.assertRaisesRegex(ContractError, "tenant"):
            build_patch_proposal(
                feedback_records=[feedback_a, feedback_b],
                reproduction=reproduction(),
                failure_type="procedure",
                root_cause="A deterministic procedure was missing.",
                target_artifacts=[{
                    "artifact_ref": "procedure/test@1",
                    "artifact_hash": "d" * 64,
                    "artifact_type": "procedure",
                }],
                before_semantics=structured_content(),
                after_semantics=structured_content(),
                source_refs=["source_001"],
                affected_issue_family_ids=["AC-REV-01"],
                affected_domains=["accounting"],
                risk_classification="high",
                regression_cases=[regression],
                expected_behavior_changes=["Change one procedure."],
                forbidden_side_effects=["No unrelated change."],
                rollback_conditions=["Regression failure."],
                required_stage2_roles=["domain_expert"],
                created_at=T1,
            )


if __name__ == "__main__":
    unittest.main()
