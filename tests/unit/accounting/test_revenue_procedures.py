from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError


def valid_input() -> dict:
    return {
        "run_id": "run_revenue",
        "revision": 4,
        "period_start": "2026-01-01",
        "period_end": "2026-12-31",
        "contracts": [
            {
                "contract_id": "C1",
                "customer_id": "CUSTOMER-1",
                "entity": "E1",
                "currency": "KRW",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
                "approved": True,
                "enforceable_rights": True,
                "collectability_evidence_ref": "EV-COLLECT-1",
                "fixed_consideration": "1000",
                "constrained_variable_consideration": "100",
                "credits": "50",
                "refunds": "0",
                "approved_modifications": "0",
                "recorded_transaction_price": "1050",
                "payment_due_date": "2026-12-31",
                "significant_financing_recorded": "0",
                "discount_rate": "0",
                "presentation": "gross",
                "controls_before_transfer": True,
                "inventory_risk": True,
                "price_discretion": True,
                "license_type": "none",
                "side_agreement_ref": None,
                "cancelled_date": None,
                "tax_judgement_required": False,
                "legal_judgement_required": False,
            }
        ],
        "obligations": [
            {
                "obligation_id": "O1",
                "contract_id": "C1",
                "promise_ref": "EV-PROMISE-1",
                "distinct": True,
                "standalone_selling_price": "600",
                "allocated_price": "630",
                "satisfaction_pattern": "over_time",
                "progress_method": "input",
                "eligible_to_date": "50",
                "expected_total_eligible": "100",
                "control_transfer_date": None,
                "acceptance_date": None,
                "recognized_revenue": "315",
            },
            {
                "obligation_id": "O2",
                "contract_id": "C1",
                "promise_ref": "EV-PROMISE-2",
                "distinct": True,
                "standalone_selling_price": "400",
                "allocated_price": "420",
                "satisfaction_pattern": "point_in_time",
                "progress_method": "none",
                "eligible_to_date": "0",
                "expected_total_eligible": "0",
                "control_transfer_date": "2026-06-30",
                "acceptance_date": "2026-06-30",
                "recognized_revenue": "420",
            },
        ],
        "events": [
            {
                "event_id": "EV-CONTRACT-1",
                "contract_id": "C1",
                "obligation_id": None,
                "event_type": "contract",
                "event_date": "2026-01-01",
                "amount": "1050",
                "entity": "E1",
                "currency": "KRW",
                "period": "2026-01",
                "source_ref": "SRC-CONTRACT-1",
            },
            {
                "event_id": "EV-PROMISE-1",
                "contract_id": "C1",
                "obligation_id": "O1",
                "event_type": "promise",
                "event_date": "2026-01-01",
                "amount": "630",
                "entity": "E1",
                "currency": "KRW",
                "period": "2026-01",
                "source_ref": "SRC-CONTRACT-1",
            },
            {
                "event_id": "EV-PROMISE-2",
                "contract_id": "C1",
                "obligation_id": "O2",
                "event_type": "promise",
                "event_date": "2026-01-01",
                "amount": "420",
                "entity": "E1",
                "currency": "KRW",
                "period": "2026-01",
                "source_ref": "SRC-CONTRACT-1",
            },
            {
                "event_id": "EV-PERF-1",
                "contract_id": "C1",
                "obligation_id": "O1",
                "event_type": "performance",
                "event_date": "2026-06-30",
                "amount": "315",
                "entity": "E1",
                "currency": "KRW",
                "period": "2026-06",
                "source_ref": "SRC-PERF-1",
            },
            {
                "event_id": "EV-ACCEPT-2",
                "contract_id": "C1",
                "obligation_id": "O2",
                "event_type": "acceptance",
                "event_date": "2026-06-30",
                "amount": "420",
                "entity": "E1",
                "currency": "KRW",
                "period": "2026-06",
                "source_ref": "SRC-ACCEPT-2",
            },
            {
                "event_id": "EV-REVENUE-1",
                "contract_id": "C1",
                "obligation_id": "O1",
                "event_type": "revenue",
                "event_date": "2026-06-30",
                "amount": "315",
                "entity": "E1",
                "currency": "KRW",
                "period": "2026-06",
                "source_ref": "SRC-GL-1",
            },
            {
                "event_id": "EV-REVENUE-2",
                "contract_id": "C1",
                "obligation_id": "O2",
                "event_type": "revenue",
                "event_date": "2026-06-30",
                "amount": "420",
                "entity": "E1",
                "currency": "KRW",
                "period": "2026-06",
                "source_ref": "SRC-GL-2",
            },
            {
                "event_id": "EV-BILL-1",
                "contract_id": "C1",
                "obligation_id": None,
                "event_type": "billing",
                "event_date": "2026-07-01",
                "amount": "735",
                "entity": "E1",
                "currency": "KRW",
                "period": "2026-07",
                "source_ref": "SRC-INVOICE-1",
            },
            {
                "event_id": "EV-CASH-1",
                "contract_id": "C1",
                "obligation_id": None,
                "event_type": "collection",
                "event_date": "2026-07-15",
                "amount": "735",
                "entity": "E1",
                "currency": "KRW",
                "period": "2026-07",
                "source_ref": "SRC-BANK-1",
            },
        ],
        "balances": [
            {
                "contract_id": "C1",
                "entity": "E1",
                "currency": "KRW",
                "period": "2026-12",
                "accounts_receivable": "0",
                "contract_asset": "0",
                "contract_liability": "0",
                "refund_liability": "0",
            }
        ],
        "contract_costs": [
            {
                "cost_id": "COST-1",
                "contract_id": "C1",
                "cost_type": "acquisition",
                "amount": "10",
                "incremental": True,
                "directly_related": True,
                "recoverable": True,
                "capitalized_amount": "10",
                "source_ref": "SRC-COST-1",
            }
        ],
        "credit_risks": [
            {
                "contract_id": "C1",
                "entity": "E1",
                "currency": "KRW",
                "period": "2026-12",
                "aging_days": 0,
                "outstanding_amount": "0",
                "lifetime_loss_rate": "0.02",
                "recorded_ecl": "0",
                "credit_evidence_ref": "SRC-CREDIT-1",
            }
        ],
    }


