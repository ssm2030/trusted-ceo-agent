import unittest

from trusted_ceo_agent.contracts.condition_dsl import ConditionContext, evaluate_condition, validate_condition
from trusted_ceo_agent.errors import ContractError


class ConditionDslSafetyTests(unittest.TestCase):
    def test_depth_and_argument_limits_are_enforced(self) -> None:
        expression = {"op": "exists", "operand": {"mission_ref": "/business_model"}}
        for _ in range(9):
            expression = {"not": expression}
        with self.assertRaises(ContractError):
            validate_condition(expression)
        with self.assertRaises(ContractError):
            validate_condition({"all": [{"op": "exists", "operand": {"mission_ref": "/business_model"}}] * 17})

    def test_code_shaped_literal_is_never_executed(self) -> None:
        expression = {
            "op": "eq",
            "left": {"literal": {"type": "string", "value": "__import__('os').system('echo unsafe')"}},
            "right": {"literal": {"type": "string", "value": "ordinary-data"}},
        }
        result = evaluate_condition(expression, ConditionContext((), (), {}, {}))
        self.assertEqual("false", result.outcome)
        with self.assertRaises(ContractError):
            validate_condition({"op": "__import__", "left": expression["left"], "right": expression["right"]})


if __name__ == "__main__":
    unittest.main()
