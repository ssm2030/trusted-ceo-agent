import unittest

from trusted_ceo_agent.components import component_contracts


class ComponentRegistryTests(unittest.TestCase):
    def test_minimum_nine_components_are_registered_and_parallel_safe(self) -> None:
        contracts = component_contracts()
        self.assertEqual(
            {
                "aggregate",
                "compare",
                "ratio",
                "trend_persistence",
                "mix_concentration",
                "reconcile",
                "flow_aging",
                "bridge_decompose",
                "temporal_alignment",
            },
            set(contracts),
        )
        for contract in contracts.values():
            with self.subTest(component_id=contract.component_id):
                self.assertEqual("1.0.0", contract.version)
                self.assertTrue(contract.parallel_safe)
                self.assertGreater(contract.max_input_records, 0)
                self.assertGreater(contract.timeout_seconds, 0)


if __name__ == "__main__":
    unittest.main()
