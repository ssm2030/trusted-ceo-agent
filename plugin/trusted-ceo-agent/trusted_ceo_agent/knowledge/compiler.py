from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


CARD_SCHEMAS = {
    "method_card": "method-card.schema.json",
    "norm_card": "norm-card.schema.json",
    "expectation_card": "expectation-card.schema.json",
    "procedure_card": "procedure-card.schema.json",
    "counter_hypothesis_card": "counter-hypothesis-card.schema.json",
    "cross_domain_trigger_card": "cross-domain-trigger-card.schema.json",
}
DEPTH_SLOT_TYPES = {
    "D1": "event_population",
    "D2": "impact",
    "D3": "expectation",
    "D4": "hypothesis_set",
    "D5": "norm",
    "D6": "procedure",
    "D7": "evidence_counter_evidence",
    "D8": "quantification",
    "D9": "action_candidates",
    "D10": "cross_domain_trigger",
    "D11": "limits_authority",
    "D12": "oracle_cases",
}
REQUIRED_ORACLE_CASE_TYPES = (
    "normal",
    "clear_error",
    "boundary",
    "counter_evidence",
    "missing_data",
    "mapping_error",
    "compound",
    "same_signal_different_cause",
    "cross_domain_conflict",
)
_FORBIDDEN_REASONING_KEYS = frozenset(
    {
        "chain_of_thought",
        "chainofthought",
        "hidden_reasoning",
        "private_reasoning",
        "reasoning_trace",
        "internal_monologue",
        "thoughts",
    }
)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def hash_without(value: Mapping[str, Any], field: str) -> str:
    body = copy.deepcopy(dict(value))
    body.pop(field, None)
    return digest(body)


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value


def _require_hash(value: Any, field: str) -> str:
    text = _require_text(value, field)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ContractError(f"{field} must be a lowercase SHA-256")
    return text


