from __future__ import annotations

import copy
import hashlib
import heapq
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


WORK_ITEM_STATUSES = frozenset({
    "pending",
    "ready",
    "leased",
    "running",
    "succeeded",
    "needs_input",
    "deep_review_pending",
    "failed",
    "cancelled",
    "superseded",
})
GRAPH_STATUSES = frozenset({
    "pending",
    "running",
    "needs_prioritization",
    "needs_input",
    "deep_review_pending",
    "succeeded",
    "failed",
    "cancelled",
    "superseded",
})
FAILURE_CODES = frozenset({
    "contract_invalid",
    "packet_hash_mismatch",
    "source_unavailable",
    "model_timeout",
    "model_contract_failure",
    "procedure_failed",
    "required_evidence_missing",
    "stale_revision",
    "cancelled_by_human",
    "resource_exhausted",
    "unsupported_pack",
})
RETRYABLE_FAILURE_CODES = frozenset({
    "contract_invalid",
    "source_unavailable",
    "model_timeout",
    "model_contract_failure",
})
CONCURRENCY_PROFILES = frozenset({
    "sequential", "parallel_2", "parallel_3", "parallel_4",
})

GRAPH_FIELDS = frozenset({
    "graph_id", "run_id", "base_revision", "signal_case_ids", "node_ids", "edge_ids",
    "required_node_ids", "policy_release_id", "concurrency_profile_id",
    "created_from_hash", "status", "checkpoint_ref",
})
WORK_ITEM_FIELDS = frozenset({
    "task_id", "graph_id", "signal_case_id", "event_id", "domain", "issue_family",
    "procedure_refs", "dependency_ids", "required", "packet_ref", "packet_hash",
    "pack_release_id", "policy_release_id", "attempt", "timeout_policy", "status",
    "lease_owner", "result_ref", "result_hash", "failure_code",
})
SPEC_FIELDS = frozenset({
    "local_key", "signal_case_id", "event_id", "domain", "issue_family",
    "procedure_refs", "dependency_keys", "required", "packet_ref", "packet_hash",
    "pack_release_id", "timeout_policy",
})
TIMEOUT_POLICY_FIELDS = frozenset({"timeout_seconds", "retryable_failure_codes"})


