import unittest

from trusted_ceo_agent.packs.evidence_selection import (
    build_problem_capability_map,
    build_problem_selection,
)
from trusted_ceo_agent.packs.runtime_index import RuntimePackIndex


SOURCE_ID = "source_" + "a" * 24


def pack_index(entry_condition=None) -> RuntimePackIndex:
    problem = {
        "pack_id": "customer-concentration",
        "pack_version": "1.0.0",
        "applicability": {"required_data_roles": ["ledger"]},
        "content": {
            "problem_family_code": "customer_concentration",
            "entry_conditions": [entry_condition or {
                "op": "exists",
                "operand": {"fact_ref": {"fact_code": "customer_revenue", "reducer": "sum"}},
            }],
            "required_capabilities": ["customer_revenue"],
        },
    }
    return RuntimePackIndex(
        manifest={"packs": [{"effective_authority": "provisional"}]},
        mission_pack={},
        domain_pack={"pack_id": "b2b-services", "pack_version": "1.0.0"},
        problem_packs=(problem,),
    )


def customer_revenue_fact(value: str = "100") -> dict:
    return {
        "fact_id": "fact_" + "b" * 24,
        "fact_code": "customer_revenue",
        "observation_role": "ledger",
        "scope": [],
        "time_context": {"period": "2026-01"},
        "value": {"value_type": "decimal", "canonical_value": value, "unit_code": "KRW"},
        "source_refs": [{"source_id": SOURCE_ID, "observation_role": "ledger"}],
    }


class ProblemEvidenceSelectionTests(unittest.TestCase):
    def test_actual_fact_and_referenced_source_role_select_problem(self) -> None:
        index = pack_index()
        facts = [customer_revenue_fact()]
        sources = [{"source_id": SOURCE_ID, "observation_roles": ["ledger"]}]

        capability_map = build_problem_capability_map(index, facts, [], sources)
        selection = build_problem_selection(index, facts, [], capability_map)

        capability = capability_map["capabilities"][0]
        self.assertEqual("customer_revenue", capability["capability_code"])
        self.assertEqual("available", capability["status"])
        self.assertEqual(["ledger"], capability["available_source_roles"])
        self.assertIn("capability_requirement_fallback_to_entry_fact_refs", capability["reason_codes"])
        self.assertEqual("selected", selection["problems"][0]["status"])
        self.assertEqual(["customer-concentration@1.0.0"], selection["selected_problem_refs"])

    def test_missing_entry_fact_is_not_assessable_not_not_applicable(self) -> None:
        index = pack_index()
        sources = [{"source_id": SOURCE_ID, "observation_roles": ["ledger"]}]

        capability_map = build_problem_capability_map(index, [], [], sources)
        selection = build_problem_selection(index, [], [], capability_map)

        self.assertEqual("unsupported", capability_map["capabilities"][0]["status"])
        problem = selection["problems"][0]
        self.assertEqual("not_assessable", problem["status"])
        self.assertIn("missing_entry_fact", problem["reason_codes"])
        self.assertEqual("not_assessable", problem["entry_outcomes"][0]["outcome"])

    def test_source_role_not_used_by_a_fact_cannot_make_capability_available(self) -> None:
        index = pack_index()
        index.problem_packs[0]["applicability"]["required_data_roles"] = ["monthly_financials"]
        facts = [customer_revenue_fact()]
        sources = [{
            "source_id": SOURCE_ID,
            "observation_roles": ["ledger", "monthly_financials"],
        }]

        capability_map = build_problem_capability_map(index, facts, [], sources)
        selection = build_problem_selection(index, facts, [], capability_map)

        capability = capability_map["capabilities"][0]
        self.assertEqual("partial", capability["status"])
        self.assertEqual([], capability["available_source_roles"])
        self.assertEqual(["monthly_financials"], capability["missing_source_roles"])
        self.assertEqual("not_assessable", selection["problems"][0]["status"])

    def test_blocking_quality_degrades_capability_and_selection(self) -> None:
        index = pack_index()
        facts = [customer_revenue_fact()]
        sources = [{"source_id": SOURCE_ID, "observation_roles": ["ledger"]}]
        quality = [{
            "quality_issue_id": "quality_" + "c" * 24,
            "severity": "blocking",
            "normalized_role": "customer_revenue",
        }]

        capability_map = build_problem_capability_map(index, facts, quality, sources)
        selection = build_problem_selection(index, facts, [], capability_map)

        capability = capability_map["capabilities"][0]
        self.assertEqual("partial", capability["status"])
        self.assertEqual(["quality_" + "c" * 24], capability["quality_issue_ids"])
        self.assertIn("blocking_quality", capability["reason_codes"])
        self.assertEqual("not_assessable", selection["problems"][0]["status"])

    def test_false_entry_condition_with_available_inputs_is_not_applicable(self) -> None:
        index = pack_index({
            "op": "gt",
            "left": {"fact_ref": {"fact_code": "customer_revenue", "reducer": "sum"}},
            "right": {"literal": {"type": "decimal", "value": "200"}},
        })
        facts = [customer_revenue_fact("100")]
        sources = [{"source_id": SOURCE_ID, "observation_roles": ["ledger"]}]

        capability_map = build_problem_capability_map(index, facts, [], sources)
        selection = build_problem_selection(index, facts, [], capability_map)

        self.assertEqual("available", capability_map["capabilities"][0]["status"])
        self.assertEqual("not_applicable", selection["problems"][0]["status"])
        self.assertEqual(
            ["customer-concentration@1.0.0"],
            selection["not_applicable_problem_refs"],
        )

    def test_explicit_capability_requirements_override_legacy_applicability_fallback(self) -> None:
        index = pack_index()
        index.problem_packs[0]["applicability"]["required_data_roles"] = ["monthly_financials"]
        index.problem_packs[0]["content"]["capability_requirements"] = [{
            "capability_code": "customer_revenue",
            "required_fact_codes": ["customer_revenue"],
            "required_observation_roles": ["ledger"],
        }]
        facts = [customer_revenue_fact()]
        sources = [{"source_id": SOURCE_ID, "observation_roles": ["ledger"]}]

        capability_map = build_problem_capability_map(index, facts, [], sources)

        capability = capability_map["capabilities"][0]
        self.assertEqual("available", capability["status"])
        self.assertNotIn(
            "capability_requirement_fallback_to_entry_fact_refs",
            capability["reason_codes"],
        )

if __name__ == "__main__":
    unittest.main()
