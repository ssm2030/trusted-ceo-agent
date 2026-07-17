import copy
import importlib
import unittest

from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


def _api():
    try:
        graph = importlib.import_module("trusted_ceo_agent.orchestration.graph")
        budget = importlib.import_module("trusted_ceo_agent.orchestration.budget")
        checkpoint = importlib.import_module("trusted_ceo_agent.orchestration.checkpoint")
    except ModuleNotFoundError as error:
        raise AssertionError(f"orchestration API is missing: {error}") from error
    return graph, budget, checkpoint


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


def _spec(local_key, dependencies=()):
    return {
        "local_key": local_key,
        "signal_case_id": "case_001",
        "event_id": "event_001",
        "domain": "accounting",
        "issue_family": f"AC-{local_key.upper()}",
        "procedure_refs": [f"procedure_{local_key}"],
        "dependency_keys": list(dependencies),
        "required": True,
        "packet_ref": f"packets/{local_key}.json",
        "packet_hash": (local_key[0] * 64),
        "pack_release_id": "pack_release_001",
        "timeout_policy": {
            "timeout_seconds": 30,
            "retryable_failure_codes": ["contract_invalid", "model_timeout"],
        },
    }


class OrchestrationSchemaTests(unittest.TestCase):
    def setUp(self):
        self.schemas = SchemaStore()

    def test_graph_and_work_item_contracts_are_closed(self):
        graph_api, _, _ = _api()
        graph, items = graph_api.compile_work_graph(
            run_id="run_contract",
            base_revision=7,
            signal_case_ids=["case_001"],
            work_item_specs=[_spec("a"), _spec("b", ("a",))],
            policy_release_id="policy_release_001",
            concurrency_profile_id="parallel_2",
        )
        self.schemas.validate("analysis-work-graph.schema.json", graph)
        for item in items:
            self.schemas.validate("analysis-work-item.schema.json", item)

        invalid = copy.deepcopy(items[0])
        invalid["hidden_reasoning"] = "forbidden"
        with self.assertRaises(ContractError):
            self.schemas.validate("analysis-work-item.schema.json", invalid)

        invalid = copy.deepcopy(graph)
        invalid["status"] = "infinite_loop"
        with self.assertRaises(ContractError):
            self.schemas.validate("analysis-work-graph.schema.json", invalid)

    def test_budget_and_checkpoint_contracts_are_closed(self):
        graph_api, budget_api, checkpoint_api = _api()
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
            benchmark_refs=["benchmark_b", "benchmark_a"],
            approved_concurrency_profile_id="parallel_2",
            effective_from="2026-07-17T00:00:00Z",
        )
        graph, items = graph_api.compile_work_graph(
            run_id="run_contract",
            base_revision=7,
            signal_case_ids=["case_001"],
            work_item_specs=[_spec("a"), _spec("b", ("a",))],
            policy_release_id="policy_release_001",
            concurrency_profile_id="parallel_2",
        )
        checkpoint = checkpoint_api.build_work_checkpoint(
            graph, items, sequence=0, previous_checkpoint_ref=None
        )

        self.schemas.validate("work-budget-policy.schema.json", policy)
        self.schemas.validate("work-checkpoint.schema.json", checkpoint)

        invalid = copy.deepcopy(policy)
        invalid["overflow_action"] = "drop_required_work"
        with self.assertRaises(ContractError):
            self.schemas.validate("work-budget-policy.schema.json", invalid)

        invalid = copy.deepcopy(checkpoint)
        invalid["task_states"][0]["status"] = "unknown"
        with self.assertRaises(ContractError):
            self.schemas.validate("work-checkpoint.schema.json", invalid)


if __name__ == "__main__":
    unittest.main()
