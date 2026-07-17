from __future__ import annotations

import copy
import unittest

from tests.unit.accounting.test_cashflow_procedures import valid_input as cash_input
from tests.unit.accounting.test_core_extended_procedures import (
    METRICS as CORE_METRICS,
)
from tests.unit.accounting.test_core_extended_procedures import _input as core_input
from tests.unit.accounting.test_project_cost_procedures import (
    METRICS as COST_METRICS,
)
from tests.unit.accounting.test_project_cost_procedures import _input as cost_input
from tests.unit.accounting.test_revenue_procedures import valid_input as revenue_input
from tests.unit.accounting.test_tier_zero import valid_input as tier_zero_input
from trusted_ceo_agent.errors import ContractError


RUN_ID = "run-accounting-suite"
REVISION = 9


def _bind(value: dict) -> dict:
    result = copy.deepcopy(value)
    result["run_id"] = RUN_ID
    result["revision"] = REVISION
    return result


class AccountingExecutionRegistryTests(unittest.TestCase):
    def _completed_registry(self):
        from trusted_ceo_agent.accounting.core_extended_procedures import (
            run_core_extended_procedure,
        )
        from trusted_ceo_agent.accounting.core_procedures import run_tier_zero_procedures
        from trusted_ceo_agent.accounting.cashflow_procedures import (
            run_cashflow_procedures,
        )
        from trusted_ceo_agent.accounting.execution import AccountingExecutionRegistry
        from trusted_ceo_agent.accounting.project_cost_procedures import (
            run_project_cost_procedure,
        )
        from trusted_ceo_agent.accounting.revenue_procedures import (
            run_revenue_procedures,
        )
        from trusted_ceo_agent.accounting.suite import build_machine_draft_suite

        suite = build_machine_draft_suite(
            release_id="accounting-release-1",
            effective_from="2026-01-01",
        )
        registry = AccountingExecutionRegistry(suite)
        registry.record_tier_zero(run_tier_zero_procedures(_bind(tier_zero_input())))
        for issue_id, metrics in CORE_METRICS.items():
            registry.record_core_extended(
                run_core_extended_procedure(issue_id, _bind(core_input(metrics)))
            )
        registry.record_revenue(run_revenue_procedures(_bind(revenue_input())))
        registry.record_cashflow(run_cashflow_procedures(_bind(cash_input())))
        for issue_id, metrics in COST_METRICS.items():
            registry.record_project_cost(
                run_project_cost_procedure(issue_id, _bind(cost_input(metrics)))
            )
        return suite, registry

    def test_all_64_families_derive_implementation_and_test_evidence(self):
        from trusted_ceo_agent.accounting.execution import (
            verify_accounting_execution_manifest,
        )
        from trusted_ceo_agent.accounting.seeds import PROCEDURE_SEED_TITLES
        from trusted_ceo_agent.accounting.suite import assess_suite_readiness

        suite, registry = self._completed_registry()
        manifest = registry.finalize()
        verify_accounting_execution_manifest(manifest)

        self.assertEqual(64, len(manifest["family_records"]))
        self.assertEqual(
            list(PROCEDURE_SEED_TITLES),
            [item["procedure_id"] for item in manifest["procedure_records"]],
        )
        self.assertTrue(manifest["coverage_complete"])
        self.assertEqual(
            "P-AC-15",
            next(
                item["procedure_id"]
                for item in manifest["family_records"]
                if item["issue_family_id"] == "AC-15"
            ),
        )
        self.assertEqual(
            "P-AC-16",
            next(
                item["procedure_id"]
                for item in manifest["family_records"]
                if item["issue_family_id"] == "AC-16"
            ),
        )

        readiness = assess_suite_readiness(suite, execution_evidence=manifest)
        self.assertNotIn("procedure_implementation_incomplete", readiness["blocker_codes"])
        self.assertIn("norm_grounding_unverified", readiness["blocker_codes"])
        self.assertIn("expert_review_required", readiness["blocker_codes"])

    def test_missing_duplicate_or_cross_revision_evidence_fails_closed(self):
        _, registry = self._completed_registry()
        manifest = registry.finalize()

        with self.assertRaises(ContractError):
            registry.record_core_extended(
                copy.deepcopy(registry.family_result("AC-06"))
            )

        incomplete = copy.deepcopy(manifest)
        incomplete["family_records"].pop()
        with self.assertRaises(ContractError):
            from trusted_ceo_agent.accounting.execution import (
                verify_accounting_execution_manifest,
            )

            verify_accounting_execution_manifest(incomplete)

        suite, _ = self._completed_registry()
        from trusted_ceo_agent.accounting.execution import AccountingExecutionRegistry

        stale_registry = AccountingExecutionRegistry(suite)
        stale_registry.record_tier_zero(registry.family_result("AC-01"))
        stale = copy.deepcopy(registry.family_result("AC-06"))
        stale["revision"] = REVISION + 1
        with self.assertRaises(ContractError):
            stale_registry.record_core_extended(stale)


if __name__ == "__main__":
    unittest.main()
