import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


SCHEMA_ROOT = Path(__file__).parents[2] / "plugin" / "trusted-ceo-agent" / "schemas"


class SchemaContractTests(unittest.TestCase):
    def load(self, name: str) -> dict:
        schema = json.loads((SCHEMA_ROOT / name).read_text("utf-8"))
        Draft202012Validator.check_schema(schema)
        self.assertFalse(schema.get("additionalProperties", True))
        return schema

    def test_owned_schemas_are_valid_draft_2020_12_and_strict(self) -> None:
        names = [
            "reasoning-job.schema.json", "schema-mapping-draft.schema.json", "lens-card-draft.schema.json",
            "normalized-card.schema.json", "join-manifest.schema.json", "integrated-draft.schema.json",
            "deep-dive-draft.schema.json", "writer-draft.schema.json", "grading-input.schema.json",
            "grade-record.schema.json", "hitl-overlay.schema.json", "approval-request.schema.json",
            "approval.schema.json", "workflow-state.schema.json",
        ]
        for name in names:
            with self.subTest(name=name):
                self.load(name)

    def test_reasoning_job_stage_contract_rejects_missing_lens_fields(self) -> None:
        schema = self.load("reasoning-job.schema.json")
        validator = Draft202012Validator(schema)
        invalid = {
            "contract_version": "1.0", "job_id": "job_1", "stage": "lens", "artifact_ref": "artifact_1",
            "mission_contract_hash": "a" * 64, "pack_manifest_hash": "b" * 64,
            "prompt_template_hash": "c" * 64, "model_profile": "balanced_structured",
            "capability_ids": [], "allowed_fact_ids": [], "allowed_signal_ids": [], "allowed_mechanism_refs": [],
            "allowed_test_refs": [], "allowed_expert_trigger_refs": [], "allowed_decision_type_refs": [],
            "allowed_decision_unit_refs": [], "required_signal_ids": [], "output_schema_ref": "lens-card-draft.schema.json",
            "limits_ref": "default", "untrusted_text_markers": [],
        }
        self.assertTrue(list(validator.iter_errors(invalid)))

    def test_integrated_and_deep_draft_nested_payloads_are_closed(self) -> None:
        integrated = {
            "join_manifest_ref": "join_1", "card_refs": ["card_1"],
            "issue_clusters": [],
            "integrated_issues": [{
                "local_key": "issue_margin",
                "payload": {
                    "problem_family_ref": "profitability_erosion",
                    "scope_key": "enterprise",
                    "decision_unit_ref": "unit_enterprise",
                    "source_candidate_ids": ["claim_problem"],
                    "observation_claim_refs": ["claim_observation"],
                    "cause_hypothesis_refs": ["claim_cause"],
                    "counter_hypothesis_refs": ["claim_counter"],
                    "unresolved_conflict_refs": [],
                    "impact_evidence_refs": ["signal_margin"],
                    "urgency_evidence_refs": ["signal_margin"],
                    "counter_evidence_refs": [],
                    "decision_need_proposal": {
                        "decision_type_ref": "portfolio_review",
                        "decision_unit_ref": "unit_enterprise",
                        "basis_claim_refs": ["claim_problem"],
                        "rationale_template": "A portfolio decision may be required."
                    },
                    "verification_requirement_refs": ["test_mix"],
                    "response_type_refs": ["portfolio_rebalance"],
                    "expert_trigger_refs": []
                }
            }],
            "causal_relation_hypotheses": [], "cross_issue_conflicts": [],
            "blind_spots": [], "response_type_candidates": [],
            "expert_review_candidates": []
        }
        validator = Draft202012Validator(self.load("integrated-draft.schema.json"))
        self.assertFalse(list(validator.iter_errors(integrated)))
        integrated["integrated_issues"][0]["payload"]["primary_grade"] = "Decision Required"
        self.assertTrue(list(validator.iter_errors(integrated)))

        deep = {
            "approved_scope_ref": "scope_1", "component_run_refs": ["component_run_1"],
            "updated_cause_hypotheses": [], "updated_counter_hypotheses": [],
            "distinguishing_test_results": [],
            "conditional_response_candidates": [{
                "local_key": "response_1",
                "payload": {
                    "target_issue_ref": "issue_1", "response_ref": "portfolio_rebalance",
                    "action_template": "Review the portfolio mix.", "value_refs": [],
                    "precondition_refs": ["mix_verified"], "disqualifier_refs": [],
                    "monitoring_metric_refs": ["gross_margin"], "reversibility": "reversible",
                    "owner_role": "ceo", "expert_review_refs": []
                }
            }],
            "expert_review_candidates": [], "remaining_uncertainties": [],
            "additional_data_requests": []
        }
        validator = Draft202012Validator(self.load("deep-dive-draft.schema.json"))
        self.assertFalse(list(validator.iter_errors(deep)))
        deep["conditional_response_candidates"][0]["payload"]["primary_grade"] = "Decision Required"
        self.assertTrue(list(validator.iter_errors(deep)))


if __name__ == "__main__":
    unittest.main()
