from __future__ import annotations

import hashlib
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


_POLICY_PATH = "workflow/human-response-policy.json"
_SOURCE_REGISTRY_PATH = "sources/registry.json"


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _native_numbers(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value != value.to_integral_value():
            raise ContractError("Human Response policy contains a non-integral number")
        return int(value)
    if isinstance(value, dict):
        return {key: _native_numbers(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_native_numbers(child) for child in value]
    return value


def _object_from_bytes(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = strict_loads(payload)
    except (UnicodeError, ValueError) as error:
        raise ContractError(f"{label} is invalid") from error
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be an object")
    return _native_numbers(value)


def verify_human_response_policy(policy: Mapping[str, Any]) -> None:
    value = dict(policy)
    SchemaStore().validate("human-response-policy.schema.json", value)
    supplied_hash = value.pop("policy_hash")
    if _hash(value) != supplied_hash:
        raise ContractError("Human Response policy hash is invalid")
    actor_ids = [actor["actor_id"] for actor in value["authorized_actors"]]
    if len(actor_ids) != len(set(actor_ids)):
        raise ContractError("Human Response policy actor IDs must be unique")


def verify_human_response_policy_decision(decision: Mapping[str, Any]) -> None:
    value = dict(decision)
    supplied_hash = value.pop("decision_hash", None)
    if _hash(value) != supplied_hash:
        raise ContractError("Human Response policy decision hash is invalid")
    SchemaStore().validate("human-response-policy-decision.schema.json", dict(decision))


def _response_is_bound(
    action: Mapping[str, Any],
    normalized_response: Mapping[str, Any],
    response_record: Mapping[str, Any],
) -> bool:
    return (
        response_record.get("action_id") == action.get("action_id")
        and response_record.get("action_content_hash") == action.get("content_hash")
        and response_record.get("response_type") == normalized_response.get("response_type")
        and response_record.get("payload") == normalized_response.get("payload")
        and response_record.get("actor_id") == normalized_response.get("actor_id")
    )


def _source_refs(normalized_response: Mapping[str, Any]) -> tuple[list[str], bool]:
    payload = normalized_response.get("payload")
    if not isinstance(payload, Mapping):
        return [], False
    raw_refs = payload.get("source_refs")
    if raw_refs is None:
        return [], True
    if (
        not isinstance(raw_refs, list)
        or any(not isinstance(item, str) or not item for item in raw_refs)
        or len(raw_refs) != len(set(raw_refs))
    ):
        return [], False
    return sorted(raw_refs), True


def _source_policy_reasons(
    files: Mapping[str, bytes],
    source_refs: list[str],
    restricted_allowlist: set[str],
) -> set[str]:
    if not source_refs:
        return set()
    payload = files.get(_SOURCE_REGISTRY_PATH)
    if payload is None:
        return {"source_registry_missing"}
    try:
        registry = strict_loads(payload)
    except (UnicodeError, ValueError):
        return {"source_registry_invalid"}
    if not isinstance(registry, list):
        return {"source_registry_invalid"}
    by_id: dict[str, str] = {}
    for item in registry:
        if not isinstance(item, dict):
            return {"source_registry_invalid"}
        source_id = item.get("source_id")
        access_policy = item.get("access_policy")
        if (
            not isinstance(source_id, str)
            or access_policy not in {"permitted", "restricted", "prohibited"}
            or source_id in by_id
        ):
            return {"source_registry_invalid"}
        by_id[source_id] = access_policy
    reasons: set[str] = set()
    for source_id in source_refs:
        access_policy = by_id.get(source_id)
        if access_policy is None:
            reasons.add("source_not_registered")
        elif access_policy == "prohibited":
            reasons.add("source_prohibited")
        elif access_policy == "restricted" and source_id not in restricted_allowlist:
            reasons.add("source_restricted_not_allowlisted")
    return reasons


def evaluate_human_response_policy(
    *,
    files: Mapping[str, bytes],
    action: Mapping[str, Any],
    normalized_response: Mapping[str, Any],
    response_record: Mapping[str, Any],
    trusted_principal: Mapping[str, Any],
    created_at: str,
) -> dict[str, Any]:
    """Return an immutable authorization decision; absence or ambiguity denies."""

    policy_payload = files.get(_POLICY_PATH)
    if policy_payload is None:
        raise ContractError("Human Response policy is missing")
    policy = _object_from_bytes(policy_payload, label="Human Response policy")
    verify_human_response_policy(policy)

    action_id = action.get("action_id")
    action_hash = action.get("content_hash")
    gate = action.get("gate")
    response_id = response_record.get("response_id")
    actor_id = normalized_response.get("actor_id")
    if (
        not isinstance(action_id, str)
        or not isinstance(action_hash, str)
        or not isinstance(gate, str)
        or not isinstance(response_id, str)
        or not isinstance(actor_id, str)
    ):
        raise ContractError("Human Response policy evaluation inputs are invalid")

    subject = trusted_principal.get("subject")
    principal_roles = trusted_principal.get("roles")
    transport_subject = subject if isinstance(subject, str) and subject else "<invalid>"
    roles = (
        {item for item in principal_roles if isinstance(item, str) and item}
        if isinstance(principal_roles, list)
        else set()
    )
    reasons: set[str] = set()
    if set(trusted_principal) != {"subject", "roles"} or subject != policy["transport_principal"]:
        reasons.add("transport_principal_mismatch")

    authorized_actor = next(
        (
            candidate
            for candidate in policy["authorized_actors"]
            if candidate["actor_id"] == actor_id
        ),
        None,
    )
    if authorized_actor is None:
        reasons.add("actor_not_authorized")
    else:
        if not roles.intersection(authorized_actor["roles"]):
            reasons.add("transport_role_not_authorized")
        if gate not in authorized_actor["allowed_gates"]:
            reasons.add("gate_not_authorized")

    if not _response_is_bound(action, normalized_response, response_record):
        reasons.add("response_binding_mismatch")
    source_refs, source_refs_valid = _source_refs(normalized_response)
    if not source_refs_valid:
        reasons.add("response_binding_mismatch")
    reasons.update(_source_policy_reasons(
        files,
        source_refs,
        set(policy["restricted_source_allowlist"]),
    ))

    allowed = not reasons
    decision: dict[str, Any] = {
        "schema_version": "1.0.0",
        "policy_id": policy["policy_id"],
        "policy_version": policy["policy_version"],
        "policy_hash": policy["policy_hash"],
        "action_id": action_id,
        "response_id": response_id,
        "gate": gate,
        "actor_id": actor_id,
        "transport_subject": transport_subject,
        "allowed": allowed,
        "reason_codes": ["authorized"] if allowed else sorted(reasons),
        "evaluated_source_refs": source_refs,
        "created_at": created_at,
    }
    decision["decision_hash"] = _hash(decision)
    verify_human_response_policy_decision(decision)
    return decision
