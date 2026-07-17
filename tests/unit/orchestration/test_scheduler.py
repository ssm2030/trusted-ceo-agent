import importlib
import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError


def _apis():
    try:
        return (
            importlib.import_module("trusted_ceo_agent.orchestration.graph"),
            importlib.import_module("trusted_ceo_agent.orchestration.budget"),
            importlib.import_module("trusted_ceo_agent.orchestration.scheduler"),
        )
    except ModuleNotFoundError as error:
        raise AssertionError(f"scheduler API is missing: {error}") from error


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


def _policy(max_workers=2):
    _, budget, _ = _apis()
    return budget.build_work_budget_policy(
        policy_id=f"budget_{max_workers}",
        workload_class="b2b_service_accounting",
        max_active_signal_cases=1,
        max_parallel_workers=max_workers,
        max_model_attempts_per_task=2,
        task_timeout=5,
        case_timeout=120,
        max_optional_issue_families=4,
        evidence_packet_limits=_limits(),
        overflow_action="deep_review_pending",
        benchmark_refs=["benchmark_a"],
        approved_concurrency_profile_id="parallel_2",
        effective_from="2026-07-17T00:00:00Z",
    )


def _spec(local_key, dependencies=(), *, case_id="case_a", required=True):
    return {
        "local_key": local_key,
        "signal_case_id": case_id,
        "event_id": f"event_{case_id}",
        "domain": "accounting",
        "issue_family": f"AC-{local_key.upper()}",
        "procedure_refs": [f"procedure_{local_key}"],
        "dependency_keys": list(dependencies),
        "required": required,
        "packet_ref": f"packets/{local_key}.json",
        "packet_hash": local_key[0] * 64,
        "pack_release_id": "pack_release_001",
        "timeout_policy": {
            "timeout_seconds": 5,
            "retryable_failure_codes": ["contract_invalid", "model_timeout"],
        },
    }


def _compile(specs, cases=("case_a",)):
    graph_api, _, _ = _apis()
    return graph_api.compile_work_graph(
        run_id="run_scheduler",
        base_revision=5,
        signal_case_ids=list(cases),
        work_item_specs=specs,
        policy_release_id="policy_release_001",
        concurrency_profile_id="parallel_2",
    )


