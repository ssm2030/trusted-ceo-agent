from __future__ import annotations

import unittest

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.evaluation.metrics import QUALITY_SCORE_METRICS
from trusted_ceo_agent.evaluation.non_inferiority import (
    ConcurrencyProfileRegistry,
    build_concurrency_profile,
    build_non_inferiority_report,
    build_quality_policy,
)
from trusted_ceo_agent.evaluation.performance import (
    build_performance_policy,
    summarize_stage_timings,
)

from ._fixtures import run_complete


def quality_policy():
    return build_quality_policy(
        policy_id="quality_policy_fixture",
        metric_margins={metric: "0" for metric in QUALITY_SCORE_METRICS},
        min_workload_classes=4,
        min_runs_per_condition=10,
    )


def reports(batch, policy):
    return [
        build_non_inferiority_report(
            batch["results"], policy, candidate_profile_id=profile_id
        )
        for profile_id in ("parallel_2", "parallel_3", "parallel_4")
    ]


class PerformanceGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batch = run_complete()
        cls.quality = quality_policy()
        cls.reports = reports(cls.batch, cls.quality)

    def test_summary_reports_p50_p95_and_max_by_profile_condition(self):
        summary = summarize_stage_timings(
            self.batch["results"],
            self.batch["timings"],
            eligible_profile_ids={"sequential", "parallel_2", "parallel_3", "parallel_4"},
            min_workload_classes=4,
            min_runs_per_condition=10,
        )
        warm_parallel_3 = summary["profiles"]["parallel_3"]["conditions"]["warm"]
        self.assertEqual(60, warm_parallel_3["total"]["p50_ms"])
        self.assertEqual(60, warm_parallel_3["total"]["p95_ms"])
        self.assertEqual(60, warm_parallel_3["total"]["max_ms"])

    def test_unapproved_policy_cannot_claim_activation(self):
        value = build_performance_policy(
            results=self.batch["results"],
            stage_timings=self.batch["timings"],
            non_inferiority_reports=self.reports,
            target_environment="target-mac-warm-local",
            approval=None,
        )
        self.assertEqual("proposed", value["status"])
        self.assertFalse(value["activation_eligible"])
        self.assertIsNone(value["approval_ref"])

    def test_approved_policy_selects_fastest_passing_profile(self):
        value = build_performance_policy(
            results=self.batch["results"],
            stage_timings=self.batch["timings"],
            non_inferiority_reports=self.reports,
            target_environment="target-mac-warm-local",
            approval={
                "approval_ref": "approvals/performance-policy.json",
                "approved_by": "release_owner",
                "approved_at": "2026-07-17T00:00:00Z",
                "rollback_drill_passed": True,
            },
        )
        self.assertEqual("approved", value["status"])
        self.assertEqual("parallel_4", value["selected_profile_id"])
        self.assertEqual("sequential", value["rollback_profile_id"])
        self.assertTrue(value["activation_eligible"])

    def test_registry_requires_both_quality_and_approved_performance_gates(self):
        proposed = build_performance_policy(
            results=self.batch["results"],
            stage_timings=self.batch["timings"],
            non_inferiority_reports=self.reports,
            target_environment="target-mac-warm-local",
            approval=None,
        )
        profiles = [
            build_concurrency_profile(profile_id, self.quality)
            for profile_id in ("sequential", "parallel_2", "parallel_3", "parallel_4")
        ]
        registry = ConcurrencyProfileRegistry(profiles)
        with self.assertRaises(ContractError):
            registry.activate(
                profile_id="parallel_4",
                non_inferiority_report=self.reports[-1],
                performance_policy=proposed,
                approval_ref="approvals/activate.json",
                current_revision=7,
            )

    def test_activation_is_revision_bound_and_rollback_is_fail_closed(self):
        approved = build_performance_policy(
            results=self.batch["results"],
            stage_timings=self.batch["timings"],
            non_inferiority_reports=self.reports,
            target_environment="target-mac-warm-local",
            approval={
                "approval_ref": "approvals/performance-policy.json",
                "approved_by": "release_owner",
                "approved_at": "2026-07-17T00:00:00Z",
                "rollback_drill_passed": True,
            },
        )
        profiles = [
            build_concurrency_profile(profile_id, self.quality)
            for profile_id in ("sequential", "parallel_2", "parallel_3", "parallel_4")
        ]
        registry = ConcurrencyProfileRegistry(profiles)
        activation = registry.activate(
            profile_id="parallel_4",
            non_inferiority_report=self.reports[-1],
            performance_policy=approved,
            approval_ref="approvals/activate.json",
            current_revision=7,
        )
        self.assertEqual(8, activation["effective_for_runs_after_revision"])
        self.assertEqual("sequential", registry.bind_profile(run_revision=7))
        self.assertEqual("parallel_4", registry.bind_profile(run_revision=8))

        rollback = registry.rollback(
            approval_ref="approvals/rollback.json",
            reason="production_slo_regression",
            current_revision=9,
        )
        self.assertEqual("sequential", rollback["to_profile_id"])
        self.assertEqual("parallel_4", registry.bind_profile(run_revision=9))
        self.assertEqual("sequential", registry.bind_profile(run_revision=10))

    def test_insufficient_benchmark_shape_is_rejected(self):
        with self.assertRaises(ContractError):
            summarize_stage_timings(
                [
                    item
                    for item in self.batch["results"]
                    if item["workload_class"] != "workload_3"
                ],
                self.batch["timings"],
                eligible_profile_ids={"sequential"},
                min_workload_classes=4,
                min_runs_per_condition=10,
            )


if __name__ == "__main__":
    unittest.main()

