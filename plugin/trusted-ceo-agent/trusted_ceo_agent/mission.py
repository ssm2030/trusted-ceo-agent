from __future__ import annotations

import hashlib
import hmac
from copy import deepcopy
from collections.abc import Mapping
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


CONTEXT_EDITABLE_FIELDS = frozenset({
    "business_question",
    "customer_hypotheses",
    "decision_context",
    "analysis_horizon",
    "priority_dimensions",
    "recent_business_changes",
    "included_scopes",
    "excluded_scopes",
})


def is_confirmed_mission(mission: Mapping[str, Any]) -> bool:
    confirmation = mission.get("confirmation")
    return isinstance(confirmation, Mapping) and confirmation.get("confirmed") is True


def mission_contract_hash(mission: Mapping[str, Any]) -> str:
    body = dict(mission)
    body.pop("confirmation", None)
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def validate_confirmed_mission(mission: Mapping[str, Any]) -> None:
    if not is_confirmed_mission(mission):
        raise ContractError("Mission Contract has not been confirmed")
    SchemaStore().validate("mission-contract.schema.json", dict(mission))
    confirmation = mission["confirmation"]
    supplied = str(confirmation.get("contract_hash", ""))
    expected = mission_contract_hash(mission)
    if not hmac.compare_digest(supplied, expected):
        raise ContractError("Mission Contract hash does not cover the confirmed contract body")


def materialize_confirmed_mission(
    base_mission: Mapping[str, Any],
    overlay: Mapping[str, Any],
    *,
    actor_id: str,
    actor_role: str,
    confirmed_at: str,
) -> dict[str, Any]:
    if not actor_id or not actor_role or not confirmed_at:
        raise ContractError("Context confirmation metadata is incomplete")
    edits = overlay.get("mission_contract", {})
    if not isinstance(edits, Mapping):
        raise ContractError("Context overlay mission_contract must be an object")
    forbidden = set(edits) - CONTEXT_EDITABLE_FIELDS
    if forbidden:
        raise ContractError(f"Context overlay contains forbidden Mission fields: {sorted(forbidden)}")
    body = deepcopy(dict(base_mission))
    body.pop("confirmation", None)
    for key, value in edits.items():
        body[str(key)] = deepcopy(value)
    confirmation = {
        "confirmed": True,
        "actor_id": actor_id,
        "actor_role": actor_role,
        "confirmed_at": confirmed_at,
        "contract_hash": hashlib.sha256(canonical_bytes(body)).hexdigest(),
    }
    mission = {**body, "confirmation": confirmation}
    validate_confirmed_mission(mission)
    return mission
