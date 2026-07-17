import copy
import unittest

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.workflow.completion import assess_completion_from_artifacts

from tests.integrator_support import REVISION, RUN_ID, complete_inputs
from tests.unit.analysis.test_integrator import build_manifest, integrate


def completion_input(inputs: dict) -> dict:
    return {
        "run_id": RUN_ID,
        "revision": REVISION,
        "signal_cases": [{
            "case_id": "case_terminal",
            "status": "terminal",
            "disposition": "substantiated",
            "materiality_review_required": True,
        }],
        "work_items": [{"task_id": "required_work", "required": True, "status": "succeeded"}],
        "domain_routes": inputs["routes"],
        "findings": inputs["findings"],
        "integrity_failure_refs": [],
        "contract_failure_refs": [],
        "stale_revision_refs": [],
        "coverage_gaps": [],
        "expert_review_refs": [],
        "blind_spot_refs": [],
        "limited_basis": "none",
        "user_confirmed_limitations": False,
        "cross_finding_join_complete": False,
        "cross_domain_integrator_complete": False,
        "duplicate_merge_complete": False,
        "conflicts_disclosed": False,
        "coverage_complete": False,
        "final_validator_passed": True,
        "tty_final_approval_ready": True,
    }


class IntegratedCompletionArtifactTests(unittest.TestCase):
    def test_k_artifacts_prove_join_gates_without_caller_booleans(self) -> None:
        inputs = complete_inputs()
        manifest = build_manifest(inputs)
        integration = integrate(inputs, manifest)
        assessment = assess_completion_from_artifacts(
            completion_input(inputs),
            finding_join_manifest=manifest,
            cross_domain_integration=integration,
        )
        self.assertEqual("finalization_ready", assessment["status"])
        self.assertTrue(assessment["gate_results"]["cross_finding_join_complete"])
        self.assertTrue(assessment["gate_results"]["cross_domain_integrator_complete"])

    def test_stale_or_incomplete_integration_fails_closed(self) -> None:
        inputs = complete_inputs()
        manifest = build_manifest(inputs)
        integration = integrate(inputs, manifest)
        stale = copy.deepcopy(integration)
        stale["manifest_hash"] = "0" * 64
        with self.assertRaises(ContractError):
            assess_completion_from_artifacts(
                completion_input(inputs),
                finding_join_manifest=manifest,
                cross_domain_integration=stale,
            )


if __name__ == "__main__":
    unittest.main()