class WorkSchedulerTests(unittest.TestCase):
    def test_dependencies_gate_leases_and_success_opens_successor(self):
        _, _, scheduler_api = _apis()
        graph, items = _compile([_spec("a"), _spec("b", ("a",))])
        scheduler = scheduler_api.WorkScheduler(graph, items, _policy())

        first = scheduler.lease("worker_1", now=0)
        self.assertIsNotNone(first)
        self.assertEqual("AC-A", first["issue_family"])
        self.assertIsNone(scheduler.lease("worker_2", now=0))
        scheduler.start(first["task_id"], "worker_1")
        scheduler.complete(
            first["task_id"],
            "worker_1",
            result_ref="results/a.json",
            result_payload=b'{"a":1}',
            active_created_from_hash=graph["created_from_hash"],
        )
        second = scheduler.lease("worker_2", now=1)
        self.assertIsNotNone(second)
        self.assertEqual("AC-B", second["issue_family"])

    def test_timeout_retries_once_then_stops_without_weak_result(self):
        _, _, scheduler_api = _apis()
        graph, items = _compile([_spec("a")])
        scheduler = scheduler_api.WorkScheduler(graph, items, _policy())

        first = scheduler.lease("worker_1", now=0)
        scheduler.start(first["task_id"], "worker_1")
        scheduler.expire(now=5)
        current = scheduler.work_items()[0]
        self.assertEqual("ready", current["status"])
        self.assertEqual(1, current["attempt"])
        self.assertIsNone(current["result_ref"])

        second = scheduler.lease("worker_1", now=5)
        self.assertEqual(2, second["attempt"])
        scheduler.start(second["task_id"], "worker_1")
        scheduler.expire(now=10)
        current = scheduler.work_items()[0]
        self.assertEqual("deep_review_pending", current["status"])
        self.assertEqual(2, current["attempt"])
        self.assertIsNone(current["result_ref"])
        self.assertIsNone(scheduler.lease("worker_1", now=11))

    def test_cancel_propagates_to_unstarted_downstream_and_rejects_late_output(self):
        _, _, scheduler_api = _apis()
        graph, items = _compile([
            _spec("a"),
            _spec("b", ("a",)),
            _spec("c", ("b",)),
        ])
        scheduler = scheduler_api.WorkScheduler(graph, items, _policy())
        first = scheduler.lease("worker_1", now=0)
        scheduler.start(first["task_id"], "worker_1")
        scheduler.cancel(first["task_id"])
        by_issue = {item["issue_family"]: item for item in scheduler.work_items()}
        self.assertEqual("cancelled", by_issue["AC-A"]["status"])
        self.assertEqual("cancelled", by_issue["AC-B"]["status"])
        self.assertEqual("cancelled", by_issue["AC-C"]["status"])
        with self.assertRaises(ContractError):
            scheduler.complete(
                first["task_id"],
                "worker_1",
                result_ref="results/late.json",
                result_payload=b"late",
                active_created_from_hash=graph["created_from_hash"],
            )

    def test_stale_semantic_generation_supersedes_without_publishing_result(self):
        _, _, scheduler_api = _apis()
        graph, items = _compile([_spec("a")])
        scheduler = scheduler_api.WorkScheduler(graph, items, _policy())
        leased = scheduler.lease("worker_1", now=0)
        scheduler.start(leased["task_id"], "worker_1")
        with self.assertRaises(ContractError):
            scheduler.complete(
                leased["task_id"],
                "worker_1",
                result_ref="results/stale.json",
                result_payload=b"stale",
                active_created_from_hash="f" * 64,
            )
        current = scheduler.work_items()[0]
        self.assertEqual("superseded", current["status"])
        self.assertIsNone(current["result_ref"])
        self.assertEqual("superseded", scheduler.graph_snapshot()["status"])

    def test_case_and_worker_caps_apply_backpressure(self):
        _, _, scheduler_api = _apis()
        graph, items = _compile(
            [_spec("a1"), _spec("a2"), _spec("b1", case_id="case_b")],
            cases=("case_a", "case_b"),
        )
        scheduler = scheduler_api.WorkScheduler(graph, items, _policy(max_workers=2))
        first = scheduler.lease("worker_1", now=0)
        second = scheduler.lease("worker_2", now=0)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual("case_a", first["signal_case_id"])
        self.assertEqual("case_a", second["signal_case_id"])
        self.assertIsNone(scheduler.lease("worker_3", now=0))

    def test_task_timeout_cannot_exceed_policy_timeout(self):
        _, _, scheduler_api = _apis()
        spec = _spec("a")
        spec["timeout_policy"]["timeout_seconds"] = 6
        graph, items = _compile([spec])
        with self.assertRaises(ContractError):
            scheduler_api.WorkScheduler(graph, items, _policy())

    def test_success_replay_is_idempotent_and_conflicting_replay_fails(self):
        _, _, scheduler_api = _apis()
        graph, items = _compile([_spec("a")])
        scheduler = scheduler_api.WorkScheduler(graph, items, _policy())
        leased = scheduler.lease("worker_1", now=0)
        scheduler.start(leased["task_id"], "worker_1")
        first = scheduler.complete(
            leased["task_id"],
            "worker_1",
            result_ref="results/a.json",
            result_payload=b'{"a":1}',
            active_created_from_hash=graph["created_from_hash"],
        )
        replay = scheduler.complete(
            leased["task_id"],
            "worker_1",
            result_ref="results/a.json",
            result_payload=b'{"a":1}',
            active_created_from_hash=graph["created_from_hash"],
        )
        self.assertEqual(first, replay)
        with self.assertRaises(ContractError):
            scheduler.complete(
                leased["task_id"],
                "worker_1",
                result_ref="results/a.json",
                result_payload=b'{"a":2}',
                active_created_from_hash=graph["created_from_hash"],
            )

    def test_sequential_and_parallel_completion_are_byte_equivalent(self):
        _, _, scheduler_api = _apis()
        graph, items = _compile([_spec("a"), _spec("b")])
        sequential = scheduler_api.WorkScheduler(graph, items, _policy(max_workers=1))
        parallel = scheduler_api.WorkScheduler(graph, items, _policy(max_workers=2))

        for worker, now in (("worker_1", 0), ("worker_1", 1)):
            leased = sequential.lease(worker, now=now)
            sequential.start(leased["task_id"], worker)
            sequential.complete(
                leased["task_id"],
                worker,
                result_ref=f"results/{leased['issue_family']}.json",
                result_payload=leased["issue_family"].encode("utf-8"),
                active_created_from_hash=graph["created_from_hash"],
            )

        leased = [
            parallel.lease("worker_1", now=0),
            parallel.lease("worker_2", now=0),
        ]
        for item, worker in zip(leased, ("worker_1", "worker_2")):
            parallel.start(item["task_id"], worker)
        for item, worker in reversed(list(zip(leased, ("worker_1", "worker_2")))):
            parallel.complete(
                item["task_id"],
                worker,
                result_ref=f"results/{item['issue_family']}.json",
                result_payload=item["issue_family"].encode("utf-8"),
                active_created_from_hash=graph["created_from_hash"],
            )

        self.assertEqual(
            canonical_bytes(sequential.semantic_result_manifest()),
            canonical_bytes(parallel.semantic_result_manifest()),
        )


if __name__ == "__main__":
    unittest.main()
