from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.orchestration.graph import (
    CONCURRENCY_PROFILES,
    _native_integers,
)


OVERFLOW_ACTIONS = frozenset({
    "needs_prioritization", "needs_input", "deep_review_pending",
})
PROFILE_WORKER_LIMITS = {
    "sequential": 1,
    "parallel_2": 2,
    "parallel_3": 3,
    "parallel_4": 4,
}
BASELINE_EVIDENCE_LIMITS = {
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
EVIDENCE_LIMIT_FIELDS = frozenset(BASELINE_EVIDENCE_LIMITS)
POLICY_FIELDS = frozenset({
    "policy_id",
    "workload_class",
    "max_active_signal_cases",
    "max_parallel_workers",
    "max_model_attempts_per_task",
    "task_timeout",
    "case_timeout",
    "max_optional_issue_families",
    "evidence_packet_limits",
    "overflow_action",
    "benchmark_refs",
    "approved_concurrency_profile_id",
    "effective_from",
    "content_hash",
})


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{field} must be a non-empty string")
    return value


def _integer(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise ContractError(f"{field} must be an integer >= {minimum}")
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContractError(f"{field} must be an integer >= {minimum}")
    return value


def _string_set(values: Any, field: str) -> list[str]:
    if not isinstance(values, (list, tuple)):
        raise ContractError(f"{field} must be an array")
    normalized = [_text(value, field) for value in values]
    if len(normalized) != len(set(normalized)):
        raise ContractError(f"{field} contains duplicates")
    return sorted(normalized)


def _effective_from(value: Any) -> str:
    text = _text(value, "effective_from")
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ContractError("effective_from must be an ISO-8601 datetime") from error
    if parsed.tzinfo is None:
        raise ContractError("effective_from must include a timezone")
    return text


def _limits(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != EVIDENCE_LIMIT_FIELDS:
        raise ContractError("evidence_packet_limits fields do not match the contract")
    normalized: dict[str, int] = {}
    for key in sorted(EVIDENCE_LIMIT_FIELDS):
        limit = _integer(value[key], f"evidence_packet_limits.{key}", minimum=1)
        if limit > BASELINE_EVIDENCE_LIMITS[key]:
            raise ContractError(
                f"evidence_packet_limits.{key} exceeds the frozen baseline"
            )
        normalized[key] = limit
    return normalized


def _validate_body(body: Mapping[str, Any]) -> None:
    _text(body.get("policy_id"), "policy_id")
    _text(body.get("workload_class"), "workload_class")
    _integer(body.get("max_active_signal_cases"), "max_active_signal_cases", minimum=1)
    workers = _integer(body.get("max_parallel_workers"), "max_parallel_workers", minimum=1)
    attempts = _integer(
        body.get("max_model_attempts_per_task"),
        "max_model_attempts_per_task",
        minimum=1,
    )
    if attempts > 2:
        raise ContractError("max_model_attempts_per_task cannot exceed two")
    _integer(body.get("task_timeout"), "task_timeout", minimum=1)
    _integer(body.get("case_timeout"), "case_timeout", minimum=1)
    _integer(
        body.get("max_optional_issue_families"),
        "max_optional_issue_families",
    )
    _limits(body.get("evidence_packet_limits"))
    if body.get("overflow_action") not in OVERFLOW_ACTIONS:
        raise ContractError("overflow_action must preserve required work explicitly")
    _string_set(body.get("benchmark_refs"), "benchmark_refs")
    profile = body.get("approved_concurrency_profile_id")
    if profile not in CONCURRENCY_PROFILES:
        raise ContractError("approved_concurrency_profile_id is invalid")
    if workers > PROFILE_WORKER_LIMITS[str(profile)]:
        raise ContractError("max_parallel_workers exceeds the approved profile")
    _effective_from(body.get("effective_from"))


def build_work_budget_policy(
    *,
    policy_id: str,
    workload_class: str,
    max_active_signal_cases: int,
    max_parallel_workers: int,
    max_model_attempts_per_task: int,
    task_timeout: int,
    case_timeout: int,
    max_optional_issue_families: int,
    evidence_packet_limits: Mapping[str, Any],
    overflow_action: str,
    benchmark_refs: Sequence[str],
    approved_concurrency_profile_id: str,
    effective_from: str,
) -> dict[str, Any]:
    body = _native_integers({
        "policy_id": policy_id,
        "workload_class": workload_class,
        "max_active_signal_cases": max_active_signal_cases,
        "max_parallel_workers": max_parallel_workers,
        "max_model_attempts_per_task": max_model_attempts_per_task,
        "task_timeout": task_timeout,
        "case_timeout": case_timeout,
        "max_optional_issue_families": max_optional_issue_families,
        "evidence_packet_limits": _limits(evidence_packet_limits),
        "overflow_action": overflow_action,
        "benchmark_refs": _string_set(benchmark_refs, "benchmark_refs"),
        "approved_concurrency_profile_id": approved_concurrency_profile_id,
        "effective_from": effective_from,
    })
    _validate_body(body)
    policy = dict(body)
    policy["content_hash"] = _digest(body)
    SchemaStore().validate("work-budget-policy.schema.json", policy)
    return policy


def verify_work_budget_policy(policy: Mapping[str, Any]) -> None:
    normalized = _native_integers(dict(policy))
    if set(normalized) != POLICY_FIELDS:
        raise ContractError("WorkBudgetPolicy fields do not match the contract")
    body = {
        key: normalized[key] for key in normalized if key != "content_hash"
    }
    _validate_body(body)
    content_hash = normalized.get("content_hash")
    if not isinstance(content_hash, str) or content_hash != _digest(body):
        raise ContractError("WorkBudgetPolicy content hash mismatch")
    SchemaStore().validate("work-budget-policy.schema.json", normalized)


def assess_work_budget(
    policy: Mapping[str, Any],
    work_items: Sequence[Mapping[str, Any]],
    *,
    elapsed_seconds: int,
) -> dict[str, Any]:
    verify_work_budget_policy(policy)
    policy = _native_integers(dict(policy))
    elapsed = _integer(elapsed_seconds, "elapsed_seconds")
    items = sorted(
        (dict(item) for item in work_items),
        key=lambda item: str(item.get("task_id", "")),
    )
    if not items:
        raise ContractError("budget assessment requires Work Items")

    unfinished = [
        item for item in items
        if item.get("status") not in {
            "succeeded", "failed", "cancelled", "superseded",
            "needs_input", "deep_review_pending",
        }
    ]
    required = sorted(
        str(item["task_id"]) for item in unfinished if item.get("required") is True
    )
    optional = [item for item in unfinished if item.get("required") is False]
    optional_families = sorted({
        _text(item.get("issue_family"), "issue_family") for item in optional
    })
    selected_families = set(
        optional_families[: int(policy["max_optional_issue_families"])]
    )
    selected_optional = sorted(
        str(item["task_id"])
        for item in optional
        if item["issue_family"] in selected_families
    )
    deferred_optional = sorted(
        str(item["task_id"])
        for item in optional
        if item["issue_family"] not in selected_families
    )

    overflow = elapsed >= int(policy["case_timeout"]) and bool(required)
    if overflow:
        scheduled: list[str] = []
        deferred_optional = sorted(str(item["task_id"]) for item in optional)
        status = str(policy["overflow_action"])
    else:
        scheduled = sorted(required + selected_optional)
        status = "ready"
    coverage_records = [
        {
            "task_id": task_id,
            "reason": "optional_budget_deferred",
        }
        for task_id in deferred_optional
    ]
    return {
        "status": status,
        "required_task_ids": required,
        "scheduled_task_ids": scheduled,
        "deferred_optional_task_ids": deferred_optional,
        "coverage_records": coverage_records,
    }
