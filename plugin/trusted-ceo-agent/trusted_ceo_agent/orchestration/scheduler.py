from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.orchestration.budget import (
    assess_work_budget,
    verify_work_budget_policy,
)
from trusted_ceo_agent.orchestration.checkpoint import (
    TERMINAL_WORK_ITEM_STATUSES,
    build_work_checkpoint,
    restore_work_items,
)
from trusted_ceo_agent.orchestration.graph import (
    FAILURE_CODES,
    _native_integers,
    validate_work_graph,
    work_idempotency_key,
)


ACTIVE_STATUSES = frozenset({"leased", "running"})
NONTERMINAL_STATUSES = frozenset({"pending", "ready", "leased", "running"})


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{field} must be a non-empty string")
    return value


def _clock(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractError("scheduler clock must be a non-negative integer")
    return value


class WorkScheduler:
    """Pure in-memory state reducer for one immutable AnalysisWorkGraph."""

    def __init__(
        self,
        graph: Mapping[str, Any],
        work_items: Sequence[Mapping[str, Any]],
        policy: Mapping[str, Any],
    ) -> None:
        graph = _native_integers(dict(graph))
        work_items = _native_integers([dict(item) for item in work_items])
        policy = _native_integers(dict(policy))
        verify_work_budget_policy(policy)
        validate_work_graph(graph, work_items)
        if (
            policy["approved_concurrency_profile_id"]
            != graph["concurrency_profile_id"]
        ):
            raise ContractError("WorkBudgetPolicy does not approve the graph profile")
        if any(
            int(item["timeout_policy"]["timeout_seconds"])
            > int(policy["task_timeout"])
            for item in work_items
        ):
            raise ContractError("Work Item timeout exceeds WorkBudgetPolicy task_timeout")
        self._graph = copy.deepcopy(dict(graph))
        self._items = {
            str(item["task_id"]): copy.deepcopy(dict(item))
            for item in work_items
        }
        self._policy = copy.deepcopy(dict(policy))
        self._lease_started_at: dict[str, int] = {}
        self._refresh()

    @classmethod
    def from_checkpoint(
        cls,
        graph: Mapping[str, Any],
        work_items: Sequence[Mapping[str, Any]],
        policy: Mapping[str, Any],
        checkpoint: Mapping[str, Any],
        *,
        active_created_from_hash: str,
        result_payloads: Mapping[str, bytes],
    ) -> "WorkScheduler":
        restored = restore_work_items(
            checkpoint,
            graph,
            work_items,
            policy,
            active_created_from_hash=active_created_from_hash,
            result_payloads=result_payloads,
        )
        return cls(graph, restored, policy)

    def graph_snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self._graph)

    def work_items(self) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(self._items[task_id])
            for task_id in sorted(self._items)
        ]

    def _assert_active_generation(self, active_created_from_hash: str) -> None:
        if active_created_from_hash == self._graph["created_from_hash"]:
            return
        self._graph["status"] = "superseded"
        for item in self._items.values():
            if item["status"] in NONTERMINAL_STATUSES:
                item["status"] = "superseded"
                item["lease_owner"] = None
                item["result_ref"] = None
                item["result_hash"] = None
                item["failure_code"] = "stale_revision"
                self._lease_started_at.pop(item["task_id"], None)
        raise ContractError("stale semantic generation")

    def _refresh(self) -> None:
        changed = True
        while changed:
            changed = False
            for task_id in sorted(self._items):
                item = self._items[task_id]
                if item["status"] != "pending":
                    continue
                dependencies = [
                    self._items[dependency_id]
                    for dependency_id in item["dependency_ids"]
                ]
                if not dependencies:
                    item["status"] = "ready"
                    changed = True
                    continue
                if any(
                    dependency["status"] not in TERMINAL_WORK_ITEM_STATUSES
                    for dependency in dependencies
                ):
                    continue
                blockers = [
                    dependency
                    for dependency in dependencies
                    if dependency["required"]
                    and dependency["status"] != "succeeded"
                ]
                if not blockers:
                    item["status"] = "ready"
                    changed = True
                    continue
                blocker_states = {blocker["status"] for blocker in blockers}
                if blocker_states & {"needs_input", "deep_review_pending"}:
                    continue
                if "superseded" in blocker_states:
                    item["status"] = "superseded"
                    item["failure_code"] = "stale_revision"
                elif "cancelled" in blocker_states:
                    item["status"] = "cancelled"
                    item["failure_code"] = "cancelled_by_human"
                else:
                    item["status"] = "failed"
                    item["failure_code"] = "procedure_failed"
                changed = True

        if self._graph["status"] in {"cancelled", "superseded"}:
            return
        items = list(self._items.values())
        if any(item["status"] == "needs_input" for item in items):
            self._graph["status"] = "needs_input"
        elif any(item["status"] == "deep_review_pending" for item in items):
            self._graph["status"] = "deep_review_pending"
        elif any(
            item["required"] and item["status"] == "failed" for item in items
        ):
            self._graph["status"] = "failed"
        elif any(
            item["required"] and item["status"] == "cancelled" for item in items
        ):
            self._graph["status"] = "cancelled"
        elif (
            all(item["status"] in TERMINAL_WORK_ITEM_STATUSES for item in items)
            and all(
                not item["required"] or item["status"] == "succeeded"
                for item in items
            )
        ):
            self._graph["status"] = "succeeded"
        elif any(
            item["status"] in {"leased", "running", "succeeded"} for item in items
        ):
            self._graph["status"] = "running"
        else:
            self._graph["status"] = "pending"

    def lease(self, worker_id: str, *, now: int) -> dict[str, Any] | None:
        worker_id = _text(worker_id, "worker_id")
        now = _clock(now)
        active = [
            item for item in self._items.values()
            if item["status"] in ACTIVE_STATUSES
        ]
        if any(item["lease_owner"] == worker_id for item in active):
            raise ContractError("worker already owns an active lease")
        if len(active) >= int(self._policy["max_parallel_workers"]):
            return None

        ready = sorted(
            (
                item for item in self._items.values()
                if item["status"] == "ready"
            ),
            key=lambda item: (item["signal_case_id"], item["task_id"]),
        )
        if not ready:
            return None
        active_cases = {str(item["signal_case_id"]) for item in active}
        if active_cases:
            candidates = [
                item for item in ready if item["signal_case_id"] in active_cases
            ]
            if not candidates and len(active_cases) < int(
                self._policy["max_active_signal_cases"]
            ):
                candidates = ready
        else:
            first_case = str(ready[0]["signal_case_id"])
            candidates = [
                item for item in ready if item["signal_case_id"] == first_case
            ]
        if not candidates:
            return None
        item = candidates[0]
        if int(item["attempt"]) >= int(
            self._policy["max_model_attempts_per_task"]
        ):
            item["status"] = (
                "deep_review_pending" if item["required"] else "failed"
            )
            item["failure_code"] = "resource_exhausted"
            self._refresh()
            return None
        item["attempt"] = int(item["attempt"]) + 1
        item["status"] = "leased"
        item["lease_owner"] = worker_id
        self._lease_started_at[item["task_id"]] = now
        self._graph["status"] = "running"
        return copy.deepcopy(item)

    def start(self, task_id: str, worker_id: str) -> dict[str, Any]:
        task_id = _text(task_id, "task_id")
        worker_id = _text(worker_id, "worker_id")
        item = self._items.get(task_id)
        if item is None:
            raise ContractError(f"unknown Work Item: {task_id}")
        if item["status"] != "leased" or item["lease_owner"] != worker_id:
            raise ContractError("only the lease owner may start a leased Work Item")
        item["status"] = "running"
        return copy.deepcopy(item)

    def complete(
        self,
        task_id: str,
        worker_id: str,
        *,
        result_ref: str,
        result_payload: bytes,
        active_created_from_hash: str,
    ) -> dict[str, Any]:
        task_id = _text(task_id, "task_id")
        worker_id = _text(worker_id, "worker_id")
        result_ref = _text(result_ref, "result_ref")
        if not isinstance(result_payload, bytes):
            raise ContractError("result_payload must be bytes")
        self._assert_active_generation(active_created_from_hash)
        item = self._items.get(task_id)
        if item is None:
            raise ContractError(f"unknown Work Item: {task_id}")
        result_hash = hashlib.sha256(result_payload).hexdigest()
        if item["status"] == "succeeded":
            if (
                item["result_ref"] == result_ref
                and item["result_hash"] == result_hash
            ):
                return copy.deepcopy(item)
            raise ContractError("idempotent Work Item result conflicts with stored success")
        if item["status"] != "running" or item["lease_owner"] != worker_id:
            raise ContractError("only the running lease owner may complete a Work Item")
        work_idempotency_key(item)
        item["status"] = "succeeded"
        item["lease_owner"] = None
        item["result_ref"] = result_ref
        item["result_hash"] = result_hash
        item["failure_code"] = None
        self._lease_started_at.pop(task_id, None)
        self._refresh()
        return copy.deepcopy(item)

    def _apply_failure(self, item: dict[str, Any], failure_code: str) -> None:
        if failure_code not in FAILURE_CODES:
            raise ContractError(f"unknown failure code: {failure_code}")
        if item["status"] not in ACTIVE_STATUSES:
            raise ContractError("only active Work Items may fail")
        retryable = failure_code in set(
            item["timeout_policy"]["retryable_failure_codes"]
        )
        item["lease_owner"] = None
        item["result_ref"] = None
        item["result_hash"] = None
        item["failure_code"] = failure_code
        self._lease_started_at.pop(item["task_id"], None)
        if retryable and int(item["attempt"]) < int(
            self._policy["max_model_attempts_per_task"]
        ):
            item["status"] = "ready"
        elif failure_code == "required_evidence_missing":
            item["status"] = "needs_input"
        elif failure_code == "stale_revision":
            item["status"] = "superseded"
        elif failure_code == "cancelled_by_human":
            item["status"] = "cancelled"
        elif item["required"]:
            item["status"] = "deep_review_pending"
        else:
            item["status"] = "failed"

    def fail(
        self,
        task_id: str,
        worker_id: str,
        *,
        failure_code: str,
        active_created_from_hash: str,
    ) -> dict[str, Any]:
        task_id = _text(task_id, "task_id")
        worker_id = _text(worker_id, "worker_id")
        self._assert_active_generation(active_created_from_hash)
        item = self._items.get(task_id)
        if item is None:
            raise ContractError(f"unknown Work Item: {task_id}")
        if item["lease_owner"] != worker_id:
            raise ContractError("only the lease owner may fail a Work Item")
        self._apply_failure(item, failure_code)
        self._refresh()
        return copy.deepcopy(item)

    def expire(self, *, now: int) -> list[str]:
        now = _clock(now)
        expired: list[str] = []
        for task_id in sorted(self._items):
            item = self._items[task_id]
            if item["status"] not in ACTIVE_STATUSES:
                continue
            started_at = self._lease_started_at.get(task_id)
            if started_at is None:
                raise ContractError(f"active Work Item lacks lease time: {task_id}")
            if now - started_at < int(item["timeout_policy"]["timeout_seconds"]):
                continue
            self._apply_failure(item, "model_timeout")
            expired.append(task_id)
        self._refresh()
        return expired

    def cancel(self, task_id: str | None = None) -> list[str]:
        if task_id is None:
            targets = set(self._items)
        else:
            task_id = _text(task_id, "task_id")
            if task_id not in self._items:
                raise ContractError(f"unknown Work Item: {task_id}")
            targets = {task_id}
            changed = True
            while changed:
                changed = False
                for candidate in self._items.values():
                    if candidate["task_id"] in targets:
                        continue
                    if set(candidate["dependency_ids"]) & targets:
                        targets.add(candidate["task_id"])
                        changed = True
        cancelled: list[str] = []
        for target_id in sorted(targets):
            item = self._items[target_id]
            if item["status"] not in NONTERMINAL_STATUSES:
                continue
            item["status"] = "cancelled"
            item["lease_owner"] = None
            item["result_ref"] = None
            item["result_hash"] = None
            item["failure_code"] = "cancelled_by_human"
            self._lease_started_at.pop(target_id, None)
            cancelled.append(target_id)
        if task_id is None:
            self._graph["status"] = "cancelled"
        self._refresh()
        return cancelled

    def assess_budget(self, *, elapsed_seconds: int) -> dict[str, Any]:
        assessment = assess_work_budget(
            self._policy,
            self.work_items(),
            elapsed_seconds=elapsed_seconds,
        )
        if assessment["status"] != "ready":
            self._graph["status"] = assessment["status"]
        return assessment

    def checkpoint(
        self,
        *,
        sequence: int,
        previous_checkpoint_ref: str | None,
    ) -> dict[str, Any]:
        return build_work_checkpoint(
            self._graph,
            self.work_items(),
            sequence=sequence,
            previous_checkpoint_ref=previous_checkpoint_ref,
            lease_started_at_by_task=self._lease_started_at,
        )

    def semantic_result_manifest(self) -> dict[str, Any]:
        return {
            "created_from_hash": self._graph["created_from_hash"],
            "policy_release_id": self._graph["policy_release_id"],
            "task_results": [
                {
                    "task_id": item["task_id"],
                    "status": item["status"],
                    "result_ref": item["result_ref"],
                    "result_hash": item["result_hash"],
                    "failure_code": item["failure_code"],
                }
                for item in self.work_items()
            ],
        }
