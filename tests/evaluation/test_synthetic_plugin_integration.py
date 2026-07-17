from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from trusted_ceo_agent.accounting.dispatcher import dispatch_accounting_suite
from trusted_ceo_agent.accounting.input_adapter import build_accounting_request
from trusted_ceo_agent.canonical import strict_loads
from trusted_ceo_agent.intake.adapters.accounting_json import (
    ACCOUNTING_MULTITABLE_ADAPTER_ID,
    AccountingMultitableJsonAdapter,
)
from trusted_ceo_agent.intake.adapters.selection import select_adapter


ROOT = Path(__file__).resolve().parents[2]
_ANALYSIS_INPUT = ROOT / "evaluation" / "synthetic" / "analysis-input"
_PLUGIN_PACKAGE = ROOT / "plugin" / "trusted-ceo-agent" / "trusted_ceo_agent"
_ALLOWED_SCENARIOS = (
    "boundary-adversarial",
    "boundary-degraded",
    "boundary-expert-trigger",
    "boundary-realistic-missing",
    "clean-baseline",
    "integrated-case",
    "single-ac-08-approved-control",
    "single-ac-08-manual-override",
    "single-ca-02-direct-cost-misclassification",
    "single-ca-04-driver-control",
    "single-cf-07-collection-deterioration",
    "single-cf-10-concentration-control",
    "single-rv-08-early-billing",
    "single-rv-13-sla-control",
)
_REQUEST_KEYS = {
    "scope_ref",
    "suite",
    "tier_zero_input",
    "raw_core_population",
    "revenue_input",
    "cashflow_input",
    "project_cost_inputs",
}
_EXPECTED_NOT_ASSESSABLE = {
    *[f"AC-{number:02d}" for number in range(6, 17)],
    *[f"RV-{number:02d}" for number in range(1, 17)],
    *[f"CF-{number:02d}" for number in range(1, 17)],
    *[
        f"CA-{number:02d}"
        for number in range(1, 17)
        if number not in {2, 4}
    ],
}


def _dispatch(request: dict) -> dict:
    return dispatch_accounting_suite(
        suite=request["suite"],
        tier_zero_input=request["tier_zero_input"],
        raw_core_population=request["raw_core_population"],
        revenue_input=request["revenue_input"],
        cashflow_input=request["cashflow_input"],
        project_cost_inputs=request["project_cost_inputs"],
    )


class SyntheticPluginIntegrationTests(unittest.TestCase):
    def test_explicit_allowed_inputs_follow_the_bounded_plugin_path(self) -> None:
        selected_types: set[type] = set()
        releases: set[str] = set()

        for scenario in _ALLOWED_SCENARIOS:
            with self.subTest(scenario=scenario):
                path = _ANALYSIS_INPUT / scenario / "dataset.json"
                snapshot = path.read_bytes()
                snapshot_sha256 = hashlib.sha256(snapshot).hexdigest()
                source_id = "source_" + snapshot_sha256[:24]
                document = strict_loads(snapshot)

                self.assertEqual(33, len(document["tables"]))
                self.assertEqual(
                    360,
                    sum(len(rows) for rows in document["tables"].values()),
                )

                adapter = select_adapter(f"{scenario}.json", path)
                selected_types.add(type(adapter))
                self.assertIs(type(adapter), AccountingMultitableJsonAdapter)
                parsed = adapter.parse(path, source_id)
                self.assertEqual(
                    ACCOUNTING_MULTITABLE_ADAPTER_ID,
                    parsed.metadata["adapter_id"],
                )
                self.assertEqual(33, len(parsed.metadata["table_row_counts"]))
                self.assertEqual(360, len(parsed.records))

                arguments = {
                    "run_id": "run_synthetic_plugin",
                    "revision": 1,
                    "scope_ref": "scope_synthetic_plugin",
                    "source_id": source_id,
                    "snapshot_sha256": snapshot_sha256,
                }
                request = build_accounting_request(document, **arguments)
                self.assertEqual(
                    request,
                    build_accounting_request(document, **arguments),
                )
                self.assertEqual(_REQUEST_KEYS, set(request))
                self.assertEqual("machine_draft", request["suite"]["authority"])
                releases.add(request["suite"]["release_id"])

                raw = request["raw_core_population"]
                self.assertEqual(
                    {
                        "run_id",
                        "revision",
                        "close_timestamp",
                        "journals",
                        "allowed_account_pairs",
                        "subsequent_disbursements",
                        "policy_changes",
                        "capitalization_items",
                        "counterparties",
                    },
                    set(raw),
                )
                for field in (
                    "journals",
                    "allowed_account_pairs",
                    "subsequent_disbursements",
                    "policy_changes",
                    "capitalization_items",
                    "counterparties",
                ):
                    self.assertEqual([], raw[field], field)

                revenue = request["revenue_input"]
                for field in (
                    "contracts",
                    "obligations",
                    "events",
                    "balances",
                    "contract_costs",
                    "credit_risks",
                ):
                    self.assertEqual([], revenue[field], field)
                cashflow = request["cashflow_input"]
                for field, value in cashflow.items():
                    if field not in {"run_id", "revision", "as_of_date"}:
                        self.assertEqual([], value, field)
                for issue_id, value in request["project_cost_inputs"].items():
                    if issue_id not in {"CA-02", "CA-04"}:
                        self.assertEqual([], value["rows"], issue_id)

                bundle = _dispatch(request)
                records = bundle["execution_manifest"]["family_records"]
                self.assertEqual(64, len(records))
                self.assertEqual(30, len(bundle["result_artifacts"]))
                self.assertEqual("Boundary", bundle["authority_ceiling"])
                self.assertEqual(
                    _EXPECTED_NOT_ASSESSABLE,
                    {
                        record["issue_family_id"]
                        for record in records
                        if record["status"] == "not_assessable"
                    },
                )

        self.assertEqual({AccountingMultitableJsonAdapter}, selected_types)
        self.assertEqual({"accounting-suite-2026-07-17"}, releases)

    def test_production_package_has_no_evaluation_helper_dependency(self) -> None:
        forbidden = (
            "tools.synthetic_data",
            "tests.evaluation",
            "evaluation.synthetic",
        )
        for path in _PLUGIN_PACKAGE.rglob("*.py"):
            source = path.read_text("utf-8")
            for dependency in forbidden:
                with self.subTest(
                    module=str(path.relative_to(_PLUGIN_PACKAGE)),
                    dependency=dependency,
                ):
                    self.assertNotIn(dependency, source)


if __name__ == "__main__":
    unittest.main()
