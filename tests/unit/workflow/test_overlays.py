import unittest

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.workflow.overlays import apply_overlay, invalidated_gates


class OverlayTests(unittest.TestCase):
    def test_gate_allowlist_and_remove_prohibition(self) -> None:
        overlay = apply_overlay({}, "context", [{"op": "add", "path": "/mission_contract/business_question", "value": "Review margin"}])
        self.assertEqual("Review margin", overlay["mission_contract"]["business_question"])
        with self.assertRaises(ContractError):
            apply_overlay({}, "context", [{"op": "remove", "path": "/mission_contract/business_question"}])
        with self.assertRaises(ContractError):
            apply_overlay({}, "context", [{"op": "add", "path": "/fact_register/fact_1/value", "value": "9"}])

    def test_scope_narrowing_recomputes_cardinality_and_blind_spots(self) -> None:
        operations = [
            {"op": "add", "path": "/scope_narrowing/included_scope_keys", "value": ["scope_a"]},
            {"op": "add", "path": "/scope_narrowing/excluded_scope_keys", "value": ["scope_b"]},
            {"op": "add", "path": "/scope_narrowing/blind_spot_reason_codes", "value": {"scope_b": "card_limit"}},
            {"op": "add", "path": "/scope_narrowing/estimated_card_count", "value": 1},
        ]
        overlay = apply_overlay({}, "scope_narrowing", operations, runtime_context={"estimated_card_count": 1})
        self.assertEqual(["scope_b"], overlay["scope_narrowing"]["excluded_scope_keys"])
        with self.assertRaises(ContractError):
            apply_overlay({}, "scope_narrowing", operations, runtime_context={"estimated_card_count": 2})

    def test_invalidation_matrix_is_monotonic(self) -> None:
        self.assertEqual(
            {"diagnostic", "deep_authorization", "final"},
            invalidated_gates(["/mission_contract/business_question"]),
        )
        self.assertEqual({"final"}, invalidated_gates(["/ceo_wording/title"]),)


if __name__ == "__main__":
    unittest.main()
