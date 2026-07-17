from __future__ import annotations

import copy
import unittest
from decimal import getcontext

from tests.support_accounting_multitable import (
    valid_accounting_multitable_document,
)
from trusted_ceo_agent.accounting.dispatcher import dispatch_accounting_suite
from trusted_ceo_agent.accounting.input_adapter import build_accounting_request
from trusted_ceo_agent.errors import ContractError


SNAPSHOT_SHA256 = "a" * 64
SOURCE_ID = "source_" + SNAPSHOT_SHA256[:24]
RUN_ID = "run_fixture"
REVISION = 4
SCOPE_REF = "scope_fixture"


def _build(
    document: dict | None = None,
    *,
    run_id: object = RUN_ID,
    revision: object = REVISION,
    scope_ref: object = SCOPE_REF,
    source_id: object = SOURCE_ID,
    snapshot_sha256: object = SNAPSHOT_SHA256,
) -> dict:
    return build_accounting_request(
        document or valid_accounting_multitable_document(),
        run_id=run_id,  # type: ignore[arg-type]
        revision=revision,  # type: ignore[arg-type]
        scope_ref=scope_ref,  # type: ignore[arg-type]
        source_id=source_id,  # type: ignore[arg-type]
        snapshot_sha256=snapshot_sha256,  # type: ignore[arg-type]
    )


def _dispatch(request: dict) -> dict:
    return dispatch_accounting_suite(
        suite=request["suite"],
        tier_zero_input=request["tier_zero_input"],
        raw_core_population=request["raw_core_population"],
        revenue_input=request["revenue_input"],
        cashflow_input=request["cashflow_input"],
        project_cost_inputs=request["project_cost_inputs"],
    )


