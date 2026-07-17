from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from trusted_ceo_agent.canonical import canonical_bytes, canonical_decimal
from trusted_ceo_agent.components.models import NotAssessable
from trusted_ceo_agent.contracts.ids import fact_id, signal_id


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _fact_by_id(facts: Sequence[Mapping[str, Any]], requested_id: str) -> Mapping[str, Any]:
    for fact in facts:
        if fact.get("fact_id") == requested_id:
            return fact
    raise NotAssessable("missing_input_fact")


def _facts_by_code(facts: Sequence[Mapping[str, Any]], fact_code: str) -> list[Mapping[str, Any]]:
    selected = [fact for fact in facts if fact.get("fact_code") == fact_code]
    if not selected:
        raise NotAssessable("missing_input_fact")
    return sorted(selected, key=lambda item: str(item.get("fact_id", "")))


def _value_body(fact: Mapping[str, Any]) -> Mapping[str, Any]:
    body = fact.get("value")
    if not isinstance(body, Mapping):
        raise NotAssessable("invalid_fact_value")
    return body


def _decimal(fact: Mapping[str, Any]) -> Decimal:
    body = _value_body(fact)
    if body.get("value_type") not in {"decimal", "integer"}:
        raise NotAssessable("numeric_value_required")
    try:
        value = Decimal(str(body["canonical_value"]))
    except (KeyError, InvalidOperation) as error:
        raise NotAssessable("invalid_fact_value") from error
    if not value.is_finite():
        raise NotAssessable("invalid_fact_value")
    return value


def _date(fact: Mapping[str, Any]) -> date:
    body = _value_body(fact)
    if body.get("value_type") != "date":
        raise NotAssessable("date_value_required")
    try:
        return date.fromisoformat(str(body["canonical_value"]))
    except (KeyError, ValueError) as error:
        raise NotAssessable("invalid_date_value") from error


def _unit(fact: Mapping[str, Any]) -> str | None:
    return _value_body(fact).get("unit_code")


def _same_units(facts: Sequence[Mapping[str, Any]]) -> str | None:
    units = {_unit(fact) for fact in facts}
    if len(units) != 1:
        raise NotAssessable("unit_mismatch")
    return next(iter(units))


def _scope(facts: Sequence[Mapping[str, Any]], parameters: Mapping[str, Any]) -> list[dict[str, str]]:
    if "scope" in parameters:
        return [dict(item) for item in parameters["scope"]]
    scopes = {canonical_bytes(fact.get("scope", [])).decode("utf-8") for fact in facts}
    if len(scopes) != 1:
        raise NotAssessable("scope_mismatch")
    return [dict(item) for item in facts[0].get("scope", [])]


def _common_scope(facts: Sequence[Mapping[str, Any]], parameters: Mapping[str, Any]) -> list[dict[str, str]]:
    if "scope" in parameters:
        return [dict(item) for item in parameters["scope"]]
    common = {
        (str(item["dimension_code"]), str(item["member_code"]))
        for item in facts[0].get("scope", [])
    }
    for fact in facts[1:]:
        common &= {
            (str(item["dimension_code"]), str(item["member_code"]))
            for item in fact.get("scope", [])
        }
    return [{"dimension_code": d, "member_code": m} for d, m in sorted(common)]


def _time_context(facts: Sequence[Mapping[str, Any]], parameters: Mapping[str, Any]) -> dict[str, Any]:
    if "time_context" in parameters:
        return dict(parameters["time_context"])
    contexts = {canonical_bytes(fact.get("time_context", {})).decode("utf-8") for fact in facts}
    if len(contexts) != 1:
        raise NotAssessable("time_context_mismatch")
    return dict(facts[0].get("time_context", {}))


