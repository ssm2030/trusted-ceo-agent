from __future__ import annotations

import copy
import hashlib
import hmac
import re
from typing import Any, Mapping

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, IntegrityError
from trusted_ceo_agent.grading.grader import grade
from trusted_ceo_agent.outputs.final_result import build_final_result
from trusted_ceo_agent.outputs.render import render_package
from trusted_ceo_agent.outputs.validation import revalidate_package
from trusted_ceo_agent.runtime_documents import (
    artifact_payload as _artifact_payload,
    load_document as _load,
    mission_document as _mission,
    status_value as _status,
)


NUMBER_LITERAL = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:[.,]\d+)?\s*%?")


def _reject_runtime_owned(value: Any) -> None:
    forbidden = {"primary_grade", "grade", "secondary_flags", "evidence_link_ids", "value_refs"}
    if isinstance(value, Mapping):
        overlap = forbidden & set(value)
        if overlap:
            raise ContractError(f"overlay attempts to modify runtime-owned fields: {sorted(overlap)}")
        for child in value.values():
            _reject_runtime_owned(child)
    elif isinstance(value, list):
        for child in value:
            _reject_runtime_owned(child)


def _template_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 400:
        raise ContractError(f"{label} must be a non-empty template of at most 400 characters")
    if NUMBER_LITERAL.search(value):
        raise ContractError(f"numeric literal is forbidden in {label}")
    return value


def _apply_writer(structured: dict[str, Any], files: Mapping[str, bytes]) -> None:
    if "reasoning/writer-result.json" not in files:
        return
    document = _load(files, "reasoning/writer-result.json")
    _reject_runtime_owned(document)
    payload = _artifact_payload(document, "writer result")
    if payload.get("structured_output_ref") != "final/structured-output.json":
        raise ContractError("writer result references a stale structured output")
    issue_by_id = {
        item["issue_id"]: item for item in structured.get("issues", [])
        if isinstance(item, dict) and isinstance(item.get("issue_id"), str)
    }
    packet_by_id = {
        item["expert_packet_id"]: item for item in structured.get("expert_review_packets", [])
        if isinstance(item, dict) and isinstance(item.get("expert_packet_id"), str)
    }
    seen: set[str] = set()
    templates = payload.get("claim_templates", [])
    if not isinstance(templates, list):
        raise ContractError("writer claim templates must be an array")
    for item in templates:
        if not isinstance(item, Mapping) or not isinstance(item.get("claim_id"), str):
            raise ContractError("writer claim template identity is invalid")
        claim_id = str(item["claim_id"])
        if claim_id in seen or claim_id not in issue_by_id:
            raise ContractError(f"writer references an unknown or duplicate issue: {claim_id}")
        seen.add(claim_id)
        issue_by_id[claim_id]["why_it_matters_template"] = _template_text(
            item.get("template"), "writer claim template",
        )
    seen_packets: set[str] = set()
    packet_templates = payload.get("expert_packet_templates", [])
    if not isinstance(packet_templates, list):
        raise ContractError("writer expert packet templates must be an array")
    for item in packet_templates:
        if not isinstance(item, Mapping) or not isinstance(item.get("claim_id"), str):
            raise ContractError("writer expert packet template identity is invalid")
        packet_id = str(item["claim_id"])
        if packet_id in seen_packets or packet_id not in packet_by_id:
            raise ContractError(f"writer references an unknown or duplicate expert packet: {packet_id}")
        seen_packets.add(packet_id)
        packet_by_id[packet_id]["question_template"] = _template_text(
            item.get("template"), "writer expert packet template",
        )
    order = payload.get("ceo_brief_section_order", [])
    if not isinstance(order, list) or any(not isinstance(item, str) for item in order):
        raise ContractError("writer section order must be an array of strings")


def _dispositions(raw: Any, expected: set[str], label: str) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        raise ContractError(f"{label} must be an object")
    unknown = set(raw) - expected
    missing = expected - set(raw)
    if unknown:
        raise ContractError(f"{label} contains unknown references: {sorted(unknown)}")
    if missing:
        raise ContractError(f"{label} is incomplete: {sorted(missing)}")
    result: dict[str, str] = {}
    for reference in sorted(expected):
        status = _status(raw[reference])
        if status not in {"accepted", "rejected"}:
            raise ContractError(f"{label} has an invalid disposition: {reference}")
        result[reference] = status
    return result


def _public_item(item: Mapping[str, Any], *, issue: bool = False) -> dict[str, Any]:
    omitted = {"local_key", "problem_family_ref"} if issue else set()
    return {
        key: copy.deepcopy(value)
        for key, value in item.items()
        if key not in omitted and not key.startswith("_")
    }