class AccountingInputAdapterTests(unittest.TestCase):
    def test_builds_exact_snapshot_bound_seven_field_request(self) -> None:
        request = _build()

        self.assertEqual(
            {
                "scope_ref",
                "suite",
                "tier_zero_input",
                "raw_core_population",
                "revenue_input",
                "cashflow_input",
                "project_cost_inputs",
            },
            set(request),
        )
        self.assertEqual(SCOPE_REF, request["scope_ref"])
        self.assertEqual(
            "accounting-suite-2026-07-17",
            request["suite"]["release_id"],
        )
        self.assertNotEqual(SNAPSHOT_SHA256, request["suite"]["release_id"])
        self.assertEqual(
            {"from": "2026-01-01", "to": "2026-06-30"},
            request["suite"]["effective_period"],
        )

        inputs = [
            request["tier_zero_input"],
            request["raw_core_population"],
            request["revenue_input"],
            request["cashflow_input"],
            *request["project_cost_inputs"].values(),
        ]
        self.assertEqual(20, len(inputs))
        self.assertTrue(
            all(
                (item["run_id"], item["revision"]) == (RUN_ID, REVISION)
                for item in inputs
            )
        )

        manifest = request["tier_zero_input"]["source_manifests"]
        self.assertEqual(
            [
                {
                    "source_id": SOURCE_ID,
                    "source_sha256": SNAPSHOT_SHA256,
                    "period_start": "2026-01-01",
                    "period_end": "2026-06-30",
                    "header_count": 1,
                    "line_count": 2,
                    "debit_total": "100",
                    "credit_total": "100",
                }
            ],
            manifest,
        )
        self.assertEqual(
            SOURCE_ID,
            request["tier_zero_input"]["journal_headers"][0]["source_id"],
        )
        self.assertEqual(
            "-100",
            request["tier_zero_input"]["subledger_balances"][0]["amount"],
        )
        self.assertEqual(
            "100.00",
            request["tier_zero_input"]["journal_lines"][0]["debit"],
        )
        self.assertEqual(
            "-100.00",
            request["tier_zero_input"]["trial_balance"][0]["closing"],
        )

        expected_vendor_ref = (
            f"{SOURCE_ID}@{SNAPSHOT_SHA256}#/tables/vendor_costs/0"
        )
        ca02_row = request["project_cost_inputs"]["CA-02"]["rows"][0]
        self.assertEqual([expected_vendor_ref], ca02_row["source_refs"])
        self.assertEqual(
            [
                f"{SOURCE_ID}@{SNAPSHOT_SHA256}"
                "#/tables/direct_costs/0"
            ],
            ca02_row["counter_evidence_refs"],
        )

    def test_only_safe_families_are_assessable(self) -> None:
        request = _build()
        bundle = _dispatch(request)
        records = {
            item["issue_family_id"]: item["status"]
            for item in bundle["execution_manifest"]["family_records"]
        }

        self.assertEqual(64, len(records))
        self.assertEqual(30, len(bundle["result_artifacts"]))
        for issue_id in [f"AC-{number:02d}" for number in range(1, 6)]:
            self.assertNotEqual("not_assessable", records[issue_id])
        for issue_id in ("CA-02", "CA-04"):
            self.assertNotEqual("not_assessable", records[issue_id])

        expected_not_assessable = {
            *[f"AC-{number:02d}" for number in range(6, 17)],
            *[f"RV-{number:02d}" for number in range(1, 17)],
            *[f"CF-{number:02d}" for number in range(1, 17)],
            *[
                f"CA-{number:02d}"
                for number in range(1, 17)
                if number not in {2, 4}
            ],
        }
        self.assertEqual(
            expected_not_assessable,
            {
                issue_id
                for issue_id, status in records.items()
                if status == "not_assessable"
            },
        )

    def test_maps_only_evidence_backed_ca02_and_ca04_metrics(self) -> None:
        request = _build()
        ca02 = request["project_cost_inputs"]["CA-02"]["rows"]
        ca04 = request["project_cost_inputs"]["CA-04"]["rows"]

        self.assertEqual(1, len(ca02))
        self.assertEqual(
            {
                "classified_direct_cost": "100",
                "traceable_direct_cost": "80",
            },
            ca02[0]["metrics"],
        )
        self.assertEqual(1, len(ca04))
        self.assertEqual(
            {
                "current_allocated_cost": "100",
                "causal_driver_allocated_cost": "120",
            },
            ca04[0]["metrics"],
        )
        self.assertEqual(
            [
                f"{SOURCE_ID}@{SNAPSHOT_SHA256}"
                "#/tables/allocation_results/0"
            ],
            ca04[0]["source_refs"],
        )
        self.assertEqual(
            {
                f"{SOURCE_ID}@{SNAPSHOT_SHA256}"
                "#/tables/allocation_pools/0",
                f"{SOURCE_ID}@{SNAPSHOT_SHA256}"
                "#/tables/allocation_drivers/0",
            },
            set(ca04[0]["counter_evidence_refs"]),
        )

    def test_ca02_includes_unlinked_explicit_vendor_classification(self) -> None:
        document = valid_accounting_multitable_document()
        second_vendor = copy.deepcopy(document["tables"]["vendor_costs"][0])
        second_vendor.update(
            {
                "amount": "20.00",
                "invoice_reference": "INV-V2",
                "vendor_cost_id": "VC2",
            }
        )
        document["tables"]["vendor_costs"].append(second_vendor)

        row = _build(document)["project_cost_inputs"]["CA-02"]["rows"][0]

        self.assertEqual(
            {
                "classified_direct_cost": "120",
                "traceable_direct_cost": "80",
            },
            row["metrics"],
        )
        self.assertEqual(
            [
                f"{SOURCE_ID}@{SNAPSHOT_SHA256}#/tables/vendor_costs/0",
                f"{SOURCE_ID}@{SNAPSHOT_SHA256}#/tables/vendor_costs/1",
            ],
            row["source_refs"],
        )

    def test_rejects_linked_ca02_period_mismatch(self) -> None:
        document = valid_accounting_multitable_document()
        document["tables"]["direct_costs"][0]["cost_date"] = "2026-05-31"

        with self.assertRaisesRegex(ContractError, "period"):
            _build(document)

    def test_missing_ca02_source_population_does_not_invent_zero(self) -> None:
        document = valid_accounting_multitable_document()
        document["tables"]["direct_costs"] = []

        request = _build(document)

        self.assertEqual(
            [],
            request["project_cost_inputs"]["CA-02"]["rows"],
        )

    def test_unsupported_populations_remain_empty_without_defaults(self) -> None:
        request = _build()

        raw = request["raw_core_population"]
        self.assertEqual("2026-06-30", raw["close_timestamp"])
        for field in (
            "journals",
            "allowed_account_pairs",
            "subsequent_disbursements",
            "policy_changes",
            "capitalization_items",
            "counterparties",
        ):
            self.assertEqual([], raw[field])

        revenue = request["revenue_input"]
        for field in (
            "contracts",
            "obligations",
            "events",
            "balances",
            "contract_costs",
            "credit_risks",
        ):
            self.assertEqual([], revenue[field])

        cashflow = request["cashflow_input"]
        for field, value in cashflow.items():
            if field not in {"run_id", "revision", "as_of_date"}:
                self.assertEqual([], value, field)

    def test_rejects_duplicate_trial_balance_dimension(self) -> None:
        document = valid_accounting_multitable_document()
        duplicate = copy.deepcopy(document["tables"]["trial_balance"][0])
        duplicate["trial_balance_id"] = "TB-DUPLICATE-DIMENSION"
        document["tables"]["trial_balance"].append(duplicate)

        with self.assertRaisesRegex(ContractError, "trial_balance.*duplicate"):
            _build(document)

    def test_rejects_allocation_result_driver_scope_mismatch(self) -> None:
        document = valid_accounting_multitable_document()
        second_pool = copy.deepcopy(document["tables"]["allocation_pools"][0])
        second_pool.update({"pool_id": "POOL2", "pool_name": "Other"})
        document["tables"]["allocation_pools"].append(second_pool)
        second_driver = copy.deepcopy(
            document["tables"]["allocation_drivers"][0]
        )
        second_driver.update({"driver_id": "DRV2", "pool_id": "POOL2"})
        document["tables"]["allocation_drivers"].append(second_driver)
        document["tables"]["allocation_results"][0]["driver_id"] = "DRV2"

        with self.assertRaisesRegex(ContractError, "driver"):
            _build(document)

    def test_rejects_aging_rows_without_exact_control_match(self) -> None:
        document = valid_accounting_multitable_document()
        unmatched = copy.deepcopy(document["tables"]["payable_aging"][0])
        unmatched.update({"ap_item_id": "AP2", "as_of_date": "2026-05-31"})
        document["tables"]["payable_aging"].append(unmatched)

        with self.assertRaisesRegex(ContractError, "control"):
            _build(document)

    def test_accepts_only_supported_monthly_and_half_year_periods(self) -> None:
        accepted = valid_accounting_multitable_document()
        accepted["tables"]["management_kpis"] = [
            {
                "dimension_id": "E1",
                "dimension_type": "company",
                "entity": "E1",
                "kpi_id": "KPI1",
                "metric_name": "customer_concentration",
                "period": "2026-H1",
                "unit": "ratio",
                "value": "0.36",
            }
        ]
        accepted["tables"]["budgets"] = [
            {
                "budget_id": "B1",
                "cost_budget": "100",
                "currency": "KRW",
                "entity": "E1",
                "hours_budget": "10",
                "period": "2026-H1",
                "project_id": "P1",
                "revenue_budget": "200",
            }
        ]
        _build(accepted)

        rejected = copy.deepcopy(accepted)
        rejected["tables"]["management_kpis"][0]["period"] = "2026-Q1"
        with self.assertRaisesRegex(ContractError, "period"):
            _build(rejected)

        rejected_budget = copy.deepcopy(accepted)
        rejected_budget["tables"]["budgets"][0]["period"] = "2026-Q1"
        with self.assertRaisesRegex(ContractError, "period"):
            _build(rejected_budget)

        rejected_month = valid_accounting_multitable_document()
        rejected_month["tables"]["journal_headers"][0]["period"] = "2026-H1"
        with self.assertRaisesRegex(ContractError, "period"):
            _build(rejected_month)

    def test_rejects_schema_key_primary_and_foreign_key_failures(self) -> None:
        cases: dict[str, tuple[dict, str]] = {}

        missing_field = valid_accounting_multitable_document()
        missing_field["tables"]["vendor_costs"][0].pop("amount")
        cases["missing field"] = (missing_field, "field")

        unknown_field = valid_accounting_multitable_document()
        unknown_field["tables"]["vendor_costs"][0]["unexpected"] = "x"
        cases["unknown field"] = (unknown_field, "field")

        duplicate = valid_accounting_multitable_document()
        duplicate["tables"]["journal_lines"].append(
            copy.deepcopy(duplicate["tables"]["journal_lines"][0])
        )
        cases["duplicate primary key"] = (duplicate, "duplicate")

        missing_fk = valid_accounting_multitable_document()
        missing_fk["tables"]["journal_lines"][0]["account_id"] = "UNKNOWN"
        cases["missing foreign key"] = (missing_fk, "foreign key")

        missing_source_fk = valid_accounting_multitable_document()
        missing_source_fk["tables"]["direct_costs"][0][
            "source_row_id"
        ] = "UNKNOWN"
        cases["missing source foreign key"] = (
            missing_source_fk,
            "source_row_id",
        )

        for label, (document, pattern) in cases.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(ContractError, pattern):
                    _build(document)

    def test_decimal_calculations_ignore_process_context(self) -> None:
        document = valid_accounting_multitable_document()
        second_project = copy.deepcopy(document["tables"]["projects"][0])
        second_project.update(
            {"project_id": "P2", "project_name": "Second project"}
        )
        document["tables"]["projects"].append(second_project)
        document["tables"]["allocation_pools"][0]["source_amount"] = "100.00"
        document["tables"]["allocation_drivers"][0].update(
            {"driver_quantity": "1.00", "driver_share": "0.333333"}
        )
        second_driver = copy.deepcopy(
            document["tables"]["allocation_drivers"][0]
        )
        second_driver.update(
            {
                "driver_id": "DRV2",
                "driver_quantity": "2.00",
                "driver_share": "0.666667",
                "project_id": "P2",
            }
        )
        document["tables"]["allocation_drivers"].append(second_driver)

        original_precision = getcontext().prec
        values = []
        try:
            for precision in (6, 28):
                getcontext().prec = precision
                row = _build(copy.deepcopy(document))["project_cost_inputs"][
                    "CA-04"
                ]["rows"][0]
                values.append(row["metrics"]["causal_driver_allocated_cost"])
        finally:
            getcontext().prec = original_precision

        self.assertEqual(values[0], values[1])

    def test_rejects_invalid_dates_decimals_dimensions_and_journals(self) -> None:
        cases: dict[str, tuple[dict, str]] = {}

        invalid_date = valid_accounting_multitable_document()
        invalid_date["tables"]["journal_headers"][0][
            "posting_date"
        ] = "2026-02-30"
        cases["invalid date"] = (invalid_date, "date")

        invalid_timestamp = valid_accounting_multitable_document()
        invalid_timestamp["tables"]["journal_headers"][0][
            "entered_at"
        ] = "2026-06-30T10:00:00"
        cases["timezone-naive timestamp"] = (invalid_timestamp, "timestamp")

        invalid_decimal = valid_accounting_multitable_document()
        invalid_decimal["tables"]["journal_lines"][0]["debit"] = "not-money"
        cases["invalid decimal"] = (invalid_decimal, "decimal")

        non_finite = valid_accounting_multitable_document()
        non_finite["tables"]["journal_lines"][0]["debit"] = "NaN"
        cases["non-finite decimal"] = (non_finite, "finite")

        exponent = valid_accounting_multitable_document()
        exponent["tables"]["vendor_costs"][0]["amount"] = "1e10000"
        cases["exponent expansion"] = (exponent, "plain decimal")

        currency = valid_accounting_multitable_document()
        currency["tables"]["vendor_costs"][0]["currency"] = "USD"
        cases["currency mismatch"] = (currency, "currency")

        entity = valid_accounting_multitable_document()
        entity["tables"]["vendor_costs"][0]["entity"] = "E2"
        cases["entity mismatch"] = (entity, "entity")

        both_sides = valid_accounting_multitable_document()
        both_sides["tables"]["journal_lines"][0]["credit"] = "1.00"
        cases["both sides positive"] = (both_sides, "both")

        unbalanced = valid_accounting_multitable_document()
        unbalanced["tables"]["journal_lines"][1]["credit"] = "99.00"
        cases["unbalanced journal"] = (unbalanced, "balance")

        large_unbalanced = valid_accounting_multitable_document()
        large_unbalanced["tables"]["journal_lines"][0]["debit"] = (
            "1000000000000000000000000000001"
        )
        large_unbalanced["tables"]["journal_lines"][1]["credit"] = (
            "1000000000000000000000000000000"
        )
        cases["large unbalanced journal"] = (large_unbalanced, "balance")

        for label, (document, pattern) in cases.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(ContractError, pattern):
                    _build(document)

    def test_rejects_invalid_runtime_binding(self) -> None:
        cases = (
            ("empty run", {"run_id": ""}, "run_id"),
            ("empty scope", {"scope_ref": ""}, "scope_ref"),
            ("empty source", {"source_id": ""}, "source_id"),
            ("negative revision", {"revision": -1}, "revision"),
            ("boolean revision", {"revision": True}, "revision"),
            (
                "short hash",
                {"snapshot_sha256": "a" * 63},
                "snapshot_sha256",
            ),
            (
                "uppercase hash",
                {"snapshot_sha256": "A" * 64},
                "snapshot_sha256",
            ),
            (
                "source mismatch",
                {"source_id": "source_" + "b" * 24},
                "source_id",
            ),
        )
        for label, kwargs, pattern in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ContractError, pattern):
                    _build(**kwargs)


if __name__ == "__main__":
    unittest.main()
