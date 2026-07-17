from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator, validators

from trusted_ceo_agent.errors import ContractError


def _is_integer(checker: Any, instance: Any) -> bool:
    return (
        isinstance(instance, int)
        and not isinstance(instance, bool)
        or isinstance(instance, Decimal)
        and instance.is_finite()
        and instance == instance.to_integral_value()
    )


def _is_number(checker: Any, instance: Any) -> bool:
    return (
        isinstance(instance, (int, Decimal))
        and not isinstance(instance, bool)
        and (not isinstance(instance, Decimal) or instance.is_finite())
    )


_TYPE_CHECKER = (
    Draft202012Validator.TYPE_CHECKER
    .redefine("integer", _is_integer)
    .redefine("number", _is_number)
)
StrictDraft202012Validator = validators.extend(Draft202012Validator, type_checker=_TYPE_CHECKER)


def load_schema(path: Path) -> dict[str, Any]:
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    for reference in _references(schema):
        if reference.startswith(("http://", "https://", "file:")) or reference.startswith(("/", "\\")):
            raise ContractError(f"non-local schema reference is forbidden: {reference}")
    return schema


def _references(value: Any) -> list[str]:
    if isinstance(value, dict):
        found = [str(value["$ref"])] if "$ref" in value else []
        for child in value.values():
            found.extend(_references(child))
        return found
    if isinstance(value, list):
        return [reference for child in value for reference in _references(child)]
    return []


def validate_document(document: Any, schema_path: Path) -> None:
    validator = StrictDraft202012Validator(load_schema(schema_path))
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
    if errors:
        first = errors[0]
        location = "/" + "/".join(str(part) for part in first.absolute_path)
        raise ContractError(f"schema validation failed at {location}: {first.message}")

def validate_problem_capability_contract(problem: Mapping[str, Any]) -> None:
    content = problem.get("content")
    if not isinstance(content, Mapping):
        raise ContractError("Problem Pack content must be an object")
    required = content.get("required_capabilities")
    definitions = content.get("capability_requirements")
    if not isinstance(required, list) or any(not isinstance(code, str) or not code for code in required):
        raise ContractError("required_capabilities must contain non-empty capability codes")
    if len(set(required)) != len(required):
        raise ContractError("duplicate required capability code")
    if not isinstance(definitions, list):
        raise ContractError("capability_requirements must be defined")

    defined_codes: list[str] = []
    for definition in definitions:
        if not isinstance(definition, Mapping):
            raise ContractError("capability requirement must be an object")
        code = definition.get("capability_code")
        facts = definition.get("required_fact_codes")
        roles = definition.get("required_observation_roles")
        if not isinstance(code, str) or not code:
            raise ContractError("capability requirement requires capability_code")
        if code in defined_codes:
            raise ContractError(f"duplicate capability requirement: {code}")
        defined_codes.append(code)
        if (
            not isinstance(facts, list)
            or not facts
            or any(not isinstance(item, str) or not item for item in facts)
            or len(set(facts)) != len(facts)
        ):
            raise ContractError(f"invalid required_fact_codes for capability: {code}")
        if (
            not isinstance(roles, list)
            or not roles
            or any(not isinstance(item, str) or not item for item in roles)
            or len(set(roles)) != len(roles)
        ):
            raise ContractError(f"invalid required_observation_roles for capability: {code}")
    if set(required) != set(defined_codes) or len(required) != len(defined_codes):
        raise ContractError(
            "capability requirement mismatch: required_capabilities and definitions must be one-to-one"
        )


def _fact_selectors(value: Any) -> list[Mapping[str, Any]]:
    selectors: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        selector = value.get("fact_selector")
        if isinstance(selector, Mapping):
            selectors.append(selector)
        for child in value.values():
            selectors.extend(_fact_selectors(child))
    elif isinstance(value, list):
        for child in value:
            selectors.extend(_fact_selectors(child))
    return selectors


def _produced_fact_codes(problem: Mapping[str, Any]) -> set[str]:
    output_fields = {
        "output_fact_code",
        "output_metric_code",
        "share_output_fact_code",
        "hhi_output_fact_code",
        "output_fact_code_prefix",
    }
    result: set[str] = set()
    content = problem.get("content", {})
    if not isinstance(content, Mapping):
        return result
    for plan_name in ("analysis_plan", "deep_dive_plan"):
        plan = content.get(plan_name, [])
        if not isinstance(plan, list):
            continue
        for step in plan:
            if not isinstance(step, Mapping):
                continue
            parameters = step.get("parameter_template", {})
            if not isinstance(parameters, Mapping):
                continue
            for name in output_fields:
                value = parameters.get(name)
                if isinstance(value, str) and value:
                    result.add(value)
    return result


