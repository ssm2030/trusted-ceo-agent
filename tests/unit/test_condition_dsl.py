import unittest

from trusted_ceo_agent.contracts.condition_dsl import (
    ConditionContext,
    evaluate_condition,
    validate_condition,
)
from trusted_ceo_agent.errors import ContractError


class ConditionDslTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = ConditionContext(
            facts=(
                {
                    "fact_id": "fact_margin",
                    "fact_code": "gross_margin_change_pp",
                    "scope": [{"dimension_code": "enterprise", "member_code": "all"}],
                    "time_context": {"period": "2026-06"},
                    "value": {
                        "value_type": "decimal",
                        "canonical_value": "-7",
                        "unit_code": "percentage_point",
                        "currency_code": None,
                        "scale": "1",
                    },
                },
            ),
            signals=(),
            mission={"priority_dimensions": ["profitability"]},
            hitl={"diagnostic": {"accepted": True}},
        )

    def test_decimal_fact_comparison_is_true(self) -> None:
        expression = {
            "op": "lte",
            "left": {
                "fact_ref": {
                    "fact_code": "gross_margin_change_pp",
                    "reducer": "only",
                    "unit_code": "percentage_point",
                }
            },
            "right": {"literal": {"type": "decimal", "value": "-3"}},
        }

        result = evaluate_condition(expression, self.context)

        self.assertEqual("true", result.outcome)
        self.assertEqual((), result.reason_codes)

    def test_missing_fact_is_not_assessable_instead_of_false(self) -> None:
        expression = {
            "op": "gte",
            "left": {"fact_ref": {"fact_code": "missing_metric", "reducer": "only"}},
            "right": {"literal": {"type": "decimal", "value": "1"}},
        }

        result = evaluate_condition(expression, self.context)

        self.assertEqual("not_assessable", result.outcome)
        self.assertEqual(("missing_fact",), result.reason_codes)

    def test_any_prefers_true_over_not_assessable(self) -> None:
        expression = {
            "any": [
                {
                    "op": "exists",
                    "operand": {"fact_ref": {"fact_code": "missing_metric", "reducer": "only"}},
                },
                {
                    "op": "in",
                    "left": {"mission_ref": "/priority_dimensions/0"},
                    "values": [
                        {"literal": {"type": "string", "value": "profitability"}},
                        {"literal": {"type": "string", "value": "liquidity"}},
                    ],
                },
            ]
        }

        result = evaluate_condition(expression, self.context)

        self.assertEqual("true", result.outcome)

    def test_disallowed_pointer_and_unknown_operator_are_contract_errors(self) -> None:
        with self.assertRaises(ContractError):
            validate_condition(
                {
                    "op": "eq",
                    "left": {"mission_ref": "/secrets/api_key"},
                    "right": {"literal": {"type": "string", "value": "x"}},
                }
            )
        with self.assertRaises(ContractError):
            validate_condition(
                {
                    "op": "eval",
                    "left": {"literal": {"type": "string", "value": "1"}},
                    "right": {"literal": {"type": "string", "value": "1"}},
                }
            )


if __name__ == "__main__":
    unittest.main()
