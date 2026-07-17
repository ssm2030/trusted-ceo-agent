from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, RevisionConflict
from trusted_ceo_agent.evaluation.metrics import QUALITY_SCORE_METRICS
from trusted_ceo_agent.evaluation.non_inferiority import (
    ConcurrencyProfileRegistry,
    build_concurrency_profile,
    build_non_inferiority_report,
    build_quality_policy,
)
from trusted_ceo_agent.evaluation.performance import build_performance_policy
from trusted_ceo_agent.knowledge.depth_gate import assess_professional_depth
from trusted_ceo_agent.knowledge.release import ReleaseRegistry
from trusted_ceo_agent.orchestration.budget import build_work_budget_policy

from tests.foundry_support import make_candidate, make_initial_release, make_stage3
from tests.professional_knowledge_support import make_knowledge_bundle
from tests.unit.evaluation._fixtures import run_complete


RUN_ID = "run_execution_authority"
REVISION = 8
POLICY_RELEASE_ID = "policy_release_execution_authority"

PACKET_LIMITS = {
    "max_facts": 48,
    "max_signals": 48,
    "max_observations": 12,
    "max_problem_candidates": 6,
    "max_causes_per_problem": 4,
    "max_counters_per_cause": 2,
    "max_verifications_per_problem": 3,
    "max_data_requests": 8,
    "max_human_questions": 8,
    "max_expert_candidates": 6,
    "max_payload_bytes": 65536,
}


def work_policy(profile_id: str) -> dict:
    workers = {
        "sequential": 1,
        "parallel_2": 2,
        "parallel_3": 3,
        "parallel_4": 4,
    }[profile_id]
    return build_work_budget_policy(
        policy_id="work_budget_execution_authority",
        workload_class="professional_analysis",
        max_active_signal_cases=1,
        max_parallel_workers=workers,
        max_model_attempts_per_task=2,
        task_timeout=30,
        case_timeout=120,
        max_optional_issue_families=4,
        evidence_packet_limits=PACKET_LIMITS,
        overflow_action="needs_prioritization",
        benchmark_refs=["evaluation/professional-analysis.json"],
        approved_concurrency_profile_id=profile_id,
        effective_from="2026-07-17T00:00:00Z",
    )


def depth_assessment(*, full: bool) -> dict:
    family, cards, expert, release = make_knowledge_bundle(
        pack_authority="full" if full else "boundary"
    )
    return assess_professional_depth(
        family,
        cards,
        effective_on="2026-06-30",
        jurisdiction="KR",
        industry_scope="b2b_services",
        expert_approval=expert if full else None,
        release=release,
    )


def deployed_release() -> dict:
    base, _, _, _, _, candidate = make_candidate()
    _, approval = make_stage3(candidate)
    return ReleaseRegistry(base).deploy(candidate, approval, current_revision=4)


class ExecutionAuthorityGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.quality_policy = build_quality_policy(
            policy_id="quality_policy_execution_authority",
            metric_margins={metric: "0" for metric in QUALITY_SCORE_METRICS},
            min_workload_classes=4,
            min_runs_per_condition=10,
        )
        cls.profiles = {
            profile_id: build_concurrency_profile(
                profile_id, cls.quality_policy
            )
            for profile_id in (
                "sequential",
                "parallel_2",
                "parallel_3",
                "parallel_4",
            )
        }
        cls.release = deployed_release()

    def binding(self, policy: dict, *, revision: int = REVISION) -> dict:
        from trusted_ceo_agent.analysis.execution_authority import (
            build_knowledge_release_binding,
        )

        return build_knowledge_release_binding(
            run_id=RUN_ID,
            revision=revision,
            policy_release_id=POLICY_RELEASE_ID,
            work_budget_policy=policy,
            knowledge_release=self.release,
        )

    def test_full_sequential_gate_is_deterministic_and_schema_valid(self) -> None:
        from trusted_ceo_agent.analysis.execution_authority import (
            evaluate_execution_authority,
        )

        policy = work_policy("sequential")
        arguments = {
            "run_id": RUN_ID,
            "revision": REVISION,
            "policy_release_id": POLICY_RELEASE_ID,
            "expected_policy_release_id": POLICY_RELEASE_ID,
            "work_budget_policy": policy,
            "depth_assessments": [depth_assessment(full=True)],
            "knowledge_release": self.release,
            "knowledge_release_binding": self.binding(policy),
            "concurrency_profile": self.profiles["sequential"],
            "requested_authority": "full",
        }

        first = evaluate_execution_authority(**arguments)
        second = evaluate_execution_authority(**arguments)

        self.assertEqual(canonical_bytes(first), canonical_bytes(second))
        self.assertTrue(first["execution_allowed"])
        self.assertTrue(first["requested_authority_allowed"])
        self.assertTrue(first["full_allowed"])
        self.assertEqual("full", first["effective_authority"])
        self.assertEqual([], first["blockers"])
        SchemaStore().validate("execution-authority-gate.schema.json", first)

    def test_parallel_requires_passed_report_policy_and_activation_receipt(self) -> None:
        from trusted_ceo_agent.analysis.execution_authority import (
            evaluate_execution_authority,
        )

        batch = run_complete()
        reports = [
            build_non_inferiority_report(
                batch["results"],
                self.quality_policy,
                candidate_profile_id=profile_id,
            )
            for profile_id in ("parallel_2", "parallel_3", "parallel_4")
        ]
        performance = build_performance_policy(
            results=batch["results"],
            stage_timings=batch["timings"],
            non_inferiority_reports=reports,
            target_environment="professional-runtime-local",
            approval={
                "approval_ref": "approvals/performance-policy.json",
                "approved_by": "release_owner",
                "approved_at": "2026-07-17T00:00:00Z",
                "rollback_drill_passed": True,
            },
        )
        registry = ConcurrencyProfileRegistry(list(self.profiles.values()))
        activation = registry.activate(
            profile_id="parallel_4",
            non_inferiority_report=reports[-1],
            performance_policy=performance,
            approval_ref="approvals/concurrency-activation.json",
            current_revision=7,
        )
        policy = work_policy("parallel_4")

        result = evaluate_execution_authority(
            run_id=RUN_ID,
            revision=REVISION,
            policy_release_id=POLICY_RELEASE_ID,
            expected_policy_release_id=POLICY_RELEASE_ID,
            work_budget_policy=policy,
            depth_assessments=[depth_assessment(full=True)],
            knowledge_release=self.release,
            knowledge_release_binding=self.binding(policy),
            concurrency_profile=self.profiles["parallel_4"],
            non_inferiority_report=reports[-1],
            performance_policy=performance,
            profile_activation_receipt=activation,
            requested_authority="full",
        )

        self.assertTrue(result["execution_allowed"])
        self.assertTrue(result["full_allowed"])
        self.assertEqual(reports[-1]["report_hash"], result["concurrency"]["report_hash"])
        self.assertEqual(activation["event_hash"], result["concurrency"]["activation_hash"])

    def test_missing_official_approval_downgrades_and_missing_receipts_block(self) -> None:
        from trusted_ceo_agent.analysis.execution_authority import (
            build_knowledge_release_binding,
            evaluate_execution_authority,
        )

        initial = make_initial_release()
        policy = work_policy("sequential")
        binding = build_knowledge_release_binding(
            run_id=RUN_ID,
            revision=REVISION,
            policy_release_id=POLICY_RELEASE_ID,
            work_budget_policy=policy,
            knowledge_release=initial,
        )
        boundary = evaluate_execution_authority(
            run_id=RUN_ID,
            revision=REVISION,
            policy_release_id=POLICY_RELEASE_ID,
            expected_policy_release_id=POLICY_RELEASE_ID,
            work_budget_policy=policy,
            depth_assessments=[depth_assessment(full=False)],
            knowledge_release=initial,
            knowledge_release_binding=binding,
            concurrency_profile=self.profiles["sequential"],
            requested_authority="full",
        )
        self.assertTrue(boundary["execution_allowed"])
        self.assertFalse(boundary["requested_authority_allowed"])
        self.assertFalse(boundary["full_allowed"])
        self.assertEqual("boundary", boundary["effective_authority"])
        self.assertEqual("Boundary", boundary["product_display"])
        self.assertIn("knowledge_release_approval_missing", boundary["blockers"])

        blocked = evaluate_execution_authority(
            run_id=RUN_ID,
            revision=REVISION,
            policy_release_id=POLICY_RELEASE_ID,
            expected_policy_release_id=POLICY_RELEASE_ID,
            work_budget_policy=policy,
            depth_assessments=[depth_assessment(full=True)],
            knowledge_release=self.release,
            knowledge_release_binding=None,
            concurrency_profile=self.profiles["sequential"],
            requested_authority="boundary",
        )
        self.assertFalse(blocked["execution_allowed"])
        self.assertIn("knowledge_release_binding_missing", blocked["blockers"])

        parallel_policy = work_policy("parallel_2")
        parallel = evaluate_execution_authority(
            run_id=RUN_ID,
            revision=REVISION,
            policy_release_id=POLICY_RELEASE_ID,
            expected_policy_release_id=POLICY_RELEASE_ID,
            work_budget_policy=parallel_policy,
            depth_assessments=[depth_assessment(full=True)],
            knowledge_release=self.release,
            knowledge_release_binding=self.binding(parallel_policy),
            concurrency_profile=self.profiles["parallel_2"],
            requested_authority="boundary",
        )
        self.assertFalse(parallel["execution_allowed"])
        self.assertIn("non_inferiority_report_missing", parallel["blockers"])
        self.assertIn("profile_activation_receipt_missing", parallel["blockers"])

    def test_run_revision_hash_and_policy_release_mismatches_fail_closed(self) -> None:
        from trusted_ceo_agent.analysis.execution_authority import (
            evaluate_execution_authority,
        )

        policy = work_policy("sequential")
        base = {
            "run_id": RUN_ID,
            "revision": REVISION,
            "policy_release_id": POLICY_RELEASE_ID,
            "expected_policy_release_id": POLICY_RELEASE_ID,
            "work_budget_policy": policy,
            "depth_assessments": [depth_assessment(full=True)],
            "knowledge_release": self.release,
            "knowledge_release_binding": self.binding(policy),
            "concurrency_profile": self.profiles["sequential"],
            "requested_authority": "boundary",
        }

        with self.assertRaisesRegex(ContractError, "policy release mismatch"):
            evaluate_execution_authority(
                **{**base, "expected_policy_release_id": "other-policy-release"}
            )

        stale = self.binding(policy, revision=REVISION + 1)
        with self.assertRaisesRegex(RevisionConflict, "revision"):
            evaluate_execution_authority(
                **{**base, "knowledge_release_binding": stale}
            )

        tampered = copy.deepcopy(self.profiles["sequential"])
        tampered["profile_hash"] = "f" * 64
        with self.assertRaisesRegex(ContractError, "hash mismatch"):
            evaluate_execution_authority(
                **{**base, "concurrency_profile": tampered}
            )


if __name__ == "__main__":
    unittest.main()
