from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any, Mapping, Sequence

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, IntegrityError, RevisionConflict
from trusted_ceo_agent.evidence.core import EvidenceCoreValidator


EVENT_FACT_FIELDS = (
    "party_roles",
    "rights",
    "obligations",
    "resource_and_control",
    "consideration",
    "conditions",
    "event_dates",
    "performance_state",
    "billing_state",
    "payment_state",
    "cancellation_state",
    "amounts",
    "incentives",
    "document_refs",
    "system_event_refs",
)

_BLOCKING_QUALITY_CODES = {
    "ambiguous_unit",
    "ambiguous_period",
    "invalid_decimal",
    "invalid_date",
    "untrusted_formula_value",
}


def _payload_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _unique_by_id(items: Sequence[Mapping[str, Any]], key: str) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in items:
        identifier = str(item[key])
        if identifier in result:
            raise IntegrityError(f"duplicate ID: {identifier}")
        result[identifier] = item
    return result


def _normalize_bindings(field_fact_refs: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    if set(field_fact_refs) != set(EVENT_FACT_FIELDS):
        missing = sorted(set(EVENT_FACT_FIELDS) - set(field_fact_refs))
        extra = sorted(set(field_fact_refs) - set(EVENT_FACT_FIELDS))
        raise ContractError(f"Economic Event bindings differ from contract; missing={missing}, extra={extra}")
    result: dict[str, list[str]] = {}
    for field in EVENT_FACT_FIELDS:
        raw = field_fact_refs[field]
        if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
            raise ContractError(f"Economic Event binding must be a Fact reference array: {field}")
        values: list[str] = []
        for item in raw:
            if not isinstance(item, str) or not item.startswith("fact_"):
                raise ContractError(f"invalid Fact reference in Economic Event binding: {field}")
            values.append(item)
        result[field] = sorted(set(values))
    if not any(result.values()):
        raise ContractError("Economic Event requires at least one source Fact")
    return result


def _fact_closure(fact_id: str, facts: Mapping[str, Mapping[str, Any]]) -> set[str]:
    closure: set[str] = set()
    visiting: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in visiting:
            raise IntegrityError(f"Fact derivation cycle: {identifier}")
        if identifier in closure:
            return
        fact = facts.get(identifier)
        if fact is None:
            raise IntegrityError(f"Fact derivation references unknown Fact: {identifier}")
        visiting.add(identifier)
        derivation = fact.get("derivation")
        if isinstance(derivation, Mapping):
            for input_id in derivation.get("input_fact_ids", []):
                visit(str(input_id))
        visiting.remove(identifier)
        closure.add(identifier)

    visit(fact_id)
    return closure


def _lineage_record(
    fact_id: str,
    *,
    facts: Mapping[str, Mapping[str, Any]],
    sources: Mapping[str, Mapping[str, Any]],
    evidence_links: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], set[str]]:
    closure = _fact_closure(fact_id, facts)
    roots = sorted(identifier for identifier in closure if facts[identifier]["fact_type"] == "observed")
    if not roots:
        raise IntegrityError(f"Fact lineage does not reach an observed Fact: {fact_id}")
    source_lineage: dict[str, set[str]] = {}
    for identifier in sorted(closure):
        for source_ref in facts[identifier]["source_refs"]:
            source_id = str(source_ref["source_id"])
            source = sources.get(source_id)
            if source is None:
                raise IntegrityError(f"Fact references unknown Source: {source_id}")
            if source["access_policy"] == "prohibited":
                raise ContractError(f"prohibited Source cannot materialize an Economic Event: {source_id}")
            source_lineage.setdefault(source_id, set()).add(str(source_ref["lineage_set_ref"]))
    if not source_lineage:
        raise IntegrityError(f"Fact lineage does not reach Source: {fact_id}")
    lineage = [{
        "source_id": source_id,
        "source_sha256": str(sources[source_id]["sha256"]),
        "lineage_set_refs": sorted(lineage_refs),
    } for source_id, lineage_refs in sorted(source_lineage.items())]
    linked = sorted({
        str(item["evidence_link_id"])
        for item in evidence_links
        if item.get("evidence_kind") == "fact" and str(item.get("evidence_ref")) in closure
    })
    return {
        "fact_ref": fact_id,
        "root_fact_refs": roots,
        "sources": lineage,
        "evidence_link_refs": linked,
    }, closure


