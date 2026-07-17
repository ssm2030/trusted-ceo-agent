from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from jsonschema import Draft202012Validator

from trusted_ceo_agent.components.models import ComponentContract
from trusted_ceo_agent.errors import ContractError


ComponentImplementation = Callable[..., tuple[list[dict[str, Any]], list[dict[str, Any]]]]


_COMPONENT_IDS = (
    "aggregate",
    "compare",
    "ratio",
    "trend_persistence",
    "mix_concentration",
    "reconcile",
    "flow_aging",
    "bridge_decompose",
    "temporal_alignment",
)


_TEXT = {"type": "string", "minLength": 1}
_FACT_ID = {"type": "string", "minLength": 1}
_SCOPE = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["dimension_code", "member_code"],
        "properties": {"dimension_code": _TEXT, "member_code": _TEXT},
        "additionalProperties": False,
    },
    "uniqueItems": True,
}
_TIME_CONTEXT = {
    "oneOf": [
        {
            "type": "object", "required": ["period"],
            "properties": {"period": _TEXT}, "additionalProperties": False,
        },
        {
            "type": "object", "required": ["as_of"],
            "properties": {"as_of": _TEXT}, "additionalProperties": False,
        },
        {
            "type": "object", "required": ["window"],
            "properties": {
                "window": {
                    "type": "object", "required": ["start", "end"],
                    "properties": {"start": _TEXT, "end": _TEXT},
                    "additionalProperties": False,
                }
            },
            "additionalProperties": False,
        },
    ]
}


def _parameter_schema(
    required: Sequence[str],
    properties: Mapping[str, Any],
) -> dict[str, Any]:
    common = {
        "output_metric_code": _TEXT,
        "output_unit_code": _TEXT,
        "scope": _SCOPE,
        "time_context": _TIME_CONTEXT,
    }
    return {
        "type": "object",
        "required": list(required),
        "properties": {**common, **dict(properties)},
        "additionalProperties": False,
    }


PARAMETER_SCHEMAS: dict[str, dict[str, Any]] = {
    "aggregate": _parameter_schema(
        ("input_fact_code", "operation", "output_fact_code"),
        {
            "input_fact_code": _TEXT,
            "operation": {"enum": ["sum", "average", "minimum", "maximum", "count"]},
            "output_fact_code": _TEXT,
        },
    ),
    "compare": _parameter_schema(
        ("baseline_fact_id", "current_fact_id", "mode", "output_fact_code"),
        {
            "baseline_fact_id": _FACT_ID,
            "current_fact_id": _FACT_ID,
            "mode": {"enum": ["difference", "percent_change", "percentage_point_change"]},
            "output_fact_code": _TEXT,
        },
    ),
    "ratio": _parameter_schema(
        ("numerator_fact_id", "denominator_fact_id", "output_fact_code"),
        {
            "numerator_fact_id": _FACT_ID,
            "denominator_fact_id": _FACT_ID,
            "output_fact_code": _TEXT,
        },
    ),
    "trend_persistence": _parameter_schema(
        ("input_fact_code", "minimum_observations_ref", "direction", "output_signal_code"),
        {
            "input_fact_code": _TEXT,
            "minimum_observations_ref": _TEXT,
            "direction": {"enum": ["decreasing", "increasing"]},
            "output_signal_code": _TEXT,
        },
    ),
    "mix_concentration": _parameter_schema(
        ("input_fact_code", "top_n", "share_output_fact_code", "hhi_output_fact_code"),
        {
            "input_fact_code": _TEXT,
            "top_n": {"type": "integer", "minimum": 1},
            "share_output_fact_code": _TEXT,
            "hhi_output_fact_code": _TEXT,
        },
    ),
    "reconcile": _parameter_schema(
        ("total_fact_id", "part_fact_ids", "tolerance_ref", "output_signal_code"),
        {
            "total_fact_id": _FACT_ID,
            "part_fact_ids": {
                "type": "array", "minItems": 1, "uniqueItems": True, "items": _FACT_ID,
            },
            "tolerance_ref": _TEXT,
            "output_signal_code": _TEXT,
        },
    ),
    "flow_aging": _parameter_schema(
        ("input_fact_code", "observation_end_fact_id", "bucket_edges_days", "output_fact_code_prefix"),
        {
            "input_fact_code": _TEXT,
            "observation_end_fact_id": _FACT_ID,
            "bucket_edges_days": {
                "type": "array", "minItems": 1, "uniqueItems": True,
                "items": {"type": "integer", "minimum": 0},
            },
            "output_fact_code_prefix": _TEXT,
        },
    ),
    "bridge_decompose": _parameter_schema(
        ("gap_fact_id", "driver_fact_ids", "residual_tolerance_ref", "output_fact_code"),
        {
            "gap_fact_id": _FACT_ID,
            "driver_fact_ids": {
                "type": "array", "minItems": 1, "uniqueItems": True, "items": _FACT_ID,
            },
            "residual_tolerance_ref": _TEXT,
            "output_fact_code": _TEXT,
        },
    ),
    "temporal_alignment": _parameter_schema(
        ("earlier_fact_id", "later_fact_id", "max_lag_days_ref", "output_fact_code", "output_signal_code"),
        {
            "earlier_fact_id": _FACT_ID,
            "later_fact_id": _FACT_ID,
            "max_lag_days_ref": _TEXT,
            "output_fact_code": _TEXT,
            "output_signal_code": _TEXT,
        },
    ),
}

THRESHOLD_PARAMETER_KEYS = frozenset(
    {"minimum_observations_ref", "tolerance_ref", "residual_tolerance_ref", "max_lag_days_ref"}
)


def validate_component_parameters(component_id: str, parameters: Mapping[str, Any]) -> None:
    schema = PARAMETER_SCHEMAS.get(component_id)
    if schema is None:
        raise ContractError(f"unknown Component parameter contract: {component_id}")
    errors = sorted(
        Draft202012Validator(schema).iter_errors(dict(parameters)),
        key=lambda error: tuple(str(item) for item in error.path),
    )
    if errors:
        first = errors[0]
        location = "/" + "/".join(str(item) for item in first.path) if first.path else "/"
        raise ContractError(f"invalid Component parameters for {component_id} at {location}: {first.message}")


def validate_component_thresholds(
    parameters: Mapping[str, Any], thresholds: Mapping[str, Any] | None,
) -> None:
    available = dict(thresholds or {})
    for key in sorted(THRESHOLD_PARAMETER_KEYS & set(parameters)):
        reference = parameters[key]
        if not isinstance(reference, str) or reference not in available:
            raise ContractError(f"Component threshold ref is unavailable: {key}={reference!r}")


def build_contracts() -> dict[str, ComponentContract]:
    common_reasons = (
        "missing_input_fact",
        "unit_mismatch",
        "scope_mismatch",
        "invalid_parameter",
    )
    return {
        component_id: ComponentContract(
            component_id=component_id,
            version="1.0.0",
            supported_input_fact_codes=("*",),
            required_dimensions=(),
            parameter_schema=PARAMETER_SCHEMAS[component_id],
            output_fact_codes=("runtime_parameter",),
            output_signal_codes=("runtime_parameter",),
            failure_reason_codes=common_reasons,
            parallel_safe=True,
            max_input_records=10_000,
            timeout_seconds=5,
        )
        for component_id in _COMPONENT_IDS
    }


CONTRACTS = build_contracts()
