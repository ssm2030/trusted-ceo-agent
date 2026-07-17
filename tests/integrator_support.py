from __future__ import annotations

import copy
import hashlib
from typing import Any

from trusted_ceo_agent.analysis.findings import (
    build_finding,
    build_finding_relation,
    build_issue_cluster,
)
from trusted_ceo_agent.canonical import canonical_bytes


RUN_ID = "run_integrator"
REVISION = 7
EVENT_ID = "event_" + "a" * 24
FACT_ID = "fact_" + "b" * 24
PACK_HASH = "c" * 64


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def event_fixture() -> dict[str, Any]:
    body = {
        "schema_version": "1.0.0",
        "event_id": EVENT_ID,
        "event_type": "contract_performance",
        "base_revision": REVISION,
        "evidence_core_ref": {
            "artifact_id": "artifact_" + "d" * 24,
            "artifact_hash": "d" * 64,
            "payload_hash": "e" * 64,
            "revision": REVISION,
        },
        "party_roles": [FACT_ID],
        "rights": [],
        "obligations": [],
        "resource_and_control": [],
        "consideration": [],
        "conditions": [],
        "event_dates": [],
        "performance_state": [],
        "billing_state": [],
        "payment_state": [],
        "cancellation_state": [],
        "amounts": [],
        "incentives": [],
        "document_refs": [],
        "system_event_refs": [],
        "fact_refs": [FACT_ID],
        "source_lineage": [{
            "fact_ref": FACT_ID,
            "root_fact_refs": [FACT_ID],
            "sources": [{
                "source_id": "source_" + "f" * 24,
                "source_sha256": "f" * 64,
                "lineage_set_refs": ["lineage/sets/" + "f" * 64 + ".json"],
            }],
            "evidence_link_refs": [],
        }],
        "data_quality_refs": [],
        "materialization": {
            "producer": "deterministic_component",
            "input_hash": "1" * 64,
        },
    }
    return {**body, "integrity": {"payload_hash": digest(body)}}


def route_fixture(
    domain: str,
    *,
    status: str = "completed",
    authority: str = "provisional",
    required: bool = True,
) -> dict[str, Any]:
    selected = [] if status in {"unsupported_pack", "not_applicable"} else [{
        "pack_ref": f"{domain}-core@1.0.0",
        "pack_sha256": PACK_HASH,
        "effective_authority": authority,
    }]
    route_identity = {"event_id": EVENT_ID, "domain": domain, "revision": REVISION}
    body = {
        "schema_version": "1.0.0",
        "route_id": "route_" + digest(route_identity)[:24],
        "event_id": EVENT_ID,
        "base_revision": REVISION,
        "domain": domain,
        "screen_status": (
            "not_applicable" if status == "not_applicable"
            else "unsupported_pack" if status == "unsupported_pack"
            else "triggered"
        ),
        "status": status,
        "trigger_card_refs": [],
        "fact_refs": [] if status == "not_applicable" else [FACT_ID],
        "signal_refs": [],
        "missing_capability_refs": [],
        "selected_pack_refs": [item["pack_ref"] for item in selected],
        "selected_packs": selected,
        "pack_manifest_hash": PACK_HASH,
        "effective_authority": (
            "none" if status == "not_applicable"
            else "boundary" if status == "unsupported_pack"
            else authority
        ),
        "required": required,
        "routing_reason_codes": [f"screen_{domain}"],
        "estimated_cost_class": "none" if status == "not_applicable" else "medium",
        "expert_role": {
            "accounting": "senior_accountant",
            "labor": "labor_specialist",
            "legal": "legal_counsel",
            "tax": "tax_specialist",
        }[domain],
    }
    return {**body, "integrity": {"payload_hash": digest(body)}}


