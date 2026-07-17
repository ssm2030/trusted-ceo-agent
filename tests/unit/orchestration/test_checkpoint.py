import copy
import hashlib
import importlib
import unittest

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.errors import ContractError


def _apis():
    try:
        return (
            importlib.import_module("trusted_ceo_agent.orchestration.graph"),
            importlib.import_module("trusted_ceo_agent.orchestration.budget"),
            importlib.import_module("trusted_ceo_agent.orchestration.checkpoint"),
        )
    except ModuleNotFoundError as error:
        raise AssertionError(f"checkpoint API is missing: {error}") from error


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


def _fixture():
    graph_api, budget_api, _ = _apis()
    specs = []
    for key, deps in (("a", ()), ("b", ("a",)), ("c", ())):
        specs.append({
            "local_key": key,
            "signal_case_id": "case_001",
            "event_id": "event_001",
            "domain": "accounting",
            "issue_family": f"AC-{key.upper()}",
            "procedure_refs": [f"procedure_{key}"],
            "dependency_keys": list(deps),
            "required": True,
            "packet_ref": f"packets/{key}.json",
            "packet_hash": key * 64,
            "pack_release_id": "pack_release_001",
            "timeout_policy": {
                "timeout_seconds": 30,
                "retryable_failure_codes": ["contract_invalid", "model_timeout"],
            },
        })
    graph, items = graph_api.compile_work_graph(
        run_id="run_checkpoint",
        base_revision=8,
        signal_case_ids=["case_001"],
        work_item_specs=specs,
        policy_release_id="policy_release_001",
        concurrency_profile_id="parallel_2",
    )
    policy = budget_api.build_work_budget_policy(
        policy_id="budget_default",
        workload_class="b2b_service_accounting",
        max_active_signal_cases=1,
        max_parallel_workers=2,
        max_model_attempts_per_task=2,
        task_timeout=30,
        case_timeout=120,
        max_optional_issue_families=1,
        evidence_packet_limits=_limits(),
        overflow_action="deep_review_pending",
        benchmark_refs=["benchmark_a"],
        approved_concurrency_profile_id="parallel_2",
        effective_from="2026-07-17T00:00:00Z",
    )
    return graph, items, policy


class WorkCheckpointTests(unittest.TestCase):
    def test_checkpoint_has_deterministic_partitions_and_content_hash(self):
        _, _, checkpoint_api = _apis()
        graph, items, _ = _fixture()
        payload = b'{"ok":true}'
        items[0]["status"] = "succeeded"
        items[0]["attempt"] = 1
        items[0]["result_ref"] = "results/a.json"
        items[0]["result_hash"] = hashlib.sha256(payload).hexdigest()
        items[1]["status"] = "ready"
        items[2]["status"] = "running"
        items[2]["attempt"] = 1
        items[2]["lease_owner"] = "worker_1"

        first = checkpoint_api.build_work_checkpoint(
            graph,
            items,
            sequence=2,
            previous_checkpoint_ref="checkpoints/previous.json",
            lease_started_at_by_task={items[2]["task_id"]: 10},
        )
        second = checkpoint_api.build_work_checkpoint(
            graph,
            list(reversed(items)),
            sequence=2,
            previous_checkpoint_ref="checkpoints/previous.json",
            lease_started_at_by_task={items[2]["task_id"]: 10},
        )
        self.assertEqual(first, second)
        self.assertEqual([items[1]["task_id"]], first["ready_task_ids"])
        self.assertEqual([items[2]["task_id"]], first["running_task_ids"])
        self.assertEqual([items[0]["task_id"]], first["terminal_task_ids"])
        checkpoint_api.verify_work_checkpoint(
            first,
            graph,
            items,
            active_created_from_hash=graph["created_from_hash"],
            result_payloads={"results/a.json": payload},
        )

    def test_checkpoint_tamper_and_stale_generation_fail_closed(self):
        _, _, checkpoint_api = _apis()
        graph, items, _ = _fixture()
        checkpoint = checkpoint_api.build_work_checkpoint(
            graph, items, sequence=0, previous_checkpoint_ref=None
        )
        tampered = copy.deepcopy(checkpoint)
        tampered["task_states"][0]["attempt"] = 2
        with self.assertRaises(ContractError):
            checkpoint_api.verify_work_checkpoint(
                tampered,
                graph,
                items,
                active_created_from_hash=graph["created_from_hash"],
                result_payloads={},
            )
        with self.assertRaises(ContractError):
            checkpoint_api.verify_work_checkpoint(
                checkpoint,
                graph,
                items,
                active_created_from_hash="f" * 64,
                result_payloads={},
            )

    def test_persisted_checkpoint_round_trip_preserves_hash_and_partitions(self):
        _, _, checkpoint_api = _apis()
        graph, items, _ = _fixture()
        checkpoint = checkpoint_api.build_work_checkpoint(
            graph, items, sequence=1, previous_checkpoint_ref=None
        )

        checkpoint_api.verify_work_checkpoint(
            strict_loads(canonical_bytes(checkpoint)),
            strict_loads(canonical_bytes(graph)),
            strict_loads(canonical_bytes(items)),
            active_created_from_hash=graph["created_from_hash"],
            result_payloads={},
        )

    def test_resume_skips_verified_success_and_requeues_only_incomplete_work(self):
        _, _, checkpoint_api = _apis()
        graph, items, policy = _fixture()
        payload = b'{"ok":true}'
        items[0]["status"] = "succeeded"
        items[0]["attempt"] = 1
        items[0]["result_ref"] = "results/a.json"
        items[0]["result_hash"] = hashlib.sha256(payload).hexdigest()
        items[2]["status"] = "running"
        items[2]["attempt"] = 1
        items[2]["lease_owner"] = "worker_1"
        checkpoint = checkpoint_api.build_work_checkpoint(
            graph,
            items,
            sequence=1,
            previous_checkpoint_ref=None,
            lease_started_at_by_task={items[2]["task_id"]: 10},
        )
        restored = checkpoint_api.restore_work_items(
            checkpoint,
            graph,
            items,
            policy,
            active_created_from_hash=graph["created_from_hash"],
            result_payloads={"results/a.json": payload},
        )
        by_id = {item["task_id"]: item for item in restored}
        self.assertEqual("succeeded", by_id[items[0]["task_id"]]["status"])
        self.assertEqual("ready", by_id[items[2]["task_id"]]["status"])
        self.assertIsNone(by_id[items[2]["task_id"]]["lease_owner"])

        with self.assertRaises(ContractError):
            checkpoint_api.restore_work_items(
                checkpoint,
                graph,
                items,
                policy,
                active_created_from_hash=graph["created_from_hash"],
                result_payloads={"results/a.json": b"tampered"},
            )


if __name__ == "__main__":
    unittest.main()
