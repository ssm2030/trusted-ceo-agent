import unittest
from pathlib import Path

from trusted_ceo_agent.packs import PackLoader, PackRegistry, select_domain, select_problem_packs
from trusted_ceo_agent.contracts.condition_dsl import ConditionContext


ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = ROOT / "plugin" / "trusted-ceo-agent"


class PackSelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        registry = PackRegistry.load(
            PLUGIN_ROOT / "trust" / "pack-registry.json",
            PLUGIN_ROOT / "schemas" / "pack-registry.schema.json",
        )
        cls.packs = PackLoader(PLUGIN_ROOT / "packs", PLUGIN_ROOT / "schemas", registry).load_installed()

    def test_b2b_services_is_selected_for_supported_business_model(self) -> None:
        selection = select_domain(
            self.packs,
            {"business_model": "project_b2b_services"},
            {"industry": "professional_services", "available_data_roles": ["monthly_financials"]},
        )
        self.assertEqual("selected", selection.status)
        self.assertEqual("b2b-services", selection.pack.pack_id)

    def test_missing_data_roles_do_not_route_a_supported_business_model_to_boundary(self) -> None:
        selection = select_domain(
            self.packs,
            {"business_model": "project_b2b_services"},
            {"industry": None, "available_data_roles": []},
        )
        self.assertEqual("selected", selection.status)
        self.assertEqual("b2b-services", selection.pack.pack_id)

    def test_unsupported_business_model_routes_to_generic_boundary(self) -> None:
        selection = select_domain(
            self.packs,
            {"business_model": "regulated_bank"},
            {"industry": "banking", "available_data_roles": ["monthly_financials"]},
        )
        self.assertEqual("boundary", selection.status)
        self.assertEqual("generic-business-boundary", selection.pack.pack_id)

    def test_problem_selection_requires_requested_and_challenge_lenses(self) -> None:
        context = ConditionContext(
            facts=(
                {
                    "fact_id": "margin",
                    "fact_code": "gross_margin_change_pp",
                    "scope": [],
                    "time_context": {"period": "2026-06"},
                    "value": {"value_type": "decimal", "canonical_value": "-7", "unit_code": "percentage_point"},
                },
            ),
            signals=(),
            mission={},
            hitl={},
        )
        selected = select_problem_packs(self.packs, "b2b-services@1.0.0", context)
        profitability = next(pack for pack in selected if pack.pack_id == "profitability-erosion")
        roles = {lens["role"] for lens in profitability.document["content"]["lens_plan"]}
        self.assertIn("requested", roles)
        self.assertIn("challenge", roles)


if __name__ == "__main__":
    unittest.main()
