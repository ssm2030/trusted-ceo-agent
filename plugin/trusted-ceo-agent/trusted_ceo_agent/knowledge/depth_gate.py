from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.knowledge.compiler import (
    CARD_SCHEMAS,
    DEPTH_SLOT_TYPES,
    REQUIRED_ORACLE_CASE_TYPES,
    digest,
    hash_without,
    verify_card,
)
from trusted_ceo_agent.knowledge.registry import KnowledgeRegistry
from trusted_ceo_agent.knowledge.resolver import applicability_blockers, covers_date


_TRUST_ORDER = {
    "machine_draft": 0,
    "source_grounded": 1,
    "synthetic_tested": 2,
    "poc_stable": 3,
    "expert_reviewed": 4,
    "full": 5,
}
_AUTHORITY_ORDER = {"machine_draft": 0, "boundary": 1, "provisional": 2, "full": 3}
_KNOWLEDGE_AUTHORITY = {
    "machine_draft": "machine_draft",
    "source_grounded": "boundary",
    "synthetic_tested": "provisional",
    "poc_stable": "provisional",
    "expert_reviewed": "provisional",
    "full": "full",
}
_PRODUCT_DISPLAY = {
    "machine_draft": "machine_draft",
    "boundary": "Boundary",
    "provisional": "Provisional",
    "full": "Full",
}
_REQUIRED_CARD_TYPES = frozenset(CARD_SCHEMAS)
_ALLOWED_CARD_TYPES = {
    "D1": frozenset({"method_card", "procedure_card"}),
    "D2": frozenset({"method_card", "expectation_card"}),
    "D3": frozenset({"expectation_card"}),
    "D4": frozenset({"counter_hypothesis_card", "method_card"}),
    "D5": frozenset({"norm_card"}),
    "D6": frozenset({"procedure_card"}),
    "D7": frozenset({"counter_hypothesis_card", "procedure_card"}),
    "D8": frozenset({"procedure_card", "expectation_card"}),
    "D9": frozenset({"method_card", "procedure_card"}),
    "D10": frozenset({"cross_domain_trigger_card"}),
    "D11": frozenset({"method_card", "norm_card"}),
    "D12": frozenset({"procedure_card", "counter_hypothesis_card"}),
}


