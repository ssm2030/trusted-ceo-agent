import unittest

from trusted_ceo_agent.outputs.final_result import build_final_result
from trusted_ceo_agent.outputs.validation import FinalValidationError


def issue(issue_id: str, grade: str = "Decision Required") -> dict:
    return {
        "issue_id": issue_id,
        "title_template": f"Issue {issue_id}",
        "primary_grade": grade,
        "secondary_flags": [],
        "why_it_matters_template": "Material issue supported by evidence.",
        "value_refs": ["fact_revenue"],
        "evidence_link_ids": [f"link_{issue_id}"],
        "cause_hypotheses": [],
        "counter_hypotheses": [],
        "unresolved_conflicts": [],
        "verification_next_steps": [],
        "conditional_response_refs": [],
        "expert_review_refs": [],
        "disposition": "accepted",
    }


class FinalResultTests(unittest.TestCase):
    def test_missing_material_evidence_is_rejected(self) -> None:
        with self.assertRaises(FinalValidationError):
            build_final_result(
                run_summary={"run_id": "run_x", "revision": 4},
                mission_summary={"objective": "diagnose"},
                capability_summary={"status": "sufficient"},
                issues=[issue("a")],
                evidence_links={},
                approvals=[{"gate": "final", "status": "current"}],
            )

    def test_rejected_issue_is_not_active(self) -> None:
        rejected = issue("a")
        rejected["disposition"] = "rejected"
        result = build_final_result(
            run_summary={"run_id": "run_x", "revision": 4},
            mission_summary={"objective": "diagnose"},
            capability_summary={"status": "sufficient"},
            issues=[rejected],
            evidence_links={},
            approvals=[{"gate": "final", "status": "current"}],
        )
        self.assertEqual([], result["issues"])


if __name__ == "__main__":
    unittest.main()

