from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any, Mapping, Sequence

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.condition_dsl import ConditionContext, ConditionResult, evaluate_condition
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.packs.runtime_index import RuntimePackIndex
from trusted_ceo_agent.packs.schema_validation import validate_problem_capability_contract


def _fact_refs(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, Mapping):
        body = value.get("fact_ref")
        if isinstance(body, Mapping) and isinstance(body.get("fact_code"), str):
            result.add(str(body["fact_code"]))
        for child in value.values():
            result.update(_fact_refs(child))
    elif isinstance(value, list):
        for child in value:
            result.update(_fact_refs(child))
    return result


def _missing_entry_presence_reasons(
    value: Any,
    fact_codes: set[str],
    signal_codes: set[str],
) -> set[str]:
    reasons: set[str] = set()
    if isinstance(value, Mapping):
        if value.get("op") == "exists" and isinstance(value.get("operand"), Mapping):
            operand = value["operand"]
            fact_ref = operand.get("fact_ref")
            signal_ref = operand.get("signal_ref")
            if isinstance(fact_ref, Mapping) and fact_ref.get("fact_code") not in fact_codes:
                reasons.add("missing_entry_fact")
            if isinstance(signal_ref, Mapping) and signal_ref.get("signal_code") not in signal_codes:
                reasons.add("missing_entry_signal")
        for child in value.values():
            reasons.update(_missing_entry_presence_reasons(child, fact_codes, signal_codes))
    elif isinstance(value, list):
        for child in value:
            reasons.update(_missing_entry_presence_reasons(child, fact_codes, signal_codes))
    return reasons


def _trusted_fact_roles(
    facts: Sequence[Mapping[str, Any]],
    source_registry: Sequence[Mapping[str, Any]],
) -> dict[str, set[str]]:
    declared_by_source = {
        str(source["source_id"]): {
            str(role) for role in source.get("observation_roles", [])
            if isinstance(role, str)
        }
        for source in source_registry
        if isinstance(source.get("source_id"), str)
    }
    trusted: dict[str, set[str]] = defaultdict(set)
    for fact in facts:
        fact_code = fact.get("fact_code")
        fact_role = fact.get("observation_role")
        if not isinstance(fact_code, str) or not isinstance(fact_role, str):
            continue
        for source_ref in fact.get("source_refs", []):
            if not isinstance(source_ref, Mapping):
                continue
            source_id = source_ref.get("source_id")
            source_role = source_ref.get("observation_role")
            if (
                isinstance(source_id, str)
                and source_role == fact_role
                and fact_role in declared_by_source.get(source_id, set())
            ):
                trusted[fact_code].add(fact_role)
    return {code: set(roles) for code, roles in trusted.items()}

