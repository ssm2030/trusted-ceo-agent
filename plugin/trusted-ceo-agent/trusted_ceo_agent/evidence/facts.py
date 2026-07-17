from __future__ import annotations

import hashlib
from copy import deepcopy
from decimal import Decimal
from typing import Any, Mapping, Sequence

from trusted_ceo_agent.canonical import canonical_bytes, canonical_decimal
from trusted_ceo_agent.contracts.ids import fact_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


_UNKNOWN_MARKERS = {"unknown", "null", "n/a", "na", "not available"}


def _scope(value: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    result = sorted(
        ({"dimension_code": str(item["dimension_code"]), "member_code": str(item["member_code"])} for item in value),
        key=lambda item: (item["dimension_code"], item["member_code"]),
    )
    if len({(item["dimension_code"], item["member_code"]) for item in result}) != len(result):
        raise ContractError("Fact scope contains duplicate members")
    return result


def _time_context(value: Mapping[str, Any]) -> dict[str, Any]:
    if len(value) != 1 or next(iter(value), None) not in {"period", "as_of", "window"}:
        raise ContractError("Fact time_context requires exactly one of period, as_of, window")
    return deepcopy(dict(value))


def _fact_value(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    canonical = result.get("canonical_value")
    if isinstance(canonical, Decimal):
        canonical = canonical_decimal(canonical)
        result["canonical_value"] = canonical
    if isinstance(canonical, str) and canonical.strip().casefold() in _UNKNOWN_MARKERS:
        raise ContractError("unknown/null/n-a values are Quality issues, not Facts")
    if canonical is None:
        raise ContractError("Fact canonical_value cannot be null")
    return result


def _integrity(payload: Mapping[str, Any]) -> dict[str, str]:
    return {"payload_hash": hashlib.sha256(canonical_bytes(payload)).hexdigest()}


def build_observed_fact(
    *,
    fact_code: str,
    metric_code: str,
    semantic_role: str,
    observation_role: str,
    scope: Sequence[Mapping[str, str]],
    time_context: Mapping[str, Any],
    value: Mapping[str, Any],
    source_refs: Sequence[Mapping[str, Any]],
    quality_issue_ids: Sequence[str] = (),
) -> dict[str, Any]:
    refs = sorted((deepcopy(dict(item)) for item in source_refs), key=lambda item: (item["source_id"], item["extraction_hash"]))
    if not refs:
        raise ContractError("observed Fact requires Source references")
    normalized_scope = _scope(scope)
    normalized_time = _time_context(time_context)
    lineage_fingerprint = hashlib.sha256(canonical_bytes([
        {"source_id": item["source_id"], "observation_role": item["observation_role"], "lineage_set_ref": item["lineage_set_ref"]}
        for item in refs
    ])).hexdigest()
    identifier = fact_id("observed", fact_code, semantic_role, normalized_scope, normalized_time, lineage_fingerprint)
    body = {
        "fact_id": identifier,
        "fact_code": fact_code,
        "fact_type": "observed",
        "metric_code": metric_code,
        "semantic_role": semantic_role,
        "observation_role": observation_role,
        "scope": normalized_scope,
        "time_context": normalized_time,
        "value": _fact_value(value),
        "source_refs": refs,
        "derivation": None,
        "quality": sorted(set(quality_issue_ids)),
        "producer": "runtime_intake",
    }
    result = {**body, "integrity": _integrity(body)}
    SchemaStore().validate("fact.schema.json", result)
    return result


def build_calculated_fact(
    *,
    fact_type: str,
    fact_code: str,
    metric_code: str,
    semantic_role: str,
    observation_role: str,
    scope: Sequence[Mapping[str, str]],
    time_context: Mapping[str, Any],
    value: Mapping[str, Any],
    component_id: str,
    component_version: str,
    operation_code: str,
    formula_ref: str,
    parameter_hash: str,
    input_fact_ids: Sequence[str],
    component_run_id: str,
    source_refs: Sequence[Mapping[str, Any]] = (),
    quality_issue_ids: Sequence[str] = (),
) -> dict[str, Any]:
    if fact_type not in {"aggregated", "calculated"}:
        raise ContractError("deterministic Fact type must be aggregated or calculated")
    inputs = sorted(set(input_fact_ids))
    if not inputs:
        raise ContractError("deterministic Fact requires input Facts")
    normalized_scope = _scope(scope)
    normalized_time = _time_context(time_context)
    identifier = fact_id(fact_type, fact_code, semantic_role, normalized_scope, normalized_time)
    body = {
        "fact_id": identifier,
        "fact_code": fact_code,
        "fact_type": fact_type,
        "metric_code": metric_code,
        "semantic_role": semantic_role,
        "observation_role": observation_role,
        "scope": normalized_scope,
        "time_context": normalized_time,
        "value": _fact_value(value),
        "source_refs": sorted((deepcopy(dict(item)) for item in source_refs), key=lambda item: (item["source_id"], item["extraction_hash"])),
        "derivation": {
            "component_id": component_id,
            "component_version": component_version,
            "operation_code": operation_code,
            "formula_ref": formula_ref,
            "parameter_hash": parameter_hash,
            "input_fact_ids": inputs,
            "component_run_id": component_run_id,
        },
        "quality": sorted(set(quality_issue_ids)),
        "producer": "deterministic_component",
    }
    result = {**body, "integrity": _integrity(body)}
    SchemaStore().validate("fact.schema.json", result)
    return result