def _validate_fact_quality_and_units(
    fact: Mapping[str, Any],
    *,
    is_amount: bool,
    quality: Mapping[str, Mapping[str, Any]],
) -> None:
    value = fact["value"]
    if value["value_type"] in {"decimal", "integer"}:
        if not value.get("unit_code") or not value.get("scale"):
            raise ContractError(f"numeric Fact lacks an explicit unit or scale: {fact['fact_id']}")
    if is_amount and not value.get("currency_code"):
        raise ContractError(f"amount Fact lacks an explicit currency: {fact['fact_id']}")
    for issue_id in fact["quality"]:
        issue = quality[issue_id]
        unresolved = issue["resolution_status"] == "open"
        if unresolved and (
            issue["severity"] == "blocking" or issue["issue_code"] in _BLOCKING_QUALITY_CODES
        ):
            raise ContractError(f"blocking Data Quality issue prevents Event materialization: {issue_id}")


def materialize_economic_event(
    *,
    evidence_core: Mapping[str, Any],
    expected_revision: int,
    expected_artifact_hash: str,
    event_type: str,
    field_fact_refs: Mapping[str, Sequence[str]],
    schema_store: SchemaStore | None = None,
) -> dict[str, Any]:
    """Materialize a domain-neutral Event from pinned, validated Fact lineage only."""
    schemas = schema_store or SchemaStore()
    EvidenceCoreValidator(schemas).validate(evidence_core)
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        raise ContractError("expected_revision must be an integer")
    envelope = evidence_core["envelope"]
    actual_revision = int(envelope["revision"])
    if actual_revision != expected_revision:
        raise RevisionConflict(
            f"stale Evidence Core revision: expected {expected_revision}, current {actual_revision}"
        )
    if str(envelope["artifact_hash"]) != expected_artifact_hash:
        raise IntegrityError("Evidence Core artifact hash differs from pinned input")
    if not isinstance(event_type, str) or not event_type:
        raise ContractError("event_type must be a non-empty string")

    normalized = _normalize_bindings(field_fact_refs)
    facts = _unique_by_id(evidence_core["fact_register"], "fact_id")
    sources = _unique_by_id(evidence_core["source_registry"], "source_id")
    quality = _unique_by_id(evidence_core["data_quality_register"], "quality_issue_id")
    selected_fact_ids = sorted({item for refs in normalized.values() for item in refs})
    unknown = sorted(set(selected_fact_ids) - set(facts))
    if unknown:
        raise ContractError(f"Economic Event references unknown Facts: {unknown}")

    for fact_id in selected_fact_ids:
        _validate_fact_quality_and_units(
            facts[fact_id], is_amount=fact_id in normalized["amounts"], quality=quality
        )

    source_lineage: list[dict[str, Any]] = []
    closure: set[str] = set()
    for fact_id in selected_fact_ids:
        record, fact_closure = _lineage_record(
            fact_id,
            facts=facts,
            sources=sources,
            evidence_links=evidence_core["evidence_links"],
        )
        source_lineage.append(record)
        closure.update(fact_closure)
    quality_refs = sorted({
        str(issue_id)
        for identifier in closure
        for issue_id in facts[identifier]["quality"]
    })
    for identifier in closure:
        _validate_fact_quality_and_units(
            facts[identifier],
            is_amount=identifier in normalized["amounts"],
            quality=quality,
        )

    identity = {"event_type": event_type, "field_fact_refs": normalized}
    input_contract = {
        **identity,
        "evidence_core_artifact_hash": expected_artifact_hash,
        "evidence_core_payload_hash": evidence_core["integrity"]["payload_hash"],
        "revision": actual_revision,
    }
    body = {
        "schema_version": "1.0.0",
        "event_id": make_id("event", identity),
        "event_type": event_type,
        "base_revision": actual_revision,
        "evidence_core_ref": {
            "artifact_id": str(envelope["artifact_id"]),
            "artifact_hash": expected_artifact_hash,
            "payload_hash": str(evidence_core["integrity"]["payload_hash"]),
            "revision": actual_revision,
        },
        **deepcopy(normalized),
        "fact_refs": selected_fact_ids,
        "source_lineage": sorted(source_lineage, key=lambda item: item["fact_ref"]),
        "data_quality_refs": quality_refs,
        "materialization": {
            "producer": "deterministic_component",
            "input_hash": _payload_hash(input_contract),
        },
    }
    result = {**body, "integrity": {"payload_hash": _payload_hash(body)}}
    schemas.validate("economic-event.schema.json", result)
    return result
