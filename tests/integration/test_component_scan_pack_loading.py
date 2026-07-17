import unittest
from pathlib import Path

from trusted_ceo_agent.components import execute_plan
from trusted_ceo_agent.packs import PackLoader, PackRegistry, select_domain, threshold_values
from tests.unit.components.test_components import fact


ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugin" / "trusted-ceo-agent"


class ComponentPackIntegrationTests(unittest.TestCase):
    def test_loaded_domain_and_deterministic_component_scan_integrate(self) -> None:
        registry = PackRegistry.load(
            PLUGIN_ROOT / "trust" / "pack-registry.json",
            PLUGIN_ROOT / "schemas" / "pack-registry.schema.json",
        )
        packs = PackLoader(PLUGIN_ROOT / "packs", PLUGIN_ROOT / "schemas", registry).load_installed()
        domain = select_domain(
            packs,
            {"business_model": "project_b2b_services"},
            {"industry": "professional_services", "available_data_roles": ["monthly_financials"]},
        ).pack
        thresholds = threshold_values(domain)
        runs = execute_plan(
            [
                {
                    "component_id": "aggregate",
                    "parameters": {
                        "input_fact_code": "revenue",
                        "operation": "sum",
                        "output_fact_code": "revenue_total",
                        "scope": [{"dimension_code": "enterprise", "member_code": "all"}],
                        "time_context": {"period": "2026-03"}
                    },
                }
            ],
            [
                fact("a", "revenue", "10", member="a", period="2026-03"),
                fact("b", "revenue", "20", member="b", period="2026-03")
            ],
            thresholds=thresholds,
            pack_refs=[domain.ref],
            max_workers=4,
        )
        self.assertEqual("provisional", domain.effective_authority)
        self.assertEqual("3", thresholds["margin_decline_high"])
        self.assertEqual("completed", runs[0].status)
        self.assertEqual("30", runs[0].output_facts[0]["value"]["canonical_value"])


if __name__ == "__main__":
    unittest.main()