def _native_integers(value: Any) -> Any:
    """Restore strict JSON integer Decimals before validation or hashing."""
    if isinstance(value, Decimal):
        if value.is_finite() and value == value.to_integral_value():
            return int(value)
        return value
    if isinstance(value, dict):
        return {key: _native_integers(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_native_integers(child) for child in value]
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{field} must be a non-empty string")
    return value


def _integer(value: Any, field: str, *, minimum: int = 0) -> int:
    value = _native_integers(value)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContractError(f"{field} must be an integer >= {minimum}")
    return value


def _hash(value: Any, field: str) -> str:
    text = _text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ContractError(f"{field} must be a lowercase SHA-256")
    return text


def _string_set(values: Any, field: str, *, non_empty: bool = False) -> list[str]:
    if not isinstance(values, (list, tuple)):
        raise ContractError(f"{field} must be an array")
    normalized = [_text(value, field) for value in values]
    if len(normalized) != len(set(normalized)):
        raise ContractError(f"{field} contains duplicates")
    if non_empty and not normalized:
        raise ContractError(f"{field} must not be empty")
    return sorted(normalized)


def _timeout_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != TIMEOUT_POLICY_FIELDS:
        raise ContractError("timeout_policy has invalid fields")
    retryable = _string_set(
        value["retryable_failure_codes"], "retryable_failure_codes"
    )
    unknown = set(retryable) - RETRYABLE_FAILURE_CODES
    if unknown:
        raise ContractError(f"unsafe retryable failure codes: {sorted(unknown)}")
    return {
        "timeout_seconds": _integer(
            value["timeout_seconds"], "timeout_seconds", minimum=1
        ),
        "retryable_failure_codes": retryable,
    }


def _normalize_spec(raw: Mapping[str, Any]) -> dict[str, Any]:
    if set(raw) != SPEC_FIELDS:
        missing = sorted(SPEC_FIELDS - set(raw))
        extra = sorted(set(raw) - SPEC_FIELDS)
        raise ContractError(f"Work Item spec fields are invalid: missing={missing}, extra={extra}")
    required = raw["required"]
    if not isinstance(required, bool):
        raise ContractError("required must be boolean")
    return {
        "local_key": _text(raw["local_key"], "local_key"),
        "signal_case_id": _text(raw["signal_case_id"], "signal_case_id"),
        "event_id": _text(raw["event_id"], "event_id"),
        "domain": _text(raw["domain"], "domain"),
        "issue_family": _text(raw["issue_family"], "issue_family"),
        "procedure_refs": _string_set(raw["procedure_refs"], "procedure_refs"),
        "dependency_keys": _string_set(raw["dependency_keys"], "dependency_keys"),
        "required": required,
        "packet_ref": _text(raw["packet_ref"], "packet_ref"),
        "packet_hash": _hash(raw["packet_hash"], "packet_hash"),
        "pack_release_id": _text(raw["pack_release_id"], "pack_release_id"),
        "timeout_policy": _timeout_policy(raw["timeout_policy"]),
    }


def _edge_id(predecessor_id: str, successor_id: str) -> str:
    return "edge_" + _digest({
        "predecessor_task_id": predecessor_id,
        "successor_task_id": successor_id,
    })[:24]


def stable_topological_order(work_items: Sequence[Mapping[str, Any]]) -> list[str]:
    by_id: dict[str, Mapping[str, Any]] = {}
    for item in work_items:
        task_id = _text(item.get("task_id"), "task_id")
        if task_id in by_id:
            raise ContractError(f"duplicate Work Item: {task_id}")
        by_id[task_id] = item
    if not by_id:
        raise ContractError("AnalysisWorkGraph must contain at least one Work Item")

    indegree = {task_id: 0 for task_id in by_id}
    successors = {task_id: [] for task_id in by_id}
    for task_id, item in by_id.items():
        dependencies = _string_set(item.get("dependency_ids"), "dependency_ids")
        for dependency_id in dependencies:
            if dependency_id not in by_id:
                raise ContractError(
                    f"dangling dependency for {task_id}: {dependency_id}"
                )
            if dependency_id == task_id:
                raise ContractError(f"self dependency is forbidden: {task_id}")
            indegree[task_id] += 1
            successors[dependency_id].append(task_id)

    ready = [task_id for task_id, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        task_id = heapq.heappop(ready)
        order.append(task_id)
        for successor_id in sorted(successors[task_id]):
            indegree[successor_id] -= 1
            if indegree[successor_id] == 0:
                heapq.heappush(ready, successor_id)
    if len(order) != len(by_id):
        raise ContractError("AnalysisWorkGraph must be acyclic")
    return order


def validate_work_graph(
    graph: Mapping[str, Any],
    work_items: Sequence[Mapping[str, Any]],
    *,
    active_created_from_hash: str | None = None,
) -> None:
    graph = _native_integers(dict(graph))
    work_items = _native_integers([dict(item) for item in work_items])
    if set(graph) != GRAPH_FIELDS:
        raise ContractError("AnalysisWorkGraph fields do not match the contract")
    if graph.get("status") not in GRAPH_STATUSES:
        raise ContractError(f"invalid AnalysisWorkGraph status: {graph.get('status')}")
    created_from_hash = _hash(graph.get("created_from_hash"), "created_from_hash")
    if graph.get("graph_id") != f"graph_{created_from_hash[:24]}":
        raise ContractError("AnalysisWorkGraph ID does not match created_from_hash")
    if active_created_from_hash is not None and created_from_hash != _hash(
        active_created_from_hash, "active_created_from_hash"
    ):
        raise ContractError("stale semantic generation")
    if not isinstance(graph.get("run_id"), str) or not str(graph["run_id"]).startswith("run_"):
        raise ContractError("invalid run_id")
    _integer(graph.get("base_revision"), "base_revision")
    signal_case_ids = _string_set(
        graph.get("signal_case_ids"), "signal_case_ids", non_empty=True
    )
    node_ids = _string_set(graph.get("node_ids"), "node_ids", non_empty=True)
    required_node_ids = _string_set(
        graph.get("required_node_ids"), "required_node_ids"
    )
    if not set(required_node_ids).issubset(node_ids):
        raise ContractError("required_node_ids must be a subset of node_ids")
    if graph.get("concurrency_profile_id") not in CONCURRENCY_PROFILES:
        raise ContractError("unapproved concurrency profile")
    policy_release_id = _text(graph.get("policy_release_id"), "policy_release_id")
    if graph.get("checkpoint_ref") is not None:
        _text(graph.get("checkpoint_ref"), "checkpoint_ref")

    items = [dict(item) for item in work_items]
    if any(set(item) != WORK_ITEM_FIELDS for item in items):
        raise ContractError("AnalysisWorkItem fields do not match the contract")
    by_id = {str(item.get("task_id")): item for item in items}
    if len(by_id) != len(items) or sorted(by_id) != node_ids:
        raise ContractError("graph node_ids do not exactly match Work Items")
    for task_id, item in by_id.items():
        if item.get("graph_id") != graph.get("graph_id"):
            raise ContractError(f"Work Item belongs to another graph: {task_id}")
        if item.get("policy_release_id") != policy_release_id:
            raise ContractError(f"Work Item uses another policy release: {task_id}")
        if item.get("signal_case_id") not in signal_case_ids:
            raise ContractError(f"Work Item uses an unknown Signal Case: {task_id}")
        if item.get("status") not in WORK_ITEM_STATUSES:
            raise ContractError(f"invalid Work Item status: {task_id}")
        _hash(item.get("packet_hash"), "packet_hash")
        _timeout_policy(item.get("timeout_policy"))
        _integer(item.get("attempt"), "attempt")
        if int(item["attempt"]) > 2:
            raise ContractError("Work Item attempt cannot exceed two")
        if not isinstance(item.get("required"), bool):
            raise ContractError("Work Item required must be boolean")

    computed_required = sorted(
        task_id for task_id, item in by_id.items() if item["required"]
    )
    if computed_required != required_node_ids:
        raise ContractError("required_node_ids do not match Work Item requirements")
    expected_edges = sorted(
        _edge_id(dependency_id, task_id)
        for task_id, item in by_id.items()
        for dependency_id in _string_set(item["dependency_ids"], "dependency_ids")
    )
    if expected_edges != _string_set(graph.get("edge_ids"), "edge_ids"):
        raise ContractError("edge_ids do not match Work Item dependencies")
    stable_topological_order(items)


def compile_work_graph(
    *,
    run_id: str,
    base_revision: int,
    signal_case_ids: Sequence[str],
    work_item_specs: Sequence[Mapping[str, Any]],
    policy_release_id: str,
    concurrency_profile_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    run_id = _text(run_id, "run_id")
    if not run_id.startswith("run_"):
        raise ContractError("run_id must begin with run_")
    base_revision = _integer(base_revision, "base_revision")
    cases = _string_set(signal_case_ids, "signal_case_ids", non_empty=True)
    policy_release_id = _text(policy_release_id, "policy_release_id")
    if concurrency_profile_id not in CONCURRENCY_PROFILES:
        raise ContractError(f"unsupported concurrency profile: {concurrency_profile_id}")
    if not isinstance(work_item_specs, (list, tuple)) or not work_item_specs:
        raise ContractError("AnalysisWorkGraph requires Work Item specs")

    normalized_specs = [_normalize_spec(spec) for spec in work_item_specs]
    normalized_specs.sort(key=lambda item: item["local_key"])
    local_keys = [item["local_key"] for item in normalized_specs]
    if len(local_keys) != len(set(local_keys)):
        raise ContractError("Work Item local_key must be unique")
    known_keys = set(local_keys)
    for spec in normalized_specs:
        if spec["signal_case_id"] not in cases:
            raise ContractError(
                f"Work Item uses an unknown Signal Case: {spec['signal_case_id']}"
            )
        dangling = set(spec["dependency_keys"]) - known_keys
        if dangling:
            raise ContractError(
                f"dangling dependency keys for {spec['local_key']}: {sorted(dangling)}"
            )

    source = {
        "run_id": run_id,
        "base_revision": base_revision,
        "signal_case_ids": cases,
        "work_item_specs": normalized_specs,
        "policy_release_id": policy_release_id,
        "concurrency_profile_id": concurrency_profile_id,
    }
    created_from_hash = _digest(source)
    graph_id = f"graph_{created_from_hash[:24]}"
    task_id_by_key = {
        local_key: "task_" + _digest({
            "graph_id": graph_id,
            "local_key": local_key,
        })[:24]
        for local_key in local_keys
    }

    items: list[dict[str, Any]] = []
    for spec in normalized_specs:
        item = {
            "task_id": task_id_by_key[spec["local_key"]],
            "graph_id": graph_id,
            "signal_case_id": spec["signal_case_id"],
            "event_id": spec["event_id"],
            "domain": spec["domain"],
            "issue_family": spec["issue_family"],
            "procedure_refs": list(spec["procedure_refs"]),
            "dependency_ids": sorted(
                task_id_by_key[key] for key in spec["dependency_keys"]
            ),
            "required": spec["required"],
            "packet_ref": spec["packet_ref"],
            "packet_hash": spec["packet_hash"],
            "pack_release_id": spec["pack_release_id"],
            "policy_release_id": policy_release_id,
            "attempt": 0,
            "timeout_policy": copy.deepcopy(spec["timeout_policy"]),
            "status": "pending",
            "lease_owner": None,
            "result_ref": None,
            "result_hash": None,
            "failure_code": None,
        }
        items.append(item)
    items.sort(key=lambda item: item["task_id"])

    graph = {
        "graph_id": graph_id,
        "run_id": run_id,
        "base_revision": base_revision,
        "signal_case_ids": cases,
        "node_ids": [item["task_id"] for item in items],
        "edge_ids": sorted(
            _edge_id(dependency_id, item["task_id"])
            for item in items
            for dependency_id in item["dependency_ids"]
        ),
        "required_node_ids": sorted(
            item["task_id"] for item in items if item["required"]
        ),
        "policy_release_id": policy_release_id,
        "concurrency_profile_id": concurrency_profile_id,
        "created_from_hash": created_from_hash,
        "status": "pending",
        "checkpoint_ref": None,
    }
    validate_work_graph(graph, items)
    schemas = SchemaStore()
    schemas.validate("analysis-work-graph.schema.json", graph)
    for item in items:
        schemas.validate("analysis-work-item.schema.json", item)
    return graph, items


def work_idempotency_key(work_item: Mapping[str, Any]) -> str:
    task_id = _text(work_item.get("task_id"), "task_id")
    packet_hash = _hash(work_item.get("packet_hash"), "packet_hash")
    policy_release_id = _text(
        work_item.get("policy_release_id"), "policy_release_id"
    )
    return "idem_" + _digest({
        "task_id": task_id,
        "packet_hash": packet_hash,
        "policy_release_id": policy_release_id,
    })
