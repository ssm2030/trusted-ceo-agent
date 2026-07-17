from __future__ import annotations

import copy
import hashlib
import hmac
from collections.abc import Mapping, Sequence
from typing import Any

from trusted_ceo_agent.analysis.findings import (
    validate_finding_graph,
    validate_finding_records,
)
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


TERMINAL_ROUTE_STATUSES = frozenset({
    "completed",
    "not_assessable",
    "unsupported_pack",
    "expert_review_required",
    "not_applicable",
    "excluded_by_approved_scope",
})
EXPERT_BOUNDARY_STATUSES = frozenset({
    "not_assessable", "unsupported_pack", "expert_review_required",
})
ASSESSMENT_FIELDS = frozenset({
    "assessment_id",
    "route_id",
    "event_id",
    "domain",
    "revision",
    "status",
    "authority",
    "finding_ids",
    "additional_data_refs",
    "expert_role",
    "content_hash",
})
AUTHORITY_RANK = {
    "none": 0,
    "machine_draft": 1,
    "boundary": 2,
    "Boundary": 2,
    "provisional": 3,
    "Provisional": 3,
    "full": 4,
    "Full": 4,
}
CROSS_IMPACT_TYPES = frozenset({
    "possible_cause_of",
    "possible_consequence_of",
    "depends_on",
    "requires_joint_decision_with",
})
AGREEMENT_TYPES = frozenset({"supports", "shares_driver_with"})


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _records(value: Sequence[Mapping[str, Any]], label: str) -> list[dict[str, Any]]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ContractError(f"{label} must be an array of objects")
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ContractError(f"{label} must contain only objects")
        result.append(copy.deepcopy(dict(item)))
    return result


