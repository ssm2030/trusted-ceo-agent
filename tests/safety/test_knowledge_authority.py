from __future__ import annotations

import unittest

from trusted_ceo_agent.knowledge.depth_gate import assess_professional_depth

from tests.professional_knowledge_support import make_knowledge_bundle


class KnowledgeAuthoritySafetyTests(unittest.TestCase):
    def test_unapproved_source_and_revoked_release_have_zero_activation(self):
        family, cards, expert, release = make_knowledge_bundle(source_approved=False)
        unapproved = assess_professional_depth(
            family,
            cards,
            effective_on="2026-06-30",
            jurisdiction="KR",
            industry_scope="b2b_services",
            expert_approval=expert,
            release=release,
        )
        self.assertFalse(unapproved["activation_allowed"])
        self.assertEqual("machine_draft", unapproved["effective_authority"])
        self.assertTrue(
            any(value.startswith("source_unapproved:") for value in unapproved["blockers"])
        )

        family, cards, expert, release = make_knowledge_bundle()
        release["status"] = "revoked"
        revoked = assess_professional_depth(
            family,
            cards,
            effective_on="2026-06-30",
            jurisdiction="KR",
            industry_scope="b2b_services",
            expert_approval=expert,
            release=release,
        )
        self.assertFalse(revoked["activation_allowed"])
        self.assertIn("knowledge_release_revoked", revoked["blockers"])

    def test_expert_scope_mismatch_cannot_authorize_full(self):
        family, cards, expert, release = make_knowledge_bundle()
        expert["domain"] = "legal"
        assessment = assess_professional_depth(
            family,
            cards,
            effective_on="2026-06-30",
            jurisdiction="KR",
            industry_scope="b2b_services",
            expert_approval=expert,
            release=release,
        )
        self.assertFalse(assessment["full_allowed"])
        self.assertEqual("provisional", assessment["effective_authority"])
        self.assertIn("expert_domain_mismatch", assessment["blockers"])


if __name__ == "__main__":
    unittest.main()