def _selector_unit_matches(unit_policy: str, unit_code: Any) -> bool:
    exact = {
        "ratio": "ratio",
        "hour": "hour",
        "percentage_point": "percentage_point",
        "count": "count",
        "day": "day",
        "date": None,
    }
    if unit_policy == "single_currency_or_verified_conversion":
        return isinstance(unit_code, str) and re.fullmatch(r"[A-Z]{3}", unit_code) is not None
    return unit_policy in exact and unit_code == exact[unit_policy]


def validate_pack_ontology(
    domain: Mapping[str, Any],
    problems: Sequence[Mapping[str, Any]],
) -> None:
    domain_content = domain.get("content")
    if not isinstance(domain_content, Mapping):
        raise ContractError("Domain Pack content must be an object")
    definitions = domain_content.get("metric_definitions")
    if not isinstance(definitions, list):
        raise ContractError("Domain metric_definitions must be an array")

    metrics: dict[str, Mapping[str, Any]] = {}
    for definition in definitions:
        if not isinstance(definition, Mapping):
            raise ContractError("metric definition must be an object")
        code = definition.get("metric_code")
        if not isinstance(code, str) or not code:
            raise ContractError("metric definition requires metric_code")
        if code in metrics:
            raise ContractError(f"duplicate metric definition: {code}")
        origin = definition.get("metric_origin")
        if origin not in {"raw_input", "derived_output"}:
            raise ContractError(f"metric origin is invalid: {code}")
        roles = definition.get("accepted_observation_roles")
        if (
            not isinstance(roles, list)
            or not roles
            or any(not isinstance(role, str) or not role for role in roles)
            or len(set(roles)) != len(roles)
        ):
            raise ContractError(f"metric observation roles are invalid: {code}")
        data_type = definition.get("data_type")
        unit_policy = definition.get("unit_policy")
        if data_type == "date" and unit_policy != "date":
            raise ContractError(f"date metric requires date unit policy: {code}")
        if data_type != "date" and unit_policy == "date":
            raise ContractError(f"date unit policy requires date data type: {code}")
        metrics[code] = definition

    produced = set().union(*(_produced_fact_codes(problem) for problem in problems)) if problems else set()
    seen_capabilities: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
    for problem in problems:
        validate_problem_capability_contract(problem)
        content = problem["content"]
        for requirement in content["capability_requirements"]:
            code = str(requirement["capability_code"])
            fact_codes = tuple(sorted(str(item) for item in requirement["required_fact_codes"]))
            roles = tuple(sorted(str(item) for item in requirement["required_observation_roles"]))
            identity = (fact_codes, roles)
            previous = seen_capabilities.get(code)
            if previous is not None and previous != identity:
                raise ContractError(f"capability ontology mismatch across Problem Packs: {code}")
            seen_capabilities[code] = identity
            accepted_union: set[str] = set()
            for fact_code in fact_codes:
                metric = metrics.get(fact_code)
                if metric is None:
                    raise ContractError(f"capability fact is not defined by Domain: {fact_code}")
                if metric.get("metric_origin") != "raw_input":
                    raise ContractError(f"capability fact must be a raw input: {fact_code}")
                accepted = {str(item) for item in metric["accepted_observation_roles"]}
                accepted_union.update(accepted)
                if not accepted.intersection(roles):
                    raise ContractError(
                        f"capability observation role does not match fact ontology: {code}/{fact_code}"
                    )
            missing_roles = set(roles) - accepted_union
            if missing_roles:
                raise ContractError(
                    f"capability observation role is not accepted by Domain: {code}/{sorted(missing_roles)}"
                )

        for selector in _fact_selectors([
            content.get("analysis_plan", []),
            content.get("deep_dive_plan", []),
        ]):
            fact_code = selector.get("fact_code")
            if not isinstance(fact_code, str) or not fact_code:
                raise ContractError("fact selector requires fact_code")
            metric = metrics.get(fact_code)
            if metric is None:
                raise ContractError(f"selector fact is not defined by Domain: {fact_code}")
            expected_origin = "derived_output" if fact_code in produced else "raw_input"
            if metric.get("metric_origin") != expected_origin:
                raise ContractError(
                    f"selector metric origin mismatch: {fact_code} must be {expected_origin}"
                )
            if not _selector_unit_matches(str(metric.get("unit_policy", "")), selector.get("unit_code")):
                raise ContractError(f"selector unit policy mismatch: {fact_code}")

    for fact_code in sorted(produced):
        metric = metrics.get(fact_code)
        if metric is None:
            raise ContractError(f"derived output is not defined by Domain: {fact_code}")
        if metric.get("metric_origin") != "derived_output":
            raise ContractError(f"derived output metric origin mismatch: {fact_code}")
