import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.components import execute_plan

from tests.unit.components.test_components import fact


class ComponentParallelDeterminismTests(unittest.TestCase):
    def test_worker_one_and_four_have_identical_semantic_bytes(self) -> None:
        facts = [fact("a", "revenue", "10", member="a"), fact("b", "revenue", "20", member="b")]
        plan = [
            {
                "component_id": "aggregate",
                "parameters": {
                    "input_fact_code": "revenue",
                    "operation": "sum",
                    "output_fact_code": "revenue_total",
                },
            },
            {
                "component_id": "ratio",
                "parameters": {
                    "numerator_fact_id": "a",
                    "denominator_fact_id": "b",
                    "output_fact_code": "revenue_ratio",
                },
            },
        ]

        sequential = execute_plan(plan, facts, max_workers=1)
        parallel = execute_plan(list(reversed(plan)), list(reversed(facts)), max_workers=4)

        self.assertEqual(
            canonical_bytes([run.semantic_dict() for run in sequential]),
            canonical_bytes([run.semantic_dict() for run in parallel]),
        )


if __name__ == "__main__":
    unittest.main()
