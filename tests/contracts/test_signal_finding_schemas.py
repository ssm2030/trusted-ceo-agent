from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


class SignalFindingSchemaTests(unittest.TestCase):
    """D09 §§8.4, 10.1–10.3, 12.6; Integration Index Tasks I–J."""

    def setUp(self) -> None:
        self.schemas = SchemaStore()

    def test_signal_case_and_priority_are_closed_hash_bound_contracts(self) -> None:
        priority = {
            "priority_record_id": "priority_" + "a" * 24,
            "schema_version": "1.0.0",
            "case_id": "case_" + "b" * 24,
            "policy_ref": "priority_policy_v1",
            "dimensions": {
                "deterministic_risk": 90,
                "amount_cash_impact": 70,
                "legal_human_impact": 80,
                "control_failure": 60,
                "urgency": 50,
                "data_sufficiency": 40,
                "ceo_question_relevance": 30,
            },
            "sort_vector": [90, 80, 60, 50, 70, 30, 40],
            "created_from_hash": "c" * 64,
            "content_hash": "d" * 64,
        }
        case = {
            "case_id": priority["case_id"],
            "schema_version": "1.0.0",
            "run_id": "run_contract",
            "base_revision": 4,
            "case_revision": 0,
            "signal_ids": ["signal_" + "e" * 24],
            "event_id": "event_001",
            "priority_record_ref": priority["priority_record_id"],
            "required_domain_routes": ["accounting"],
            "optional_domain_routes": [],
            "current_stage": 1,
            "status": "queued",
            "disposition": None,
            "finding_ref": None,
            "related_case_ids": [],
            "checkpoint_ref": None,
            "lease_owner": None,
            "pause_reason": None,
            "terminal_reason": None,
            "created_from_hash": "f" * 64,
            "previous_content_hash": None,
            "content_hash": "0" * 64,
        }
        self.schemas.validate("priority-record.schema.json", priority)
        self.schemas.validate("signal-case.schema.json", case)

        for schema_name, value in (
            ("priority-record.schema.json", priority),
            ("signal-case.schema.json", case),
        ):
            invalid = copy.deepcopy(value)
            invalid["hidden_reasoning"] = "forbidden"
            with self.subTest(schema=schema_name):
                with self.assertRaises(ContractError):
                    self.schemas.validate(schema_name, invalid)

    def test_finding_relation_and_cluster_are_closed_contracts(self) -> None:
        finding = {
            "finding_id": "finding_" + "1" * 24,
            "schema_version": "1.0.0",
            "run_id": "run_contract",
            "revision": 5,
            "case_id": "case_" + "2" * 24,
            "event_id": "event_001",
            "signal_ids": ["signal_" + "3" * 24],
            "domain_assessment_refs": ["assessment_001"],
            "issue_family_refs": ["AC-01"],
            "fact_refs": ["fact_" + "4" * 24],
            "evidence_link_refs": ["evidence_" + "5" * 24],
            "source_refs": ["source_" + "6" * 24],
            "procedure_result_refs": ["procedure_result_001"],
            "norm_refs": ["norm_001"],
            "calculation_refs": ["calculation_001"],
            "hypotheses": ["Revenue cut-off risk is supported."],
            "counter_hypotheses": ["Timing difference only."],
            "supporting_evidence_refs": ["evidence_" + "5" * 24],
            "contradicting_evidence_refs": [],
            "unresolved_conflicts": [],
            "disposition": "substantiated",
            "conclusion": {
                "statement": "Cut-off risk is supported within the tested scope.",
                "scope": "2026-Q2 sampled contracts",
                "basis_refs": ["procedure_result_001"],
                "qualifier": "supported_within_current_scope",
            },
            "conclusion_strength": "supported",
            "impact_dimensions": {
                "amount": "material",
                "cash": "possible",
                "legal": "not_assessed",
                "tax": "not_assessed",
                "human": "not_assessed",
                "operations": "possible",
                "control": "material",
            },
            "coverage": {
                "required_procedures_complete": True,
                "counter_evidence_complete": True,
                "evidence_coverage_complete": True,
                "missing_evidence_refs": [],
                "missing_procedure_refs": [],
                "scope_note": "Sampled contracts only.",
            },
            "data_gaps": [],
            "expert_review": {
                "required": False,
                "packet_ref": None,
                "decision_boundary": None,
                "owner": None,
            },
            "grade": {
                "status": "published",
                "grade_record_ref": "grade_record_001",
            },
            "authority": {
                "effective_level": "Provisional",
                "pack_release_refs": ["pack_release_001"],
                "approval_refs": [],
            },
            "uncertainty": {"status": "partial", "reason_codes": ["sample_scope"]},
            "verification": {
                "required_procedure_refs": ["procedure_001"],
                "completed_procedure_refs": ["procedure_001"],
                "counter_evidence_checked": True,
                "counter_evidence_refs": ["evidence_" + "7" * 24],
                "verification_step_refs": ["verification_001"],
            },
            "related_finding_ids": [],
            "supersedes_finding_id": None,
            "created_from_hash": "8" * 64,
            "content_hash": "9" * 64,
            "producer": "analysis_runtime",
        }
        relation = {
            "relation_id": "relation_" + "a" * 24,
            "schema_version": "1.0.0",
            "run_id": "run_contract",
            "revision": 5,
            "source_finding_id": finding["finding_id"],
            "target_finding_id": "finding_" + "b" * 24,
            "relation_type": "supports",
            "evidence_refs": ["evidence_" + "c" * 24],
            "confidence_status": "verified",
            "contradicting_evidence_refs": [],
            "created_from_hash": "d" * 64,
            "content_hash": "e" * 64,
            "producer": "analysis_runtime",
        }
        cluster = {
            "cluster_id": "cluster_" + "f" * 24,
            "schema_version": "1.0.0",
            "run_id": "run_contract",
            "revision": 5,
            "finding_ids": [finding["finding_id"], relation["target_finding_id"]],
            "relation_ids": [relation["relation_id"]],
            "decision_unit": {
                "title": "Revenue cut-off remediation",
                "decision_required": True,
                "owner_role": "CEO",
                "option_refs": ["option_001"],
            },
            "unresolved_conflicts": [],
            "created_from_hash": "0" * 64,
            "content_hash": "1" * 64,
        }
        for schema_name, value in (
            ("finding-record.schema.json", finding),
            ("finding-relation.schema.json", relation),
            ("issue-cluster.schema.json", cluster),
        ):
            self.schemas.validate(schema_name, value)
            invalid = copy.deepcopy(value)
            invalid["chain_of_thought"] = "forbidden"
            with self.subTest(schema=schema_name):
                with self.assertRaises(ContractError):
                    self.schemas.validate(schema_name, invalid)

    def test_disposition_specific_fields_fail_closed(self) -> None:
        schema = self.schemas.load("finding-record.schema.json")
        self.assertEqual("object", schema["type"])
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("allOf", schema)


if __name__ == "__main__":
    unittest.main()
