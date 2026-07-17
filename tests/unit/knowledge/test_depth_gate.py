from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.knowledge.compiler import DEPTH_SLOT_TYPES
from trusted_ceo_agent.knowledge.depth_gate import assess_professional_depth, require_authority

from tests.professional_knowledge_support import make_knowledge_bundle


class ProfessionalDepthGateTests(unittest.TestCase):
    def test_full_requires_all_twelve_typed_slots_and_all_authorities(self):
        family, cards, expert, release = make_knowledge_bundle()
        assessment = assess_professional_depth(
            family,
            cards,
            effective_on="2026-06-30",
            jurisdiction="KR",
            industry_scope="b2b_services",
            expert_approval=expert,
            release=release,
        )
        self.assertTrue(assessment["activation_allowed"])
        self.assertTrue(assessment["full_allowed"])
        self.assertEqual("full", assessment["effective_authority"])
        require_authority(assessment, "full")

        for slot_id in DEPTH_SLOT_TYPES:
            incomplete = copy.deepcopy(family)
            incomplete["depth_slots"].pop(slot_id)
            blocked = assess_professional_depth(
                incomplete,
                cards,
                effective_on="2026-06-30",
                jurisdiction="KR",
                industry_scope="b2b_services",
                expert_approval=expert,
                release=release,
            )
            self.assertFalse(blocked["activation_allowed"], slot_id)
            self.assertIn(f"missing_depth_slot:{slot_id}", blocked["blockers"])

    def test_lowest_authority_wins_and_expert_absence_never_allows_full(self):
        family, cards, _, release = make_knowledge_bundle(pack_authority="boundary")
        assessment = assess_professional_depth(
            family,
            cards,
            effective_on="2026-06-30",
            jurisdiction="KR",
            industry_scope="b2b_services",
            expert_approval=None,
            release=release,
        )
        self.assertTrue(assessment["activation_allowed"])
        self.assertFalse(assessment["full_allowed"])
        self.assertEqual("boundary", assessment["effective_authority"])
        self.assertIn("expert_approval_missing", assessment["blockers"])
        with self.assertRaisesRegex(ContractError, "exceeds effective authority"):
            require_authority(assessment, "full")

    def test_assessment_is_deterministic_and_tamper_fails_closed(self):
        family, cards, expert, release = make_knowledge_bundle()
        first = assess_professional_depth(
            family,
            cards,
            effective_on="2026-06-30",
            jurisdiction="KR",
            industry_scope="b2b_services",
            expert_approval=expert,
            release=release,
        )
        second = assess_professional_depth(
            family,
            list(reversed(cards)),
            effective_on="2026-06-30",
            jurisdiction="KR",
            industry_scope="b2b_services",
            expert_approval=expert,
            release=release,
        )
        self.assertEqual(canonical_bytes(first), canonical_bytes(second))

        tampered = copy.deepcopy(cards)
        tampered[0]["content"]["review_sequence"].append("unhashed mutation")
        blocked = assess_professional_depth(
            family,
            tampered,
            effective_on="2026-06-30",
            jurisdiction="KR",
            industry_scope="b2b_services",
            expert_approval=expert,
            release=release,
        )
        self.assertFalse(blocked["activation_allowed"])
        self.assertTrue(
            any(value.startswith("knowledge_artifact_contract_invalid:") for value in blocked["blockers"])
        )


if __name__ == "__main__":
    unittest.main()