def _verify_structured_grades(
    structured: Mapping[str, Any], files: Mapping[str, bytes],
) -> None:
    inputs = _load(files, "grading/inputs.json")
    if not isinstance(inputs, list):
        raise IntegrityError("grading inputs must be an array")
    records_by_issue: dict[str, Mapping[str, Any]] = {}
    records_by_id: dict[str, Mapping[str, Any]] = {}
    for path in sorted(files):
        if not path.startswith("grading/records/") or not path.endswith(".json"):
            continue
        record = _load(files, path)
        if not isinstance(record, Mapping):
            raise IntegrityError(f"Grade Record must be an object: {path}")
        issue_id = record.get("issue_id")
        record_id = record.get("grade_record_id")
        if not isinstance(issue_id, str) or not isinstance(record_id, str):
            raise IntegrityError(f"Grade Record identity is invalid: {path}")
        if issue_id in records_by_issue or record_id in records_by_id:
            raise IntegrityError("duplicate Grade Record identity")
        records_by_issue[issue_id] = record
        records_by_id[record_id] = record
    recomputed_ids: set[str] = set()
    for grading_input in inputs:
        if not isinstance(grading_input, Mapping):
            raise IntegrityError("grading input must be an object")
        recomputed = grade(grading_input)
        stored = records_by_issue.get(str(grading_input.get("issue_id")))
        if stored is None or canonical_bytes(stored) != canonical_bytes(recomputed):
            raise IntegrityError(f"Grade Record mismatch: {grading_input.get('issue_id')}")
        recomputed_ids.add(str(stored["grade_record_id"]))
    declared_ids = structured.get("grade_record_ids", [])
    if not isinstance(declared_ids, list) or set(declared_ids) != recomputed_ids:
        raise IntegrityError("structured output Grade Record references do not match recomputation")
    for issue in structured.get("issues", []):
        if not isinstance(issue, Mapping) or not isinstance(issue.get("issue_id"), str):
            raise IntegrityError("structured issue identity is invalid")
        record = records_by_issue.get(str(issue["issue_id"]))
        if record is None or record.get("publication_status") != "published":
            raise IntegrityError(f"structured issue lacks a published Grade Record: {issue['issue_id']}")
        if issue.get("primary_grade") != record.get("primary_grade"):
            raise IntegrityError(f"structured issue grade differs from Grade Record: {issue['issue_id']}")
        if sorted(issue.get("secondary_flags", [])) != sorted(record.get("secondary_flags", [])):
            raise IntegrityError(f"structured issue flags differ from Grade Record: {issue['issue_id']}")


def _verify_professional_publication_binding(
    files: Mapping[str, bytes],
    structured: Mapping[str, Any],
) -> None:
    path = "final/professional-publication.json"
    if path not in files:
        return
    publication = _load(files, path)
    if not isinstance(publication, Mapping):
        raise IntegrityError("professional publication must be an object")
    claimed_hash = publication.get("content_hash")
    body = {
        key: copy.deepcopy(value)
        for key, value in publication.items()
        if key != "content_hash"
    }
    if (
        not isinstance(claimed_hash, str)
        or not hmac.compare_digest(
            claimed_hash, hashlib.sha256(canonical_bytes(body)).hexdigest()
        )
    ):
        raise IntegrityError("professional publication content hash mismatch")
    if canonical_bytes(body.get("structured_output")) != canonical_bytes(structured):
        raise IntegrityError("professional publication structured output mismatch")