def _artifact_mapping(
    artifacts: KnowledgeRegistry | Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    if isinstance(artifacts, KnowledgeRegistry):
        return {
            str(item["artifact_id"]): item
            for item in artifacts.find()
        }
    if isinstance(artifacts, Mapping):
        return {
            str(key): copy.deepcopy(dict(value))
            for key, value in artifacts.items()
            if isinstance(value, Mapping)
        }
    if isinstance(artifacts, (list, tuple)):
        result: dict[str, dict[str, Any]] = {}
        for value in artifacts:
            if not isinstance(value, Mapping):
                raise ContractError("knowledge artifacts must be objects")
            artifact_id = str(value.get("artifact_id", ""))
            if not artifact_id:
                raise ContractError("knowledge artifact is missing artifact_id")
            if artifact_id in result:
                raise ContractError(f"duplicate knowledge artifact: {artifact_id}")
            result[artifact_id] = copy.deepcopy(dict(value))
        return result
    raise ContractError("artifacts must be a KnowledgeRegistry, mapping, or sequence")


def _minimum_authority(values: Sequence[str]) -> str:
    return min(values, key=lambda item: _AUTHORITY_ORDER[item])


def _expert_gate(
    approval: Mapping[str, Any] | None,
    *,
    issue_family_id: str,
    domain: str,
    jurisdiction: str,
    risk_level: str,
) -> tuple[str, set[str]]:
    blockers: set[str] = set()
    if not isinstance(approval, Mapping) or approval.get("approved") is not True:
        blockers.add("expert_approval_missing")
        return "provisional", blockers
    if approval.get("issue_family_id") != issue_family_id:
        blockers.add("expert_issue_family_mismatch")
    if approval.get("domain") != domain:
        blockers.add("expert_domain_mismatch")
    if approval.get("jurisdiction") != jurisdiction:
        blockers.add("expert_jurisdiction_mismatch")
    if not isinstance(approval.get("reviewer_id"), str) or not approval["reviewer_id"].strip():
        blockers.add("expert_identity_missing")
    if not isinstance(approval.get("reviewer_role"), str) or not approval["reviewer_role"].strip():
        blockers.add("expert_role_missing")
    if risk_level in {"high", "disputed"} and approval.get("independent_second_review") is not True:
        blockers.add("independent_second_review_missing")
    return ("full" if not blockers else "provisional"), blockers


def _release_gate(
    release: Mapping[str, Any] | None,
    *,
    effective_on: str,
    referenced_hashes: set[str],
) -> tuple[str, set[str], set[str]]:
    full_blockers: set[str] = set()
    hard_blockers: set[str] = set()
    if release is None:
        full_blockers.add("knowledge_release_missing")
        return "provisional", full_blockers, hard_blockers
    if not isinstance(release, Mapping):
        hard_blockers.add("knowledge_release_contract_invalid")
        return "provisional", full_blockers, hard_blockers
    value = copy.deepcopy(dict(release))
    try:
        SchemaStore().validate("knowledge-release-gate.schema.json", value)
    except ContractError:
        hard_blockers.add("knowledge_release_contract_invalid")
        return "provisional", full_blockers, hard_blockers
    if value["status"] != "active":
        hard_blockers.add(f"knowledge_release_{value['status']}")
    if value["quality_gate_passed"] is not True:
        full_blockers.add("release_quality_gate_failed")
    if value["release_manager_approved"] is not True:
        full_blockers.add("release_manager_approval_missing")
    try:
        in_period = covers_date(
            effective_from=value["effective_from"],
            effective_to=value["effective_to"],
            effective_on=effective_on,
        )
    except ContractError:
        in_period = False
    if not in_period:
        hard_blockers.add("release_effective_period_gap")
    omitted = referenced_hashes - set(value["artifact_hashes"])
    for artifact_hash in sorted(omitted):
        full_blockers.add(f"release_artifact_missing:{artifact_hash}")
    authority = (
        "full"
        if not full_blockers and not hard_blockers
        else "provisional"
    )
    return authority, full_blockers, hard_blockers


def assess_professional_depth(
    issue_family: Mapping[str, Any],
    artifacts: KnowledgeRegistry | Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    effective_on: str,
    jurisdiction: str,
    industry_scope: str,
    expert_approval: Mapping[str, Any] | None = None,
    release: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(issue_family, Mapping):
        raise ContractError("issue family must be an object")
    family = copy.deepcopy(dict(issue_family))
    artifact_by_id = _artifact_mapping(artifacts)
    hard_blockers: set[str] = set()
    full_blockers: set[str] = set()

    issue_family_id = str(family.get("issue_family_id") or "unknown")
    domain = str(family.get("domain") or "unknown")
    family_jurisdiction = str(family.get("jurisdiction") or "unknown")
    family_industry = str(family.get("industry_scope") or "unknown")
    family_hash = str(family.get("family_hash") or ("0" * 64))
    risk_level = str(family.get("risk_level") or "standard")
    pack_authority = str(family.get("pack_authority") or "boundary")
    if pack_authority not in {"boundary", "provisional", "full"}:
        hard_blockers.add("pack_authority_invalid")
        pack_authority = "boundary"

    try:
        SchemaStore().validate("issue-family.schema.json", family)
    except ContractError:
        hard_blockers.add("issue_family_contract_invalid")
    if family.get("family_hash") != hash_without(family, "family_hash"):
        hard_blockers.add("issue_family_hash_invalid")
    if family_jurisdiction != jurisdiction:
        hard_blockers.add("family_jurisdiction_mismatch")
    if family_industry != industry_scope:
        hard_blockers.add("family_industry_scope_mismatch")
    try:
        family_in_period = covers_date(
            effective_from=family.get("effective_from"),
            effective_to=family.get("effective_to"),
            effective_on=effective_on,
        )
    except ContractError:
        family_in_period = False
    if not family_in_period:
        hard_blockers.add("family_effective_period_gap")

    slots = family.get("depth_slots")
    if not isinstance(slots, Mapping):
        slots = {}
        hard_blockers.add("depth_slots_missing")
    slot_status: dict[str, bool] = {}
    referenced_ids: set[str] = set()
    referenced_hashes: set[str] = set()
    referenced_types: set[str] = set()
    trust_levels: list[str] = []

    for slot_id, expected_slot_type in DEPTH_SLOT_TYPES.items():
        slot_valid = True
        slot = slots.get(slot_id)
        if not isinstance(slot, Mapping):
            hard_blockers.add(f"missing_depth_slot:{slot_id}")
            slot_status[slot_id] = False
            continue
        if slot.get("slot_type") != expected_slot_type:
            hard_blockers.add(f"depth_slot_type_mismatch:{slot_id}")
            slot_valid = False
        refs = slot.get("artifact_refs")
        if not isinstance(refs, (list, tuple)) or not refs:
            hard_blockers.add(f"depth_slot_refs_missing:{slot_id}")
            slot_status[slot_id] = False
            continue
        for ref in refs:
            if not isinstance(ref, Mapping):
                hard_blockers.add(f"depth_ref_contract_invalid:{slot_id}")
                slot_valid = False
                continue
            artifact_id = str(ref.get("ref_id") or "unknown")
            artifact_type = str(ref.get("ref_type") or "unknown")
            if artifact_type not in _ALLOWED_CARD_TYPES[slot_id]:
                hard_blockers.add(f"depth_ref_type_not_allowed:{slot_id}:{artifact_type}")
                slot_valid = False
            artifact = artifact_by_id.get(artifact_id)
            if artifact is None:
                hard_blockers.add(f"knowledge_artifact_missing:{artifact_id}")
                slot_valid = False
                continue
            try:
                verify_card(artifact)
            except ContractError:
                hard_blockers.add(f"knowledge_artifact_contract_invalid:{artifact_id}")
                slot_valid = False
                continue
            if artifact["artifact_type"] != artifact_type:
                hard_blockers.add(f"knowledge_artifact_type_mismatch:{artifact_id}")
                slot_valid = False
            if artifact["content_hash"] != ref.get("content_hash"):
                hard_blockers.add(f"knowledge_artifact_hash_mismatch:{artifact_id}")
                slot_valid = False
            if artifact["issue_family_id"] != issue_family_id:
                hard_blockers.add(f"knowledge_issue_family_mismatch:{artifact_id}")
                slot_valid = False
            if artifact["domain"] != domain:
                hard_blockers.add(f"knowledge_domain_mismatch:{artifact_id}")
                slot_valid = False
            card_blockers = applicability_blockers(
                artifact, jurisdiction=jurisdiction, effective_on=effective_on
            )
            if card_blockers:
                hard_blockers.update(card_blockers)
                slot_valid = False
            referenced_ids.add(artifact_id)
            referenced_hashes.add(str(artifact["content_hash"]))
            referenced_types.add(str(artifact["artifact_type"]))
            trust_level = str(artifact["trust_level"])
            if trust_level not in _TRUST_ORDER:
                hard_blockers.add(f"knowledge_trust_invalid:{artifact_id}")
                trust_level = "machine_draft"
            trust_levels.append(trust_level)
        slot_status[slot_id] = slot_valid

    for card_type in sorted(_REQUIRED_CARD_TYPES - referenced_types):
        hard_blockers.add(f"required_card_missing:{card_type}")
    oracle_types = set(family.get("required_test_case_types") or ())
    for case_type in sorted(set(REQUIRED_ORACLE_CASE_TYPES) - oracle_types):
        hard_blockers.add(f"oracle_case_missing:{case_type}")

    knowledge_trust = (
        min(trust_levels, key=lambda value: _TRUST_ORDER[value])
        if trust_levels
        else "machine_draft"
    )
    knowledge_authority = _KNOWLEDGE_AUTHORITY[knowledge_trust]
    if knowledge_authority == "machine_draft":
        hard_blockers.add("knowledge_trust_not_activatable")
    if knowledge_authority != "full":
        full_blockers.add(f"knowledge_trust_below_full:{knowledge_trust}")
    if pack_authority != "full":
        full_blockers.add(f"pack_authority_below_full:{pack_authority}")

    expert_authority, expert_blockers = _expert_gate(
        expert_approval,
        issue_family_id=issue_family_id,
        domain=domain,
        jurisdiction=jurisdiction,
        risk_level=risk_level,
    )
    full_blockers.update(expert_blockers)
    release_authority, release_blockers, release_hard_blockers = _release_gate(
        release, effective_on=effective_on, referenced_hashes=referenced_hashes
    )
    full_blockers.update(release_blockers)
    hard_blockers.update(release_hard_blockers)

    if hard_blockers:
        effective_authority = "machine_draft"
    else:
        effective_authority = _minimum_authority(
            [
                knowledge_authority,
                pack_authority,
                expert_authority,
                release_authority,
            ]
        )
    activation_allowed = (
        not hard_blockers
        and _AUTHORITY_ORDER[effective_authority] >= _AUTHORITY_ORDER["boundary"]
    )
    full_allowed = activation_allowed and effective_authority == "full"
    blockers = sorted(hard_blockers | full_blockers)

    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "issue_family_id": issue_family_id,
        "domain": domain,
        "jurisdiction": jurisdiction,
        "industry_scope": industry_scope,
        "effective_on": effective_on,
        "family_hash": family_hash,
        "slot_status": {slot_id: slot_status.get(slot_id, False) for slot_id in DEPTH_SLOT_TYPES},
        "referenced_artifact_ids": sorted(referenced_ids),
        "authority_inputs": {
            "knowledge_trust": knowledge_trust,
            "knowledge_authority": knowledge_authority,
            "pack_authority": pack_authority,
            "expert_authority": expert_authority,
            "release_authority": release_authority,
        },
        "effective_authority": effective_authority,
        "product_display": _PRODUCT_DISPLAY[effective_authority],
        "activation_allowed": activation_allowed,
        "full_allowed": full_allowed,
        "blockers": blockers,
    }
    body["assessment_id"] = "depth_assessment_" + digest(body)[:24]
    body["assessment_hash"] = hash_without(body, "assessment_hash")
    verify_professional_depth_assessment(body)
    return body


def verify_professional_depth_assessment(assessment: Mapping[str, Any]) -> None:
    value = copy.deepcopy(dict(assessment))
    SchemaStore().validate("professional-depth-assessment.schema.json", value)
    if value["assessment_hash"] != hash_without(value, "assessment_hash"):
        raise ContractError("professional depth assessment hash is invalid")
    if value["full_allowed"] and value["effective_authority"] != "full":
        raise ContractError("Full cannot be allowed below full effective authority")
    if value["activation_allowed"] and not all(value["slot_status"].values()):
        raise ContractError("activation cannot bypass an incomplete D1-D12 slot")


def require_authority(assessment: Mapping[str, Any], requested_authority: str) -> None:
    verify_professional_depth_assessment(assessment)
    if requested_authority not in _AUTHORITY_ORDER:
        raise ContractError(f"unsupported requested authority: {requested_authority}")
    if not assessment["activation_allowed"]:
        raise ContractError("professional knowledge activation is blocked")
    if _AUTHORITY_ORDER[str(assessment["effective_authority"])] < _AUTHORITY_ORDER[
        requested_authority
    ]:
        raise ContractError(
            f"requested {requested_authority} exceeds effective authority "
            f"{assessment['effective_authority']}"
        )
