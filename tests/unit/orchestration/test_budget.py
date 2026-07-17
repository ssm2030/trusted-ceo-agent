import importlib
import unittest

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.errors import ContractError


def _apis():
    try:
        return (
            importlib.import_module("trusted_ceo_agent.orchestration.graph"),
            importlib.import_module("trusted_ceo_agent.orchestration.budget"),
        )
    except ModuleNotFoundError as error:
        raise AssertionError(f"budget API is missing: {error}") from error


def _limits():
    return {
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


def _policy(overflow_action="deep_review_pending", **overrides):
    _, budget = _apis()
    fields = {
        "policy_id": "budget_default",
        "workload_class": "b2b_service_accounting",
        "max_active_signal_cases": 1,
        "max_parallel_workers": 2,
        "max_model_attempts_per_task": 2,
        "task_timeout": 30,
        "case_timeout": 120,
        "max_optional_issue_families": 1,
        "evidence_packet_limits": _limits(),
        "overflow_action": overflow_action,
        "benchmark_refs": ["benchmark_b", "benchmark_a"],
        "approved_concurrency_profile_id": "parallel_2",
        "effective_from": "2026-07-17T00:00:00Z",
    }
    fields.update(overrides)
    return budget.build_work_budget_policy(**fields)


def _spec(local_key, *, required):
    return {
        "local_key": local_key,
        "signal_case_id": "case_001",
        "event_id": "event_001",
        "domain": "accounting",
        "issue_family": f"AC-{local_key.upper()}",
        "procedure_refs": [f"procedure_{local_key}"],
        "dependency_keys": [],
        "required": required,
        "packet_ref": f"packets/{local_key}.json",
        "packet_hash": (local_key[0] * 64),
        "pack_release_id": "pack_release_001",
        "timeout_policy": {
            "timeout_seconds": 30,
            "retryable_failure_codes": ["contract_invalid", "model_timeout"],
        },
    }


class WorkBudgetTests(unittest.TestCase):
    def items(self):
        graph, _ = _apis()
        _, items = graph.compile_work_graph(
            run_id="run_budget",
            base_revision=3,
            signal_case_ids=["case_001"],
            work_item_specs=[
                _spec("a", required=True),
                _spec("b", required=True),
                _spec("c", required=False),
                _spec("d", required=False),
            ],
            policy_release_id="policy_release_001",
            concurrency_profile_id="parallel_2",
        )
        return items

    def test_policy_is_deterministic_and_content_hash_is_verified(self):
        _, budget = _apis()
        first = _policy()
        second = _policy()
        self.assertEqual(first, second)
        self.assertEqual(["benchmark_a", "benchmark_b"], first["benchmark_refs"])
        budget.verify_work_budget_policy(first)
        tampered = dict(first)
        tampered["case_timeout"] = 121
        with self.assertRaises(ContractError):
            budget.verify_work_budget_policy(tampered)

    def test_persisted_policy_round_trip_preserves_content_hash(self):
        _, budget = _apis()
        persisted = strict_loads(canonical_bytes(_policy()))
        budget.verify_work_budget_policy(persisted)

    def test_attempts_overflow_and_profile_limits_are_fail_closed(self):
        for overrides in (
            {"max_model_attempts_per_task": 3},
            {"overflow_action": "skip_required"},
            {"max_parallel_workers": 3},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(ContractError):
                    _policy(**overrides)

    def test_evidence_packet_limits_cannot_exceed_frozen_baseline(self):
        limits = _limits()
        limits["max_facts"] = 49
        with self.assertRaises(ContractError):
            _policy(evidence_packet_limits=limits)

    def test_optional_cap_never_defers_required_work(self):
        _, budget = _apis()
        assessment = budget.assess_work_budget(_policy(), self.items(), elapsed_seconds=0)
        required = sorted(item["task_id"] for item in self.items() if item["required"])
        self.assertEqual("ready", assessment["status"])
        self.assertTrue(set(required).issubset(assessment["scheduled_task_ids"]))
        self.assertFalse(set(required) & set(assessment["deferred_optional_task_ids"]))
        self.assertEqual(1, len(assessment["deferred_optional_task_ids"]))
        self.assertEqual("optional_budget_deferred", assessment["coverage_records"][0]["reason"])

    def test_required_timeout_uses_only_three_explicit_overflow_states(self):
        _, budget = _apis()
        for state in ("needs_prioritization", "needs_input", "deep_review_pending"):
            with self.subTest(state=state):
                assessment = budget.assess_work_budget(
                    _policy(state), self.items(), elapsed_seconds=120
                )
                self.assertEqual(state, assessment["status"])
                self.assertEqual(
                    sorted(item["task_id"] for item in self.items() if item["required"]),
                    assessment["required_task_ids"],
                )
                self.assertFalse(
                    set(assessment["required_task_ids"])
                    & set(assessment["deferred_optional_task_ids"])
                )


if __name__ == "__main__":
    unittest.main()
