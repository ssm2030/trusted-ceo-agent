from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.knowledge.compiler import compile_card, compile_issue_evidence_packet
from trusted_ceo_agent.knowledge.depth_gate import assess_professional_depth

from tests.professional_knowledge_support import make_knowledge_bundle


class ProfessionalKnowledgeSchemaTests(unittest.TestCase):
    def test_cards_family_assessment_and_packet_are_closed_contracts(self):
        family, cards, expert, release = make_knowledge_bundle()
        schemas = SchemaStore()
        schema_by_type = {
            "method_card": "method-card.schema.json",
            "norm_card": "norm-card.schema.json",
            "expectation_card": "expectation-card.schema.json",
            "procedure_card": "procedure-card.schema.json",
            "counter_hypothesis_card": "counter-hypothesis-card.schema.json",
            "cross_domain_trigger_card": "cross-domain-trigger-card.schema.json",
        }
        for card in cards:
            schemas.validate(schema_by_type[card["artifact_type"]], card)
            schemas.validate("knowledge-artifact.schema.json", card)
        schemas.validate("issue-family.schema.json", family)
        schemas.validate("knowledge-release-gate.schema.json", release)

        assessment = assess_professional_depth(
            family,
            cards,
            effective_on="2026-06-30",
            jurisdiction="KR",
            industry_scope="b2b_services",
            expert_approval=expert,
            release=release,
        )
        schemas.validate("professional-depth-assessment.schema.json", assessment)
        packet = compile_issue_evidence_packet(
            issue_family=family,
            run_id="run_1",
            revision=3,
            fact_refs=["fact_1"],
            signal_refs=["signal_1"],
            coverage_refs=["coverage_1"],
            procedure_run_refs=["procedure_run_1"],
            supporting_evidence_refs=["evidence_1"],
            counter_evidence_refs=["evidence_counter_1"],
            missing_evidence_roles=[],
            prohibited_conclusions=["final legal conclusion"],
            expert_triggers=["tax review"],
        )
        schemas.validate("issue-evidence-packet.schema.json", packet)

        invalid = copy.deepcopy(assessment)
        invalid["hidden_chain_of_thought"] = "forbidden"
        with self.assertRaises(ContractError):
            schemas.validate("professional-depth-assessment.schema.json", invalid)

    def test_card_compiler_rejects_hidden_reasoning(self):
        _, cards, _, _ = make_knowledge_bundle()
        base = cards[0]
        with self.assertRaisesRegex(ContractError, "chain-of-thought"):
            compile_card(
                artifact_type="method_card",
                domain=base["domain"],
                issue_family_id=base["issue_family_id"],
                version=2,
                status="active",
                trust_level="full",
                jurisdiction="KR",
                effective_from="2026-01-01",
                effective_to="2026-12-31",
                source_refs=base["source_refs"],
                author="author",
                reviewer_refs=["reviewer"],
                created_at="2026-01-02T00:00:00Z",
                supersedes=base["artifact_id"],
                test_refs=["normal"],
                content={
                    "review_sequence": ["step"],
                    "required_questions": ["question"],
                    "scope_conditions": ["scope"],
                    "chain_of_thought": "never persist this",
                },
            )


if __name__ == "__main__":
    unittest.main()