def _assert_no_hidden_reasoning(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower().replace("-", "_").replace(" ", "_")
            if normalized in _FORBIDDEN_REASONING_KEYS:
                raise ContractError(f"hidden chain-of-thought field is forbidden: {path}.{key}")
            _assert_no_hidden_reasoning(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_no_hidden_reasoning(child, f"{path}[{index}]")


def _sorted_unique_strings(values: Sequence[str], field: str, *, required: bool = False) -> list[str]:
    if not isinstance(values, (list, tuple)):
        raise ContractError(f"{field} must be an array")
    result = sorted({_require_text(value, field) for value in values})
    if required and not result:
        raise ContractError(f"{field} must not be empty")
    return result


def _normalize_sources(values: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(values, (list, tuple)) or not values:
        raise ContractError("source_refs must not be empty")
    result: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise ContractError("source_refs entries must be objects")
        result.append(
            {
                "source_id": _require_text(value.get("source_id"), "source_id"),
                "source_type": _require_text(value.get("source_type"), "source_type"),
                "retrieval": _require_text(value.get("retrieval"), "retrieval"),
                "locator": _require_text(value.get("locator"), "locator"),
                "source_hash": _require_hash(value.get("source_hash"), "source_hash"),
                "verified_hash": _require_hash(value.get("verified_hash"), "verified_hash"),
                "approved": value.get("approved"),
            }
        )
    result.sort(key=lambda item: (item["source_id"], item["locator"], item["source_hash"]))
    if len({canonical_bytes(item) for item in result}) != len(result):
        raise ContractError("source_refs contains duplicates")
    return result


def compile_card(
    *,
    artifact_type: str,
    domain: str,
    issue_family_id: str,
    version: int,
    status: str,
    trust_level: str,
    jurisdiction: str,
    effective_from: str,
    effective_to: str | None,
    source_refs: Sequence[Mapping[str, Any]],
    author: str,
    reviewer_refs: Sequence[str],
    created_at: str,
    supersedes: str | None,
    test_refs: Sequence[str],
    content: Mapping[str, Any],
) -> dict[str, Any]:
    if artifact_type not in CARD_SCHEMAS:
        raise ContractError(f"unsupported professional card type: {artifact_type}")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ContractError("version must be an integer >= 1")
    if not isinstance(content, Mapping):
        raise ContractError("content must be an object")
    _assert_no_hidden_reasoning(content)
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_type": artifact_type,
        "domain": _require_text(domain, "domain"),
        "issue_family_id": _require_text(issue_family_id, "issue_family_id"),
        "version": version,
        "status": _require_text(status, "status"),
        "trust_level": _require_text(trust_level, "trust_level"),
        "jurisdiction": _require_text(jurisdiction, "jurisdiction"),
        "effective_from": _require_text(effective_from, "effective_from"),
        "effective_to": effective_to,
        "source_refs": _normalize_sources(source_refs),
        "author": _require_text(author, "author"),
        "reviewer_refs": _sorted_unique_strings(reviewer_refs, "reviewer_refs"),
        "created_at": _require_text(created_at, "created_at"),
        "supersedes": supersedes,
        "test_refs": _sorted_unique_strings(test_refs, "test_refs"),
        "content": copy.deepcopy(dict(content)),
    }
    body["artifact_id"] = "knowledge_" + digest(body)[:24]
    body["content_hash"] = hash_without(body, "content_hash")
    verify_card(body)
    return body


def verify_card(card: Mapping[str, Any]) -> None:
    if not isinstance(card, Mapping):
        raise ContractError("knowledge card must be an object")
    value = copy.deepcopy(dict(card))
    _assert_no_hidden_reasoning(value)
    artifact_type = value.get("artifact_type")
    if artifact_type not in CARD_SCHEMAS:
        raise ContractError(f"unsupported professional card type: {artifact_type}")
    SchemaStore().validate(CARD_SCHEMAS[str(artifact_type)], value)
    if value["content_hash"] != hash_without(value, "content_hash"):
        raise ContractError("knowledge card content_hash is invalid")


def artifact_ref(card: Mapping[str, Any]) -> dict[str, str]:
    verify_card(card)
    return {
        "ref_id": str(card["artifact_id"]),
        "ref_type": str(card["artifact_type"]),
        "content_hash": str(card["content_hash"]),
    }


def depth_slot(slot_id: str, cards: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if slot_id not in DEPTH_SLOT_TYPES:
        raise ContractError(f"unsupported depth slot: {slot_id}")
    refs = [artifact_ref(card) for card in cards]
    refs.sort(key=lambda item: (item["ref_type"], item["ref_id"], item["content_hash"]))
    if not refs:
        raise ContractError(f"{slot_id} must reference at least one knowledge card")
    if len({canonical_bytes(item) for item in refs}) != len(refs):
        raise ContractError(f"{slot_id} contains duplicate artifact refs")
    return {"slot_type": DEPTH_SLOT_TYPES[slot_id], "artifact_refs": refs}


def compile_issue_family(
    *,
    issue_family_id: str,
    domain: str,
    industry_scope: str,
    jurisdiction: str,
    effective_from: str,
    effective_to: str | None,
    risk_level: str,
    pack_id: str,
    pack_version: str,
    pack_hash: str,
    pack_authority: str,
    depth_slots: Mapping[str, Mapping[str, Any]],
    required_test_case_types: Sequence[str],
    not_assessable_conditions: Sequence[str],
) -> dict[str, Any]:
    slots = {key: copy.deepcopy(dict(value)) for key, value in sorted(depth_slots.items())}
    for slot_id, value in slots.items():
        if slot_id in DEPTH_SLOT_TYPES and value.get("slot_type") != DEPTH_SLOT_TYPES[slot_id]:
            raise ContractError(f"{slot_id} has the wrong typed slot")
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "issue_family_id": _require_text(issue_family_id, "issue_family_id"),
        "domain": _require_text(domain, "domain"),
        "industry_scope": _require_text(industry_scope, "industry_scope"),
        "jurisdiction": _require_text(jurisdiction, "jurisdiction"),
        "effective_from": _require_text(effective_from, "effective_from"),
        "effective_to": effective_to,
        "risk_level": _require_text(risk_level, "risk_level"),
        "pack_id": _require_text(pack_id, "pack_id"),
        "pack_version": _require_text(pack_version, "pack_version"),
        "pack_hash": _require_hash(pack_hash, "pack_hash"),
        "pack_authority": _require_text(pack_authority, "pack_authority"),
        "depth_slots": slots,
        "required_test_case_types": _sorted_unique_strings(
            required_test_case_types, "required_test_case_types", required=True
        ),
        "not_assessable_conditions": _sorted_unique_strings(
            not_assessable_conditions, "not_assessable_conditions", required=True
        ),
    }
    body["family_hash"] = hash_without(body, "family_hash")
    verify_issue_family(body)
    return body


def verify_issue_family(issue_family: Mapping[str, Any]) -> None:
    if not isinstance(issue_family, Mapping):
        raise ContractError("issue family must be an object")
    value = copy.deepcopy(dict(issue_family))
    _assert_no_hidden_reasoning(value)
    SchemaStore().validate("issue-family.schema.json", value)
    if value["family_hash"] != hash_without(value, "family_hash"):
        raise ContractError("issue family hash is invalid")
    for slot_id, slot_type in DEPTH_SLOT_TYPES.items():
        if value["depth_slots"][slot_id]["slot_type"] != slot_type:
            raise ContractError(f"{slot_id} has the wrong typed slot")


def compile_issue_evidence_packet(
    *,
    issue_family: Mapping[str, Any],
    run_id: str,
    revision: int,
    fact_refs: Sequence[str],
    signal_refs: Sequence[str],
    coverage_refs: Sequence[str],
    procedure_run_refs: Sequence[str],
    supporting_evidence_refs: Sequence[str],
    counter_evidence_refs: Sequence[str],
    missing_evidence_roles: Sequence[str],
    prohibited_conclusions: Sequence[str],
    expert_triggers: Sequence[str],
) -> dict[str, Any]:
    verify_issue_family(issue_family)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ContractError("revision must be an integer >= 0")
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "issue_family_id": issue_family["issue_family_id"],
        "run_id": _require_text(run_id, "run_id"),
        "revision": revision,
        "family_hash": issue_family["family_hash"],
        "pack_id": issue_family["pack_id"],
        "pack_hash": issue_family["pack_hash"],
        "fact_refs": _sorted_unique_strings(fact_refs, "fact_refs", required=True),
        "signal_refs": _sorted_unique_strings(signal_refs, "signal_refs"),
        "coverage_refs": _sorted_unique_strings(coverage_refs, "coverage_refs", required=True),
        "procedure_run_refs": _sorted_unique_strings(procedure_run_refs, "procedure_run_refs"),
        "supporting_evidence_refs": _sorted_unique_strings(
            supporting_evidence_refs, "supporting_evidence_refs"
        ),
        "counter_evidence_refs": _sorted_unique_strings(
            counter_evidence_refs, "counter_evidence_refs"
        ),
        "missing_evidence_roles": _sorted_unique_strings(
            missing_evidence_roles, "missing_evidence_roles"
        ),
        "prohibited_conclusions": _sorted_unique_strings(
            prohibited_conclusions, "prohibited_conclusions", required=True
        ),
        "expert_triggers": _sorted_unique_strings(expert_triggers, "expert_triggers"),
    }
    body["packet_id"] = "issue_packet_" + digest(body)[:24]
    body["packet_hash"] = hash_without(body, "packet_hash")
    SchemaStore().validate("issue-evidence-packet.schema.json", body)
    return body
