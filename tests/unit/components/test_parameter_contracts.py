import unittest

from trusted_ceo_agent.components.runner import execute_component


class ComponentParameterContractTests(unittest.TestCase):
    def test_empty_parameters_are_contract_failure_even_without_facts(self) -> None:
        for component_id in (
            "aggregate", "compare", "ratio", "trend_persistence", "mix_concentration",
            "reconcile", "flow_aging", "bridge_decompose", "temporal_alignment",
        ):
            with self.subTest(component_id=component_id):
                run = execute_component(component_id, [], {})
                self.assertEqual("failed", run.status)
                self.assertEqual(("component_contract_failure",), run.reason_codes)

    def test_missing_threshold_definition_is_contract_failure(self) -> None:
        run = execute_component(
            "trend_persistence",
            [],
            {
                "input_fact_code": "gross_margin",
                "minimum_observations_ref": "trend_minimum",
                "direction": "decreasing",
                "output_signal_code": "gross_margin_decline_persistent",
            },
            thresholds={},
        )
        self.assertEqual("failed", run.status)
        self.assertEqual(("component_contract_failure",), run.reason_codes)


if __name__ == "__main__":
    unittest.main()
