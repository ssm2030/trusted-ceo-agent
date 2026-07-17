from __future__ import annotations

import copy
import hashlib
import unittest

from tests.unit.accounting.test_cashflow_procedures import valid_input as cash_input
from tests.unit.accounting.test_core_population_adapter import valid_population
from tests.unit.accounting.test_project_cost_procedures import (
    METRICS as COST_METRICS,
)
from tests.unit.accounting.test_project_cost_procedures import _input as cost_input
from tests.unit.accounting.test_revenue_procedures import valid_input as revenue_input
from tests.unit.accounting.test_tier_zero import valid_input as tier_zero_input
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError


RUN_ID = "run-accounting-dispatch"
REVISION = 17


def _bind(value: dict) -> dict:
    result = copy.deepcopy(value)
    result["run_id"] = RUN_ID
    result["revision"] = REVISION
    return result


def _arguments(*, reverse_projects: bool = False) -> dict:
    from trusted_ceo_agent.accounting.suite import build_machine_draft_suite

    items = list(COST_METRICS.items())
    if reverse_projects:
        items.reverse()
    return {
        "suite": build_machine_draft_suite(
            release_id="accounting-dispatch-release-1",
            effective_from="2026-01-01",
        ),
        "tier_zero_input": _bind(tier_zero_input()),
        "raw_core_population": _bind(valid_population()),
        "revenue_input": _bind(revenue_input()),
        "cashflow_input": _bind(cash_input()),
        "project_cost_inputs": {
            issue_id: _bind(cost_input(metrics)) for issue_id, metrics in items
        },
    }


def _rehash(value: dict) -> None:
    body = dict(value)
    body.pop("content_hash", None)
    value["content_hash"] = hashlib.sha256(canonical_bytes(body)).hexdigest()


class AccountingDispatcherTests(unittest.TestCase):
    def test_dispatches_real_pack_runners_into_one_verified_64_family_bundle(self):
        from trusted_ceo_agent.accounting.dispatcher import (
            dispatch_accounting_suite,
            verify_accounting_execution_bundle,
        )

        bundle = dispatch_accounting_suite(**_arguments())
        verified = verify_accounting_execution_bundle(bundle)

        self.assertEqual(64, len(verified["execution_manifest"]["family_records"]))
        self.assertEqual(30, len(verified["result_artifacts"]))
        self.assertEqual(
            ["tier_zero"]
            + ["core_extended"] * 11
            + ["revenue", "cashflow"]
            + ["project_cost"] * 16,
            [item["result_type"] for item in verified["result_artifacts"]],
        )
        self.assertEqual(
            {item["content_hash"] for item in verified["result_artifacts"]},
            {
                item["parent_result_hash"]
                for item in verified["execution_manifest"]["family_records"]
            },
        )
        self.assertEqual("Boundary", verified["authority_ceiling"])

    def test_project_input_order_cannot_change_bundle_bytes(self):
        from trusted_ceo_agent.accounting.dispatcher import dispatch_accounting_suite

        forward = dispatch_accounting_suite(**_arguments())
        reverse = dispatch_accounting_suite(**_arguments(reverse_projects=True))

        self.assertEqual(canonical_bytes(forward), canonical_bytes(reverse))

    def test_missing_duplicate_or_cross_revision_data_fails_closed(self):
        from trusted_ceo_agent.accounting.dispatcher import (
            dispatch_accounting_suite,
            verify_accounting_execution_bundle,
        )

        missing = _arguments()
        missing["project_cost_inputs"].pop("CA-16")
        with self.assertRaises(ContractError):
            dispatch_accounting_suite(**missing)

        stale = _arguments()
        stale["project_cost_inputs"]["CA-16"]["revision"] = REVISION + 1
        with self.assertRaises(ContractError):
            dispatch_accounting_suite(**stale)

        duplicate = dispatch_accounting_suite(**_arguments())
        duplicate["result_artifacts"][-1] = copy.deepcopy(
            duplicate["result_artifacts"][0]
        )
        _rehash(duplicate)
        with self.assertRaises(ContractError):
            verify_accounting_execution_bundle(duplicate)


if __name__ == "__main__":
    unittest.main()
