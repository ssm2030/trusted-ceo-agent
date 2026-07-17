from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


_DISPOSITIONS = (
    "substantiated", "not_substantiated", "inconclusive", "merged",
    "out_of_scope", "expert_review_required", "deferred", "failed", "cancelled",
)
_ROUTE_TERMINAL = {
    "completed", "not_assessable", "unsupported_pack", "expert_review_required",
    "not_applicable", "excluded_by_approved_scope", "approved_out_of_scope",
}
_GATE_FIELDS = (
    "cross_finding_join_complete", "cross_domain_integrator_complete",
    "duplicate_merge_complete", "conflicts_disclosed", "coverage_complete",
    "final_validator_passed", "tty_final_approval_ready",
)


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _sorted_refs(values: Sequence[Any]) -> list[str]:
    return sorted({str(value) for value in values if isinstance(value, str) and value})


def _mapping_list(value: Any, *, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ContractError(f"Completion input {label} must be an object array")
    return sorted(value, key=lambda item: canonical_bytes(item))


def _finding_valid(finding: Mapping[str, Any]) -> bool:
    disposition = finding.get("disposition")
    coverage = finding.get("coverage")
    if not isinstance(coverage, Mapping):
        return False
    procedures = coverage.get("required_procedures_complete") is True
    counter = coverage.get("counter_evidence_complete") is True
    evidence = (
        coverage.get("evidence_coverage_complete") is True
        if "evidence_coverage_complete" in coverage
        else coverage.get("evidence_complete") is True
    )
    if disposition == "substantiated":
        return procedures and counter and evidence
    if disposition in {"inconclusive", "deferred", "out_of_scope"}:
        return (
            procedures
            and counter
            and bool(_sorted_refs(finding.get("reason_codes", [])))
            and bool(_sorted_refs(finding.get("impact_scope_refs", [])))
        )
    if disposition == "expert_review_required":
        expert = finding.get("expert_review")
        current_contract = (
            isinstance(expert, Mapping)
            and expert.get("required") is True
            and isinstance(expert.get("packet_ref"), str)
            and bool(expert.get("packet_ref"))
            and isinstance(expert.get("decision_boundary"), str)
            and bool(expert.get("decision_boundary"))
            and isinstance(expert.get("owner"), str)
            and bool(expert.get("owner"))
        )
        legacy_contract = (
            isinstance(expert, Mapping)
            and expert.get("required") is True
            and expert.get("packet_complete") is True
            and expert.get("conclusion_boundary_complete") is True
            and isinstance(expert.get("responsible_role"), str)
            and bool(expert.get("responsible_role"))
        )
        return (
            procedures
            and counter
            and (current_contract or legacy_contract)
        )
    return disposition in {"not_substantiated", "merged"} and procedures and counter


def assess_completion(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError("Completion input must be an object")
    run_id = value.get("run_id")
    revision = value.get("revision")
    if not isinstance(run_id, str) or not run_id or not isinstance(revision, int):
        raise ContractError("Completion run and revision are required")
    cases = _mapping_list(value.get("signal_cases"), label="signal_cases")
    work_items = _mapping_list(value.get("work_items"), label="work_items")
    routes = _mapping_list(value.get("domain_routes"), label="domain_routes")
    findings = _mapping_list(value.get("findings"), label="findings")

    counts = {disposition: 0 for disposition in _DISPOSITIONS}
    blocking_cases: list[str] = []
    for case in cases:
        case_id = str(case.get("case_id", "<unknown-case>"))
        disposition = case.get("disposition")
        if disposition in counts:
            counts[str(disposition)] += 1
        if (
            case.get("materiality_review_required") is True
            and (case.get("status") != "terminal" or disposition not in counts)
        ) or disposition in {"failed", "cancelled"}:
            blocking_cases.append(case_id)

    blocking_work = [
        str(item.get("task_id", "<unknown-task>"))
        for item in work_items
        if item.get("required") is True and item.get("status") != "succeeded"
    ]
    blocking_routes = [
        str(item.get("route_id", "<unknown-route>"))
        for item in routes
        if item.get("required") is True and item.get("status") not in _ROUTE_TERMINAL
    ]
    invalid_findings = [
        str(item.get("finding_id", "<unknown-finding>"))
        for item in findings
        if not _finding_valid(item)
    ]
    hard_failures = _sorted_refs(
        list(value.get("integrity_failure_refs", []))
        + list(value.get("contract_failure_refs", []))
        + list(value.get("stale_revision_refs", []))
    )
    gates = {field: value.get(field) is True for field in _GATE_FIELDS}
    incomplete_gates = sorted(field for field, complete in gates.items() if not complete)

    coverage_gaps = _sorted_refs(value.get("coverage_gaps", []))
    limited_findings = [
        str(item.get("finding_id", "<unknown-finding>"))
        for item in findings
        if item.get("limitation_origin") == "data_or_capability"
        or item.get("disposition") == "deferred"
    ]
    limited_basis = value.get("limited_basis")
    if limited_basis not in {"none", "data_unavailable", "user_excluded_scope"}:
        raise ContractError("Completion limited basis is invalid")
    confirmed = value.get("user_confirmed_limitations") is True
    blockers = bool(
        blocking_cases or blocking_work or blocking_routes or invalid_findings
        or hard_failures or incomplete_gates
    )
    has_limit = bool(limited_findings or coverage_gaps or limited_basis != "none")
    limited_eligible = (
        not blockers
        and has_limit
        and limited_basis in {"data_unavailable", "user_excluded_scope"}
        and confirmed
    )
    status = (
        "not_ready"
        if blockers or (has_limit and not limited_eligible)
        else "limited_completion_ready"
        if limited_eligible
        else "finalization_ready"
    )
    limitations = sorted(set(limited_findings + coverage_gaps + incomplete_gates))
    semantic: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "revision": revision,
        "status": status,
        "disposition_counts": counts,
        "blocking_case_refs": sorted(set(blocking_cases)),
        "blocking_required_work_refs": sorted(set(blocking_work)),
        "blocking_domain_route_refs": sorted(set(blocking_routes)),
        "invalid_finding_refs": sorted(set(invalid_findings)),
        "hard_failure_refs": hard_failures,
        "coverage_gaps": coverage_gaps,
        "expert_review_refs": _sorted_refs(value.get("expert_review_refs", [])),
        "blind_spot_refs": _sorted_refs(value.get("blind_spot_refs", [])),
        "gate_results": gates,
        "limited_basis": limited_basis,
        "user_confirmed_limitations": confirmed,
        "limited_completion_eligible": limited_eligible,
        "completion_limitations": limitations,
    }
    assessment_id = make_id("completion", semantic)
    assessment = {"assessment_id": assessment_id, **semantic}
    assessment["content_hash"] = _hash(assessment)
    verify_completion_assessment(assessment)
    return assessment


def _verify_payload_artifact(value: Mapping[str, Any], schema_name: str) -> dict[str, Any]:
    document = deepcopy(dict(value))
    SchemaStore().validate(schema_name, document)
    integrity = document.pop("integrity")
    if not hmac.compare_digest(str(integrity["payload_hash"]), _hash(document)):
        raise ContractError(f"{schema_name} payload hash is invalid")
    return {**document, "integrity": deepcopy(integrity)}


def assess_completion_from_artifacts(
    value: Mapping[str, Any],
    *,
    finding_join_manifest: Mapping[str, Any],
    cross_domain_integration: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive cross-Finding/domain gates from immutable K artifacts, not caller booleans."""

    if not isinstance(value, Mapping):
        raise ContractError("Completion input must be an object")
    manifest = _verify_payload_artifact(
        finding_join_manifest, "finding-join-manifest.schema.json"
    )
    integration = _verify_payload_artifact(
        cross_domain_integration, "cross-domain-integration.schema.json"
    )
    run_id = value.get("run_id")
    revision = value.get("revision")
    if (
        manifest["run_id"] != run_id
        or integration["run_id"] != run_id
        or manifest["revision"] != revision
        or integration["revision"] != revision
    ):
        raise ContractError("Completion artifacts cross run or revision")
    if (
        integration["manifest_id"] != manifest["manifest_id"]
        or integration["manifest_hash"] != manifest["integrity"]["payload_hash"]
    ):
        raise ContractError("Completion integration does not match the frozen Join")

    routes = _mapping_list(value.get("domain_routes"), label="domain_routes")
    route_by_id = {
        str(item.get("route_id")): item
        for item in routes
        if isinstance(item.get("route_id"), str)
    }
    frozen_routes = {item["route_id"]: item for item in manifest["route_inputs"]}
    if set(route_by_id) != set(frozen_routes):
        raise ContractError("Completion DomainRoutes differ from the frozen Join")
    for route_id, frozen in frozen_routes.items():
        route = route_by_id[route_id]
        if (
            route.get("status") != frozen["status"]
            or route.get("required") is not frozen["required"]
            or not isinstance(route.get("integrity"), Mapping)
            or route["integrity"].get("payload_hash") != frozen["payload_hash"]
        ):
            raise ContractError(f"Completion DomainRoute is stale: {route_id}")

    findings = _mapping_list(value.get("findings"), label="findings")
    frozen_findings = {
        item["finding_id"]: item["content_hash"]
        for item in manifest["finding_inputs"]
    }
    actual_findings = {
        str(item.get("finding_id")): item.get("content_hash")
        for item in findings
    }
    if actual_findings != frozen_findings:
        raise ContractError("Completion Findings differ from the frozen Join")

    required_route_ids = {
        item["route_id"] for item in manifest["route_inputs"] if item["required"]
    }
    terminal_route_ids = {
        item["route_id"] for item in integration["required_domain_terminal_map"]
    }
    if terminal_route_ids != required_route_ids:
        raise ContractError("Completion integration hides a required DomainRoute")
    if set(integration["cross_finding_relation_refs"]) != {
        item["relation_id"] for item in manifest["relation_inputs"]
    }:
        raise ContractError("Completion integration omits a Finding relation")
    if set(integration["issue_cluster_refs"]) != {
        item["cluster_id"] for item in manifest["cluster_inputs"]
    }:
        raise ContractError("Completion integration omits an IssueCluster")

    strict = deepcopy(dict(value))
    strict.update({
        "cross_finding_join_complete": True,
        "cross_domain_integrator_complete": True,
        "duplicate_merge_complete": True,
        "conflicts_disclosed": True,
        "coverage_complete": all(_finding_valid(item) for item in findings),
    })
    return assess_completion(strict)


def verify_completion_assessment(value: Mapping[str, Any]) -> None:
    document = deepcopy(dict(value))
    SchemaStore().validate("completion-assessment.schema.json", document)
    claimed = document.pop("content_hash")
    if _hash(document) != claimed:
        raise ContractError("Completion Assessment content hash is invalid")
    expected_id_body = dict(document)
    assessment_id = expected_id_body.pop("assessment_id")
    if make_id("completion", expected_id_body) != assessment_id:
        raise ContractError("Completion Assessment ID is invalid")
    hard_blocked = bool(
        document["blocking_case_refs"]
        or document["blocking_required_work_refs"]
        or document["blocking_domain_route_refs"]
        or document["invalid_finding_refs"]
        or document["hard_failure_refs"]
        or not all(document["gate_results"].values())
    )
    if hard_blocked and document["status"] != "not_ready":
        raise ContractError("Completion Assessment bypasses a required blocker")
    if document["limited_completion_eligible"] and document["status"] != "limited_completion_ready":
        raise ContractError("Completion limited eligibility is inconsistent")


def compile_completion_action_card(assessment: Mapping[str, Any]) -> dict[str, Any]:
    verify_completion_assessment(assessment)
    if assessment["status"] == "not_ready":
        raise ContractError("Completion Action Card requires an eligible assessment")
    options = [
        {"option_id": "finalize", "response_type": "confirm", "next_step": "Create the final TTY approval request."},
        {"option_id": "add_data", "response_type": "provide_data", "next_step": "Reopen only affected cases."},
        {"option_id": "review_finding", "response_type": "choose_one", "next_step": "Reopen the selected Finding."},
    ]
    if assessment["status"] == "limited_completion_ready":
        options.append({
            "option_id": "accept_limited",
            "response_type": "proceed_limited",
            "next_step": "Record limitations in a new revision and request final TTY approval.",
        })
    options.append({"option_id": "stop", "response_type": "stop", "next_step": "Stop without finalizing."})
    semantic: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": assessment["run_id"],
        "base_revision": assessment["revision"],
        "assessment_id": assessment["assessment_id"],
        "assessment_hash": assessment["content_hash"],
        "completion_status": assessment["status"],
        "disposition_counts": deepcopy(assessment["disposition_counts"]),
        "coverage_gaps": list(assessment["coverage_gaps"]),
        "completion_limitations": list(assessment["completion_limitations"]),
        "options": options,
    }
    action_id = make_id("completion_action", semantic)
    card = {"action_id": action_id, **semantic}
    card["content_hash"] = _hash(card)
    SchemaStore().validate("completion-action-card.schema.json", card)
    return card
