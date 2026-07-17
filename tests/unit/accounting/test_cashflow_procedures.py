from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError


def _scope() -> dict[str, str]:
    return {"entity": "E1", "currency": "KRW", "period": "2026-06"}


def valid_input() -> dict:
    scope = _scope()
    return {
        "run_id": "run_cashflow",
        "revision": 3,
        "as_of_date": "2026-06-30",
        "bank_reconciliations": [{
            "reconciliation_id": "BR1",
            "bank_account_id": "BANK-1",
            **scope,
            "bank_balance": "1000",
            "deposits_in_transit": "100",
            "outstanding_payments": "50",
            "verified_reconciling_items": "0",
            "cash_gl_balance": "1050",
            "bank_source_ref": "SRC-BANK-1",
            "gl_source_ref": "SRC-GL-1",
        }],
        "cash_items": [{
            "cash_item_id": "CI1",
            **scope,
            "amount": "500",
            "instrument_type": "demand_deposit",
            "maturity_days": 0,
            "readily_convertible": True,
            "value_change_risk": "insignificant",
            "restricted": False,
            "restriction_evidence_ref": None,
            "recorded_classification": "cash",
        }],
        "cash_transactions": [{
            "transaction_id": "TX1",
            **scope,
            "amount": "100",
            "economic_event": "asset_purchase",
            "original_event_ref": "EV-ASSET-1",
            "reported_classification": "investing",
            "expected_classification": "investing",
            "is_cash": True,
            "reported_in_cashflow": True,
            "counterparty_id": "SUP-1",
            "invoice_id": "INV-1",
            "source_ref": "SRC-BANK-TX1",
        }],
        "financing_bridges": [{
            "bridge_id": "FB1",
            **scope,
            "opening_liability": "1000",
            "cash_proceeds": "200",
            "cash_repayments": "100",
            "noncash_changes": "50",
            "fx_changes": "-10",
            "other_changes": "0",
            "closing_liability": "1140",
            "source_ref": "SRC-DEBT-1",
        }],
        "supplier_finance_programs": [{
            "program_id": "SF1",
            **scope,
            "amount": "0",
            "standard_term_days": 30,
            "actual_term_days": 30,
            "financial_institution_pays_supplier": False,
            "contract_ref": "CONTRACT-SF1",
            "disclosure_ref": "DISC-SF1",
            "recorded_classification": "ap",
            "counterparty_id": "SUP-1",
        }],
        "receivables": [{
            "invoice_id": "AR1",
            "customer_id": "CUS-1",
            **scope,
            "outstanding_amount": "100",
            "aging_days": 10,
            "subsequent_collections": "100",
            "credit_notes": "0",
            "disputes": "0",
            "write_offs": "0",
            "expected_credit_loss": "0",
            "source_ref": "SRC-AR1",
        }],
        "payables": [{
            "payable_id": "AP1",
            "supplier_id": "SUP-1",
            **scope,
            "amount": "100",
            "outstanding_amount": "0",
            "days_overdue": 0,
            "standard_term_days": 30,
            "actual_term_days": 30,
            "paid_after_period": "100",
            "disputed": False,
            "supplier_finance_program_id": None,
            "source_ref": "SRC-AP1",
        }],
        "profit_cash_bridges": [{
            "bridge_id": "PCB1",
            **scope,
            "operating_result": "100",
            "noncash_expense": "20",
            "noncash_income": "10",
            "ar_change": "-30",
            "contract_balance_change": "0",
            "ap_change": "20",
            "payroll_tax_change": "0",
            "provision_change": "0",
            "deferred_change": "0",
            "other_working_capital_change": "0",
            "operating_adjustments": "0",
            "reported_operating_cash_flow": "100",
            "source_ref": "SRC-PCB1",
        }],
        "counterparty_exposures": [{
            "exposure_id": "EX1",
            "counterparty_id": "CUS-1",
            "counterparty_type": "customer",
            **scope,
            "exposure_amount": "10",
            "total_population_amount": "100",
            "stress_loss_rate": "0.10",
            "source_ref": "SRC-EX1",
        }],
        "receivable_transfers": [{
            "transfer_id": "RT1",
            **scope,
            "amount": "100",
            "cash_received": "100",
            "recourse_amount": "0",
            "retained_risk": False,
            "servicing_retained": False,
            "repurchase_obligation": False,
            "recorded_treatment": "sale",
            "contract_evidence_ref": "CONTRACT-RT1",
        }],
        "covenants": [{
            "covenant_id": "CV1",
            **scope,
            "metric_name": "current_ratio",
            "actual_value": "2",
            "threshold_value": "1",
            "direction": "min",
            "headroom": "1",
            "contract_ref": "CONTRACT-CV1",
        }],
        "mandatory_payments": [{
            "payment_id": "MP1",
            **scope,
            "payment_type": "tax",
            "amount_due": "100",
            "amount_paid": "100",
            "days_overdue": 0,
            "due_evidence_ref": "SRC-TAX-1",
        }],
        "period_end_events": [{
            "event_id": "PE1",
            **scope,
            "event_type": "ordinary",
            "inflow_amount": "0",
            "outflow_amount": "10",
            "related_event_ref": None,
            "days_from_period_end": 1,
            "source_ref": "SRC-PE1",
        }],
        "forecasts": [{
            "forecast_id": "FC1",
            **scope,
            "forecast_amount": "100",
            "actual_amount": "100",
            "opening_available_cash": "100",
            "mandatory_outflows": "40",
            "scenario_inflows": "40",
            "minimum_cash_required": "50",
            "horizon_days": 91,
            "source_ref": "SRC-FC1",
        }],
        "liquidity_positions": [{
            "position_id": "LP1",
            **scope,
            "unrestricted_cash": "100",
            "committed_undrawn_facilities": "50",
            "mandatory_outflows": "75",
            "scenario_inflows": "25",
            "covenant_headroom": "10",
            "runway_days": 180,
            "minimum_runway_days": 90,
            "stress_shortfall": "0",
            "management_plan_evidence_ref": "SRC-PLAN-1",
            "going_concern_assessment_ref": "SRC-GC-1",
        }],
    }


