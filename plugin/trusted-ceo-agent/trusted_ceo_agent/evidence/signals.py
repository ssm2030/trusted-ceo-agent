from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from trusted_ceo_agent.contracts.ids import signal_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


def build_signal(
    *,
    signal_code: str,
    rule_ref: str,
    component_id: str,
    component_version: str,
    component_run_id: str,
    threshold_ref: str | None,
    input_fact_ids: Sequence[str],
    required_fact_codes: Sequence[str],
    missing_fact_codes: Sequence[str],
    scope: Sequence[Mapping[str, str]],
    time_context: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    outcome: str,
    direction: str | None = None,
    impact_band_candidate: str | None = None,
    urgency_band_candidate: str | None = None,
    reason_codes: Sequence[str] = (),
) -> dict[str, Any]:
    if outcome not in {"triggered", "not_triggered", "not_assessable"}:
        raise ContractError(f"invalid Signal outcome: {outcome}")
    missing = sorted(set(missing_fact_codes))
    reasons = sorted(set(reason_codes))
    if outcome == "not_assessable" and not (missing or reasons):
        raise ContractError("not_assessable Signal requires missing Facts or a reason")
    normalized_scope = sorted(
        ({"dimension_code": str(item["dimension_code"]), "member_code": str(item["member_code"])} for item in scope),
        key=lambda item: (item["dimension_code"], item["member_code"]),
    )
    normalized_time = deepcopy(dict(time_context))
    identity = {
        "signal_code": signal_code,
        "rule_ref": rule_ref,
        "component_version": component_version,
        "scope": normalized_scope,
        "time_context": normalized_time,
        "threshold_ref": threshold_ref,
    }
    result = {
        "signal_id": signal_id(identity),
        "signal_code": signal_code,
        "rule_ref": rule_ref,
        "component_ref": {"component_id": component_id, "component_version": component_version, "component_run_id": component_run_id},
        "threshold_ref": threshold_ref,
        "input_fact_ids": sorted(set(input_fact_ids)),
        "required_fact_codes": sorted(set(required_fact_codes)),
        "missing_fact_codes": missing,
        "scope": normalized_scope,
        "time_context": normalized_time,
        "evaluation": deepcopy(dict(evaluation)),
        "outcome": outcome,
        "direction": direction,
        "impact_band_candidate": impact_band_candidate,
        "urgency_band_candidate": urgency_band_candidate,
        "reason_codes": reasons,
        "producer": "deterministic_component",
    }
    SchemaStore().validate("signal.schema.json", result)
    return result

