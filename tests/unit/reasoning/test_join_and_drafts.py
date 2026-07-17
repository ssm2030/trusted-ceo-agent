import copy
import unittest

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.reasoning.join import JoinBlocked, freeze_join_manifest, reduce_join
from trusted_ceo_agent.reasoning.stage_drafts import (
    normalize_deep_dive_draft,
    normalize_integrated_draft,
    normalize_writer_draft,
)


class JoinTests(unittest.TestCase):
    def manifest(self) -> dict:
        return freeze_join_manifest(
            artifact_ref="artifact_001",
            mission_contract_hash="a" * 64,
            pack_manifest_hash="b" * 64,
            cutoff_at="2026-07-17T00:00:00Z",
            tasks=[
                {"job_id": "job_b", "required": False, "required_signal_ids": []},
                {"job_id": "job_a", "required": True, "required_signal_ids": ["signal_a"]},
            ],
        )

    def card(self) -> dict:
        return {
            "card_id": "card_a",
            "job_id": "job_a",
            "artifact_ref": "artifact_001",
            "pack_manifest_hash": "b" * 64,
            "normalized_payload": {"signal_dispositions": [{"signal_id": "signal_a"}], "problem_candidates": []},
        }

    def test_required_failure_blocks_and_optional_timeout_can_pass(self) -> None:
        with self.assertRaises(JoinBlocked):
            reduce_join(self.manifest(), [
                {"job_id": "job_a", "status": "failed_contract"},
                {"job_id": "job_b", "status": "timed_out"},
            ])
        joined = reduce_join(self.manifest(), [
            {"job_id": "job_b", "status": "timed_out"},
            {"job_id": "job_a", "status": "completed", "card": self.card()},
        ])
        self.assertEqual(["card_a"], joined["card_refs"])

    def test_reduction_is_completion_order_invariant_and_stale_card_is_rejected(self) -> None:
        results = [
            {"job_id": "job_b", "status": "not_applicable"},
            {"job_id": "job_a", "status": "completed", "card": self.card()},
        ]
        self.assertEqual(reduce_join(self.manifest(), results), reduce_join(self.manifest(), list(reversed(results))))
        stale = self.card()
        stale["artifact_ref"] = "artifact_old"
        with self.assertRaises(JoinBlocked):
            reduce_join(self.manifest(), [
                {"job_id": "job_a", "status": "completed", "card": stale},
                {"job_id": "job_b", "status": "not_applicable"},
            ])