def api():
    from trusted_ceo_agent.accounting.cashflow_procedures import (
        run_cashflow_procedures,
        verify_cashflow_procedure_result,
    )

    return run_cashflow_procedures, verify_cashflow_procedure_result


def _codes(result: dict) -> set[str]:
    return {item["code"] for item in result["outcomes"]}


class CashFlowProcedureTests(unittest.TestCase):
    def test_all_sixteen_families_have_closed_deterministic_execution(self) -> None:
        run, verify = api()
        result = run(valid_input())
        self.assertEqual(
            [f"CF-{number:02d}" for number in range(1, 17)],
            [item["issue_family_id"] for item in result["procedure_results"]],
        )
        self.assertEqual(
            [f"P-CF-{number:02d}" for number in range(1, 14)]
            + ["P-CF-13", "P-CF-12", "P-CF-11"],
            [item["procedure_id"] for item in result["procedure_results"]],
        )
        self.assertTrue(all(
            item["implementation_status"] == "implemented_deterministic"
            and item["outcomes"]
            for item in result["procedure_results"]
        ))
        self.assertTrue(result["coverage_complete"])
        self.assertFalse(result["expert_review_required"])
        self.assertEqual("Boundary", result["authority_ceiling"])
        verify(result)

    def test_each_family_executes_material_failure_behavior_and_boundaries(self) -> None:
        run, _ = api()
        value = valid_input()
        value["bank_reconciliations"][0]["cash_gl_balance"] = "1000"
        value["cash_items"][0].update(
            restricted=True,
            restriction_evidence_ref=None,
            recorded_classification="cash",
        )
        value["cash_transactions"][0].update(
            reported_classification="operating",
            is_cash=False,
            reported_in_cashflow=True,
        )
        value["financing_bridges"][0]["closing_liability"] = "1100"
        value["supplier_finance_programs"][0].update(
            amount="500",
            actual_term_days=90,
            financial_institution_pays_supplier=True,
            contract_ref=None,
            disclosure_ref=None,
        )
        value["receivables"][0].update(
            aging_days=120,
            subsequent_collections="10",
            expected_credit_loss="5",
        )
        value["payables"][0].update(
            outstanding_amount="100",
            days_overdue=45,
            actual_term_days=90,
            paid_after_period="0",
        )
        value["profit_cash_bridges"][0]["reported_operating_cash_flow"] = "80"
        value["counterparty_exposures"][0]["exposure_amount"] = "50"
        value["receivable_transfers"][0].update(
            recourse_amount="80",
            retained_risk=True,
            recorded_treatment="sale",
            contract_evidence_ref=None,
        )
        value["covenants"][0].update(actual_value="0.5", contract_ref=None)
        value["mandatory_payments"][0].update(
            amount_paid="0", days_overdue=20, due_evidence_ref=None
        )
        value["period_end_events"][0].update(
            event_type="temporary_deposit",
            inflow_amount="100",
            outflow_amount="0",
        )
        value["forecasts"][0].update(
            forecast_amount="150",
            actual_amount="50",
            opening_available_cash="20",
            scenario_inflows="0",
        )
        value["liquidity_positions"][0].update(
            runway_days=30,
            stress_shortfall="100",
            covenant_headroom="-1",
            management_plan_evidence_ref=None,
            going_concern_assessment_ref=None,
        )

        by_issue = {
            item["issue_family_id"]: item
            for item in run(value)["procedure_results"]
        }
        expected = {
            "CF-01": "bank_gl_unexplained_difference",
            "CF-02": "restriction_evidence_missing",
            "CF-03": "cashflow_classification_difference",
            "CF-04": "noncash_transaction_included",
            "CF-05": "financing_bridge_difference",
            "CF-06": "supplier_finance_contract_missing",
            "CF-07": "collection_deterioration",
            "CF-08": "overdue_payable",
            "CF-09": "profit_to_cash_bridge_difference",
            "CF-10": "counterparty_concentration",
            "CF-11": "transfer_contract_missing",
            "CF-12": "covenant_contract_missing",
            "CF-13": "mandatory_payment_evidence_missing",
            "CF-14": "period_end_reversal_link_missing",
            "CF-15": "forecast_optimism_bias",
            "CF-16": "going_concern_trigger",
        }
        for issue_id, code in expected.items():
            self.assertIn(code, _codes(by_issue[issue_id]), issue_id)

        result = run(value)
        self.assertTrue(result["expert_review_required"])
        self.assertTrue(
            {"legal", "tax", "going_concern"}
            <= {item["target_domain"] for item in result["cross_domain_triggers"]}
        )
        self.assertTrue(all(
            item["disposition"] == "expert_review_required"
            for item in result["cross_domain_triggers"]
        ))

    def test_missing_populations_fail_closed_instead_of_weak_pass(self) -> None:
        run, _ = api()
        value = valid_input()
        for name, records in list(value.items()):
            if isinstance(records, list):
                value[name] = []
        result = run(value)
        self.assertFalse(result["coverage_complete"])
        self.assertTrue(all(
            item["status"] == "not_assessable"
            and _codes(item) == {"required_population_missing"}
            for item in result["procedure_results"]
        ))

    def test_supplier_finance_classification_boundary_has_expert_packet(self) -> None:
        run, _ = api()
        value = valid_input()
        value["supplier_finance_programs"][0].update(
            amount="500",
            actual_term_days=90,
            financial_institution_pays_supplier=True,
        )
        result = run(value)
        self.assertTrue(result["expert_review_required"])
        self.assertIn(
            "supplier_finance_classification_review",
            {item["reason_code"] for item in result["cross_domain_triggers"]},
        )

    def test_order_hash_decimal_types_and_tamper_are_fail_closed(self) -> None:
        run, verify = api()
        first = valid_input()
        second = copy.deepcopy(first)
        for records in second.values():
            if isinstance(records, list):
                records.reverse()
        self.assertEqual(canonical_bytes(run(first)), canonical_bytes(run(second)))

        tampered = run(first)
        tampered["procedure_results"][0]["status"] = "exceptions_found"
        with self.assertRaises(ContractError):
            verify(tampered)

        for mutator in (
            lambda value: value["bank_reconciliations"][0].__setitem__("grade", "A"),
            lambda value: value["bank_reconciliations"][0].__setitem__("bank_balance", 1000),
            lambda value: (
                value["payables"][0].__setitem__("supplier_finance_program_id", "SF1"),
                value["payables"][0].__setitem__("currency", "USD"),
            ),
        ):
            value = valid_input()
            mutator(value)
            with self.assertRaises(ContractError):
                run(value)


if __name__ == "__main__":
    unittest.main()
