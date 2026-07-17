from __future__ import annotations

from typing import Any, Mapping, Sequence

from trusted_ceo_agent.contracts.condition_dsl import ConditionContext, evaluate_condition
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.packs.models import DomainSelection, LoadedPack


def _matches_domain(pack: LoadedPack, mission: Mapping[str, Any], data_profile: Mapping[str, Any]) -> bool:
    applicability = pack.document["applicability"]
    business_models = set(applicability["business_models"])
    industries = set(applicability["industries"])
    excluded = set(applicability["excluded_industries"])
    business_model = mission.get("business_model")
    industry = data_profile.get("industry")
    if business_models and business_model not in business_models:
        return False
    if industry not in {None, ""}:
        if industries and industry not in industries:
            return False
        if industry in excluded:
            return False
    return True


def select_domain(
    packs: Sequence[LoadedPack], mission: Mapping[str, Any], data_profile: Mapping[str, Any]
) -> DomainSelection:
    domains = [pack for pack in packs if pack.pack_type == "domain"]
    boundary = next((pack for pack in domains if pack.pack_id == "generic-business-boundary"), None)
    candidates = [
        pack for pack in domains
        if pack.pack_id != "generic-business-boundary" and _matches_domain(pack, mission, data_profile)
    ]
    if len(candidates) == 1:
        return DomainSelection("selected", candidates[0], (candidates[0].ref,))
    if len(candidates) > 1:
        return DomainSelection(
            "data_confirmation_required",
            sorted(candidates, key=lambda pack: pack.ref)[0],
            tuple(sorted(pack.ref for pack in candidates)),
            ("ambiguous_domain",),
        )
    if boundary is None:
        raise ContractError("generic business Boundary Pack is missing")
    return DomainSelection("boundary", boundary, (), ("unsupported_domain",))


def select_problem_packs(
    packs: Sequence[LoadedPack], domain_ref: str, context: ConditionContext
) -> tuple[LoadedPack, ...]:
    selected: list[LoadedPack] = []
    for pack in packs:
        if pack.pack_type != "problem":
            continue
        content = pack.document["content"]
        if domain_ref not in content["domain_pack_refs"]:
            continue
        outcomes = [evaluate_condition(expression, context).outcome for expression in content["entry_conditions"]]
        if any(outcome == "true" for outcome in outcomes):
            selected.append(pack)
    return tuple(sorted(selected, key=lambda pack: pack.ref))


def threshold_values(domain_pack: LoadedPack) -> dict[str, str]:
    if domain_pack.pack_type != "domain":
        raise ValueError("threshold values require a Domain Pack")
    return {
        str(item["threshold_id"]): str(item["value"])
        for item in domain_pack.document["content"]["threshold_definitions"]
        if item.get("value") is not None
    }
