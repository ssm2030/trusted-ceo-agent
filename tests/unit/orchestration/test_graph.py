import hashlib
import importlib
import unittest

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.errors import ContractError


def _api():
    try:
        return importlib.import_module("trusted_ceo_agent.orchestration.graph")
    except ModuleNotFoundError as error:
        raise AssertionError(f"graph API is missing: {error}") from error


def _spec(local_key, dependencies=(), *, required=True, case_id="case_001"):
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
        "packet_hash": hashlib.sha256(local_key.encode("utf-8")).hexdigest(),
        "pack_release_id": "pack_release_001",
        "timeout_policy": {
            "timeout_seconds": 30,
            "retryable_failure_codes": ["model_timeout", "contract_invalid"],
        },
    }


class WorkGraphTests(unittest.TestCase):
    def compile(self, specs):
        return _api().compile_work_graph(
            run_id="run_graph",
            base_revision=4,
            signal_case_ids=["case_001"],
            work_item_specs=specs,
            policy_release_id="policy_release_001",
            concurrency_profile_id="parallel_2",
        )

    def test_compile_is_order_invariant_and_topological(self):
        api = _api()
        specs = [_spec("a"), _spec("b", ("a",)), _spec("c", ("a",))]
        first_graph, first_items = self.compile(specs)
        second_graph, second_items = self.compile(list(reversed(specs)))

        self.assertEqual(first_graph, second_graph)
        self.assertEqual(first_items, second_items)
        order = api.stable_topological_order(first_items)
        by_issue = {item["issue_family"]: item["task_id"] for item in first_items}
        self.assertLess(order.index(by_issue["AC-A"]), order.index(by_issue["AC-B"]))
        self.assertLess(order.index(by_issue["AC-A"]), order.index(by_issue["AC-C"]))
        self.assertEqual(sorted(first_graph["node_ids"]), first_graph["node_ids"])
        self.assertEqual(sorted(first_graph["edge_ids"]), first_graph["edge_ids"])

    def test_graph_and_items_have_exact_contract_fields(self):
        graph, items = self.compile([_spec("a")])
        self.assertEqual(
            {
                "graph_id", "run_id", "base_revision", "signal_case_ids", "node_ids",
                "edge_ids", "required_node_ids", "policy_release_id",
                "concurrency_profile_id", "created_from_hash", "status", "checkpoint_ref",
            },
            set(graph),
        )
        self.assertEqual(
            {
                "task_id", "graph_id", "signal_case_id", "event_id", "domain",
                "issue_family", "procedure_refs", "dependency_ids", "required",
                "packet_ref", "packet_hash", "pack_release_id", "policy_release_id",
                "attempt", "timeout_policy", "status", "lease_owner", "result_ref",
                "result_hash", "failure_code",
            },
            set(items[0]),
        )
        self.assertEqual("pending", graph["status"])
        self.assertEqual("pending", items[0]["status"])
        self.assertEqual(0, items[0]["attempt"])
        self.assertIsNone(graph["checkpoint_ref"])

    def test_cycle_dangling_and_duplicate_nodes_are_rejected(self):
        cases = [
            [_spec("a", ("b",)), _spec("b", ("a",))],
            [_spec("a", ("missing",))],
            [_spec("a"), _spec("a")],
        ]
        for specs in cases:
            with self.subTest(specs=specs):
                with self.assertRaises(ContractError):
                    self.compile(specs)

    def test_idempotency_key_uses_exact_task_packet_policy_tuple(self):
        api = _api()
        _, items = self.compile([_spec("a")])
        item = items[0]
        expected = "idem_" + hashlib.sha256(canonical_bytes({
            "task_id": item["task_id"],
            "packet_hash": item["packet_hash"],
            "policy_release_id": item["policy_release_id"],
        })).hexdigest()
        self.assertEqual(expected, api.work_idempotency_key(item))

        changed = dict(item)
        changed["packet_hash"] = "f" * 64
        self.assertNotEqual(api.work_idempotency_key(item), api.work_idempotency_key(changed))

    def test_persisted_graph_round_trip_keeps_integer_contracts(self):
        api = _api()
        graph, items = self.compile([_spec("a")])
        persisted_graph = strict_loads(canonical_bytes(graph))
        persisted_items = strict_loads(canonical_bytes(items))

        api.validate_work_graph(
            persisted_graph,
            persisted_items,
            active_created_from_hash=graph["created_from_hash"],
        )

    def test_nonretryable_integrity_failures_cannot_be_declared_retryable(self):
        for failure_code in ("packet_hash_mismatch", "stale_revision"):
            spec = _spec("a")
            spec["timeout_policy"]["retryable_failure_codes"].append(failure_code)
            with self.subTest(failure_code=failure_code):
                with self.assertRaises(ContractError):
                    self.compile([spec])


if __name__ == "__main__":
    unittest.main()