def api():
    from trusted_ceo_agent.accounting.revenue_procedures import (
        run_revenue_procedures,
        verify_revenue_procedure_result,
    )

    return run_revenue_procedures, verify_revenue_procedure_result


class RevenueProcedureTests(unittest.TestCase):
    def test_all_sixteen_families_execute_with_seed_dispatch(self) -> None:
        run, verify = api()
        result = run(valid_input())
        self.assertEqual(
            [f"RV-{number:02d}" for number in range(1, 17)],
            [item["issue_family_id"] for item in result["procedure_results"]],
        )
        self.assertTrue(all(
            item["implementation_status"] == "implemented_deterministic"
            for item in result["procedure_results"]
        ))
        self.assertEqual(
            [
                "P-RV-01", "P-RV-02", "P-RV-03", "P-RV-04",
                "P-RV-05", "P-RV-06", "P-RV-07", "P-RV-08",
                "P-RV-09", "P-RV-10", "P-RV-11", "P-RV-04",
                "P-RV-09", "P-RV-11", "P-RV-10", "P-RV-09",
            ],
            [item["procedure_id"] for item in result["procedure_results"]],
        )
        self.assertTrue(all(item["outcomes"] for item in result["procedure_results"]))
        self.assertEqual("Boundary", result["authority_ceiling"])
        verify(result)

    def test_price_allocation_progress_cutoff_balance_cost_and_ecl_are_reperformed(self) -> None:
        run, _ = api()
        value = valid_input()
        value["contracts"][0]["recorded_transaction_price"] = "1060"
        value["obligations"][0]["allocated_price"] = "620"
        value["obligations"][0]["recognized_revenue"] = "400"
        value["events"][5]["event_date"] = "2025-12-31"
        value["balances"][0]["accounts_receivable"] = "15"
        value["contract_costs"][0]["capitalized_amount"] = "0"
        value["credit_risks"][0].update(
            outstanding_amount="100", lifetime_loss_rate="0.10", recorded_ecl="5"
        )
        result = run(value)
        by_issue = {item["issue_family_id"]: item for item in result["procedure_results"]}
        self.assertIn("transaction_price_difference", _codes(by_issue["RV-04"]))
        self.assertIn("ssp_allocation_difference", _codes(by_issue["RV-05"]))
        self.assertIn("progress_reperformance_difference", _codes(by_issue["RV-07"]))
        self.assertIn("revenue_before_satisfaction", _codes(by_issue["RV-08"]))
        self.assertIn("contract_balance_difference", _codes(by_issue["RV-11"]))
        self.assertIn("contract_cost_capitalization_difference", _codes(by_issue["RV-14"]))
        self.assertIn("ecl_reperformance_difference", _codes(by_issue["RV-16"]))

    def test_contract_promise_modification_refund_and_termination_populations_fail_closed(self) -> None:
        run, _ = api()
        value = valid_input()
        value["contracts"][0]["collectability_evidence_ref"] = None
        value["obligations"] = []
        value["events"].extend([
            _event("EV-MOD-1", "modification", "10"),
            _event("EV-REFUND-1", "refund", "20"),
            _event("EV-END-1", "termination", "0"),
        ])
        result = run(value)
        by_issue = {item["issue_family_id"]: item for item in result["procedure_results"]}
        self.assertIn("collectability_evidence_missing", _codes(by_issue["RV-01"]))
        self.assertIn("unapproved_modification", _codes(by_issue["RV-02"]))
        self.assertEqual("not_assessable", by_issue["RV-03"]["status"])
        self.assertIn("refund_liability_difference", _codes(by_issue["RV-13"]))
        self.assertIn("termination_not_reflected", _codes(by_issue["RV-15"]))

    def test_principal_license_financing_and_domain_triggers_preserve_boundaries(self) -> None:
        run, _ = api()
        value = valid_input()
        contract = value["contracts"][0]
        contract.update(
            presentation="net",
            license_type="access",
            significant_financing_recorded="0",
            discount_rate="0.10",
            payment_due_date="2028-12-31",
            tax_judgement_required=True,
            legal_judgement_required=True,
        )
        value["obligations"][1]["satisfaction_pattern"] = "point_in_time"
        value["events"].append({
            **_event("EV-FX-1", "billing", "5"),
            "currency": "USD",
        })
        result = run(value)
        by_issue = {item["issue_family_id"]: item for item in result["procedure_results"]}
        self.assertIn("principal_agent_presentation_difference", _codes(by_issue["RV-09"]))
        self.assertIn("license_pattern_difference", _codes(by_issue["RV-10"]))
        self.assertIn("financing_component_difference", _codes(by_issue["RV-12"]))
        self.assertTrue(result["expert_review_required"])
        self.assertEqual(
            {"foreign_exchange", "legal", "tax"},
            {item["target_domain"] for item in result["cross_domain_triggers"]},
        )
        self.assertTrue(all(
            item["disposition"] == "expert_review_required"
            for item in result["cross_domain_triggers"]
            if item["target_domain"] in {"legal", "tax"}
        ))

    def test_missing_populations_are_not_assessable_not_weak_passes(self) -> None:
        run, _ = api()
        value = valid_input()
        value["events"] = []
        value["balances"] = []
        value["contract_costs"] = []
        value["credit_risks"] = []
        result = run(value)
        by_issue = {item["issue_family_id"]: item for item in result["procedure_results"]}
        for issue in ("RV-01", "RV-02", "RV-08", "RV-11", "RV-13", "RV-14", "RV-15", "RV-16"):
            self.assertEqual("not_assessable", by_issue[issue]["status"])
        self.assertFalse(result["coverage_complete"])

    def test_input_order_and_hash_are_deterministic_and_tamper_evident(self) -> None:
        run, verify = api()
        first = valid_input()
        second = copy.deepcopy(first)
        for name in ("contracts", "obligations", "events", "balances", "contract_costs", "credit_risks"):
            second[name].reverse()
        self.assertEqual(canonical_bytes(run(first)), canonical_bytes(run(second)))

        result = run(first)
        result["procedure_results"][0]["status"] = "exceptions_found"
        with self.assertRaises(ContractError):
            verify(result)

    def test_closed_types_decimal_and_lineage_mismatches_fail_closed(self) -> None:
        run, _ = api()
        for mutator in (
            lambda value: value["contracts"][0].__setitem__("grade", "A"),
            lambda value: value["events"][0].__setitem__("amount", 1050),
            lambda value: value["events"][0].__setitem__("contract_id", "UNKNOWN"),
            lambda value: value["events"][0].__setitem__("currency", "USD"),
        ):
            value = valid_input()
            mutator(value)
            with self.assertRaises(ContractError):
                run(value)


def _codes(result: dict) -> set[str]:
    return {item["code"] for item in result["outcomes"]}


def _event(event_id: str, event_type: str, amount: str) -> dict:
    return {
        "event_id": event_id,
        "contract_id": "C1",
        "obligation_id": None,
        "event_type": event_type,
        "event_date": "2026-08-01",
        "amount": amount,
        "entity": "E1",
        "currency": "KRW",
        "period": "2026-08",
        "source_ref": f"SRC-{event_id}",
    }


if __name__ == "__main__":
    unittest.main()
