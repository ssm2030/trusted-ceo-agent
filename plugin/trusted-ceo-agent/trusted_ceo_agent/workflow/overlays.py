from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from trusted_ceo_agent.errors import ContractError


ALLOWED: dict[str, tuple[str, ...]] = {
    "context": (
        "/mission_contract/business_question", "/mission_contract/customer_hypotheses",
        "/mission_contract/decision_context", "/mission_contract/analysis_horizon",
        "/mission_contract/priority_dimensions", "/mission_contract/recent_business_changes",
        "/mission_contract/included_scopes", "/mission_contract/excluded_scopes",
    ),
    "data": (
        "/mapping/columns/*/observation_role", "/mapping/columns/*/unit_code",
        "/mapping/columns/*/scale", "/mapping/columns/*/time_role",
        "/mapping/columns/*/dimension_code", "/mapping/sources/*/included",
    ),
    "scope_narrowing": (
        "/scope_narrowing/included_scope_keys", "/scope_narrowing/excluded_scope_keys",
        "/scope_narrowing/blind_spot_reason_codes", "/scope_narrowing/estimated_card_count",
    ),
    "diagnostic": (
        "/issue_dispositions/*", "/decision_dispositions/*", "/verification_authorizations/*",
        "/issue_groups/*", "/materiality_context/*", "/requested_counter_checks/*",
        "/deep_dive_scope/component_ids", "/deep_dive_scope/issue_ids",
    ),
    "final": (
        "/response_dispositions/*", "/expert_routing/*", "/ceo_wording/*", "/delivery_scope/*",
    ),
}


def _segments(pointer: str) -> list[str]:
    if not isinstance(pointer, str) or not pointer.startswith("/") or pointer == "/":
        raise ContractError(f"invalid JSON Pointer: {pointer}")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def _matches(pointer: str, pattern: str) -> bool:
    actual = _segments(pointer)
    expected = _segments(pattern)
    return len(actual) == len(expected) and all(wanted == "*" or wanted == got for got, wanted in zip(actual, expected))


def _permitted(gate: str, pointer: str) -> bool:
    return any(_matches(pointer, pattern) for pattern in ALLOWED.get(gate, ()))


def _parent(document: dict[str, Any], parts: list[str], *, create: bool) -> tuple[dict[str, Any], str]:
    current = document
    for part in parts[:-1]:
        child = current.get(part)
        if child is None and create:
            child = {}
            current[part] = child
        if not isinstance(child, dict):
            raise ContractError("overlay pointer traverses a non-object")
        current = child
    return current, parts[-1]


def _validate_scope(document: Mapping[str, Any], runtime_context: Mapping[str, Any]) -> None:
    scope = document.get("scope_narrowing")
    if not isinstance(scope, dict):
        raise ContractError("scope_narrowing overlay is missing")
    included = scope.get("included_scope_keys")
    excluded = scope.get("excluded_scope_keys")
    reasons = scope.get("blind_spot_reason_codes")
    estimated = scope.get("estimated_card_count")
    if not isinstance(included, list) or included != sorted(set(included)):
        raise ContractError("included_scope_keys must be a sorted set")
    if not isinstance(excluded, list) or excluded != sorted(set(excluded)):
        raise ContractError("excluded_scope_keys must be a sorted set")
    if set(included) & set(excluded):
        raise ContractError("included and excluded scopes must be disjoint")
    if not isinstance(reasons, dict) or not set(excluded).issubset(reasons):
        raise ContractError("every excluded scope needs a blind spot reason")
    recomputed = runtime_context.get("estimated_card_count")
    if not isinstance(recomputed, int) or estimated != recomputed or estimated > 6:
        raise ContractError("scope card count is stale or exceeds six")


def _validate_context_value(pointer: str, value: Any) -> None:
    if pointer == "/mission_contract/business_question":
        if not isinstance(value, str) or not value.strip():
            raise ContractError("mission business_question overlay must be a non-empty string")
        return
    if pointer == "/mission_contract/decision_context":
        if not isinstance(value, str):
            raise ContractError("mission decision_context overlay must be a string")
        return
    if pointer == "/mission_contract/analysis_horizon":
        if not isinstance(value, dict) or set(value) != {"start", "end"}:
            raise ContractError("mission analysis_horizon overlay must contain start and end")
        if not all(isinstance(value[key], str) and value[key] for key in ("start", "end")):
            raise ContractError("mission analysis_horizon dates must be strings")
        return
    if pointer == "/mission_contract/customer_hypotheses":
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise ContractError("mission customer_hypotheses overlay must be an object list")
        return
    if pointer.startswith("/mission_contract/"):
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ContractError(f"mission list overlay must contain strings: {pointer}")
        if len(value) != len(set(value)):
            raise ContractError(f"mission list overlay must be unique: {pointer}")


def apply_overlay(
    base_overlay: Mapping[str, Any],
    gate: str,
    operations: Sequence[Mapping[str, Any]],
    *,
    runtime_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if gate not in ALLOWED:
        raise ContractError(f"unsupported HITL gate: {gate}")
    result = copy.deepcopy(dict(base_overlay))
    for operation in operations:
        op = operation.get("op")
        pointer = operation.get("path")
        if op not in {"add", "replace", "test"}:
            raise ContractError("only add, replace, and test overlay operations are allowed")
        if not isinstance(pointer, str) or not _permitted(gate, pointer):
            raise ContractError(f"overlay path is forbidden for {gate}: {pointer}")
        if gate == "context" and op != "test":
            _validate_context_value(pointer, operation.get("value"))
        parts = _segments(pointer)
        parent, key = _parent(result, parts, create=op == "add")
        if op == "test":
            if key not in parent or parent[key] != operation.get("value"):
                raise ContractError(f"overlay test failed: {pointer}")
        elif op == "replace":
            if key not in parent:
                raise ContractError(f"overlay replace target does not exist: {pointer}")
            parent[key] = copy.deepcopy(operation.get("value"))
        else:
            parent[key] = copy.deepcopy(operation.get("value"))
    if gate == "scope_narrowing":
        _validate_scope(result, dict(runtime_context or {}))
    return result


def invalidated_gates(changed_paths: Sequence[str]) -> set[str]:
    invalidated: set[str] = set()
    for path in changed_paths:
        if path.startswith(("/sources", "/mapping", "/fact", "/signal", "/mission_contract", "/scope_narrowing", "/pack", "/component")):
            invalidated.update({"diagnostic", "deep_authorization", "final"})
        elif path.startswith(("/issue_dispositions", "/decision_dispositions", "/verification_authorizations", "/issue_groups", "/deep_dive_scope")):
            invalidated.update({"deep_authorization", "final"})
        elif path.startswith(("/response_dispositions", "/expert_routing", "/ceo_wording", "/delivery_scope")):
            invalidated.add("final")
    return invalidated
