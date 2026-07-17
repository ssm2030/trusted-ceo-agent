from __future__ import annotations

import hashlib
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.mission import is_confirmed_mission, validate_confirmed_mission
from trusted_ceo_agent.workflow.human_actions import verify_action_card
from trusted_ceo_agent.workflow.human_response_policy import (
    verify_human_response_policy,
    verify_human_response_policy_decision,
)


def _load(payload: bytes, *, label: str) -> Any:
    try:
        return _native_numbers(strict_loads(payload))
    except (UnicodeError, ValueError) as error:
        raise ContractError(f"snapshot {label} is invalid JSON") from error


def _native_numbers(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value != value.to_integral_value():
            return value
        return int(value)
    if isinstance(value, dict):
        return {key: _native_numbers(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_native_numbers(child) for child in value]
    return value


def _object(payload: bytes, *, label: str) -> dict[str, Any]:
    value = _load(payload, label=label)
    if not isinstance(value, dict):
        raise ContractError(f"snapshot {label} must be an object")
    return value


def _verify_resolution(value: Mapping[str, Any], schemas: SchemaStore) -> None:
    document = dict(value)
    schemas.validate("human-action-resolution.schema.json", document)
    claimed = document.pop("resolution_hash")
    actual = hashlib.sha256(canonical_bytes(document)).hexdigest()
    if claimed != actual:
        raise ContractError("Human Action resolution hash is invalid")


def validate_snapshot_files(files: Mapping[str, bytes]) -> None:
    """Validate every recognized canonical contract before an atomic publish."""

    schemas = SchemaStore()
    state_payload = files.get("workflow/state.json")
    if state_payload is None:
        raise ContractError("workflow state is missing")
    state = _object(state_payload, label="workflow state")
    if (
        not isinstance(state.get("run_id"), str)
        or not isinstance(state.get("revision"), int)
        or not isinstance(state.get("state"), str)
    ):
        raise ContractError("workflow state contract is invalid")

    mission_payload = files.get("mission/effective-mission-contract.json")
    if mission_payload is None:
        mission_payload = files.get("mission/mission-contract.json")
    if mission_payload is not None:
        mission = _object(mission_payload, label="Mission Contract")
        if is_confirmed_mission(mission):
            validate_confirmed_mission(mission)

    policy_payload = files.get("workflow/human-response-policy.json")
    if policy_payload is None:
        raise ContractError("Human Response policy is missing")
    verify_human_response_policy(_object(policy_payload, label="Human Response policy"))

    registry_payload = files.get("sources/registry.json")
    if registry_payload is not None:
        registry = _load(registry_payload, label="Source Registry")
        if not isinstance(registry, list):
            raise ContractError("Source Registry must be an array")
        for source in registry:
            schemas.validate("source.schema.json", source)

    exact_contracts = {
        "packs/manifest.json": "pack-manifest.schema.json",
        "evidence/core.json": "evidence-core.schema.json",
        "workflow/hitl-overlay.json": "hitl-overlay.schema.json",
        "final/result.json": "final-result.schema.json",
    }
    for path, schema_name in exact_contracts.items():
        if path in files:
            schemas.validate(schema_name, _load(files[path], label=path))

    responses: dict[str, dict[str, Any]] = {}
    receipts: dict[str, dict[str, Any]] = {}
    actions: dict[str, dict[str, Any]] = {}
    for path, payload in sorted(files.items()):
        if path == "workflow/pending-action.json" or (
            path.startswith("workflow/actions/") and path.endswith(".json")
        ):
            action = _object(payload, label=path)
            verify_action_card(action)
            actions[str(action["action_id"])] = action
            if path == "workflow/pending-action.json":
                if action["base_revision"] != state["revision"]:
                    raise ContractError("pending Human Action revision is stale")
                if action["workflow_state"] != state["state"]:
                    raise ContractError("pending Human Action state is stale")
        elif path.startswith("workflow/human-responses/") and path.endswith(".json"):
            response = _object(payload, label=path)
            schemas.validate("human-response.schema.json", response)
            responses[str(response["response_id"])] = response
        elif path.startswith("workflow/human-response-receipts/") and path.endswith(".json"):
            receipt = _object(payload, label=path)
            schemas.validate("human-response-receipt.schema.json", receipt)
            receipts[str(receipt["response_id"])] = receipt
        elif path.startswith("workflow/human-response-policy-decisions/") and path.endswith(".json"):
            verify_human_response_policy_decision(_object(payload, label=path))
        elif path == "workflow/human-action-resolution.json":
            _verify_resolution(_object(payload, label=path), schemas)
        elif path.startswith("approvals/records/") and path.endswith(".json"):
            schemas.validate("approval.schema.json", _load(payload, label=path))
        elif path.startswith("approvals/requests/") and path.endswith(".json"):
            schemas.validate("approval-request.schema.json", _load(payload, label=path))
        elif path.startswith("components/runs/") and path.endswith(".json"):
            schemas.validate("component-run.schema.json", _load(payload, label=path))
        elif path.startswith("grading/records/") and path.endswith(".json"):
            schemas.validate("grade-record.schema.json", _load(payload, label=path))

    if set(responses) != set(receipts):
        raise ContractError("Human Response records and receipts are inconsistent")
    for response_id, receipt in receipts.items():
        response = responses[response_id]
        if response["response_hash"] != receipt["response_hash"]:
            raise ContractError("Human Response receipt hash is inconsistent")
        if response["action_id"] != receipt["action_id"]:
            raise ContractError("Human Response receipt action is inconsistent")

    grading_payload = files.get("grading/inputs.json")
    if grading_payload is not None:
        grading_inputs = _load(grading_payload, label="grading/inputs.json")
        if not isinstance(grading_inputs, list):
            raise ContractError("grading inputs must be an array")
        for grading_input in grading_inputs:
            schemas.validate("grading-input.schema.json", grading_input)
