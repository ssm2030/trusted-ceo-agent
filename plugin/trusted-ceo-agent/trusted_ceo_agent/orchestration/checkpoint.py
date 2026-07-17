from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.orchestration.budget import verify_work_budget_policy
from trusted_ceo_agent.orchestration.graph import (
    WORK_ITEM_STATUSES,
    _native_integers,
    validate_work_graph,
)


TERMINAL_WORK_ITEM_STATUSES = frozenset({
    "succeeded",
    "needs_input",
    "deep_review_pending",
    "failed",
    "cancelled",
    "superseded",
})
CHECKPOINT_FIELDS = frozenset({
    "checkpoint_id",
    "graph_id",
    "run_id",
    "base_revision",
    "created_from_hash",
    "policy_release_id",
    "sequence",
    "previous_checkpoint_ref",
    "task_states",
    "pending_task_ids",
    "ready_task_ids",
    "running_task_ids",
    "terminal_task_ids",
    "result_records",
    "content_hash",
})
TASK_STATE_FIELDS = frozenset({
    "task_id",
    "status",
    "attempt",
    "packet_hash",
    "lease_owner",
    "lease_started_at",
    "result_ref",
    "result_hash",
    "failure_code",
})


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _integer(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise ContractError(f"{field} must be an integer >= {minimum}")
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContractError(f"{field} must be an integer >= {minimum}")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{field} must be a non-empty string")
    return value


def _task_state(
    item: Mapping[str, Any],
    lease_started_at_by_task: Mapping[str, int],
) -> dict[str, Any]:
    task_id = _text(item.get("task_id"), "task_id")
    status = item.get("status")
    if status not in WORK_ITEM_STATUSES:
        raise ContractError(f"unknown Work Item status: {status}")
    attempt = _integer(item.get("attempt"), "attempt")
    if attempt > 2:
        raise ContractError("Work Item attempt cannot exceed two")
    lease_started_at = lease_started_at_by_task.get(task_id)
    if status in {"leased", "running"}:
        _text(item.get("lease_owner"), "lease_owner")
        lease_started_at = _integer(
            lease_started_at, "lease_started_at", minimum=0
        )
    elif lease_started_at is not None:
        raise ContractError("only leased or running Work Items may retain a lease time")
    result_ref = item.get("result_ref")
    result_hash = item.get("result_hash")
    if (result_ref is None) != (result_hash is None):
        raise ContractError("result_ref and result_hash must be present together")
    if status == "succeeded" and result_ref is None:
        raise ContractError("succeeded Work Item lacks a result")
    return {
        "task_id": task_id,
        "status": status,
        "attempt": attempt,
        "packet_hash": _text(item.get("packet_hash"), "packet_hash"),
        "lease_owner": item.get("lease_owner"),
        "lease_started_at": lease_started_at,
        "result_ref": result_ref,
        "result_hash": result_hash,
        "failure_code": item.get("failure_code"),
    }


def _partitions(task_states: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    pending = sorted(
        str(state["task_id"]) for state in task_states
        if state["status"] == "pending"
    )
    ready = sorted(
        str(state["task_id"]) for state in task_states
        if state["status"] == "ready"
    )
    running = sorted(
        str(state["task_id"]) for state in task_states
        if state["status"] in {"leased", "running"}
    )
    terminal = sorted(
        str(state["task_id"]) for state in task_states
        if state["status"] in TERMINAL_WORK_ITEM_STATUSES
    )
    if len(pending) + len(ready) + len(running) + len(terminal) != len(task_states):
        raise ContractError("checkpoint partitions are not exhaustive")
    return {
        "pending_task_ids": pending,
        "ready_task_ids": ready,
        "running_task_ids": running,
        "terminal_task_ids": terminal,
    }


def build_work_checkpoint(
    graph: Mapping[str, Any],
    work_items: Sequence[Mapping[str, Any]],
    *,
    sequence: int,
    previous_checkpoint_ref: str | None,
    lease_started_at_by_task: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    graph = _native_integers(dict(graph))
    work_items = _native_integers([dict(item) for item in work_items])
    validate_work_graph(graph, work_items)
    sequence = _integer(sequence, "sequence")
    if previous_checkpoint_ref is not None:
        _text(previous_checkpoint_ref, "previous_checkpoint_ref")
    lease_times = dict(lease_started_at_by_task or {})
    known_task_ids = {str(item["task_id"]) for item in work_items}
    if set(lease_times) - known_task_ids:
        raise ContractError("checkpoint contains a lease for an unknown Work Item")

    task_states = sorted(
        (_task_state(item, lease_times) for item in work_items),
        key=lambda state: state["task_id"],
    )
    partitions = _partitions(task_states)
    result_records = sorted(
        (
            {
                "task_id": state["task_id"],
                "result_ref": state["result_ref"],
                "result_hash": state["result_hash"],
            }
            for state in task_states
            if state["result_ref"] is not None
        ),
        key=lambda record: record["task_id"],
    )
    body = {
        "graph_id": graph["graph_id"],
        "run_id": graph["run_id"],
        "base_revision": graph["base_revision"],
        "created_from_hash": graph["created_from_hash"],
        "policy_release_id": graph["policy_release_id"],
        "sequence": sequence,
        "previous_checkpoint_ref": previous_checkpoint_ref,
        "task_states": task_states,
        **partitions,
        "result_records": result_records,
    }
    content_hash = _digest(body)
    checkpoint = {
        "checkpoint_id": f"checkpoint_{content_hash[:24]}",
        **body,
        "content_hash": content_hash,
    }
    SchemaStore().validate("work-checkpoint.schema.json", checkpoint)
    return checkpoint


def verify_work_checkpoint(
    checkpoint: Mapping[str, Any],
    graph: Mapping[str, Any],
    work_items: Sequence[Mapping[str, Any]],
    *,
    active_created_from_hash: str,
    result_payloads: Mapping[str, bytes],
) -> None:
    checkpoint = _native_integers(dict(checkpoint))
    graph = _native_integers(dict(graph))
    work_items = _native_integers([dict(item) for item in work_items])
    if set(checkpoint) != CHECKPOINT_FIELDS:
        raise ContractError("WorkCheckpoint fields do not match the contract")
    validate_work_graph(
        graph,
        work_items,
        active_created_from_hash=active_created_from_hash,
    )
    anchors = {
        "graph_id": "graph_id",
        "run_id": "run_id",
        "base_revision": "base_revision",
        "created_from_hash": "created_from_hash",
        "policy_release_id": "policy_release_id",
    }
    for checkpoint_field, graph_field in anchors.items():
        if checkpoint.get(checkpoint_field) != graph.get(graph_field):
            raise ContractError(f"WorkCheckpoint {checkpoint_field} is stale")

    body = {
        key: checkpoint[key]
        for key in checkpoint
        if key not in {"checkpoint_id", "content_hash"}
    }
    expected_hash = _digest(body)
    if checkpoint.get("content_hash") != expected_hash:
        raise ContractError("WorkCheckpoint content hash mismatch")
    if checkpoint.get("checkpoint_id") != f"checkpoint_{expected_hash[:24]}":
        raise ContractError("WorkCheckpoint ID mismatch")
    _integer(checkpoint.get("sequence"), "sequence")

    task_states = checkpoint.get("task_states")
    if not isinstance(task_states, list) or not task_states:
        raise ContractError("WorkCheckpoint task_states must not be empty")
    if any(not isinstance(state, Mapping) or set(state) != TASK_STATE_FIELDS for state in task_states):
        raise ContractError("WorkCheckpoint task state fields are invalid")
    state_by_id = {str(state.get("task_id")): state for state in task_states}
    if len(state_by_id) != len(task_states):
        raise ContractError("WorkCheckpoint contains duplicate task states")
    item_by_id = {str(item["task_id"]): item for item in work_items}
    if set(state_by_id) != set(item_by_id):
        raise ContractError("WorkCheckpoint task set does not match the graph")
    for task_id, state in state_by_id.items():
        if state.get("packet_hash") != item_by_id[task_id].get("packet_hash"):
            raise ContractError(f"WorkCheckpoint packet hash mismatch: {task_id}")
        if state.get("status") not in WORK_ITEM_STATUSES:
            raise ContractError(f"WorkCheckpoint status is invalid: {task_id}")

    expected_partitions = _partitions(task_states)
    for field, expected in expected_partitions.items():
        if checkpoint.get(field) != expected:
            raise ContractError(f"WorkCheckpoint {field} is inconsistent")
    partition_union = set().union(*(set(values) for values in expected_partitions.values()))
    if partition_union != set(state_by_id):
        raise ContractError("WorkCheckpoint partitions do not cover every Work Item")

    expected_results = sorted(
        (
            {
                "task_id": state["task_id"],
                "result_ref": state["result_ref"],
                "result_hash": state["result_hash"],
            }
            for state in task_states
            if state.get("result_ref") is not None
        ),
        key=lambda record: record["task_id"],
    )
    if checkpoint.get("result_records") != expected_results:
        raise ContractError("WorkCheckpoint result records are inconsistent")
    for state in task_states:
        if state["status"] != "succeeded":
            continue
        result_ref = state.get("result_ref")
        result_hash = state.get("result_hash")
        if not isinstance(result_ref, str) or not isinstance(result_hash, str):
            raise ContractError(f"succeeded Work Item lacks a result: {state['task_id']}")
        payload = result_payloads.get(result_ref)
        if not isinstance(payload, bytes):
            raise ContractError(f"checkpoint result payload is unavailable: {result_ref}")
        if hashlib.sha256(payload).hexdigest() != result_hash:
            raise ContractError(f"checkpoint result hash mismatch: {result_ref}")
    SchemaStore().validate("work-checkpoint.schema.json", dict(checkpoint))


def restore_work_items(
    checkpoint: Mapping[str, Any],
    graph: Mapping[str, Any],
    work_items: Sequence[Mapping[str, Any]],
    policy: Mapping[str, Any],
    *,
    active_created_from_hash: str,
    result_payloads: Mapping[str, bytes],
) -> list[dict[str, Any]]:
    checkpoint = _native_integers(dict(checkpoint))
    graph = _native_integers(dict(graph))
    work_items = _native_integers([dict(item) for item in work_items])
    policy = _native_integers(dict(policy))
    verify_work_budget_policy(policy)
    verify_work_checkpoint(
        checkpoint,
        graph,
        work_items,
        active_created_from_hash=active_created_from_hash,
        result_payloads=result_payloads,
    )
    state_by_id = {
        str(state["task_id"]): state for state in checkpoint["task_states"]
    }
    restored: list[dict[str, Any]] = []
    max_attempts = int(policy["max_model_attempts_per_task"])
    for original in sorted(work_items, key=lambda item: str(item["task_id"])):
        item = copy.deepcopy(dict(original))
        state = state_by_id[str(item["task_id"])]
        for field in (
            "status", "attempt", "lease_owner", "result_ref", "result_hash", "failure_code",
        ):
            item[field] = state[field]
        if item["status"] in {"leased", "running"}:
            item["lease_owner"] = None
            item["result_ref"] = None
            item["result_hash"] = None
            if int(item["attempt"]) < max_attempts:
                item["status"] = "ready"
                item["failure_code"] = "source_unavailable"
            elif item["required"]:
                item["status"] = "deep_review_pending"
                item["failure_code"] = "model_timeout"
            else:
                item["status"] = "failed"
                item["failure_code"] = "model_timeout"
        restored.append(item)
    return restored
