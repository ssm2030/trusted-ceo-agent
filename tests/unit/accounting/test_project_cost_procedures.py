from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError


EXPECTED_CODES = {
    "CA-01": "gl_project_population_difference",
    "CA-02": "direct_indirect_classification_difference",
    "CA-03": "non_homogeneous_pool_cost",
    "CA-04": "allocation_driver_sensitivity",
    "CA-05": "allocation_rate_difference",
    "CA-06": "allocation_completeness_difference",
    "CA-07": "idle_or_abnormal_cost_allocated",
    "CA-08": "payroll_timesheet_difference",
    "CA-09": "vendor_usage_attribution_difference",
    "CA-10": "wip_roll_forward_difference",
    "CA-11": "contract_cost_asset_difference",
    "CA-12": "capitalization_scope_difference",
    "CA-13": "onerous_contract_provision_difference",
    "CA-14": "budget_eac_bridge_difference",
    "CA-15": "alternate_allocation_margin_difference",
    "CA-16": "cross_charge_policy_difference",
}

METRICS = {
    "CA-01": {
        "gl_cost": "100",
        "directly_assigned_cost": "40",
        "allocated_cost": "30",
        "unassigned_cost": "10",
        "excluded_cost": "5",
    },
    "CA-02": {"classified_direct_cost": "70", "traceable_direct_cost": "50"},
    "CA-03": {"pool_cost": "100", "homogeneous_pool_cost": "80"},
    "CA-04": {"current_allocated_cost": "60", "causal_driver_allocated_cost": "45"},
    "CA-05": {
        "eligible_pool_cost": "100",
        "eligible_driver_quantity": "10",
        "recorded_allocation_rate": "8",
        "project_driver_quantity": "4",
        "recorded_allocated_cost": "30",
    },
    "CA-06": {
        "eligible_pool_cost": "100",
        "total_allocated_cost": "95",
        "duplicate_allocated_cost": "2",
    },
    "CA-07": {
        "total_pool_cost": "120",
        "normal_capacity": "12",
        "actual_utilisation": "9",
        "abnormal_waste_cost": "5",
        "project_allocated_idle_cost": "7",
    },
    "CA-08": {
        "paid_or_accrued_hours": "100",
        "project_hours": "60",
        "internal_hours": "20",
        "leave_hours": "10",
        "unassigned_hours": "5",
        "payroll_cost": "1000",
        "timesheet_allocated_cost": "900",
    },
    "CA-09": {
        "vendor_or_service_cost": "100",
        "usage_matched_cost": "70",
        "recorded_project_cost": "90",
    },
    "CA-10": {
        "opening_wip": "10",
        "eligible_current_cost": "100",
        "recognised_cost": "70",
        "write_down": "5",
        "transfer": "0",
        "closing_wip": "40",
    },
    "CA-11": {
        "opening_contract_cost_asset": "10",
        "eligible_contract_cost_additions": "20",
        "recorded_contract_cost_additions": "25",
        "amortisation": "6",
        "impairment": "1",
        "closing_contract_cost_asset": "35",
    },
    "CA-12": {
        "development_cost": "40",
        "training_cost": "10",
        "maintenance_cost": "5",
        "approved_capitalisable_development_cost": "30",
        "recorded_capitalised_cost": "50",
    },
    "CA-13": {
        "expected_economic_benefits": "80",
        "unavoidable_costs": "110",
        "recognised_provision": "10",
    },
    "CA-14": {
        "baseline_budget": "100",
        "approved_change_orders": "10",
        "unapproved_scope_candidate": "5",
        "price_and_rate_changes": "4",
        "productivity_variance": "6",
        "expected_total_cost": "130",
        "eac": "140",
    },
    "CA-15": {
        "project_revenue": "150",
        "recorded_project_cost": "100",
        "alternate_driver_project_cost": "120",
    },
    "CA-16": {
        "cross_charge_cost": "40",
        "policy_supported_charge": "25",
        "recorded_project_cost": "35",
    },
}


def _input(metrics: dict[str, str], *, row_id: str = "row-1") -> dict:
    return {
        "run_id": "run-ca",
        "revision": 3,
        "rows": [
            {
                "row_id": row_id,
                "entity": "entity-a",
                "currency": "KRW",
                "period": "2026-06",
                "project_id": "project-1",
                "metrics": metrics,
                "source_refs": ["evidence:cost-ledger", "evidence:project-master"],
                "counter_evidence_refs": ["evidence:approved-exception"],
            }
        ],
    }


class ProjectCostProcedureTests(unittest.TestCase):
    def _api(self):
        from trusted_ceo_agent.accounting.project_cost_procedures import (
            SUPPORTED_PROJECT_COST_ISSUES,
            run_project_cost_procedure,
            verify_project_cost_procedure_result,
        )

        return (
            SUPPORTED_PROJECT_COST_ISSUES,
            run_project_cost_procedure,
            verify_project_cost_procedure_result,
        )

    def test_all_sixteen_issue_families_execute_real_boundary_procedures(self):
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
                self.assertEqual("project-1", result["outcomes"][0]["project_id"])
                self.assertIsInstance(result["outcomes"][0]["amount"], str)

    def test_missing_metric_or_counter_evidence_fails_closed(self):
        _, run, verify = self._api()
        missing_metric = _input(copy.deepcopy(METRICS["CA-10"]))
        del missing_metric["rows"][0]["metrics"]["closing_wip"]
        result = run("CA-10", missing_metric)
        verify(result)
        self.assertEqual("not_assessable", result["status"])
        self.assertEqual(["row-1:metrics.closing_wip"], result["missing_inputs"])
        self.assertEqual([], result["outcomes"])

        no_counter_evidence = _input(copy.deepcopy(METRICS["CA-08"]))
        no_counter_evidence["rows"][0]["counter_evidence_refs"] = []
        result = run("CA-08", no_counter_evidence)
        self.assertEqual("not_assessable", result["status"])
        self.assertEqual(["row-1:counter_evidence_refs"], result["missing_inputs"])
        self.assertEqual([], result["outcomes"])

    def test_order_and_hash_are_deterministic(self):
        _, run, _ = self._api()
        value = _input(METRICS["CA-01"], row_id="row-b")
        second = copy.deepcopy(value["rows"][0])
        second["row_id"] = "row-a"
        second["project_id"] = "project-0"
        second["source_refs"].reverse()
        value["rows"].append(second)
        reordered = copy.deepcopy(value)
        reordered["rows"].reverse()
        for row in reordered["rows"]:
            row["source_refs"].reverse()

        first = run("CA-01", value)
        second_result = run("CA-01", reordered)
        self.assertEqual(canonical_bytes(first), canonical_bytes(second_result))

    def test_closed_dispatch_and_exact_decimals(self):
        _, run, _ = self._api()
        with self.assertRaises(ContractError):
            run("CA-17", _input(METRICS["CA-01"]))
        invalid = _input(copy.deepcopy(METRICS["CA-05"]))
        invalid["rows"][0]["metrics"]["eligible_pool_cost"] = 100.0
        with self.assertRaises(ContractError):
            run("CA-05", invalid)

    def test_result_cannot_claim_fact_signal_finding_grade_or_approval(self):
        _, run, _ = self._api()
        result = run("CA-13", _input(METRICS["CA-13"]))

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