def finding_spec(suffix: str, domain: str) -> dict[str, Any]:
    evidence_ref = "evidence_" + suffix * 24
    return {
        "run_id": RUN_ID,
        "revision": REVISION,
        "case_id": "case_" + suffix * 24,
        "event_id": EVENT_ID,
        "signal_ids": ["signal_" + suffix * 24],
        "domain_assessment_refs": [f"assessment_{domain}"],
        "issue_family_refs": ["AC-01" if domain == "accounting" else "RV-01"],
        "fact_refs": [FACT_ID],
        "evidence_link_refs": [evidence_ref],
        "source_refs": ["source_" + suffix * 24],
        "procedure_result_refs": [f"procedure_result_{suffix}"],
        "norm_refs": [f"norm_{suffix}"],
        "calculation_refs": [f"calculation_{suffix}"],
        "hypotheses": [f"{domain} scoped issue is supported."],
        "counter_hypotheses": ["The pattern may be a timing-only difference."],
        "supporting_evidence_refs": [evidence_ref],
        "contradicting_evidence_refs": [],
        "unresolved_conflicts": [],
        "disposition": "substantiated",
        "conclusion": {
            "statement": f"{domain} conclusion within the tested scope.",
            "scope": "The frozen evidence packet.",
            "basis_refs": [f"procedure_result_{suffix}"],
            "qualifier": "supported_within_current_scope",
        },
        "conclusion_strength": "supported",
        "impact_dimensions": {
            "amount": "material",
            "cash": "possible",
            "legal": "possible" if domain == "tax" else "not_assessed",
            "tax": "material" if domain == "tax" else "not_assessed",
            "human": "not_assessed",
            "operations": "possible",
            "control": "material",
        },
        "coverage": {
            "required_procedures_complete": True,
            "counter_evidence_complete": True,
            "evidence_coverage_complete": True,
            "missing_evidence_refs": [],
            "missing_procedure_refs": [],
            "scope_note": "Frozen packet only.",
        },
        "data_gaps": [],
        "expert_review": {
            "required": False,
            "packet_ref": None,
            "decision_boundary": None,
            "owner": None,
        },
        "grade": {"status": "published", "grade_record_ref": f"grade_record_{suffix}"},
        "authority": {
            "effective_level": "Provisional",
            "pack_release_refs": [f"pack_release_{domain}"],
            "approval_refs": [],
        },
        "uncertainty": {"status": "partial", "reason_codes": ["sample_scope"]},
        "verification": {
            "required_procedure_refs": [f"procedure_{suffix}"],
            "completed_procedure_refs": [f"procedure_{suffix}"],
            "counter_evidence_checked": True,
            "counter_evidence_refs": ["evidence_" + "9" * 24],
            "verification_step_refs": [f"verification_{suffix}"],
        },
        "related_finding_ids": [],
        "supersedes_finding_id": None,
    }


def assessment_fixture(route: dict[str, Any], finding_ids: list[str]) -> dict[str, Any]:
    body = {
        "assessment_id": f"assessment_{route['domain']}",
        "route_id": route["route_id"],
        "event_id": route["event_id"],
        "domain": route["domain"],
        "revision": route["base_revision"],
        "status": route["status"],
        "authority": route["effective_authority"],
        "finding_ids": sorted(finding_ids),
        "additional_data_refs": (
            [f"packet_{route['domain']}"]
            if route["status"] in {"unsupported_pack", "expert_review_required", "not_assessable"}
            else []
        ),
        "expert_role": route["expert_role"],
    }
    return {**body, "content_hash": digest(body)}


def complete_inputs(*, include_unsupported: bool = False) -> dict[str, Any]:
    event = event_fixture()
    findings = [
        build_finding(finding_spec("2", "accounting")),
        build_finding(finding_spec("3", "tax")),
    ]
    routes = [
        route_fixture("accounting"),
        route_fixture("tax"),
    ]
    assessments = [
        assessment_fixture(routes[0], [findings[0]["finding_id"]]),
        assessment_fixture(routes[1], [findings[1]["finding_id"]]),
    ]
    relation = build_finding_relation({
        "run_id": RUN_ID,
        "revision": REVISION,
        "source_finding_id": findings[0]["finding_id"],
        "target_finding_id": findings[1]["finding_id"],
        "relation_type": "contradicts",
        "evidence_refs": ["evidence_" + "4" * 24],
        "confidence_status": "verified",
        "contradicting_evidence_refs": ["evidence_" + "5" * 24],
    }, findings)
    cluster = build_issue_cluster({
        "run_id": RUN_ID,
        "revision": REVISION,
        "finding_ids": [item["finding_id"] for item in findings],
        "relation_ids": [relation["relation_id"]],
        "decision_unit": {
            "title": "Resolve accounting and tax treatment conflict",
            "decision_required": True,
            "owner_role": "ceo",
            "option_refs": ["decision_option_a", "decision_option_b"],
        },
        "unresolved_conflicts": ["domain treatment conflict remains"],
    }, findings=findings, relations=[relation])
    if include_unsupported:
        legal = route_fixture("legal", status="unsupported_pack", authority="boundary")
        routes.append(legal)
        assessments.append(assessment_fixture(legal, []))
    return {
        "event": event,
        "routes": routes,
        "domain_assessments": assessments,
        "findings": findings,
        "relations": [relation],
        "clusters": [cluster],
    }


def rehash_route(route: dict[str, Any]) -> dict[str, Any]:
    body = copy.deepcopy(route)
    body.pop("integrity", None)
    return {**body, "integrity": {"payload_hash": digest(body)}}


def rehash_assessment(assessment: dict[str, Any]) -> dict[str, Any]:
    body = copy.deepcopy(assessment)
    body.pop("content_hash", None)
    return {**body, "content_hash": digest(body)}