def _unique_index(
    records: Sequence[Mapping[str, Any]], key: str, label: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in records:
        value = item.get(key)
        if not isinstance(value, str) or not value:
            raise ContractError(f"{label} {key} must be a non-empty string")
        if value in result:
            raise ContractError(f"duplicate {label} {key}: {value}")
        result[value] = copy.deepcopy(dict(item))
    return result


def _sorted_string_set(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ContractError(f"{field} must be an array")
    if any(not isinstance(item, str) or not item for item in value):
        raise ContractError(f"{field} must contain non-empty strings")
    normalized = sorted(set(value))
    if value != normalized:
        raise ContractError(f"{field} must be a sorted unique set")
    return normalized


def _verify_payload_record(
    record: Mapping[str, Any], schema_name: str, schemas: SchemaStore,
) -> None:
    schemas.validate(schema_name, dict(record))
    integrity = record.get("integrity")
    if not isinstance(integrity, Mapping):
        raise ContractError(f"{schema_name} integrity is missing")
    body = copy.deepcopy(dict(record))
    body.pop("integrity", None)
    if not hmac.compare_digest(str(integrity.get("payload_hash", "")), _digest(body)):
        raise ContractError(f"{schema_name} payload hash mismatch")


def _verify_content_record(
    record: Mapping[str, Any], schema_name: str, schemas: SchemaStore,
) -> None:
    schemas.validate(schema_name, dict(record))
    body = copy.deepcopy(dict(record))
    claimed = str(body.pop("content_hash", ""))
    if not hmac.compare_digest(claimed, _digest(body)):
        raise ContractError(f"{schema_name} content hash mismatch")


def _verify_assessment(raw: Mapping[str, Any]) -> dict[str, Any]:
    if set(raw) != ASSESSMENT_FIELDS:
        missing = sorted(ASSESSMENT_FIELDS - set(raw))
        extra = sorted(set(raw) - ASSESSMENT_FIELDS)
        raise ContractError(
            f"domain assessment fields are invalid: missing={missing}, extra={extra}"
        )
    value = copy.deepcopy(dict(raw))
    for field in ("assessment_id", "route_id", "event_id", "domain", "status", "authority"):
        if not isinstance(value[field], str) or not value[field]:
            raise ContractError(f"domain assessment {field} must be a non-empty string")
    if value["status"] not in TERMINAL_ROUTE_STATUSES:
        raise ContractError(f"domain assessment is not terminal: {value['assessment_id']}")
    if value["authority"] not in AUTHORITY_RANK:
        raise ContractError("domain assessment authority is invalid")
    if isinstance(value["revision"], bool) or not isinstance(value["revision"], int):
        raise ContractError("domain assessment revision must be an integer")
    if value["revision"] < 1:
        raise ContractError("domain assessment revision must be positive")
    _sorted_string_set(value["finding_ids"], "domain assessment finding_ids")
    _sorted_string_set(
        value["additional_data_refs"], "domain assessment additional_data_refs"
    )
    expert_role = value["expert_role"]
    if expert_role is not None and (not isinstance(expert_role, str) or not expert_role):
        raise ContractError("domain assessment expert_role must be null or non-empty")
    body = copy.deepcopy(value)
    claimed = str(body.pop("content_hash"))
    if not hmac.compare_digest(claimed, _digest(body)):
        raise ContractError("domain assessment content hash mismatch")
    return value


def _validate_inputs(
    *,
    run_id: str,
    revision: int,
    event: Mapping[str, Any],
    routes: Sequence[Mapping[str, Any]],
    domain_assessments: Sequence[Mapping[str, Any]],
    findings: Sequence[Mapping[str, Any]],
    relations: Sequence[Mapping[str, Any]],
    clusters: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not isinstance(run_id, str) or not run_id.startswith("run_"):
        raise ContractError("Integrator run_id must use the run_ prefix")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ContractError("Integrator revision must be a positive integer")
    if not isinstance(event, Mapping):
        raise ContractError("Integrator Event must be an object")

    schemas = SchemaStore()
    event_record = copy.deepcopy(dict(event))
    _verify_payload_record(event_record, "economic-event.schema.json", schemas)
    if event_record["base_revision"] != revision:
        raise ContractError("Integrator Event revision is stale")
    event_id = event_record["event_id"]
    event_fact_refs = set(event_record["fact_refs"])

    route_records = _records(routes, "routes")
    if not route_records:
        raise ContractError("Integrator requires at least one DomainRoute")
    route_by_id = _unique_index(route_records, "route_id", "DomainRoute")
    route_by_domain: dict[str, dict[str, Any]] = {}
    pack_manifest_hashes: set[str] = set()
    for route in route_by_id.values():
        _verify_payload_record(route, "domain-route.schema.json", schemas)
        domain = route["domain"]
        if domain in route_by_domain:
            raise ContractError(f"duplicate DomainRoute domain: {domain}")
        route_by_domain[domain] = route
        if route["event_id"] != event_id or route["base_revision"] != revision:
            raise ContractError(f"DomainRoute is stale: {route['route_id']}")
        if not set(route["fact_refs"]).issubset(event_fact_refs):
            raise ContractError(f"DomainRoute introduces a Fact: {route['route_id']}")
        status = route["status"]
        if status not in TERMINAL_ROUTE_STATUSES:
            raise ContractError(f"DomainRoute is not terminal: {route['route_id']}")
        if route["required"] and status == "not_applicable":
            raise ContractError("required DomainRoute cannot be not_applicable")
        if not route["required"] and status != "not_applicable":
            raise ContractError("non-required DomainRoute must be not_applicable")
        pack_manifest_hashes.add(route["pack_manifest_hash"])
    if len(pack_manifest_hashes) != 1:
        raise ContractError("DomainRoutes do not share one Pack manifest hash")

    assessment_records = [
        _verify_assessment(item)
        for item in _records(domain_assessments, "domain_assessments")
    ]
    assessment_by_id = _unique_index(
        assessment_records, "assessment_id", "domain assessment"
    )
    assessment_by_route = _unique_index(
        assessment_records, "route_id", "domain assessment route"
    )
    if set(assessment_by_route) != set(route_by_id):
        missing = sorted(set(route_by_id) - set(assessment_by_route))
        extra = sorted(set(assessment_by_route) - set(route_by_id))
        raise ContractError(
            f"every DomainRoute needs one assessment: missing={missing}, extra={extra}"
        )

    finding_records = _records(findings, "findings")
    validate_finding_records(finding_records)
    finding_by_id = _unique_index(finding_records, "finding_id", "Finding")
    for finding in finding_records:
        if finding["run_id"] != run_id or finding["event_id"] != event_id:
            raise ContractError(f"Finding crosses run or Event: {finding['finding_id']}")
        if finding["revision"] > revision:
            raise ContractError(f"Finding is from a later revision: {finding['finding_id']}")
        if not set(finding["fact_refs"]).issubset(event_fact_refs):
            raise ContractError(f"Finding introduces a Fact: {finding['finding_id']}")

    covered_findings: set[str] = set()
    for route_id, assessment in assessment_by_route.items():
        route = route_by_id[route_id]
        if (
            assessment["event_id"] != event_id
            or assessment["revision"] != revision
            or assessment["domain"] != route["domain"]
            or assessment["status"] != route["status"]
            or assessment["expert_role"] != route["expert_role"]
        ):
            raise ContractError(f"domain assessment does not match Route: {route_id}")
        if AUTHORITY_RANK[assessment["authority"]] > AUTHORITY_RANK[route["effective_authority"]]:
            raise ContractError(f"domain assessment elevates Route authority: {route_id}")
        finding_ids = set(assessment["finding_ids"])
        missing = finding_ids - set(finding_by_id)
        if missing:
            raise ContractError(f"domain assessment has dangling Findings: {sorted(missing)}")
        if route["status"] == "completed" and not finding_ids:
            raise ContractError(f"completed DomainRoute lacks a Finding: {route_id}")
        if route["status"] == "not_applicable" and finding_ids:
            raise ContractError("not_applicable DomainRoute cannot own Findings")
        for finding_id in finding_ids:
            finding = finding_by_id[finding_id]
            if assessment["assessment_id"] not in finding["domain_assessment_refs"]:
                raise ContractError(
                    f"Finding does not reference its assessment: {finding_id}"
                )
            if (
                AUTHORITY_RANK[finding["authority"]["effective_level"]]
                > AUTHORITY_RANK[assessment["authority"]]
            ):
                raise ContractError(f"Finding exceeds domain authority: {finding_id}")
        covered_findings.update(finding_ids)
    if covered_findings != set(finding_by_id):
        raise ContractError(
            f"Findings are not bound to DomainRoutes: {sorted(set(finding_by_id) - covered_findings)}"
        )
    for finding in finding_records:
        refs = set(finding["domain_assessment_refs"])
        if not refs.issubset(assessment_by_id):
            raise ContractError(
                f"Finding has a stale domain assessment ref: {finding['finding_id']}"
            )

    relation_records = _records(relations, "relations")
    validate_finding_graph(finding_records, relation_records)
    relation_by_id = _unique_index(relation_records, "relation_id", "FindingRelation")
    for relation in relation_records:
        if relation["run_id"] != run_id or relation["revision"] > revision:
            raise ContractError(f"FindingRelation crosses run or revision: {relation['relation_id']}")

    cluster_records = _records(clusters, "clusters")
    cluster_by_id = _unique_index(cluster_records, "cluster_id", "IssueCluster")
    cluster_finding_refs: set[str] = set()
    for cluster in cluster_records:
        _verify_content_record(cluster, "issue-cluster.schema.json", schemas)
        if cluster["run_id"] != run_id or cluster["revision"] > revision:
            raise ContractError(f"IssueCluster crosses run or revision: {cluster['cluster_id']}")
        missing_findings = set(cluster["finding_ids"]) - set(finding_by_id)
        missing_relations = set(cluster["relation_ids"]) - set(relation_by_id)
        if missing_findings or missing_relations:
            raise ContractError(
                f"IssueCluster has stale refs: findings={sorted(missing_findings)}, "
                f"relations={sorted(missing_relations)}"
            )
        cluster_finding_refs.update(cluster["finding_ids"])
    if finding_by_id and cluster_finding_refs != set(finding_by_id):
        raise ContractError("Cross-Finding Join does not cover every current Finding")

    return {
        "event": event_record,
        "routes": sorted(route_records, key=lambda item: item["domain"]),
        "assessments": sorted(assessment_records, key=lambda item: item["domain"]),
        "findings": sorted(finding_records, key=lambda item: item["finding_id"]),
        "relations": sorted(relation_records, key=lambda item: item["relation_id"]),
        "clusters": sorted(cluster_records, key=lambda item: item["cluster_id"]),
        "pack_manifest_hash": next(iter(pack_manifest_hashes)),
    }


def freeze_finding_join_manifest(
    *,
    run_id: str,
    revision: int,
    event: Mapping[str, Any],
    routes: Sequence[Mapping[str, Any]],
    domain_assessments: Sequence[Mapping[str, Any]],
    findings: Sequence[Mapping[str, Any]],
    relations: Sequence[Mapping[str, Any]],
    clusters: Sequence[Mapping[str, Any]],
    writer_id: str,
) -> dict[str, Any]:
    """Freeze one revision's Event/Route/Finding graph before the single Integrator runs."""

    if not isinstance(writer_id, str) or not writer_id:
        raise ContractError("Integrator writer_id must be non-empty")
    values = _validate_inputs(
        run_id=run_id,
        revision=revision,
        event=event,
        routes=routes,
        domain_assessments=domain_assessments,
        findings=findings,
        relations=relations,
        clusters=clusters,
    )
    event_record = values["event"]
    identity = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "revision": revision,
        "event_ref": {
            "event_id": event_record["event_id"],
            "payload_hash": event_record["integrity"]["payload_hash"],
        },
        "pack_manifest_hash": values["pack_manifest_hash"],
        "writer_id": writer_id,
        "route_inputs": [{
            "route_id": item["route_id"],
            "domain": item["domain"],
            "required": item["required"],
            "status": item["status"],
            "authority": item["effective_authority"],
            "payload_hash": item["integrity"]["payload_hash"],
        } for item in values["routes"]],
        "assessment_inputs": [{
            "assessment_id": item["assessment_id"],
            "route_id": item["route_id"],
            "domain": item["domain"],
            "status": item["status"],
            "authority": item["authority"],
            "content_hash": item["content_hash"],
        } for item in values["assessments"]],
        "finding_inputs": [{
            "finding_id": item["finding_id"],
            "content_hash": item["content_hash"],
        } for item in values["findings"]],
        "relation_inputs": [{
            "relation_id": item["relation_id"],
            "content_hash": item["content_hash"],
        } for item in values["relations"]],
        "cluster_inputs": [{
            "cluster_id": item["cluster_id"],
            "content_hash": item["content_hash"],
        } for item in values["clusters"]],
    }
    body = {
        **identity,
        "manifest_id": "findingjoin_" + _digest(identity)[:24],
    }
    manifest = {**body, "integrity": {"payload_hash": _digest(body)}}
    SchemaStore().validate("finding-join-manifest.schema.json", manifest)
    return manifest


def _verify_manifest(manifest: Mapping[str, Any], expected_hash: str) -> None:
    schemas = SchemaStore()
    schemas.validate("finding-join-manifest.schema.json", dict(manifest))
    body = copy.deepcopy(dict(manifest))
    integrity = body.pop("integrity")
    actual = _digest(body)
    claimed = str(integrity["payload_hash"])
    if not hmac.compare_digest(claimed, actual):
        raise ContractError("Finding Join manifest payload hash mismatch")
    if not hmac.compare_digest(claimed, expected_hash):
        raise ContractError("Finding Join manifest is stale")
    identity = copy.deepcopy(body)
    manifest_id = identity.pop("manifest_id")
    if manifest_id != "findingjoin_" + _digest(identity)[:24]:
        raise ContractError("Finding Join manifest ID mismatch")


def integrate_cross_domain(
    *,
    manifest: Mapping[str, Any],
    expected_manifest_hash: str,
    writer_id: str,
    event: Mapping[str, Any],
    routes: Sequence[Mapping[str, Any]],
    domain_assessments: Sequence[Mapping[str, Any]],
    findings: Sequence[Mapping[str, Any]],
    relations: Sequence[Mapping[str, Any]],
    clusters: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Project a frozen graph once; never create a Fact, Finding, relation, Grade, or authority."""

    if not isinstance(manifest, Mapping):
        raise ContractError("Finding Join manifest must be an object")
    _verify_manifest(manifest, expected_manifest_hash)
    if writer_id != manifest["writer_id"]:
        raise ContractError("only the frozen Integrator writer may publish")

    values = _validate_inputs(
        run_id=str(manifest["run_id"]),
        revision=int(manifest["revision"]),
        event=event,
        routes=routes,
        domain_assessments=domain_assessments,
        findings=findings,
        relations=relations,
        clusters=clusters,
    )
    rebuilt = freeze_finding_join_manifest(
        run_id=str(manifest["run_id"]),
        revision=int(manifest["revision"]),
        event=event,
        routes=routes,
        domain_assessments=domain_assessments,
        findings=findings,
        relations=relations,
        clusters=clusters,
        writer_id=writer_id,
    )
    if canonical_bytes(rebuilt) != canonical_bytes(dict(manifest)):
        raise ContractError("Integrator inputs differ from the frozen manifest")

    route_by_id = {item["route_id"]: item for item in values["routes"]}
    finding_by_id = {item["finding_id"]: item for item in values["findings"]}
    finding_domains: dict[str, set[str]] = {key: set() for key in finding_by_id}
    for assessment in values["assessments"]:
        for finding_id in assessment["finding_ids"]:
            finding_domains[finding_id].add(assessment["domain"])

    terminal_map: list[dict[str, Any]] = []
    domain_judgments: list[dict[str, Any]] = []
    expert_requirements: list[dict[str, Any]] = []
    for assessment in values["assessments"]:
        route = route_by_id[assessment["route_id"]]
        terminal = {
            "domain": assessment["domain"],
            "route_id": route["route_id"],
            "assessment_id": assessment["assessment_id"],
            "status": assessment["status"],
            "authority": assessment["authority"],
        }
        if route["required"]:
            terminal_map.append(terminal)
        impact_records = [{
            "finding_id": finding_id,
            "impact_dimensions": copy.deepcopy(finding_by_id[finding_id]["impact_dimensions"]),
        } for finding_id in assessment["finding_ids"]]
        domain_judgments.append({
            **terminal,
            "finding_ids": list(assessment["finding_ids"]),
            "impact_records": impact_records,
        })
        if assessment["status"] in EXPERT_BOUNDARY_STATUSES:
            expert_requirements.append({
                "domain": assessment["domain"],
                "expert_role": assessment["expert_role"],
                "status": assessment["status"],
                "additional_data_refs": list(assessment["additional_data_refs"]),
            })

    agreement_refs: list[str] = []
    conflicts: list[dict[str, Any]] = []
    cross_impacts: list[dict[str, Any]] = []
    for relation in values["relations"]:
        relation_type = relation["relation_type"]
        if relation_type in AGREEMENT_TYPES:
            agreement_refs.append(relation["relation_id"])
        if relation_type == "contradicts":
            conflicts.append({
                "relation_id": relation["relation_id"],
                "source_finding_id": relation["source_finding_id"],
                "target_finding_id": relation["target_finding_id"],
                "confidence_status": relation["confidence_status"],
                "evidence_refs": list(relation["evidence_refs"]),
                "contradicting_evidence_refs": list(
                    relation["contradicting_evidence_refs"]
                ),
            })
        source_domains = finding_domains[relation["source_finding_id"]]
        target_domains = finding_domains[relation["target_finding_id"]]
        if relation_type in CROSS_IMPACT_TYPES and source_domains != target_domains:
            cross_impacts.append({
                "relation_id": relation["relation_id"],
                "relation_type": relation_type,
                "source_finding_id": relation["source_finding_id"],
                "target_finding_id": relation["target_finding_id"],
            })

    ceo_units = [{
        "cluster_id": item["cluster_id"],
        "decision_unit": copy.deepcopy(item["decision_unit"]),
        "unresolved_conflicts": list(item["unresolved_conflicts"]),
    } for item in values["clusters"]]
    identity = {
        "schema_version": "1.0.0",
        "manifest_id": manifest["manifest_id"],
        "manifest_hash": manifest["integrity"]["payload_hash"],
        "run_id": manifest["run_id"],
        "revision": manifest["revision"],
        "event_id": values["event"]["event_id"],
        "pack_manifest_hash": values["pack_manifest_hash"],
        "writer_id": writer_id,
        "required_domain_terminal_map": terminal_map,
        "common_fact_refs": list(values["event"]["fact_refs"]),
        "domain_judgment_refs": domain_judgments,
        "cross_finding_relation_refs": [
            item["relation_id"] for item in values["relations"]
        ],
        "agreement_relation_refs": agreement_refs,
        "conflicts": conflicts,
        "cross_domain_impacts": cross_impacts,
        "issue_cluster_refs": [item["cluster_id"] for item in values["clusters"]],
        "ceo_decision_units": ceo_units,
        "expert_requirements": expert_requirements,
    }
    body = {
        **identity,
        "integration_id": "integration_" + _digest(identity)[:24],
    }
    result = {**body, "integrity": {"payload_hash": _digest(body)}}
    SchemaStore().validate("cross-domain-integration.schema.json", result)
    return result
