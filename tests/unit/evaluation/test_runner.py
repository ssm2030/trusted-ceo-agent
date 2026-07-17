from __future__ import annotations

import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.evaluation.metrics import semantic_output_hash
from trusted_ceo_agent.evaluation.runner import (
    EvaluationCancelled,
    build_evaluation_result,
    run_paired_evaluation,
)

from ._fixtures import evaluation_cases, execution, quality_metrics


class EvaluationRunnerTests(unittest.TestCase):
    def test_all_profiles_share_pair_identity_and_match_output_exactly(self):
        batch = run_paired_evaluation(
            evaluation_cases()[:1],
            repetitions=1,
            execute=execution,
            timeout_ms=1_000,
        )
        self.assertEqual(4, len(batch["results"]))
        self.assertEqual(
            {"sequential", "parallel_2", "parallel_3", "parallel_4"},
            {item["profile_id"] for item in batch["results"]},
        )
        self.assertEqual(1, len({item["paired_seed"] for item in batch["results"]}))
        self.assertEqual(
            1, len({item["semantic_output_hash"] for item in batch["results"]})
        )
        self.assertEqual(1, len({item["byte_output_hash"] for item in batch["results"]}))

    def test_timing_changes_do_not_change_semantic_result_hash(self):
        case = evaluation_cases()[0]
        seed = "a" * 64
        first = execution(case, "sequential", 0, seed)
        second = dict(first)
        second["stage_durations_ms"] = {
            "intake": 20,
            "deterministic": 20,
            "domain_reasoning": 40,
            "integration": 20,
            "render": 20,
        }
        first_result, first_timing = build_evaluation_result(
            case, "sequential", 0, seed, first, timeout_ms=1_000
        )
        second_result, second_timing = build_evaluation_result(
            case, "sequential", 0, seed, second, timeout_ms=1_000
        )
        self.assertEqual(
            first_result["semantic_result_hash"],
            second_result["semantic_result_hash"],
        )
        self.assertNotEqual(first_timing["telemetry_hash"], second_timing["telemetry_hash"])
        self.assertNotEqual(first_result["result_hash"], second_result["result_hash"])

    def test_timing_telemetry_inside_semantic_output_is_rejected(self):
        with self.assertRaises(ContractError):
            semantic_output_hash(
                {"finding_id": "finding_a", "stage_timing": {"total_ms": 10}}
            )

    def test_timeout_discards_professional_output_instead_of_falling_back(self):
        case = evaluation_cases()[0]
        value = execution(case, "sequential", 0, "a" * 64)
        value["stage_durations_ms"]["domain_reasoning"] = 10_000
        result, timing = build_evaluation_result(
            case, "sequential", 0, "a" * 64, value, timeout_ms=50
        )
        self.assertEqual("timeout", result["status"])
        self.assertEqual("model_timeout", result["failure_code"])
        self.assertIsNone(result["semantic_output_hash"])
        self.assertIsNone(result["quality_metrics"])
        self.assertEqual("timeout", timing["outcome"])

    def test_cancellation_does_not_invoke_executor_or_emit_weak_output(self):
        calls: list[str] = []

        def should_not_run(*args):
            calls.append("called")
            raise AssertionError("executor must not run after cancellation")

        batch = run_paired_evaluation(
            evaluation_cases()[:1],
            repetitions=1,
            execute=should_not_run,
            cancel_requested=lambda *_: True,
        )
        self.assertEqual([], calls)
        self.assertTrue(all(item["status"] == "cancelled" for item in batch["results"]))
        self.assertTrue(
            all(item["semantic_output_hash"] is None for item in batch["results"])
        )

    def test_executor_cancellation_is_classified(self):
        def cancelled(*args):
            raise EvaluationCancelled()

        batch = run_paired_evaluation(
            evaluation_cases()[:1],
            repetitions=1,
            execute=cancelled,
        )
        self.assertTrue(all(item["status"] == "cancelled" for item in batch["results"]))
        self.assertTrue(
            all(item["failure_code"] == "cancelled_by_human" for item in batch["results"])
        )

    def test_absent_external_execution_is_not_evaluated(self):
        batch = run_paired_evaluation(
            evaluation_cases()[:1],
            repetitions=1,
            execute=None,
        )
        self.assertTrue(
            all(item["status"] == "not_evaluated" for item in batch["results"])
        )
        self.assertTrue(
            all(
                item["model_evaluation_status"] == "not_evaluated"
                and item["expert_evaluation_status"] == "not_evaluated"
                for item in batch["results"]
            )
        )

    def test_noncanonical_output_bytes_are_rejected(self):
        case = evaluation_cases()[0]
        value = execution(case, "sequential", 0, "a" * 64)
        value["output_bytes"] = canonical_bytes({"different": True})
        with self.assertRaises(ContractError):
            build_evaluation_result(
                case, "sequential", 0, "a" * 64, value, timeout_ms=1_000
            )


if __name__ == "__main__":
    unittest.main()

