from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tests.integration.test_cli_components import call, prepare_authorized_scope
from tests.unit.accounting.test_cashflow_procedures import valid_input as cash_input
from tests.unit.accounting.test_core_population_adapter import valid_population
from tests.unit.accounting.test_project_cost_procedures import METRICS as cost_metrics
from tests.unit.accounting.test_project_cost_procedures import _input as cost_input
from tests.unit.accounting.test_revenue_procedures import valid_input as revenue_input
from tests.unit.accounting.test_tier_zero import valid_input as tier_zero_input
from trusted_ceo_agent.accounting import build_machine_draft_suite
from trusted_ceo_agent.canonical import canonical_bytes


ROOT = Path(__file__).resolve().parents[2]


def accounting_request(run_id: str, revision: int, scope_ref: str) -> dict:
    def bind(value: dict) -> dict:
        bound = copy.deepcopy(value)
        bound.update({"run_id": run_id, "revision": revision})
        return bound

    return {
        "scope_ref": scope_ref,
        "suite": build_machine_draft_suite(
            release_id="accounting-cli-release-1",
            effective_from="2026-01-01",
        ),
        "tier_zero_input": bind(tier_zero_input()),
        "raw_core_population": bind(valid_population()),
        "revenue_input": bind(revenue_input()),
        "cashflow_input": bind(cash_input()),
        "project_cost_inputs": {
            issue_id: bind(cost_input(metrics))
            for issue_id, metrics in cost_metrics.items()
        },
    }


class CliAccountingComponentsTests(unittest.TestCase):
    def test_dispatches_and_publishes_request_and_bundle_in_same_revision(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            _, run_id, store, common, _, scope_ref, _, _ = prepare_authorized_scope(root)
            request_path = root / "accounting.json"
            request_bytes = canonical_bytes(accounting_request(run_id, 4, scope_ref))
            request_path.write_bytes(request_bytes)
            request_hash = hashlib.sha256(request_bytes).hexdigest()

            code, result = call([
                "run-components",
                *common,
                "--scope-ref",
                scope_ref,
                "--accounting-input",
                str(request_path),
                "--expected-revision",
                "3",
            ])

            self.assertEqual(0, code, result)
            data = result["data"]
            self.assertEqual(request_hash, data["accounting_request_hash"])
            self.assertEqual(64, data["accounting_issue_family_count"])
            self.assertEqual(30, data["accounting_result_artifact_count"])
            bundle_hash = data["accounting_execution_bundle_hash"]
            snapshot = store.verify_revision(4)
            self.assertEqual(
                request_bytes,
                (
                    snapshot
                    / "accounting"
                    / "requests"
                    / f"{request_hash}.json"
                ).read_bytes(),
            )
            bundle = json.loads(
                (
                    snapshot
                    / "accounting"
                    / "executions"
                    / f"{bundle_hash}.json"
                ).read_text("utf-8")
            )
            self.assertEqual(
                (run_id, 4, bundle_hash),
                (bundle["run_id"], bundle["revision"], bundle["content_hash"]),
            )
            self.assertEqual(
                64,
                len(bundle["execution_manifest"]["family_records"]),
            )

    def test_invalid_input_fails_before_revision_publish(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            _, run_id, store, common, _, scope_ref, _, _ = prepare_authorized_scope(root)
            request_path = root / "accounting.json"
            mismatch = accounting_request(run_id, 4, "scope_not_approved")
            missing = accounting_request(run_id, 4, scope_ref)
            missing.pop("cashflow_input")
            unknown = accounting_request(run_id, 4, scope_ref)
            unknown["unexpected"] = {}

            for value in (mismatch, missing, unknown):
                request_path.write_bytes(canonical_bytes(value))
                code, result = call([
                    "run-components",
                    *common,
                    "--scope-ref",
                    scope_ref,
                    "--accounting-input",
                    str(request_path),
                    "--expected-revision",
                    "3",
                ])
                self.assertEqual(3, code, result)
                self.assertFalse(result["ok"])
                self.assertEqual(3, store.state()["revision"])


if __name__ == "__main__":
    unittest.main()
