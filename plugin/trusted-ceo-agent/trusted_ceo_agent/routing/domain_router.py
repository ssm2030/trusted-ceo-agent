from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import datetime
from typing import Any, Mapping, Sequence

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, IntegrityError, RevisionConflict


REGISTERED_DOMAINS = ("accounting", "labor", "legal", "tax")
CANDIDATE_SOURCES = (
    "mandatory_baseline",
    "mission_requested",
    "event_data_account",
    "deterministic_signal",
    "cross_domain_trigger",
    "ai_proposed",
)
SCREEN_STATUSES = {
    "not_applicable",
    "triggered",
    "possible_missing_data",
    "unsupported_pack",
    "expert_review_required",
}
_SCREEN_FIELDS = {
    "domain",
    "status",
    "trigger_card_refs",
    "fact_refs",
    "signal_refs",
    "missing_capability_refs",
    "routing_reason_codes",
    "estimated_cost_class",
}
_CATALOG_FIELDS = {
    "pack_ref",
    "domain",
    "pack_sha256",
    "effective_authority",
    "jurisdictions",
    "valid_from",
    "valid_to",
}
_EXPERT_ROLES = {
    "accounting": "senior_accountant",
    "labor": "labor_specialist",
    "legal": "licensed_attorney",
    "tax": "tax_accountant",
}
_AUTHORITY_RANK = {"machine_draft": 0, "boundary": 1, "provisional": 2, "full": 3}


def _hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _timestamp(value: str, field: str) -> datetime:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(f"{field} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{field} must include a timezone")
    return parsed