def _source_refs(facts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_bytes: dict[bytes, dict[str, Any]] = {}
    for fact in facts:
        for source_ref in fact.get("source_refs", []):
            encoded = canonical_bytes(source_ref)
            by_bytes[encoded] = dict(source_ref)
    return [by_bytes[key] for key in sorted(by_bytes)]


def _quality(facts: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted({str(item) for fact in facts for item in fact.get("quality", [])})


def _make_fact(
    *,
    inputs: Sequence[Mapping[str, Any]],
    component_id: str,
    component_version: str,
    component_run_id: str,
    parameter_hash: str,
    fact_code: str,
    metric_code: str,
    value: Decimal,
    unit_code: str | None,
    scope: Sequence[Mapping[str, str]],
    time_context: Mapping[str, Any],
    operation_code: str,
    formula_ref: str,
    fact_type: str = "calculated",
) -> dict[str, Any]:
    input_ids = sorted(str(fact["fact_id"]) for fact in inputs)
    value_body = {
        "value_type": "decimal",
        "canonical_value": canonical_decimal(value),
        "unit_code": unit_code,
        "currency_code": "KRW" if unit_code == "KRW" else None,
        "scale": "1",
    }
    body: dict[str, Any] = {
        "fact_code": fact_code,
        "fact_type": fact_type,
        "metric_code": metric_code,
        "semantic_role": "calculated",
        "observation_role": "derived",
        "scope": [dict(item) for item in scope],
        "time_context": dict(time_context),
        "value": value_body,
        "source_refs": _source_refs(inputs),
        "derivation": {
            "component_id": component_id,
            "component_version": component_version,
            "operation_code": operation_code,
            "formula_ref": formula_ref,
            "parameter_hash": parameter_hash,
            "input_fact_ids": input_ids,
            "component_run_id": component_run_id,
        },
        "quality": _quality(inputs),
        "producer": "deterministic_component",
    }
    body["fact_id"] = fact_id(
        fact_type,
        fact_code,
        "calculated",
        {item["dimension_code"]: item["member_code"] for item in scope},
        dict(time_context),
    )
    body["integrity"] = {"payload_hash": _hash(body)}
    return body


def _make_signal(
    *,
    inputs: Sequence[Mapping[str, Any]],
    component_id: str,
    component_version: str,
    component_run_id: str,
    signal_code: str,
    rule_ref: str,
    threshold_ref: str | None,
    scope: Sequence[Mapping[str, str]],
    time_context: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    outcome: str,
    direction: str | None = None,
    reason_codes: Sequence[str] = (),
) -> dict[str, Any]:
    input_ids = sorted(str(fact["fact_id"]) for fact in inputs)
    body: dict[str, Any] = {
        "signal_code": signal_code,
        "rule_ref": rule_ref,
        "component_ref": {
            "component_id": component_id,
            "component_version": component_version,
            "component_run_id": component_run_id,
        },
        "threshold_ref": threshold_ref,
        "input_fact_ids": input_ids,
        "required_fact_codes": sorted({str(fact["fact_code"]) for fact in inputs}),
        "missing_fact_codes": [],
        "scope": [dict(item) for item in scope],
        "time_context": dict(time_context),
        "evaluation": dict(evaluation),
        "outcome": outcome,
        "direction": direction,
        "impact_band_candidate": None,
        "urgency_band_candidate": None,
        "reason_codes": sorted(set(reason_codes)),
        "producer": "deterministic_component",
    }
    body["signal_id"] = signal_id(body)
    return body


def _threshold(parameters: Mapping[str, Any], key: str, thresholds: Mapping[str, Any]) -> tuple[str, Decimal]:
    reference = parameters.get(key)
    if not isinstance(reference, str) or reference not in thresholds:
        raise KeyError("missing_threshold_ref")
    raw = thresholds[reference]
    if isinstance(raw, Mapping):
        raw = raw.get("value")
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, TypeError) as error:
        raise ValueError("invalid_threshold") from error
    if not value.is_finite():
        raise ValueError("invalid_threshold")
    return reference, value


def aggregate(
    facts: Sequence[Mapping[str, Any]], parameters: Mapping[str, Any], thresholds: Mapping[str, Any],
    component_run_id: str, parameter_hash: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected = _facts_by_code(facts, str(parameters.get("input_fact_code", "")))
    operation = parameters.get("operation")
    values = [_decimal(fact) for fact in selected]
    unit = None if operation == "count" else _same_units(selected)
    if operation == "sum":
        result = sum(values, Decimal("0"))
    elif operation == "average":
        result = sum(values, Decimal("0")) / Decimal(len(values))
    elif operation == "minimum":
        result = min(values)
    elif operation == "maximum":
        result = max(values)
    elif operation == "count":
        result = Decimal(len(values))
        unit = "count"
    else:
        raise NotAssessable("invalid_parameter")
    output = _make_fact(
        inputs=selected,
        component_id="aggregate",
        component_version="1.0.0",
        component_run_id=component_run_id,
        parameter_hash=parameter_hash,
        fact_code=str(parameters["output_fact_code"]),
        metric_code=str(parameters.get("output_metric_code", parameters["output_fact_code"])),
        value=result,
        unit_code=unit,
        scope=_scope(selected, parameters),
        time_context=_time_context(selected, parameters),
        operation_code=str(operation),
        formula_ref=f"aggregate:{operation}",
        fact_type="aggregated",
    )
    return [output], []


def compare(
    facts: Sequence[Mapping[str, Any]], parameters: Mapping[str, Any], thresholds: Mapping[str, Any],
    component_run_id: str, parameter_hash: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    baseline = _fact_by_id(facts, str(parameters.get("baseline_fact_id", "")))
    current = _fact_by_id(facts, str(parameters.get("current_fact_id", "")))
    _same_units([baseline, current])
    baseline_value = _decimal(baseline)
    current_value = _decimal(current)
    mode = parameters.get("mode")
    if mode == "difference":
        value = current_value - baseline_value
        unit = _unit(current)
    elif mode == "percentage_point_change":
        if _unit(current) != "ratio":
            raise NotAssessable("ratio_unit_required")
        value = (current_value - baseline_value) * Decimal("100")
        unit = "percentage_point"
    elif mode == "percent_change":
        if baseline_value == 0:
            raise NotAssessable("zero_baseline")
        value = (current_value - baseline_value) / abs(baseline_value)
        unit = "ratio"
    else:
        raise NotAssessable("invalid_parameter")
    output = _make_fact(
        inputs=[baseline, current], component_id="compare", component_version="1.0.0",
        component_run_id=component_run_id, parameter_hash=parameter_hash,
        fact_code=str(parameters["output_fact_code"]),
        metric_code=str(parameters.get("output_metric_code", parameters["output_fact_code"])),
        value=value, unit_code=unit, scope=_scope([baseline, current], parameters),
        time_context=_time_context([current], parameters), operation_code=str(mode),
        formula_ref=f"compare:{mode}",
    )
    return [output], []


def ratio(
    facts: Sequence[Mapping[str, Any]], parameters: Mapping[str, Any], thresholds: Mapping[str, Any],
    component_run_id: str, parameter_hash: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    numerator = _fact_by_id(facts, str(parameters.get("numerator_fact_id", "")))
    denominator = _fact_by_id(facts, str(parameters.get("denominator_fact_id", "")))
    denominator_value = _decimal(denominator)
    if denominator_value == 0:
        raise NotAssessable("zero_denominator")
    output = _make_fact(
        inputs=[numerator, denominator], component_id="ratio", component_version="1.0.0",
        component_run_id=component_run_id, parameter_hash=parameter_hash,
        fact_code=str(parameters["output_fact_code"]),
        metric_code=str(parameters.get("output_metric_code", parameters["output_fact_code"])),
        value=_decimal(numerator) / denominator_value,
        unit_code=str(parameters.get("output_unit_code", "ratio")),
        scope=_scope([numerator, denominator], parameters),
        time_context=_time_context([numerator, denominator], parameters),
        operation_code="ratio", formula_ref="numerator/denominator",
    )
    return [output], []


def trend_persistence(
    facts: Sequence[Mapping[str, Any]], parameters: Mapping[str, Any], thresholds: Mapping[str, Any],
    component_run_id: str, parameter_hash: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected = _facts_by_code(facts, str(parameters.get("input_fact_code", "")))
    selected = sorted(selected, key=lambda fact: canonical_bytes(fact.get("time_context", {})))
    threshold_ref, minimum = _threshold(parameters, "minimum_observations_ref", thresholds)
    if len(selected) < int(minimum):
        raise NotAssessable("insufficient_observations")
    values = [_decimal(fact) for fact in selected]
    direction = parameters.get("direction")
    if direction == "decreasing":
        triggered = all(left > right for left, right in zip(values, values[1:]))
    elif direction == "increasing":
        triggered = all(left < right for left, right in zip(values, values[1:]))
    else:
        raise NotAssessable("invalid_parameter")
    signal = _make_signal(
        inputs=selected, component_id="trend_persistence", component_version="1.0.0",
        component_run_id=component_run_id,
        signal_code=str(parameters["output_signal_code"]), rule_ref="trend_persistence:1.0.0",
        threshold_ref=threshold_ref, scope=_scope(selected, parameters),
        time_context=_time_context([selected[-1]], parameters),
        evaluation={"observation_count": len(selected), "direction": direction},
        outcome="triggered" if triggered else "not_triggered", direction=str(direction),
    )
    return [], [signal]


def mix_concentration(
    facts: Sequence[Mapping[str, Any]], parameters: Mapping[str, Any], thresholds: Mapping[str, Any],
    component_run_id: str, parameter_hash: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected = _facts_by_code(facts, str(parameters.get("input_fact_code", "")))
    _same_units(selected)
    values = [_decimal(fact) for fact in selected]
    if any(value < 0 for value in values):
        raise NotAssessable("negative_population_value")
    total = sum(values, Decimal("0"))
    if total == 0:
        raise NotAssessable("zero_population")
    top_n = parameters.get("top_n")
    if not isinstance(top_n, int) or isinstance(top_n, bool) or not 1 <= top_n <= len(values):
        raise NotAssessable("invalid_parameter")
    shares = [value / total for value in values]
    top_share = sum(sorted(shares, reverse=True)[:top_n], Decimal("0"))
    hhi = sum((share * share for share in shares), Decimal("0"))
    scope = _common_scope(selected, parameters)
    time_context = _time_context(selected, parameters)
    common = {
        "inputs": selected, "component_id": "mix_concentration", "component_version": "1.0.0",
        "component_run_id": component_run_id, "parameter_hash": parameter_hash,
        "unit_code": "ratio", "scope": scope, "time_context": time_context,
    }
    outputs = [
        _make_fact(
            **common, fact_code=str(parameters["share_output_fact_code"]),
            metric_code=str(parameters["share_output_fact_code"]), value=top_share,
            operation_code="top_n_share", formula_ref="sum(top_n(values))/sum(values)",
        ),
        _make_fact(
            **common, fact_code=str(parameters["hhi_output_fact_code"]),
            metric_code=str(parameters["hhi_output_fact_code"]), value=hhi,
            operation_code="hhi", formula_ref="sum(square(member_share))",
        ),
    ]
    return outputs, []


def reconcile(
    facts: Sequence[Mapping[str, Any]], parameters: Mapping[str, Any], thresholds: Mapping[str, Any],
    component_run_id: str, parameter_hash: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    total = _fact_by_id(facts, str(parameters.get("total_fact_id", "")))
    part_ids = parameters.get("part_fact_ids")
    if not isinstance(part_ids, list) or not part_ids:
        raise NotAssessable("invalid_parameter")
    parts = [_fact_by_id(facts, str(part_id)) for part_id in part_ids]
    _same_units([total, *parts])
    threshold_ref, tolerance = _threshold(parameters, "tolerance_ref", thresholds)
    total_value = _decimal(total)
    difference = abs(total_value - sum((_decimal(part) for part in parts), Decimal("0")))
    relative = difference if total_value == 0 else difference / abs(total_value)
    signal = _make_signal(
        inputs=[total, *parts], component_id="reconcile", component_version="1.0.0",
        component_run_id=component_run_id, signal_code=str(parameters["output_signal_code"]),
        rule_ref="reconcile:1.0.0", threshold_ref=threshold_ref,
        scope=_scope([total], parameters), time_context=_time_context([total], parameters),
        evaluation={"difference": canonical_decimal(difference), "relative_difference": canonical_decimal(relative)},
        outcome="triggered" if relative <= tolerance else "not_triggered",
    )
    return [], [signal]


def flow_aging(
    facts: Sequence[Mapping[str, Any]], parameters: Mapping[str, Any], thresholds: Mapping[str, Any],
    component_run_id: str, parameter_hash: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected = _facts_by_code(facts, str(parameters.get("input_fact_code", "")))
    unit = _same_units(selected)
    observation_end = _fact_by_id(facts, str(parameters.get("observation_end_fact_id", "")))
    end = _date(observation_end)
    edges = parameters.get("bucket_edges_days")
    if not isinstance(edges, list) or not edges or any(not isinstance(edge, int) or edge < 0 for edge in edges):
        raise NotAssessable("invalid_parameter")
    edges = sorted(set(edges))
    totals = [Decimal("0") for _ in range(len(edges) + 1)]
    for fact in selected:
        try:
            observed = date.fromisoformat(str(fact["time_context"]["as_of"]))
        except (KeyError, ValueError) as error:
            raise NotAssessable("ambiguous_date_role") from error
        age = (end - observed).days
        if age < 0:
            raise NotAssessable("observation_after_end")
        bucket = next((index for index, edge in enumerate(edges) if age <= edge), len(edges))
        totals[bucket] += _decimal(fact)
    outputs: list[dict[str, Any]] = []
    lower = 0
    for index, total in enumerate(totals):
        label = f"{lower}_{edges[index]}" if index < len(edges) else f"{lower}_plus"
        if index < len(edges):
            lower = edges[index] + 1
        outputs.append(
            _make_fact(
                inputs=[*selected, observation_end], component_id="flow_aging", component_version="1.0.0",
                component_run_id=component_run_id, parameter_hash=parameter_hash,
                fact_code=f"{parameters['output_fact_code_prefix']}_{label}",
                metric_code=str(parameters["output_fact_code_prefix"]), value=total, unit_code=unit,
                scope=_scope(selected, parameters), time_context={"as_of": end.isoformat()},
                operation_code="aging_bucket", formula_ref="censored_at_observation_end",
                fact_type="aggregated",
            )
        )
    return outputs, []


def bridge_decompose(
    facts: Sequence[Mapping[str, Any]], parameters: Mapping[str, Any], thresholds: Mapping[str, Any],
    component_run_id: str, parameter_hash: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    gap = _fact_by_id(facts, str(parameters.get("gap_fact_id", "")))
    driver_ids = parameters.get("driver_fact_ids")
    if not isinstance(driver_ids, list) or not driver_ids:
        raise NotAssessable("invalid_parameter")
    drivers = [_fact_by_id(facts, str(driver_id)) for driver_id in driver_ids]
    _same_units([gap, *drivers])
    _, tolerance = _threshold(parameters, "residual_tolerance_ref", thresholds)
    gap_value = _decimal(gap)
    if gap_value == 0:
        raise NotAssessable("zero_gap")
    residual = gap_value - sum((_decimal(driver) for driver in drivers), Decimal("0"))
    if abs(residual / gap_value) > tolerance:
        raise NotAssessable("residual_reconciliation_failed")
    output = _make_fact(
        inputs=[gap, *drivers], component_id="bridge_decompose", component_version="1.0.0",
        component_run_id=component_run_id, parameter_hash=parameter_hash,
        fact_code=str(parameters["output_fact_code"]),
        metric_code=str(parameters.get("output_metric_code", parameters["output_fact_code"])),
        value=residual, unit_code=_unit(gap), scope=_scope([gap], parameters),
        time_context=_time_context([gap], parameters), operation_code="bridge_residual",
        formula_ref="gap-sum(driver_contributions)",
    )
    return [output], []


def temporal_alignment(
    facts: Sequence[Mapping[str, Any]], parameters: Mapping[str, Any], thresholds: Mapping[str, Any],
    component_run_id: str, parameter_hash: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    earlier = _fact_by_id(facts, str(parameters.get("earlier_fact_id", "")))
    later = _fact_by_id(facts, str(parameters.get("later_fact_id", "")))
    threshold_ref, maximum = _threshold(parameters, "max_lag_days_ref", thresholds)
    lag = Decimal((_date(later) - _date(earlier)).days)
    if lag < 0:
        raise NotAssessable("date_order_invalid")
    scope = _scope([earlier, later], parameters)
    time_context = _time_context([later], parameters)
    output = _make_fact(
        inputs=[earlier, later], component_id="temporal_alignment", component_version="1.0.0",
        component_run_id=component_run_id, parameter_hash=parameter_hash,
        fact_code=str(parameters["output_fact_code"]),
        metric_code=str(parameters.get("output_metric_code", parameters["output_fact_code"])),
        value=lag, unit_code="day", scope=scope, time_context=time_context,
        operation_code="date_lag", formula_ref="later_date-earlier_date",
    )
    signal = _make_signal(
        inputs=[earlier, later], component_id="temporal_alignment", component_version="1.0.0",
        component_run_id=component_run_id, signal_code=str(parameters["output_signal_code"]),
        rule_ref="temporal_alignment:1.0.0", threshold_ref=threshold_ref,
        scope=scope, time_context=time_context,
        evaluation={"lag_days": canonical_decimal(lag), "maximum_days": canonical_decimal(maximum)},
        outcome="triggered" if lag > maximum else "not_triggered", direction="later",
    )
    return [output], [signal]


IMPLEMENTATIONS = {
    "aggregate": aggregate,
    "compare": compare,
    "ratio": ratio,
    "trend_persistence": trend_persistence,
    "mix_concentration": mix_concentration,
    "reconcile": reconcile,
    "flow_aging": flow_aging,
    "bridge_decompose": bridge_decompose,
    "temporal_alignment": temporal_alignment,
}