def build_delivery_package(
    files: Mapping[str, bytes], *, run_id: str, revision: int,
) -> dict[str, bytes]:
    loaded = _load(files, "final/structured-output.json")
    if not isinstance(loaded, Mapping):
        raise ContractError("structured output must be an object")
    structured = copy.deepcopy(dict(loaded))
    _verify_professional_publication_binding(files, structured)
    _verify_structured_grades(structured, files)
    core = _load(files, "evidence/core.json")
    if not isinstance(core, Mapping):
        raise ContractError("Evidence Core must be an object")
    mission = _mission(files)
    _apply_writer(structured, files)

    overlay = _load(files, "workflow/hitl-overlay.json", {})
    if not isinstance(overlay, Mapping):
        raise ContractError("HITL overlay must be an object")
    _reject_runtime_owned(overlay)
    issues = [item for item in structured.get("issues", []) if isinstance(item, dict)]
    issue_by_ref: dict[str, dict[str, Any]] = {}
    for issue in issues:
        issue_id = issue.get("issue_id")
        local_key = issue.get("local_key")
        if not isinstance(issue_id, str):
            raise ContractError("structured issue identity is invalid")
        issue_by_ref[issue_id] = issue
        if isinstance(local_key, str):
            if local_key in issue_by_ref:
                raise ContractError(f"duplicate structured issue reference: {local_key}")
            issue_by_ref[local_key] = issue
    wording = overlay.get("ceo_wording", {})
    if not isinstance(wording, Mapping):
        raise ContractError("CEO wording overlay must be an object")
    for reference, changes in wording.items():
        issue = issue_by_ref.get(str(reference))
        if issue is None or not isinstance(changes, Mapping):
            raise ContractError(f"CEO wording references an unknown issue: {reference}")
        unknown = set(changes) - {"title_template", "why_it_matters_template"}
        if unknown:
            raise ContractError(f"CEO wording attempts to modify forbidden fields: {sorted(unknown)}")
        for field in sorted(changes):
            issue[field] = _template_text(changes[field], f"CEO wording {field}")

    active_issue_ids = {str(item["issue_id"]) for item in issues}
    relations = [
        item for item in structured.get("cross_issue_relations", [])
        if isinstance(item, Mapping)
        and item.get("from_issue_ref") in active_issue_ids
        and item.get("to_issue_ref") in active_issue_ids
    ]
    response_candidates = [
        item for item in structured.get("conditional_responses", [])
        if isinstance(item, Mapping) and item.get("_target_issue_ref") in active_issue_ids
    ]
    response_refs = {
        str(item["_candidate_ref"]) for item in response_candidates
        if isinstance(item.get("_candidate_ref"), str)
    }
    if len(response_refs) != len(response_candidates):
        raise ContractError("structured response candidate identities are invalid or duplicated")
    response_decisions = _dispositions(
        overlay.get("response_dispositions", {}), response_refs, "response dispositions",
    )
    accepted_responses = [
        item for item in response_candidates
        if response_decisions[str(item["_candidate_ref"])] == "accepted"
    ]
    accepted_candidate_refs = {str(item["_candidate_ref"]) for item in accepted_responses}
    accepted_response_ids = {str(item["response_id"]) for item in accepted_responses}
    monitoring = [
        item for item in structured.get("monitoring", [])
        if isinstance(item, Mapping)
        and item.get("_target_issue_ref") in active_issue_ids
        and item.get("_candidate_ref") in accepted_candidate_refs
    ]

    packets = [
        item for item in structured.get("expert_review_packets", [])
        if isinstance(item, Mapping) and item.get("_target_issue_ref") in active_issue_ids
    ]
    trigger_refs = {
        str(item["_trigger_ref"]) for item in packets
        if isinstance(item.get("_trigger_ref"), str)
    }
    routing = _dispositions(
        overlay.get("expert_routing", {}), trigger_refs, "expert routing",
    )
    for item in packets:
        reference = str(item["_trigger_ref"])
        if item.get("_required") is True and routing[reference] == "rejected":
            raise ContractError(f"required expert routing cannot be rejected: {reference}")
    accepted_packets = [
        item for item in packets if routing[str(item["_trigger_ref"])] == "accepted"
    ]
    accepted_experts_by_issue: dict[str, set[str]] = {}
    for item in accepted_packets:
        accepted_experts_by_issue.setdefault(str(item["_target_issue_ref"]), set()).add(
            str(item["_trigger_ref"])
        )
    for issue in issues:
        issue["conditional_response_refs"] = sorted(
            set(issue.get("conditional_response_refs", [])) & accepted_response_ids
        )
        issue["expert_review_refs"] = sorted(
            set(issue.get("expert_review_refs", []))
            & accepted_experts_by_issue.get(str(issue["issue_id"]), set())
        )

    delivery_scope = overlay.get("delivery_scope", {})
    if not isinstance(delivery_scope, Mapping):
        raise ContractError("delivery scope must be an object")

    approvals: list[dict[str, Any]] = []
    for path in sorted(files):
        if not path.startswith("approvals/records/") or not path.endswith(".json"):
            continue
        record = _load(files, path)
        if not isinstance(record, Mapping) or record.get("status") != "current":
            continue
        if record.get("gate") == "final" and record.get("decision") not in {
            None, "approve", "approve_with_edits",
        }:
            continue
        approvals.append({
            key: record[key]
            for key in (
                "gate", "status", "input_method", "fixture_only", "approval_id",
                "actor_role", "result_artifact_ref",
            )
            if key in record
        })
    if not any(item.get("gate") == "final" for item in approvals):
        raise ContractError("a current approved interactive Final approval is required")

    capabilities = core.get("capability_map", {}).get("capabilities", [])
    capability_status = "evaluated" if capabilities and all(
        item.get("status") == "available" for item in capabilities if isinstance(item, Mapping)
    ) else "limited"
    blind_spots = [
        item for item in structured.get("blind_spots", [])
        if isinstance(item, Mapping)
        and item.get("_target_issue_ref", next(iter(active_issue_ids), None)) in active_issue_ids
    ]
    result = build_final_result(
        run_summary={"run_id": run_id, "revision": revision},
        mission_summary={
            "objective": str(mission.get("objective", mission.get("business_question", "")))
        },
        capability_summary={"status": capability_status},
        issues=[_public_item(item, issue=True) for item in issues],
        evidence_links={
            item["evidence_link_id"]: item for item in core.get("evidence_links", [])
        },
        approvals=approvals,
        cross_issue_relations=[_public_item(item) for item in relations],
        conditional_responses=[_public_item(item) for item in accepted_responses],
        monitoring=[_public_item(item) for item in monitoring],
        blind_spots=[_public_item(item) for item in blind_spots],
        expert_review_packets=[_public_item(item) for item in accepted_packets],
    )
    SchemaStore().validate("final-result.schema.json", result)
    package = render_package(result)
    revalidate_package(
        result, package,
        evidence_links={
            item["evidence_link_id"]: item for item in core.get("evidence_links", [])
        },
    )
    return package
