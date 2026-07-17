from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.evaluation.metrics import QUALITY_SCORE_METRICS
from trusted_ceo_agent.evaluation.non_inferiority import (
    build_non_inferiority_report,
    build_quality_policy,
)

from ._fixtures import execution, quality_metrics, run_complete


def policy():
    return build_quality_policy(
        policy_id="quality_policy_fixture",
        metric_margins={metric: "0" for metric in QUALITY_SCORE_METRICS},
        require_byte_equivalence=True,
        min_workload_classes=4,
        min_runs_per_condition=10,
        require_external_model_evaluation=True,
        require_blinded_expert_evaluation=True,
    )


class NonInferiorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batch = run_complete()

    def test_equal_parallel_profile_passes_all_quality_boundaries(self):
        report = build_non_inferiority_report(
            self.batch["results"], policy(), candidate_profile_id="parallel_2"
        )
        self.assertEqual("pass", report["gate_status"])
        self.assertTrue(report["semantic_equivalent"])
        self.assertTrue(report["byte_equivalent"])
        self.assertTrue(report["eligible_for_activation"])
        self.assertEqual([], report["failure_codes"])

    def test_any_required_quality_regression_fails_candidate(self):
        def degraded(case, profile_id, repetition, paired_seed):
            value = execution(case, profile_id, repetition, paired_seed)
            if profile_id == "parallel_4":
                value["quality_metrics"] = quality_metrics(critical="0.99")
            return value

        report = build_non_inferiority_report(
            run_complete(execute=degraded)["results"],
            policy(),
            candidate_profile_id="parallel_4",
        )
        self.assertEqual("fail", report["gate_status"])
        self.assertFalse(report["eligible_for_activation"])
        self.assertIn("critical_recall_non_inferiority_failed", report["failure_codes"])

    def test_deterministic_mismatch_fails_even_when_scores_match(self):
        def mismatch(case, profile_id, repetition, paired_seed):
            value = execution(case, profile_id, repetition, paired_seed)
            if profile_id == "parallel_3":
                semantic = dict(value["semantic_output"])
                semantic["finding_ids"] = ["finding_a"]
                value["semantic_output"] = semantic
                from trusted_ceo_agent.canonical import canonical_bytes

                value["output_bytes"] = canonical_bytes(semantic)
            return value

        report = build_non_inferiority_report(
            run_complete(execute=mismatch)["results"],
            policy(),
            candidate_profile_id="parallel_3",
        )
        self.assertEqual("fail", report["gate_status"])
        self.assertIn("semantic_output_mismatch", report["failure_codes"])
        self.assertIn("byte_output_mismatch", report["failure_codes"])

    def test_absent_external_model_or_expert_score_cannot_pass(self):
        def no_external(case, profile_id, repetition, paired_seed):
            value = execution(case, profile_id, repetition, paired_seed)
            value["model_evaluation_status"] = "not_evaluated"
            value["expert_evaluation_status"] = "not_evaluated"
            value["quality_metrics"] = quality_metrics(expert=None)
            return value

        report = build_non_inferiority_report(
            run_complete(execute=no_external)["results"],
            policy(),
            candidate_profile_id="parallel_2",
        )
        self.assertEqual("not_evaluated", report["gate_status"])
        self.assertFalse(report["eligible_for_activation"])
        self.assertIn("external_model_not_evaluated", report["failure_codes"])
        self.assertIn("blinded_expert_not_evaluated", report["failure_codes"])

    def test_less_than_four_workloads_or_ten_runs_per_condition_fails_closed(self):
        incomplete = [
            item
            for item in self.batch["results"]
            if item["workload_class"] != "workload_3" and item["repetition"] < 9
        ]
        report = build_non_inferiority_report(
            incomplete, policy(), candidate_profile_id="parallel_2"
        )
        self.assertEqual("fail", report["gate_status"])
        self.assertIn("insufficient_workload_coverage", report["failure_codes"])
        self.assertIn("insufficient_condition_runs", report["failure_codes"])

    def test_tampered_result_hash_is_rejected(self):
        tampered = copy.deepcopy(self.batch["results"])
        tampered[0]["input_hash"] = "f" * 64
        with self.assertRaises(ContractError):
            build_non_inferiority_report(
                tampered, policy(), candidate_profile_id="parallel_2"
            )


if __name__ == "__main__":
    unittest.main()

