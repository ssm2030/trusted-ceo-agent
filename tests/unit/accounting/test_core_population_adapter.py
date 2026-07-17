from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError


def _journal(
    journal_id: str,
    amount: str,
    *,
    document_id: str,
    posting_date: str = "2026-06-30",
    debit_account: str = "expense",
    credit_account: str = "ap",
    reversal_of: str | None = None,
) -> dict:
    return {
        "journal_id": journal_id,
        "entity": "E1",
        "currency": "KRW",
        "period": "2026-06",
        "source_id": "journal-source",
        "document_id": document_id,
        "posting_date": posting_date,
        "economic_event_date": "2026-06-29",
        "entered_at": "2026-07-01T23:10:00Z",
        "approved_at": "2026-07-01T23:20:00Z",
        "creator_id": "admin-1",
        "approver_id": "admin-1",
        "creator_role": "admin",
        "source_type": "manual",
        "changed_from_automatic": True,
        "debit_account": debit_account,
        "credit_account": credit_account,
        "amount": amount,
        "description": f"entry {journal_id}",
        "counterparty_id": "VENDOR-1",
        "reversal_of": reversal_of,
        "expected_reversal": reversal_of is None and journal_id == "J1",
        "period_reopened": journal_id == "J1",
        "suspense": journal_id == "J1",
        "days_outstanding": 120 if journal_id == "J1" else 0,
        "clear_repost": journal_id == "J2",
        "recurring_expected": journal_id == "J2",
        "authorized_exception": journal_id == "J2",
        "timing_documented": journal_id == "J2",
        "kpi_direction": "improves" if journal_id in {"J1", "J2"} else "neutral",
        "source_refs": [f"evidence:{journal_id}"],
        "counter_evidence_refs": [f"counter:{journal_id}"],
    }


def valid_population() -> dict:
    journals = [
        _journal("J1", "100", document_id="DOC-1"),
        _journal("J2", "100", document_id="DOC-1"),
        _journal("J3", "60", document_id="DOC-3"),
        _journal("J4", "40", document_id="DOC-4"),
        _journal(
            "J5",
            "100",
            document_id="REV-1",
            debit_account="ap",
            credit_account="expense",
            reversal_of="J1",
        ),
        _journal("J6", "100", document_id="DOC-6", posting_date="2026-06-29"),
    ]
    return {
        "run_id": "run-core-population",
        "revision": 12,
        "close_timestamp": "2026-06-30T18:00:00Z",
        "journals": journals,
        "allowed_account_pairs": [
            {
                "entity": "E1",
                "debit_account": "expense",
                "credit_account": "ap",
            }
        ],
        "subsequent_disbursements": [
            {
                "row_id": "SD1",
                "entity": "E1",
                "currency": "KRW",
                "period": "2026-06",
                "prior_service_amount": "80",
                "recurring_expected": "20",
                "recorded_accrual": "50",
                "new_period_service_amount": "10",
                "source_refs": ["evidence:payment"],
                "counter_evidence_refs": ["counter:new-period-service"],
            }
        ],
        "policy_changes": [
            {
                "row_id": "PC1",
                "entity": "E1",
                "currency": "KRW",
                "period": "2026-06",
                "policy_change_amount": "40",
                "estimate_change_amount": "30",
                "prior_error_amount": "20",
                "comparative_restated_amount": "10",
                "source_refs": ["evidence:policy-paper"],
                "counter_evidence_refs": ["counter:new-information"],
            }
        ],
        "capitalization_items": [
            {
                "row_id": "CAP1",
                "entity": "E1",
                "currency": "KRW",
                "period": "2026-06",
                "recorded_capitalized_amount": "100",
                "supported_capitalizable_amount": "60",
                "impairment_indicator_amount": "30",
                "recorded_impairment_amount": "10",
                "source_refs": ["evidence:asset-register"],
                "counter_evidence_refs": ["counter:future-benefit"],
            }
        ],
        "counterparties": [
            {
                "row_id": "RP1",
                "entity": "E1",
                "currency": "KRW",
                "period": "2026-06",
                "counterparty_id": "VENDOR-1",
                "candidate_amount": "100",
                "confirmed_amount": "60",
                "disclosed_amount": "20",
                "source_refs": ["evidence:counterparty-master"],
                "counter_evidence_refs": ["counter:ownership-review"],
            }
        ],
    }


class CorePopulationAdapterTests(unittest.TestCase):
    def test_raw_population_materializes_all_ac06_to_ac16_inputs(self):
        from trusted_ceo_agent.accounting.core_extended_procedures import (
            run_core_extended_procedure,
        )
        from trusted_ceo_agent.accounting.raw_journal_adapter import (
            materialize_core_extended_inputs,
        )

        inputs = materialize_core_extended_inputs(valid_population())
        self.assertEqual(
            [f"AC-{number:02d}" for number in range(6, 17)],
            list(inputs),
        )
        self.assertGreater(
            int(inputs["AC-06"]["rows"][0]["metrics"]["exact_duplicate_amount"]),
            0,
        )
        self.assertGreater(
            int(inputs["AC-06"]["rows"][0]["metrics"]["split_duplicate_amount"]),
            0,
        )
        self.assertGreater(
            int(inputs["AC-06"]["rows"][0]["metrics"]["reversal_like_amount"]),
            0,
        )
        self.assertGreater(
            int(inputs["AC-07"]["rows"][0]["metrics"]["post_close_backdated_amount"]),
            0,
        )
        self.assertGreater(
            int(inputs["AC-08"]["rows"][0]["metrics"]["same_creator_approver_amount"]),
            0,
        )
        self.assertGreater(
            int(inputs["AC-09"]["rows"][0]["metrics"]["reverse_normal_balance_amount"]),
            0,
        )

        for issue_id, value in inputs.items():
            with self.subTest(issue_id=issue_id):
                result = run_core_extended_procedure(issue_id, value)
                self.assertNotEqual("not_assessable", result["status"])

    def test_input_order_does_not_change_materialized_bytes(self):
        from trusted_ceo_agent.accounting.raw_journal_adapter import (
            materialize_core_extended_inputs,
        )

        first = valid_population()
        second = copy.deepcopy(first)
        for field in (
            "journals",
            "allowed_account_pairs",
            "subsequent_disbursements",
            "policy_changes",
            "capitalization_items",
            "counterparties",
        ):
            second[field].reverse()
        self.assertEqual(
            canonical_bytes(materialize_core_extended_inputs(first)),
            canonical_bytes(materialize_core_extended_inputs(second)),
        )

    def test_missing_deep_review_population_stays_not_assessable(self):
        from trusted_ceo_agent.accounting.core_extended_procedures import (
            run_core_extended_procedure,
        )
        from trusted_ceo_agent.accounting.raw_journal_adapter import (
            materialize_core_extended_inputs,
        )

        value = valid_population()
        value["policy_changes"] = []
        result = run_core_extended_procedure(
            "AC-13",
            materialize_core_extended_inputs(value)["AC-13"],
        )
        self.assertEqual("not_assessable", result["status"])

    def test_unknown_fields_and_non_decimal_amounts_fail_closed(self):
        from trusted_ceo_agent.accounting.raw_journal_adapter import (
            materialize_core_extended_inputs,
        )

        unknown = valid_population()
        unknown["unexpected"] = True
        with self.assertRaises(ContractError):
            materialize_core_extended_inputs(unknown)

        invalid = valid_population()
        invalid["journals"][0]["amount"] = 100.0
        with self.assertRaises(ContractError):
            materialize_core_extended_inputs(invalid)


if __name__ == "__main__":
    unittest.main()
