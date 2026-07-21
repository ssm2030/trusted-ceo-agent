from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from trusted_ceo_agent.application.models import MutationRequest
from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.errors import ContractError


GATES = ("context", "data", "scope_narrowing", "diagnostic", "final")

SUPPORTED_MUTATIONS = frozenset({
    "scan",
    "run-components",
    "prepare-finalization",
    "prepare-jobs",
    "ingest-result",
    "reduce-stage",
    "approval-request",
    "approve-web",
    "decide-web",
    "resume",
    "stop",
    "cancel",
    "finalize",
})

_PARAMETER_CONTRACTS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "scan": (frozenset(), frozenset()),
    "run-components": (
        frozenset({"scope_ref"}),
        frozenset({"accounting_input", "professional_input"}),
    ),
    "prepare-finalization": (frozenset(), frozenset()),
    "prepare-jobs": (frozenset({"stage"}), frozenset()),
    "ingest-result": (
        frozenset({"job_id", "draft_document"}),
        frozenset({"draft_source"}),
    ),
    "reduce-stage": (frozenset({"stage"}), frozenset()),
    "approval-request": (
        frozenset({"gate", "overlay_document"}),
        frozenset(),
    ),
    "approve-web": (
        frozenset({
            "request_id",
            "actor_id",
            "actor_role",
            "nonce",
            "rationale",
            "browser_session_fingerprint",
            "response_hash",
        }),
        frozenset(),
    ),
    "decide-web": (
        frozenset({
            "request_id",
            "decision",
            "actor_id",
            "actor_role",
            "nonce",
            "rationale",
            "browser_session_fingerprint",
            "response_hash",
            "change_scope",
        }),
        frozenset(),
    ),
    "resume": (frozenset(), frozenset()),
    "stop": (frozenset(), frozenset()),
    "cancel": (frozenset(), frozenset()),
    "finalize": (frozenset(), frozenset()),
}


class _DocumentPayload:
    def __init__(self, value: Any, *, label: str) -> None:
        if isinstance(value, bytes):
            self._payload = value
            return
        if not isinstance(value, Mapping):
            raise ContractError(f"{label} must be an object or JSON bytes")
        try:
            parsed = strict_loads(json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ))
            self._payload = canonical_bytes(parsed)
        except (TypeError, ValueError) as error:
            raise ContractError(f"{label} is not valid JSON") from error

    def read_bytes(self) -> bytes:
        return self._payload


def _validated_parameters(request: MutationRequest) -> dict[str, Any]:
    if request.command not in SUPPORTED_MUTATIONS:
        raise ContractError(f"unsupported mutation command: {request.command}")
    if not isinstance(request.parameters, Mapping):
        raise ContractError("mutation parameters must be an object")
    if any(not isinstance(key, str) for key in request.parameters):
        raise ContractError("mutation parameter names must be strings")
    required, optional = _PARAMETER_CONTRACTS[request.command]
    supplied = frozenset(request.parameters)
    missing = sorted(required - supplied)
    if missing:
        raise ContractError(
            f"missing required parameters for {request.command}: {', '.join(missing)}"
        )
    unexpected = sorted(supplied - required - optional)
    if unexpected:
        raise ContractError(
            f"unexpected parameters for {request.command}: {', '.join(unexpected)}"
        )
    values = dict(request.parameters)
    document_parameters = {"draft_document", "overlay_document"}
    for key in sorted(required - document_parameters - {"change_scope"}):
        value = values[key]
        if not isinstance(value, str) or not value.strip():
            raise ContractError(f"{key} must be a non-empty string")
    change_scope = values.get("change_scope")
    if change_scope is not None and (
        not isinstance(change_scope, str) or not change_scope.strip()
    ):
        raise ContractError("change_scope must be null or a non-empty string")
    for key in ("accounting_input", "professional_input"):
        value = values.get(key)
        if value is not None and not isinstance(value, Path):
            raise ContractError(f"{key} must be a filesystem path or null")
    stage = values.get("stage")
    if "stage" in values and stage not in {
        "schema_mapping", "lens", "integrated", "deep_dive", "writer",
    }:
        raise ContractError(f"unsupported stage: {stage}")
    gate = values.get("gate")
    if "gate" in values and gate not in GATES:
        raise ContractError(f"unsupported approval gate: {gate}")
    decision = values.get("decision")
    if "decision" in values and decision not in {"request_changes", "reject"}:
        raise ContractError(f"unsupported web decision: {decision}")
    draft_source = values.get("draft_source")
    if draft_source is not None and draft_source not in {
        "model_draft",
        "deterministic_canonical",
    }:
        raise ContractError(f"unsupported draft source: {draft_source}")
    return values
DocumentPayload = _DocumentPayload
validate_parameters = _validated_parameters
