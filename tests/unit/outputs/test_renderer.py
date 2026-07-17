import unittest

from trusted_ceo_agent.outputs.render import render_ceo_brief, render_package


class RendererTests(unittest.TestCase):
    def test_all_priority_issues_are_rendered_without_top_n_cutoff(self) -> None:
        result = {
            "run_summary": {"run_id": "run_x", "revision": 4},
            "mission_summary": {},
            "capability_summary": {},
            "issues": [
                {
                    "issue_id": f"issue_{index}",
                    "title_template": f"Issue {index}",
                    "primary_grade": "Decision Required",
                    "secondary_flags": [],
                    "why_it_matters_template": "Evidence-backed.",
                    "value_refs": [],
                    "evidence_link_ids": [],
                    "cause_hypotheses": [],
                    "counter_hypotheses": [],
                    "unresolved_conflicts": [],
                    "verification_next_steps": [],
                    "conditional_response_refs": [],
                    "expert_review_refs": [],
                }
                for index in range(5)
            ],
            "cross_issue_relations": [],
            "conditional_responses": [],
            "monitoring": [],
            "blind_spots": [],
            "expert_review_packets": [],
            "approvals": [],
            "integrity": {"semantic_fingerprint": "a" * 64},
        }
        brief = render_ceo_brief(result)
        self.assertEqual(5, brief.count("## Issue"))

    def test_render_is_byte_equivalent_and_has_no_internal_files(self) -> None:
        result = {
            "run_summary": {"run_id": "run_x", "revision": 4},
            "mission_summary": {}, "capability_summary": {}, "issues": [],
            "cross_issue_relations": [], "conditional_responses": [],
            "monitoring": [], "blind_spots": [], "expert_review_packets": [],
            "approvals": [], "integrity": {"semantic_fingerprint": "a" * 64},
        }
        first = render_package(result)
        second = render_package(result)
        self.assertEqual(first, second)
        self.assertNotIn("sources/resolver.json", first)
        self.assertFalse(any("draft" in path for path in first))


if __name__ == "__main__":
    unittest.main()
