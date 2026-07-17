from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Mapping, Sequence

from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.intake.models import ParsedDataset


@dataclass(frozen=True)
class FieldMapping:
    source_field: str
    observation_role: str
    metric_code: str
    unit_code: str | None
    scale: str | None
    time_role: str | None
    dimension_code: str | None
    confirmed: bool = False


@dataclass(frozen=True)
class ResolvedFieldMapping:
    mapping_question_ref: str
    source_field_ref: str
    source_id: str
    source_field: str
    observation_role: str
    metric_code: str
    data_type: str
    unit_policy: str
    unit_code: str | None
    scale: str | None
    time_role: str
    dimension_code: str | None
    time_field: str
    scope_fields: tuple[tuple[str, str], ...]
    confirmed: bool = True


def validate_mappings(dataset: ParsedDataset, mappings: Sequence[FieldMapping]) -> tuple[FieldMapping, ...]:
    seen: set[str] = set()
    result: list[FieldMapping] = []
    for mapping in mappings:
        if mapping.source_field not in dataset.fields:
            raise ContractError(f"mapping references missing field: {mapping.source_field}")
        if mapping.source_field in seen:
            raise ContractError(f"duplicate mapping for field: {mapping.source_field}")
        if not mapping.confirmed:
            raise ContractError(f"mapping requires Data Gate confirmation: {mapping.source_field}")
        seen.add(mapping.source_field)
        result.append(mapping)
    return tuple(sorted(result, key=lambda item: item.source_field))


def _source_field_ref(dataset: ParsedDataset, source_field: str) -> str:
    return make_id("sourcefield", {"source_id": dataset.source_id, "source_field": source_field})


def _unit_default(unit_policy: str) -> str | None:
    return {
        "ratio": "ratio",
        "hour": "hour",
        "percentage_point": "percentage_point",
        "count": "count",
        "day": "day",
        "date": None,
        "single_currency_or_verified_conversion": None,
    }.get(unit_policy)


def _scale_default(data_type: str) -> str | None:
    return None if data_type == "date" else "1"

