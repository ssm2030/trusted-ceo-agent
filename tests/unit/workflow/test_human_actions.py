from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.workflow.human_actions import (
    compile_data_request_card,
    pending_action_for_state,
    verify_action_card,
)


RUN_ID = "run_20260717T000000Z_0123456789abcdef"


class HumanActionCardTests(unittest.TestCase):
    def test_pending_card_is_complete_deterministic_and_hash_bound(self) -> None:
        kwargs = {
            "run_id": RUN_ID,
            "revision": 3,
            "workflow_state": "diagnostic_approval_required",
            "evidence_refs": ["evidence_0123456789abcdef01234567"],
            "expires_at": "2026-07-17T00:10:00Z",
        }
        first = pending_action_for_state(**kwargs)
        self.assertEqual(first, pending_action_for_state(**kwargs))
        self.assertEqual("diagnostic", first["gate"])
        self.assertTrue({
            "why_asked", "current_interpretation", "options",
            "unanswered_effect", "next_step_by_option",
        }.issubset(first))
        verify_action_card(first)
        tampered = copy.deepcopy(first)
        tampered["question"] = "변조된 질문"
        with self.assertRaisesRegex(ContractError, "content hash"):
            verify_action_card(tampered)

    def test_data_request_has_all_five_unavailable_choices(self) -> None:
        card = compile_data_request_card(
            run_id=RUN_ID,
            base_revision=2,
            missing_source_roles=["contract_register"],
            missing_capabilities=["revenue_contract_terms"],
            affected_issue_family_refs=["RV-03"],
            affected_domains=["accounting"],
            evidence_refs=[],
            expires_at=None,
        )
        self.assertEqual(
            {
                "provide_data", "provide_alternative_evidence",
                "proceed_limited", "exclude_scope", "stop",
            },
            {option["response_type"] for option in card["options"]},
        )
        self.assertIn("request_explanation", card["allowed_response_types"])
        self.assertIsNone(card["recommended_option_id"])
        verify_action_card(card)

    def test_non_action_state_has_no_pending_card(self) -> None:
        self.assertIsNone(pending_action_for_state(
            run_id=RUN_ID,
            revision=3,
            workflow_state="evidence_ready",
            evidence_refs=[],
            expires_at=None,
        ))


if __name__ == "__main__":
    unittest.main()
