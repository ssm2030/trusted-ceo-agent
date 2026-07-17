from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError


def valid_input() -> dict:
    return {
        "run_id": "run_tier_zero",
        "revision": 3,
        "source_manifests": [{
            "source_id": "source_journal",
            "source_sha256": "a" * 64,
            "period_start": "2026-01",
            "period_end": "2026-01",
            "header_count": 2,
            "line_count": 4,
            "debit_total": "150",
            "credit_total": "150",
        }],
        "journal_headers": [
            {
                "journal_id": "J1", "source_id": "source_journal", "sequence": 1,
                "status": "posted", "entity": "E1", "currency": "KRW", "period": "2026-01",
            },
            {
                "journal_id": "J2", "source_id": "source_journal", "sequence": 2,
                "status": "posted", "entity": "E1", "currency": "KRW", "period": "2026-01",
            },
        ],
        "journal_lines": [
            {"line_id": "L1", "journal_id": "J1", "account_id": "cash", "debit": "100", "credit": "0", "entity": "E1", "currency": "KRW", "period": "2026-01"},
            {"line_id": "L2", "journal_id": "J1", "account_id": "revenue", "debit": "0", "credit": "100", "entity": "E1", "currency": "KRW", "period": "2026-01"},
            {"line_id": "L3", "journal_id": "J2", "account_id": "ar", "debit": "50", "credit": "0", "entity": "E1", "currency": "KRW", "period": "2026-01"},
            {"line_id": "L4", "journal_id": "J2", "account_id": "revenue", "debit": "0", "credit": "50", "entity": "E1", "currency": "KRW", "period": "2026-01"},
        ],
        "trial_balance": [
            {"account_id": "cash", "entity": "E1", "currency": "KRW", "period": "2026-01", "prior_closing": "0", "opening": "0", "debit_turnover": "100", "credit_turnover": "0", "closing": "100", "control_subledger": "cash"},
            {"account_id": "ar", "entity": "E1", "currency": "KRW", "period": "2026-01", "prior_closing": "0", "opening": "0", "debit_turnover": "50", "credit_turnover": "0", "closing": "50", "control_subledger": "ar"},
            {"account_id": "revenue", "entity": "E1", "currency": "KRW", "period": "2026-01", "prior_closing": "0", "opening": "0", "debit_turnover": "0", "credit_turnover": "150", "closing": "-150", "control_subledger": None},
        ],
        "subledger_balances": [
            {"subledger": "cash", "account_id": "cash", "object_id": "bank-1", "entity": "E1", "currency": "KRW", "period": "2026-01", "amount": "100"},
            {"subledger": "ar", "account_id": "ar", "object_id": "customer-1", "entity": "E1", "currency": "KRW", "period": "2026-01", "amount": "50"},
        ],
    }


def api():
    from trusted_ceo_agent.accounting.core_procedures import (
        assert_accounting_core_screened,
        run_tier_zero_procedures,
        verify_tier_zero_result,
    )

    return run_tier_zero_procedures, verify_tier_zero_result, assert_accounting_core_screened


class AccountingTierZeroTests(unittest.TestCase):
    def test_all_five_deterministic_procedures_complete(self) -> None:
        run, verify, claim = api()
        result = run(valid_input())
        self.assertEqual(
            ["AC-01", "AC-02", "AC-03", "AC-04", "AC-05"],
            [item["issue_family_id"] for item in result["procedure_results"]],
        )
        self.assertEqual({"passed"}, {item["status"] for item in result["procedure_results"]})
        self.assertTrue(result["coverage_complete"])
        self.assertEqual("accounting_core_screened", claim(result))
        verify(result)

        from trusted_ceo_agent.accounting.suite import (
            assert_product_claim_allowed,
            build_machine_draft_suite,
        )

        suite = build_machine_draft_suite(
            release_id="knowledge_release_seed",
            effective_from="2026-01-01",
        )
        self.assertEqual(
            "accounting_core_screened",
            assert_product_claim_allowed(
                suite,
                "accounting_core_screened",
                execution_evidence=result,
            ),
        )

    def test_individual_journal_imbalances_cannot_net_to_zero(self) -> None:
        run, _, _ = api()
        value = valid_input()
        value["journal_lines"][1]["credit"] = "99"
        value["journal_lines"][3]["credit"] = "51"
        result = run(value)
        ac02 = result["procedure_results"][1]
        self.assertEqual("exceptions_found", ac02["status"])
        self.assertEqual(2, ac02["exception_count"])
        self.assertEqual({"J1", "J2"}, {item["scope_ref"] for item in ac02["exceptions"]})

    def test_population_orphans_gaps_and_deleted_rows_are_preserved(self) -> None:
        run, _, _ = api()
        value = valid_input()
        value["journal_headers"][1]["sequence"] = 4
        value["journal_headers"][1]["status"] = "cancelled"
        value["journal_lines"].append({
            "line_id": "L5", "journal_id": "UNKNOWN", "account_id": "cash",
            "debit": "0", "credit": "0", "entity": "E1", "currency": "KRW", "period": "2026-01",
        })
        result = run(value)
        codes = {item["code"] for item in result["procedure_results"][0]["exceptions"]}
        self.assertTrue({"source_line_count_mismatch", "orphan_line", "sequence_gap"}.issubset(codes))
        self.assertEqual(1, result["population_status_counts"]["cancelled"])

    def test_missing_required_population_is_not_assessable_and_blocks_claim(self) -> None:
        run, _, claim = api()
        value = valid_input()
        value["trial_balance"] = []
        result = run(value)
        by_issue = {item["issue_family_id"]: item for item in result["procedure_results"]}
        self.assertEqual("not_assessable", by_issue["AC-03"]["status"])
        self.assertFalse(result["coverage_complete"])
        with self.assertRaises(ContractError):
            claim(result)

    def test_gl_tb_roll_forward_and_subledger_differences_stay_separate(self) -> None:
        run, _, _ = api()
        value = valid_input()
        value["trial_balance"][0]["debit_turnover"] = "90"
        value["trial_balance"][1]["prior_closing"] = "10"
        value["subledger_balances"][1]["amount"] = "45"
        result = run(value)
        by_issue = {item["issue_family_id"]: item for item in result["procedure_results"]}
        self.assertEqual("exceptions_found", by_issue["AC-03"]["status"])
        self.assertEqual("exceptions_found", by_issue["AC-04"]["status"])
        self.assertEqual("exceptions_found", by_issue["AC-05"]["status"])

    def test_input_order_is_byte_equivalent(self) -> None:
        run, _, _ = api()
        first = valid_input()
        second = copy.deepcopy(first)
        for field in ("source_manifests", "journal_headers", "journal_lines", "trial_balance", "subledger_balances"):
            second[field].reverse()
        self.assertEqual(canonical_bytes(run(first)), canonical_bytes(run(second)))

    def test_result_hash_and_closed_input_fail_closed(self) -> None:
        run, verify, _ = api()
        result = run(valid_input())
        result["content_hash"] = "0" * 64
        with self.assertRaises(ContractError):
            verify(result)

        value = valid_input()
        value["journal_lines"][0]["grade"] = "A"
        with self.assertRaises(ContractError):
            run(value)


if __name__ == "__main__":
    unittest.main()
