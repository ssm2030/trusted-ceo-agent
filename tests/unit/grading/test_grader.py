import unittest

from trusted_ceo_agent.grading.grader import GradeRuleUncovered, InvalidGradingInput, grade
from trusted_ceo_agent.grading.reducer import determine_evidence_state


def grading_input(**changes) -> dict:
    value = {
        "issue_id": "issue_001",
        "assessability": "assessable",
        "not_assessable_reason_codes": [],
        "evidence_state": "sufficient",
        "impact_band": "high",
        "urgency_band": "near_term",
        "mission_priority_match": False,
        "executive_materiality": True,
        "decision_needed": True,
        "expert_trigger_state": "none",
        "pack_authority": "full",
        "diagnostic_disposition": "accepted",
        "verification_authorized": False,
        "issue_disposition": "standalone",
        "trackable": True,
        "response_eligibility": "eligible",
        "provenance_refs": ["evidence_001"],
    }
    value.update(changes)
    return value


class EvidenceStateTests(unittest.TestCase):
    def test_precedence_is_none_conflict_independence_then_required_checks(self) -> None:
        self.assertEqual("none", determine_evidence_state([], True, 2, 1, True, True, True))
        self.assertEqual("conflicting", determine_evidence_state(["g1"], True, 2, 1, True, True, True))
        self.assertEqual("limited", determine_evidence_state(["g1"], False, 2, 1, True, True, True))
        self.assertEqual("limited", determine_evidence_state(["g1"], False, 1, 1, False, True, True))
        self.assertEqual("sufficient", determine_evidence_state(["g1"], False, 1, 1, True, True, True))


class GraderTests(unittest.TestCase):
    def test_core_rule_order_and_provisional_cap(self) -> None:
        self.assertEqual("Decision Required", grade(grading_input())["primary_grade"])
        provisional = grade(grading_input(pack_authority="provisional"))
        self.assertEqual("Immediate Verification", provisional["primary_grade"])
        self.assertTrue(provisional["authority_cap_applied"])
        boundary = grade(grading_input(pack_authority="boundary", expert_trigger_state="required"))
        self.assertEqual("Not Assessable", boundary["primary_grade"])
        self.assertIn("unsupported_domain", boundary["reason_codes"])

    def test_pending_rejected_and_unapproved_dispute_are_withheld(self) -> None:
        for disposition in ("pending", "rejected"):
            with self.subTest(disposition=disposition):
                record = grade(grading_input(diagnostic_disposition=disposition))
                self.assertEqual("withheld", record["publication_status"])
                self.assertNotIn("primary_grade", record)
        disputed = grade(grading_input(diagnostic_disposition="disputed", verification_authorized=False, decision_needed="unknown"))
        self.assertEqual("withheld", disputed["publication_status"])

    def test_expert_required_and_secondary_flags(self) -> None:
        record = grade(grading_input(expert_trigger_state="required"))
        self.assertEqual("Expert Review Required", record["primary_grade"])
        self.assertIn("executive_decision_after_expert_review", record["secondary_flags"])
        possible = grade(grading_input(expert_trigger_state="possible"))
        self.assertIn("possible_expert_review", possible["secondary_flags"])

    def test_unknown_and_uncovered_do_not_fall_back_silently(self) -> None:
        record = grade(grading_input(impact_band="unknown", not_assessable_reason_codes=["impact_unknown"]))
        self.assertEqual("Not Assessable", record["primary_grade"])
        with self.assertRaises(InvalidGradingInput):
            grade(grading_input(impact_band="unknown"))
        with self.assertRaises(InvalidGradingInput):
            grade(grading_input(decision_needed="unknown", diagnostic_disposition="accepted"))
        with self.assertRaises(GradeRuleUncovered):
            grade(grading_input(executive_materiality=False, trackable=False))


if __name__ == "__main__":
    unittest.main()
