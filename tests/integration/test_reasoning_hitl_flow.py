import unittest

from trusted_ceo_agent.grading.grader import grade
from trusted_ceo_agent.reasoning.join import freeze_join_manifest, reduce_join
from trusted_ceo_agent.workflow.state_machine import transition


class ReasoningHitlFlowTests(unittest.TestCase):
    def test_join_diagnostic_approval_and_grade_vertical_slice(self) -> None:
        manifest = freeze_join_manifest(
            "artifact_1", "a" * 64, "b" * 64,
            [{"job_id": "job_1", "required": True, "required_signal_ids": []}],
            "2026-07-17T00:00:00Z",
        )
        joined = reduce_join(manifest, [{"job_id": "job_1", "status": "valid_not_assessable", "card": {
            "card_id": "card_1", "job_id": "job_1", "artifact_ref": "artifact_1", "pack_manifest_hash": "b" * 64,
            "normalized_payload": {"signal_dispositions": [], "problem_candidates": []},
        }}])
        self.assertEqual(["card_1"], joined["card_refs"])
        state = transition({"status": "integrated_draft", "revision": 4}, "request_diagnostic_approval", {"issues_valid": True})
        state = transition(state, "approve_diagnostic", {"approval_valid": True, "deep_scope_empty": True})
        self.assertEqual("finalization_jobs_ready", state["status"])
        record = grade({
            "issue_id": "issue_1", "assessability": "partial", "not_assessable_reason_codes": ["missing_contract_data"],
            "evidence_state": "limited", "impact_band": "unknown", "urgency_band": "unknown",
            "mission_priority_match": False, "executive_materiality": "unknown", "decision_needed": False,
            "expert_trigger_state": "none", "pack_authority": "full", "diagnostic_disposition": "accepted",
            "verification_authorized": False, "issue_disposition": "standalone", "trackable": False,
            "response_eligibility": "prohibited", "provenance_refs": ["card_1"],
        })
        self.assertEqual("Not Assessable", record["primary_grade"])


if __name__ == "__main__":
    unittest.main()
