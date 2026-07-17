from __future__ import annotations

import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.workflow.completion import (
    assess_completion,
    compile_completion_action_card,
    verify_completion_assessment,
)


RUN_ID = "run_20260717T000000Z_0123456789abcdef"


def completion_input() -> dict:
    return {
        "run_id": RUN_ID,
        "revision": 8,
        "signal_cases": [{
            "case_id": "case_0123456789abcdef01234567",
            "status": "terminal",
            "disposition": "substantiated",
            "materiality_review_required": True,
        }],
        "work_items": [{
            "task_id": "task_0123456789abcdef01234567",
            "required": True,
            "status": "succeeded",
        }],
        "domain_routes": [{
            "route_id": "route_0123456789abcdef01234567",
            "required": True,
            "status": "completed",
        }],
        "findings": [{
            "finding_id": "finding_0123456789abcdef01234567",
            "disposition": "substantiated",
            "coverage": {
                "required_procedures_complete": True,
                "counter_evidence_complete": True,
                "evidence_complete": True,
            },
            "reason_codes": [],
            "impact_scope_refs": ["scope_enterprise"],
            "limitation_origin": "none",
            "expert_review": {
                "required": False,
                "packet_complete": False,
                "conclusion_boundary_complete": False,
                "responsible_role": None,
            },
        }],
        "cross_finding_join_complete": True,
        "cross_domain_integrator_complete": True,
        "duplicate_merge_complete": True,
        "conflicts_disclosed": True,
        "coverage_complete": True,
        "final_validator_passed": True,
        "tty_final_approval_ready": True,
        "integrity_failure_refs": [],
        "contract_failure_refs": [],
        "stale_revision_refs": [],
        "coverage_gaps": [],
        "expert_review_refs": [],
        "blind_spot_refs": [],
        "limited_basis": "none",
        "user_confirmed_limitations": False,
    }


class CompletionControllerTests(unittest.TestCase):
    def test_normal_completion_and_action_card_are_deterministic(self) -> None:
        first = assess_completion(completion_input())
        variant = completion_input()
        variant["signal_cases"] = list(reversed(variant["signal_cases"]))
        variant["work_items"] = list(reversed(variant["work_items"]))
        second = assess_completion(variant)
        self.assertEqual(canonical_bytes(first), canonical_bytes(second))
        self.assertEqual("finalization_ready", first["status"])
        verify_completion_assessment(first)
        card = compile_completion_action_card(first)
        self.assertEqual(
            ["finalize", "add_data", "review_finding", "stop"],
            [option["option_id"] for option in card["options"]],
        )

    def test_required_failure_cannot_be_bypassed_by_limited_completion(self) -> None:
        value = completion_input()
        value["work_items"][0]["status"] = "failed"
        value["limited_basis"] = "data_unavailable"
        value["user_confirmed_limitations"] = True
        assessment = assess_completion(value)
        self.assertEqual("not_ready", assessment["status"])
        self.assertIn("task_0123456789abcdef01234567", assessment["blocking_required_work_refs"])
        self.assertFalse(assessment["limited_completion_eligible"])

    def test_integrity_contract_and_stale_failures_block_every_completion_mode(self) -> None:
        for field in (
            "integrity_failure_refs",
            "contract_failure_refs",
            "stale_revision_refs",
        ):
            with self.subTest(field=field):
                value = completion_input()
                value[field] = [f"{field}:1"]
                value["limited_basis"] = "user_excluded_scope"
                value["user_confirmed_limitations"] = True
                assessment = assess_completion(value)
                self.assertEqual("not_ready", assessment["status"])
                self.assertFalse(assessment["limited_completion_eligible"])

    def test_data_limited_inconclusive_requires_confirmation_and_disclosure(self) -> None:
        value = completion_input()
        finding = value["findings"][0]
        finding["disposition"] = "inconclusive"
        finding["coverage"]["evidence_complete"] = False
        finding["reason_codes"] = ["missing_source_role"]
        finding["limitation_origin"] = "data_or_capability"
        value["coverage_gaps"] = ["contract_register"]
        value["limited_basis"] = "data_unavailable"
        not_confirmed = assess_completion(value)
        self.assertEqual("not_ready", not_confirmed["status"])
        value["user_confirmed_limitations"] = True
        limited = assess_completion(value)
        self.assertEqual("limited_completion_ready", limited["status"])
        self.assertTrue(limited["limited_completion_eligible"])
        card = compile_completion_action_card(limited)
        self.assertIn("accept_limited", [item["option_id"] for item in card["options"]])

    def test_substantiated_and_expert_terminal_contracts_fail_closed(self) -> None:
        value = completion_input()
        value["findings"][0]["coverage"]["counter_evidence_complete"] = False
        self.assertEqual("not_ready", assess_completion(value)["status"])

        expert = completion_input()
        expert["signal_cases"][0]["disposition"] = "expert_review_required"
        expert["findings"][0]["disposition"] = "expert_review_required"
        expert["findings"][0]["expert_review"] = {
            "required": True,
            "packet_complete": False,
            "conclusion_boundary_complete": True,
            "responsible_role": "senior_accountant",
        }
        self.assertEqual("not_ready", assess_completion(expert)["status"])

    def test_hash_tampering_is_rejected(self) -> None:
        assessment = assess_completion(completion_input())
        assessment["status"] = "limited_completion_ready"
        with self.assertRaisesRegex(ContractError, "hash"):
            verify_completion_assessment(assessment)


if __name__ == "__main__":
    unittest.main()