def build_problem_capability_map(
    pack_index: RuntimePackIndex,
    facts: Sequence[Mapping[str, Any]],
    quality_issues: Sequence[Mapping[str, Any]],
    source_registry: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    requirements: dict[str, dict[str, Any]] = {}
    for pack in pack_index.problem_packs:
        content = pack["content"]
        explicit = content.get("capability_requirements")
        if explicit is not None:
            validate_problem_capability_contract(pack)
            definitions = explicit
            fallback = False
        else:
            entry_fact_codes = _fact_refs(content["entry_conditions"])
            roles = {
                str(role) for role in pack.get("applicability", {}).get("required_data_roles", [])
                if isinstance(role, str)
            }
            definitions = [
                {
                    "capability_code": str(capability_code),
                    "required_fact_codes": sorted(entry_fact_codes),
                    "required_observation_roles": sorted(roles),
                }
                for capability_code in content.get("required_capabilities", [])
            ]
            fallback = True
        for definition in definitions:
            capability_code = str(definition["capability_code"])
            fact_codes = {str(item) for item in definition["required_fact_codes"]}
            roles = {str(item) for item in definition["required_observation_roles"]}
            previous = requirements.get(capability_code)
            if previous is not None and (
                previous["fact_codes"] != fact_codes or previous["roles"] != roles
            ):
                raise ContractError(
                    f"capability ontology mismatch across Problem Packs: {capability_code}"
                )
            requirements[capability_code] = {
                "roles": roles,
                "fact_codes": fact_codes,
                "fallback": bool(fallback or (previous or {}).get("fallback", False)),
            }

    available_codes = {
        str(fact.get("fact_code")) for fact in facts
        if isinstance(fact.get("fact_code"), str)
    }
    trusted_roles_by_fact = _trusted_fact_roles(facts, source_registry)
    capabilities: list[dict[str, Any]] = []
    for capability_code in sorted(requirements):
        requirement = requirements[capability_code]
        required_roles = requirement["roles"]
        required_fact_codes = requirement["fact_codes"]
        present_fact_codes = required_fact_codes & available_codes
        missing_fact_codes = sorted(required_fact_codes - available_codes)
        present_roles = sorted(set().union(*[
            trusted_roles_by_fact.get(code, set()) & required_roles
            for code in required_fact_codes
        ])) if required_fact_codes else []
        missing_roles = sorted(required_roles - set(present_roles))
        fact_codes_without_trusted_role = sorted(
            code for code in present_fact_codes
            if not trusted_roles_by_fact.get(code, set()).intersection(required_roles)
        )
        relevant_roles = {capability_code, *required_roles, *required_fact_codes}
        quality_ids = sorted({
            str(issue["quality_issue_id"])
            for issue in quality_issues
            if issue.get("severity") == "blocking"
            and issue.get("normalized_role") in relevant_roles
            and isinstance(issue.get("quality_issue_id"), str)
        })
        reasons: list[str] = []
        if requirement["fallback"]:
            reasons.append("capability_requirement_fallback_to_entry_fact_refs")
        if missing_roles:
            reasons.append("required_source_roles_missing")
        if missing_fact_codes or not required_fact_codes:
            reasons.append("required_facts_missing")
            if requirement["fallback"]:
                reasons.append("required_entry_facts_missing")
        if fact_codes_without_trusted_role:
            reasons.append("required_fact_source_role_missing")
        if not required_fact_codes:
            reasons.append("capability_metric_requirement_unmapped")
        if quality_ids:
            reasons.append("blocking_quality")
        if (
            not missing_roles
            and not missing_fact_codes
            and not fact_codes_without_trusted_role
            and required_fact_codes
            and not quality_ids
        ):
            status = "available"
        elif present_roles or present_fact_codes:
            status = "partial"
        else:
            status = "unsupported"
        identity = {
            "capability_code": capability_code,
            "required_roles": sorted(required_roles),
            "required_fact_codes": sorted(required_fact_codes),
        }
        capabilities.append({
            "capability_id": make_id("capability", identity),
            "capability_code": capability_code,
            "status": status,
            "available_source_roles": present_roles,
            "missing_source_roles": missing_roles,
            "quality_issue_ids": quality_ids,
            "reason_codes": sorted(set(reasons)),
        })
    result = {
        "capability_map_id": make_id("capability_map", capabilities),
        "capabilities": capabilities,
    }
    SchemaStore().validate("capability-map.schema.json", result)
    return result

def build_problem_selection(
    pack_index: RuntimePackIndex,
    facts: Sequence[Mapping[str, Any]],
    signals: Sequence[Mapping[str, Any]],
    capability_map: Mapping[str, Any],
) -> dict[str, Any]:
    capability_by_code = {
        str(item["capability_code"]): item
        for item in capability_map.get("capabilities", [])
    }
    context = ConditionContext(facts=facts, signals=signals, mission={}, hitl={})
    fact_codes = {str(item.get("fact_code")) for item in facts if isinstance(item.get("fact_code"), str)}
    signal_codes = {str(item.get("signal_code")) for item in signals if isinstance(item.get("signal_code"), str)}
    problems: list[dict[str, Any]] = []
    for pack in pack_index.problem_packs:
        content = pack["content"]
        outcomes: list[ConditionResult] = []
        for expression in content["entry_conditions"]:
            outcome = evaluate_condition(expression, context)
            missing_reasons = _missing_entry_presence_reasons(expression, fact_codes, signal_codes)
            if outcome.outcome != "true" and missing_reasons:
                outcome = ConditionResult("not_assessable", tuple(sorted(missing_reasons)))
            outcomes.append(outcome)
        required_capabilities = sorted(set(str(item) for item in content.get("required_capabilities", [])))
        unavailable = [
            code for code in required_capabilities
            if capability_by_code.get(code, {}).get("status") != "available"
        ]
        reasons = {
            reason for outcome in outcomes for reason in outcome.reason_codes
        }
        if any(outcome.outcome == "true" for outcome in outcomes) and not unavailable:
            status = "selected"
        elif any(outcome.outcome in {"true", "not_assessable"} for outcome in outcomes):
            status = "not_assessable"
            if unavailable:
                reasons.add("required_capability_not_available")
        else:
            status = "not_applicable"
        pack_ref = f"{pack['pack_id']}@{pack['pack_version']}"
        problems.append({
            "pack_ref": pack_ref,
            "problem_family_code": str(content["problem_family_code"]),
            "status": status,
            "entry_outcomes": [
                {"outcome": outcome.outcome, "reason_codes": list(outcome.reason_codes)}
                for outcome in outcomes
            ],
            "required_capability_codes": required_capabilities,
            "reason_codes": sorted(reasons),
        })
    body: dict[str, Any] = {
        "domain_ref": pack_index.domain_ref,
        "effective_authority": pack_index.effective_authority,
        "problems": sorted(problems, key=lambda item: item["pack_ref"]),
    }
    for status, field in (
        ("selected", "selected_problem_refs"),
        ("not_assessable", "not_assessable_problem_refs"),
        ("not_applicable", "not_applicable_problem_refs"),
    ):
        body[field] = sorted(item["pack_ref"] for item in problems if item["status"] == status)
    body["selection_id"] = make_id("pack_selection", body)
    body["integrity"] = {"payload_hash": hashlib.sha256(canonical_bytes(body)).hexdigest()}
    return body
