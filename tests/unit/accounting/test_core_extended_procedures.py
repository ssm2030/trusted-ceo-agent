from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError


EXPECTED_CODES = {
    "AC-06": "duplicate_journal_candidate",
    "AC-07": "cutoff_journal_candidate",
    "AC-08": "approval_override_candidate",
    "AC-09": "abnormal_account_pair_candidate",
    "AC-10": "reversal_pairing_difference",
    "AC-11": "aged_suspense_balance",
    "AC-12": "unrecorded_liability_candidate",
    "AC-13": "policy_estimate_error_classification_boundary",
    "AC-14": "capitalization_or_impairment_difference",
    "AC-15": "related_party_trace_boundary",
    "AC-16": "management_bias_concentration_candidate",
}

METRICS = {
    "AC-06": {
        "exact_duplicate_amount": "100",
        "near_duplicate_amount": "20",
        "split_duplicate_amount": "30",
        "reversal_like_amount": "10",
        "legitimate_recurring_amount": "15",
    },
    "AC-07": {
        "post_close_backdated_amount": "90",
        "reopened_period_amount": "20",
        "immediate_reversal_amount": "10",
        "documented_timing_difference_amount": "15",
    },
    "AC-08": {
        "same_creator_approver_amount": "70",
        "admin_posting_amount": "30",
        "manual_override_amount": "20",
        "after_hours_amount": "10",
        "authorized_exception_amount": "25",
    },
    "AC-09": {
        "rare_pair_amount": "60",
        "reverse_normal_balance_amount": "40",
        "approved_pair_exception_amount": "10",
    },
    "AC-10": {
        "original_amount": "100",
        "matched_reversal_amount": "60",
        "duplicate_reversal_amount": "10",
        "partial_reversal_amount": "5",
        "wrong_account_reversal_amount": "3",
    },
    "AC-11": {
        "closing_suspense_balance": "100",
        "aged_balance": "80",
        "clear_repost_amount": "20",
        "supported_balance": "15",
    },
    "AC-12": {
        "subsequent_payment_prior_service_amount": "80",
        "recurring_cost_expected": "20",
        "recorded_accrual_amount": "50",
        "new_period_service_amount": "10",
    },
    "AC-13": {
        "policy_change_amount": "40",
        "estimate_change_amount": "30",
        "prior_error_amount": "20",
        "comparative_restated_amount": "10",
    },
    "AC-14": {
        "recorded_capitalized_amount": "100",
        "supported_capitalizable_amount": "60",
        "impairment_indicator_amount": "30",
        "recorded_impairment_amount": "10",
    },
    "AC-15": {
        "related_party_candidate_amount": "100",
        "confirmed_related_party_amount": "60",
        "disclosed_related_party_amount": "20",
    },
    "AC-16": {
        "manual_kpi_improving_amount": "100",
        "next_period_reversal_amount": "40",
        "concentrated_user_amount": "60",
        "supported_business_amount": "30",
    },
}


def _input(metrics: dict[str, str], *, row_id: str = "row-1") -> dict:
    return {
        "run_id": "run-ac-extended",
        "revision": 4,
        "rows": [
            {
                "row_id": row_id,
                "entity": "entity-a",
                "currency": "KRW",
                "period": "2026-06",
                "metrics": metrics,
                "source_refs": ["evidence:journal", "evidence:control-log"],
                "counter_evidence_refs": ["evidence:approved-exception"],
            }
        ],
    }


class CoreExtendedProcedureTests(unittest.TestCase):
    def _api(self):
        from trusted_ceo_agent.accounting.core_extended_procedures import (
            SUPPORTED_CORE_EXTENDED_ISSUES,
            run_core_extended_procedure,
            verify_core_extended_procedure_result,
        )

        return (
            SUPPORTED_CORE_EXTENDED_ISSUES,
            run_core_extended_procedure,
            verify_core_extended_procedure_result,
        )

    def test_all_eleven_issue_families_execute_deterministic_boundary_procedures(self):
        supported, run, verify = self._api()
        self.assertEqual(tuple(EXPECTED_CODES), supported)

        for issue_id, expected_code in EXPECTED_CODES.items():
            with self.subTest(issue_id=issue_id):
                result = run(issue_id, _input(METRICS[issue_id]))
                verify(result)
                self.assertEqual("exceptions_found", result["status"])
                self.assertEqual("Boundary", result["authority_ceiling"])
                self.assertTrue(result["expert_review_required"])
                self.assertEqual(expected_code, result["outcomes"][0]["code"])
                self.assertEqual("entity-a", result["outcomes"][0]["entity"])
                self.assertEqual("KRW", result["outcomes"][0]["currency"])
                self.assertEqual("2026-06", result["outcomes"][0]["period"])
                self.assertIsInstance(result["outcomes"][0]["amount"], str)

    def test_reversal_and_unrecorded_liability_quantification_is_explicit(self):
        _, run, _ = self._api()
        reversal = run("AC-10", _input(METRICS["AC-10"]))
        liability = run("AC-12", _input(METRICS["AC-12"]))
        self.assertEqual("58", reversal["outcomes"][0]["amount"])
        self.assertEqual("40", liability["outcomes"][0]["amount"])

    def test_missing_metric_or_counter_evidence_fails_closed(self):
        _, run, verify = self._api()
        missing_metric = _input(copy.deepcopy(METRICS["AC-12"]))
        del missing_metric["rows"][0]["metrics"]["recorded_accrual_amount"]
        result = run("AC-12", missing_metric)
        verify(result)
        self.assertEqual("not_assessable", result["status"])
        self.assertEqual(["row-1:metrics.recorded_accrual_amount"], result["missing_inputs"])
        self.assertEqual([], result["outcomes"])

        no_counter_evidence = _input(copy.deepcopy(METRICS["AC-15"]))
        no_counter_evidence["rows"][0]["counter_evidence_refs"] = []
        result = run("AC-15", no_counter_evidence)
        self.assertEqual("not_assessable", result["status"])
        self.assertEqual(["row-1:counter_evidence_refs"], result["missing_inputs"])
        self.assertEqual([], result["outcomes"])

    def test_order_hash_and_exact_decimal_contracts_are_closed(self):
        _, run, _ = self._api()
        value = _input(METRICS["AC-06"], row_id="row-b")
        second = copy.deepcopy(value["rows"][0])
        second["row_id"] = "row-a"
        second["source_refs"].reverse()
        value["rows"].append(second)
        reordered = copy.deepcopy(value)
        reordered["rows"].reverse()
        for row in reordered["rows"]:
            row["source_refs"].reverse()
        self.assertEqual(
            canonical_bytes(run("AC-06", value)),
            canonical_bytes(run("AC-06", reordered)),
        )

        with self.assertRaises(ContractError):
            run("AC-17", _input(METRICS["AC-06"]))
        invalid = _input(copy.deepcopy(METRICS["AC-14"]))
        invalid["rows"][0]["metrics"]["recorded_capitalized_amount"] = 100.0
        with self.assertRaises(ContractError):
            run("AC-14", invalid)

    def test_result_cannot_claim_fact_signal_finding_grade_or_approval(self):
        _, run, _ = self._api()
        result = run("AC-16", _input(METRICS["AC-16"]))
        forbidden = {"fact", "signal", "finding", "grade", "approval"}

        def walk(value):
            if isinstance(value, dict):
                self.assertTrue(forbidden.isdisjoint(value))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(result)


if __name__ == "__main__":
    unittest.main()