def build_canonical_mapping_proposal(
    dataset: ParsedDataset,
    metric_definitions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build fail-closed candidates for exact canonical headers only."""

    by_code: dict[str, Mapping[str, Any]] = {}
    seen_codes: set[str] = set()
    for metric in metric_definitions:
        code = metric.get("metric_code")
        if not isinstance(code, str) or not code:
            raise ContractError("metric definition requires a non-empty metric_code")
        if code in seen_codes:
            raise ContractError(f"duplicate metric definition: {code}")
        seen_codes.add(code)
        origin = metric.get("metric_origin", "raw_input")
        if origin not in {"raw_input", "derived_output"}:
            raise ContractError(f"metric origin is invalid: {code}")
        if origin == "raw_input":
            by_code[code] = metric

    time_fields = sorted(field for field in dataset.fields if field in {"period", "as_of"})
    scope_fields = sorted(field for field in dataset.fields if field.startswith("scope."))
    scope_dimensions = [field.removeprefix("scope.") for field in scope_fields]
    mappings: list[dict[str, Any]] = []
    for source_field in sorted(set(dataset.fields) & set(by_code)):
        metric = by_code[source_field]
        allowed_dimensions = metric.get("allowed_dimensions", [])
        if not isinstance(allowed_dimensions, list):
            raise ContractError(f"metric allowed_dimensions must be an array: {source_field}")
        valid_profile = (
            len(time_fields) == 1
            and len(scope_fields) <= 1
            and all(dimension in allowed_dimensions for dimension in scope_dimensions)
        )
        supporting_fields = [*time_fields, *scope_fields]
        supporting_refs = sorted(_source_field_ref(dataset, field) for field in supporting_fields)
        candidates: list[dict[str, Any]] = []
        roles = metric.get("accepted_observation_roles", [])
        if not isinstance(roles, list) or any(not isinstance(role, str) or not role for role in roles):
            raise ContractError(f"metric observation roles are invalid: {source_field}")
        if valid_profile:
            for role in sorted(set(roles)):
                candidates.append({
                    "observation_role": role,
                    "metric_code": source_field,
                    "unit_code": _unit_default(str(metric.get("unit_policy", ""))),
                    "scale": _scale_default(str(metric.get("data_type", ""))),
                    "time_role": str(metric.get("time_role", "")) or None,
                    "dimension_code": scope_dimensions[0] if scope_dimensions else None,
                    "supporting_header_refs": supporting_refs,
                })
        reason = "canonical_mapping_requires_data_gate"
        if len(time_fields) != 1:
            reason = "canonical_time_field_missing_or_ambiguous"
        elif len(scope_fields) > 1:
            reason = "canonical_multiple_scope_dimensions_unsupported"
        elif not valid_profile:
            reason = "canonical_scope_dimension_not_allowed"
        source_ref = _source_field_ref(dataset, source_field)
        mappings.append({
            "mapping_question_ref": make_id("mappingquestion", {"source_field_ref": source_ref}),
            "source_field_ref": source_ref,
            "candidate_mappings": candidates,
            "ambiguity_reason_code": reason,
            "required_human_choice": True,
        })
    proposal = {"mappings": mappings}
    SchemaStore().validate("schema-mapping-draft.schema.json", proposal)
    return proposal


_EDITABLE_MAPPING_FIELDS = {
    "observation_role", "unit_code", "scale", "time_role", "dimension_code",
}


def _validate_scale(scale: str | None) -> None:
    if scale is None:
        return
    if not isinstance(scale, str):
        raise ContractError("mapping scale must be a decimal string or null")
    try:
        value = Decimal(scale)
    except InvalidOperation as error:
        raise ContractError("mapping scale must be a finite positive decimal") from error
    if not value.is_finite() or value <= 0:
        raise ContractError("mapping scale must be a finite positive decimal")


def validate_unit_contract(
    data_type: str,
    unit_policy: str,
    unit_code: str | None,
    scale: str | None,
) -> None:
    if data_type not in {"decimal", "integer", "date"}:
        raise ContractError(f"canonical materializer does not support data_type: {data_type}")
    if data_type == "date":
        if unit_policy != "date" or unit_code is not None or scale is not None:
            raise ContractError("date metric requires null unit_code and scale")
        return
    if unit_policy == "date":
        raise ContractError("date unit policy requires date data_type")
    expected = {
        "ratio": "ratio",
        "hour": "hour",
        "percentage_point": "percentage_point",
        "count": "count",
        "day": "day",
    }
    if unit_policy == "single_currency_or_verified_conversion":
        if not isinstance(unit_code, str) or re.fullmatch(r"[A-Z]{3}", unit_code) is None:
            raise ContractError("currency metric requires a confirmed ISO currency code")
    elif unit_policy not in expected:
        raise ContractError(f"unsupported unit policy: {unit_policy}")
    elif unit_code != expected[unit_policy]:
        raise ContractError(f"{unit_policy} metric requires unit_code {expected[unit_policy]}")
    _validate_scale(scale)

def resolve_confirmed_mappings(
    dataset: ParsedDataset,
    proposal: Mapping[str, Any],
    overlay: Mapping[str, Any],
    metric_definitions: Sequence[Mapping[str, Any]],
) -> tuple[ResolvedFieldMapping, ...]:
    """Resolve Data Gate edits without allowing the metric identity to be edited."""

    SchemaStore().validate("schema-mapping-draft.schema.json", proposal)
    mapping_overlay = overlay.get("mapping")
    if not isinstance(mapping_overlay, Mapping):
        raise ContractError("Data Gate mapping overlay is missing")
    source_selections = mapping_overlay.get("sources")
    if not isinstance(source_selections, Mapping):
        raise ContractError("Data Gate source selections are missing")
    source_selection = source_selections.get(dataset.source_id)
    if not isinstance(source_selection, Mapping) or source_selection.get("included") is not True:
        return ()
    if set(source_selection) != {"included"}:
        raise ContractError("source mapping may only contain included")
    column_selections = mapping_overlay.get("columns")
    if not isinstance(column_selections, Mapping):
        raise ContractError("Data Gate column selections are missing")

    metrics = {str(item.get("metric_code")): item for item in metric_definitions}
    if len(metrics) != len(metric_definitions):
        raise ContractError("metric definitions contain duplicate metric_code")
    fields_by_ref = {_source_field_ref(dataset, field): field for field in dataset.fields}
    resolved: list[ResolvedFieldMapping] = []
    legacy: list[FieldMapping] = []
    for question in proposal.get("mappings", []):
        source_field_ref = question.get("source_field_ref")
        if source_field_ref not in fields_by_ref:
            continue
        question_ref = str(question.get("mapping_question_ref", ""))
        selection = column_selections.get(question_ref)
        if not isinstance(selection, Mapping):
            raise ContractError(f"mapping requires Data Gate confirmation: {question_ref}")
        if set(selection) != _EDITABLE_MAPPING_FIELDS:
            raise ContractError(f"mapping selection has missing or forbidden fields: {question_ref}")
        observation_role = selection.get("observation_role")
        time_role = selection.get("time_role")
        dimension_code = selection.get("dimension_code")
        if not isinstance(observation_role, str) or not observation_role:
            raise ContractError("mapping observation_role must be a non-empty string")
        if not isinstance(time_role, str) or not time_role:
            raise ContractError("mapping time_role must be a non-empty string")
        if dimension_code is not None and (not isinstance(dimension_code, str) or not dimension_code):
            raise ContractError("mapping dimension_code must be a non-empty string or null")
        candidates = [
            item for item in question.get("candidate_mappings", [])
            if item.get("observation_role") == observation_role
            and item.get("time_role") == time_role
            and item.get("dimension_code") == dimension_code
        ]
        if len(candidates) != 1:
            raise ContractError(f"Data Gate selection does not resolve one candidate: {question_ref}")
        candidate = candidates[0]
        metric_code = str(candidate.get("metric_code", ""))
        metric = metrics.get(metric_code)
        if metric is None or metric_code != fields_by_ref[source_field_ref]:
            raise ContractError("mapping candidate metric is not an exact canonical header")
        unit_code = selection.get("unit_code")
        if unit_code is not None and (not isinstance(unit_code, str) or not unit_code):
            raise ContractError("mapping unit_code must be a non-empty string or null")
        scale = selection.get("scale")
        validate_unit_contract(
            str(metric.get("data_type", "")),
            str(metric.get("unit_policy", "")),
            unit_code,
            scale,
        )
        support_fields: list[str] = []
        for reference in candidate.get("supporting_header_refs", []):
            field = fields_by_ref.get(reference)
            if field is None:
                raise ContractError("mapping candidate references an unknown supporting header")
            support_fields.append(field)
        time_fields = sorted(field for field in support_fields if field in {"period", "as_of"})
        scope_fields = sorted(field for field in support_fields if field.startswith("scope."))
        if len(time_fields) != 1:
            raise ContractError("canonical mapping requires exactly one period or as_of field")
        expected_scope = [] if dimension_code is None else [f"scope.{dimension_code}"]
        if scope_fields != expected_scope:
            raise ContractError("canonical mapping scope field does not match dimension_code")
        source_field = fields_by_ref[source_field_ref]
        legacy.append(FieldMapping(
            source_field=source_field,
            observation_role=observation_role,
            metric_code=metric_code,
            unit_code=unit_code,
            scale=scale,
            time_role=time_role,
            dimension_code=dimension_code,
            confirmed=True,
        ))
        resolved.append(ResolvedFieldMapping(
            mapping_question_ref=question_ref,
            source_field_ref=str(source_field_ref),
            source_id=dataset.source_id,
            source_field=source_field,
            observation_role=observation_role,
            metric_code=metric_code,
            data_type=str(metric.get("data_type", "")),
            unit_policy=str(metric.get("unit_policy", "")),
            unit_code=unit_code,
            scale=scale,
            time_role=time_role,
            dimension_code=dimension_code,
            time_field=time_fields[0],
            scope_fields=tuple((field, field.removeprefix("scope.")) for field in scope_fields),
        ))
    validate_mappings(dataset, legacy)
    return tuple(sorted(resolved, key=lambda item: item.source_field))