class StageDraftTests(unittest.TestCase):
    def integrated_job(self) -> dict:
        return {
            "job_id": "job_integrated", "stage": "integrated", "join_manifest_ref": "join_1",
            "allowed_fact_ids": ["fact_allowed"], "allowed_signal_ids": ["signal_allowed"],
            "allowed_mechanism_refs": ["mechanism_allowed"], "allowed_test_refs": ["test_allowed"],
            "allowed_expert_trigger_refs": ["expert_allowed"],
            "allowed_decision_type_refs": ["decision_allowed"],
            "allowed_decision_unit_refs": ["unit_allowed"], "capability_ids": ["capability_allowed"]
        }

    def integrated_draft(self) -> dict:
        return {
            "join_manifest_ref": "join_1", "card_refs": ["card_allowed"],
            "issue_clusters": [],
            "integrated_issues": [{
                "local_key": "issue_margin",
                "payload": {
                    "problem_family_ref": "family_allowed", "scope_key": "enterprise",
                    "decision_unit_ref": "unit_allowed", "source_candidate_ids": ["claim_problem"],
                    "observation_claim_refs": ["claim_observation"],
                    "cause_hypothesis_refs": ["claim_cause"],
                    "counter_hypothesis_refs": ["claim_counter"], "unresolved_conflict_refs": [],
                    "impact_evidence_refs": ["signal_allowed"],
                    "urgency_evidence_refs": ["signal_allowed"],
                    "counter_evidence_refs": ["fact_allowed"],
                    "decision_need_proposal": {
                        "decision_type_ref": "decision_allowed", "decision_unit_ref": "unit_allowed",
                        "basis_claim_refs": ["claim_problem"],
                        "rationale_template": "A decision may be required."
                    },
                    "verification_requirement_refs": ["test_allowed"],
                    "response_type_refs": ["response_allowed"],
                    "expert_trigger_refs": ["expert_allowed"]
                }
            }],
            "causal_relation_hypotheses": [], "cross_issue_conflicts": [], "blind_spots": [],
            "response_type_candidates": [], "expert_review_candidates": []
        }

    def test_integrated_draft_enforces_runtime_reference_allowlists(self) -> None:
        allowed_claims = {"claim_problem", "claim_observation", "claim_cause", "claim_counter"}
        draft = self.integrated_draft()
        normalized = normalize_integrated_draft(
            self.integrated_job(), draft,
            allowed_card_refs={"card_allowed"}, allowed_claim_refs=allowed_claims,
            allowed_problem_family_refs={"family_allowed"},
            allowed_response_refs={"response_allowed"}
        )
        self.assertEqual("runtime_integrator", normalized["materialized_by"])

        mutations = (
            ("impact_evidence_refs", ["signal_outside"]),
            ("counter_evidence_refs", ["fact_outside"]),
            ("source_candidate_ids", ["claim_outside"]),
            ("problem_family_ref", "family_outside"),
            ("response_type_refs", ["response_outside"])
        )
        for field, value in mutations:
            with self.subTest(field=field):
                outside = copy.deepcopy(draft)
                outside["integrated_issues"][0]["payload"][field] = value
                with self.assertRaises(ContractError):
                    normalize_integrated_draft(
                        self.integrated_job(), outside,
                        allowed_card_refs={"card_allowed"}, allowed_claim_refs=allowed_claims,
                        allowed_problem_family_refs={"family_allowed"},
                        allowed_response_refs={"response_allowed"}
                    )

    def test_integrated_draft_rejects_invalid_local_graph_and_numeric_template(self) -> None:
        duplicate = self.integrated_draft()
        duplicate["response_type_candidates"] = [{
            "local_key": "issue_margin",
            "payload": {
                "target_issue_local_key": "missing_issue", "response_ref": "response_allowed",
                "precondition_refs": [], "disqualifier_refs": [], "verification_requirement_refs": []
            }
        }]
        with self.assertRaises(ContractError):
            normalize_integrated_draft(
                self.integrated_job(), duplicate,
                allowed_card_refs={"card_allowed"},
                allowed_claim_refs={"claim_problem", "claim_observation", "claim_cause", "claim_counter"},
                allowed_problem_family_refs={"family_allowed"}, allowed_response_refs={"response_allowed"}
            )
        numeric = self.integrated_draft()
        numeric["integrated_issues"][0]["payload"]["decision_need_proposal"]["rationale_template"] = "Review 10 contracts."
        with self.assertRaises(ContractError):
            normalize_integrated_draft(
                self.integrated_job(), numeric,
                allowed_card_refs={"card_allowed"},
                allowed_claim_refs={"claim_problem", "claim_observation", "claim_cause", "claim_counter"},
                allowed_problem_family_refs={"family_allowed"}, allowed_response_refs={"response_allowed"}
            )

    def test_deep_dive_is_limited_to_approved_scope(self) -> None:
        job = {"job_id": "job_deep", "stage": "deep_dive", "approved_scope_ref": "scope_1", "component_run_refs": ["run_1"]}
        draft = {
            "approved_scope_ref": "scope_1",
            "component_run_refs": ["run_2"],
            "updated_cause_hypotheses": [], "updated_counter_hypotheses": [],
            "distinguishing_test_results": [], "conditional_response_candidates": [],
            "expert_review_candidates": [], "remaining_uncertainties": [], "additional_data_requests": [],
        }
        with self.assertRaises(ContractError):
            normalize_deep_dive_draft(job, draft)

    def test_deep_dive_enforces_issue_claim_evidence_and_pack_allowlists(self) -> None:
        job = {
            "job_id": "job_deep", "stage": "deep_dive", "approved_scope_ref": "scope_1",
            "component_run_refs": ["component_run_1"], "allowed_fact_ids": ["fact_allowed"],
            "allowed_signal_ids": ["signal_allowed"], "allowed_mechanism_refs": ["mechanism_allowed"],
            "allowed_test_refs": ["test_allowed"], "allowed_expert_trigger_refs": ["expert_allowed"]
        }
        draft = {
            "approved_scope_ref": "scope_1", "component_run_refs": ["component_run_1"],
            "updated_cause_hypotheses": [{
                "local_key": "cause_update",
                "payload": {
                    "target_issue_ref": "issue_allowed", "claim_ref": "claim_allowed",
                    "mechanism_ref": "mechanism_allowed", "statement_template": "The cause remains plausible.",
                    "value_refs": [],
                    "evidence_proposals": [{"evidence_ref": "fact_allowed", "polarity": "supports", "role": "mechanism"}],
                    "support_condition_refs": [], "rejection_condition_refs": [],
                    "distinguishing_test_refs": ["test_allowed"]
                }
            }],
            "updated_counter_hypotheses": [], "distinguishing_test_results": [],
            "conditional_response_candidates": [], "expert_review_candidates": [],
            "remaining_uncertainties": [], "additional_data_requests": []
        }
        normalized = normalize_deep_dive_draft(
            job, draft, allowed_issue_refs={"issue_allowed"}, allowed_claim_refs={"claim_allowed"},
            allowed_response_refs=set()
        )
        self.assertEqual("runtime_integrator", normalized["materialized_by"])
        for field, value in (
            ("target_issue_ref", "issue_outside"),
            ("claim_ref", "claim_outside"),
            ("mechanism_ref", "mechanism_outside")
        ):
            with self.subTest(field=field):
                outside = copy.deepcopy(draft)
                outside["updated_cause_hypotheses"][0]["payload"][field] = value
                with self.assertRaises(ContractError):
                    normalize_deep_dive_draft(
                        job, outside, allowed_issue_refs={"issue_allowed"},
                        allowed_claim_refs={"claim_allowed"}, allowed_response_refs=set()
                    )
        outside = copy.deepcopy(draft)
        outside["updated_cause_hypotheses"][0]["payload"]["evidence_proposals"][0]["evidence_ref"] = "fact_outside"
        with self.assertRaises(ContractError):
            normalize_deep_dive_draft(
                job, outside, allowed_issue_refs={"issue_allowed"},
                allowed_claim_refs={"claim_allowed"}, allowed_response_refs=set()
            )

    def test_writer_cannot_create_claim_or_numeric_text(self) -> None:
        job = {"job_id": "job_writer", "stage": "writer", "structured_output_ref": "structured_1", "allowed_claim_ids": ["claim_a"]}
        draft = {"structured_output_ref": "structured_1", "claim_templates": [{"claim_id": "claim_b", "template": "New claim."}], "expert_packet_templates": [], "ceo_brief_section_order": []}
        with self.assertRaises(ContractError):
            normalize_writer_draft(job, draft)
        numeric = copy.deepcopy(draft)
        numeric["claim_templates"][0] = {"claim_id": "claim_a", "template": "Revenue rose 10%."}
        with self.assertRaises(ContractError):
            normalize_writer_draft(job, numeric)


if __name__ == "__main__":
    unittest.main()