def _normalize_string_set(value: Any, field: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ContractError(f"{field} must be an array")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ContractError(f"{field} contains an invalid reference")
        result.append(item)
    return sorted(set(result))


def _validate_event(
    event: Mapping[str, Any],
    *,
    expected_revision: int,
    expected_event_hash: str,
    schemas: SchemaStore,
) -> None:
    schemas.validate("economic-event.schema.json", event)
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        raise ContractError("expected_revision must be an integer")
    if int(event["base_revision"]) != expected_revision:
        raise RevisionConflict(
            f"stale Economic Event revision: expected {expected_revision}, current {event['base_revision']}"
        )
    body = {key: deepcopy(value) for key, value in event.items() if key != "integrity"}
    actual_hash = _hash(body)
    if event["integrity"]["payload_hash"] != actual_hash:
        raise IntegrityError("Economic Event payload hash mismatch")
    if expected_event_hash != actual_hash:
        raise IntegrityError("Economic Event hash differs from pinned input")


def _manifest_index(pack_manifest: Mapping[str, Any], schemas: SchemaStore) -> dict[str, Mapping[str, Any]]:
    schemas.validate("pack-manifest.schema.json", pack_manifest)
    body = {"schema_version": pack_manifest["schema_version"], "packs": pack_manifest["packs"]}
    if pack_manifest["manifest_hash"] != _hash(body):
        raise IntegrityError("Pack manifest hash mismatch")
    result: dict[str, Mapping[str, Any]] = {}
    for entry in pack_manifest["packs"]:
        ref = f"{entry['pack_id']}@{entry['pack_version']}"
        if ref in result:
            raise IntegrityError(f"duplicate Pack ref in manifest: {ref}")
        result[ref] = entry
    return result


def _catalog_index(
    pack_catalog: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for raw in pack_catalog:
        if not isinstance(raw, Mapping) or set(raw) != _CATALOG_FIELDS:
            raise ContractError("Pack routing catalog entry differs from its closed contract")
        entry = deepcopy(dict(raw))
        ref = entry["pack_ref"]
        if not isinstance(ref, str) or ref in result:
            raise IntegrityError(f"duplicate or invalid Pack catalog ref: {ref}")
        manifest_entry = manifest.get(ref)
        if manifest_entry is None:
            raise IntegrityError(f"Pack catalog entry is absent from manifested snapshots: {ref}")
        if entry["pack_sha256"] != manifest_entry["pack_sha256"]:
            raise IntegrityError(f"Pack catalog hash differs from manifest: {ref}")
        if entry["effective_authority"] != manifest_entry["effective_authority"]:
            raise IntegrityError(f"Pack catalog authority differs from manifest: {ref}")
        if entry["domain"] not in REGISTERED_DOMAINS:
            raise ContractError(f"unsupported catalog domain: {entry['domain']}")
        entry["jurisdictions"] = _normalize_string_set(entry["jurisdictions"], "jurisdictions")
        _timestamp(entry["valid_from"], "valid_from")
        if entry["valid_to"] is not None:
            if _timestamp(entry["valid_to"], "valid_to") < _timestamp(entry["valid_from"], "valid_from"):
                raise ContractError(f"Pack validity interval is inverted: {ref}")
        result[ref] = entry
    return result


def _candidate_union(
    candidate_sets: Mapping[str, Sequence[Mapping[str, Any]]],
    registered: set[str],
) -> dict[str, dict[str, set[str]]]:
    if set(candidate_sets) != set(CANDIDATE_SOURCES):
        missing = sorted(set(CANDIDATE_SOURCES) - set(candidate_sets))
        extra = sorted(set(candidate_sets) - set(CANDIDATE_SOURCES))
        raise ContractError(f"candidate sets differ from contract; missing={missing}, extra={extra}")
    result: dict[str, dict[str, set[str]]] = {domain: {} for domain in registered}
    for source in CANDIDATE_SOURCES:
        values = candidate_sets[source]
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
            raise ContractError(f"candidate set must be an array: {source}")
        for item in values:
            if not isinstance(item, Mapping) or set(item) != {"domain", "pack_ref"}:
                raise ContractError(f"candidate entry differs from contract: {source}")
            domain = item["domain"]
            pack_ref = item["pack_ref"]
            if domain not in registered:
                raise ContractError(f"candidate references an unregistered domain: {domain}")
            if not isinstance(pack_ref, str) or not pack_ref:
                raise ContractError("candidate pack_ref must be a non-empty string")
            result[domain].setdefault(pack_ref, set()).add(source)
    return result


def _screens(
    screen_results: Sequence[Mapping[str, Any]],
    registered: set[str],
    event_fact_refs: set[str],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in screen_results:
        if not isinstance(raw, Mapping) or set(raw) != _SCREEN_FIELDS:
            raise ContractError("applicability screen differs from its closed contract")
        domain = raw["domain"]
        if domain not in registered:
            raise ContractError(f"screen references an unregistered domain: {domain}")
        status = raw["status"]
        if status not in SCREEN_STATUSES:
            raise ContractError(f"unsupported applicability status: {status}")
        cost = raw["estimated_cost_class"]
        if cost not in {"none", "low", "medium", "high"}:
            raise ContractError(f"invalid estimated cost class: {cost}")
        normalized = {
            "domain": domain,
            "status": status,
            "trigger_card_refs": _normalize_string_set(raw["trigger_card_refs"], "trigger_card_refs"),
            "fact_refs": _normalize_string_set(raw["fact_refs"], "fact_refs"),
            "signal_refs": _normalize_string_set(raw["signal_refs"], "signal_refs"),
            "missing_capability_refs": _normalize_string_set(
                raw["missing_capability_refs"], "missing_capability_refs"
            ),
            "routing_reason_codes": _normalize_string_set(
                raw["routing_reason_codes"], "routing_reason_codes"
            ),
            "estimated_cost_class": cost,
        }
        unknown_facts = sorted(set(normalized["fact_refs"]) - event_fact_refs)
        if unknown_facts:
            raise ContractError(f"screen references Facts outside the Economic Event: {unknown_facts}")
        previous = result.get(domain)
        if previous is not None and canonical_bytes(previous) != canonical_bytes(normalized):
            raise ContractError(f"conflicting applicability screens for domain: {domain}")
        result[domain] = normalized
    missing = sorted(registered - set(result))
    if missing:
        raise ContractError(f"registered domains lack applicability screens: {missing}")
    return result


def _is_effective(entry: Mapping[str, Any], *, jurisdiction: str, effective_at: datetime) -> bool:
    if entry["jurisdictions"] and jurisdiction not in entry["jurisdictions"]:
        return False
    if effective_at < _timestamp(entry["valid_from"], "valid_from"):
        return False
    valid_to = entry["valid_to"]
    return valid_to is None or effective_at <= _timestamp(valid_to, "valid_to")


def _authority(selected: Sequence[Mapping[str, Any]]) -> str:
    return min(
        (str(item["effective_authority"]) for item in selected),
        key=lambda value: _AUTHORITY_RANK[value],
    )


def _route_status(screen_status: str, selected: Sequence[Mapping[str, Any]]) -> str:
    if screen_status == "not_applicable":
        return "not_applicable"
    if screen_status == "unsupported_pack":
        return "unsupported_pack"
    if screen_status == "possible_missing_data":
        return "not_assessable"
    if screen_status == "expert_review_required":
        return "expert_review_required"
    return "deep_review_pending" if selected else "unsupported_pack"


def route_economic_event(
    *,
    event: Mapping[str, Any],
    expected_revision: int,
    expected_event_hash: str,
    registered_domains: Sequence[str],
    candidate_sets: Mapping[str, Sequence[Mapping[str, Any]]],
    screen_results: Sequence[Mapping[str, Any]],
    pack_manifest: Mapping[str, Any],
    pack_catalog: Sequence[Mapping[str, Any]],
    jurisdiction: str,
    effective_at: str,
    schema_store: SchemaStore | None = None,
) -> tuple[dict[str, Any], ...]:
    """Route one immutable Event without creating Facts, judgments, Grades, or Approvals."""
    schemas = schema_store or SchemaStore()
    _validate_event(
        event,
        expected_revision=expected_revision,
        expected_event_hash=expected_event_hash,
        schemas=schemas,
    )
    registered_values = _normalize_string_set(registered_domains, "registered_domains")
    if any(domain not in REGISTERED_DOMAINS for domain in registered_values):
        raise ContractError("only accounting, labor, legal, and tax domains are registered")
    registered = set(registered_values)
    candidates = _candidate_union(candidate_sets, registered)
    screens = _screens(screen_results, registered, set(event["fact_refs"]))
    manifest = _manifest_index(pack_manifest, schemas)
    catalog = _catalog_index(pack_catalog, manifest)
    effective_time = _timestamp(effective_at, "effective_at")
    if not isinstance(jurisdiction, str) or not jurisdiction:
        raise ContractError("jurisdiction must be a non-empty code")

    routes: list[dict[str, Any]] = []
    for domain in sorted(registered):
        screen = screens[domain]
        selected: list[dict[str, str]] = []
        reasons = set(screen["routing_reason_codes"])
        if screen["status"] != "not_applicable":
            for pack_ref, sources in sorted(candidates[domain].items()):
                reasons.update(sources)
                catalog_entry = catalog.get(pack_ref)
                if catalog_entry is None:
                    continue
                if catalog_entry["domain"] != domain:
                    raise IntegrityError(
                        f"Pack catalog domain differs from candidate domain: {pack_ref}"
                    )
                if not _is_effective(
                    catalog_entry, jurisdiction=jurisdiction, effective_at=effective_time
                ):
                    continue
                selected.append({
                    "pack_ref": pack_ref,
                    "pack_sha256": str(catalog_entry["pack_sha256"]),
                    "effective_authority": str(catalog_entry["effective_authority"]),
                })
        status = _route_status(str(screen["status"]), selected)
        if status == "unsupported_pack":
            selected = []
            reasons.add(f"unsupported_{domain}_pack")
        authority = (
            "none" if status == "not_applicable"
            else "boundary" if status == "unsupported_pack" or not selected
            else _authority(selected)
        )
        route_identity = {
            "event_id": event["event_id"],
            "domain": domain,
            "base_revision": expected_revision,
            "screen_status": screen["status"],
            "selected_packs": selected,
            "pack_manifest_hash": pack_manifest["manifest_hash"],
        }
        body = {
            "schema_version": "1.0.0",
            "route_id": make_id("route", route_identity),
            "event_id": str(event["event_id"]),
            "base_revision": expected_revision,
            "domain": domain,
            "screen_status": str(screen["status"]),
            "status": status,
            "trigger_card_refs": screen["trigger_card_refs"],
            "fact_refs": screen["fact_refs"],
            "signal_refs": screen["signal_refs"],
            "missing_capability_refs": screen["missing_capability_refs"],
            "selected_pack_refs": [item["pack_ref"] for item in selected],
            "selected_packs": selected,
            "pack_manifest_hash": str(pack_manifest["manifest_hash"]),
            "effective_authority": authority,
            "required": status != "not_applicable",
            "routing_reason_codes": sorted(reasons),
            "estimated_cost_class": screen["estimated_cost_class"],
            "expert_role": _EXPERT_ROLES[domain],
        }
        result = {**body, "integrity": {"payload_hash": _hash(body)}}
        schemas.validate("domain-route.schema.json", result)
        routes.append(result)
    return tuple(routes)


def catalog_entry_from_loaded_pack(
    pack: Any,
    *,
    domain: str,
    jurisdictions: Sequence[str],
    valid_from: str,
    valid_to: str | None = None,
) -> dict[str, Any]:
    """Adapt an already verified LoadedPack without changing the legacy selector."""
    if getattr(pack, "pack_type", None) != "domain":
        raise ContractError("routing catalog adapters require a Domain Pack")
    return {
        "pack_ref": str(pack.ref),
        "domain": domain,
        "pack_sha256": str(pack.raw_sha256),
        "effective_authority": str(pack.effective_authority),
        "jurisdictions": sorted(set(str(item) for item in jurisdictions)),
        "valid_from": valid_from,
        "valid_to": valid_to,
    }


def catalog_entries_from_runtime_index(
    runtime_index: Any,
    *,
    domain: str,
    jurisdictions: Sequence[str],
    valid_from: str,
    valid_to: str | None = None,
) -> tuple[dict[str, Any], ...]:
    """Adapt a verified RuntimePackIndex manifest as read-only router input."""
    ref = str(runtime_index.domain_ref)
    entries = [
        entry for entry in runtime_index.manifest["packs"]
        if entry["pack_type"] == "domain"
        and f"{entry['pack_id']}@{entry['pack_version']}" == ref
    ]
    if len(entries) != 1:
        raise IntegrityError("Runtime Pack Index does not pin exactly one selected Domain Pack")
    entry = entries[0]
    return ({
        "pack_ref": ref,
        "domain": domain,
        "pack_sha256": str(entry["pack_sha256"]),
        "effective_authority": str(entry["effective_authority"]),
        "jurisdictions": sorted(set(str(item) for item in jurisdictions)),
        "valid_from": valid_from,
        "valid_to": valid_to,
    },)
