from __future__ import annotations

import copy
import hashlib
import re
from collections.abc import Mapping
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.reasoning.ref_validation import (
    validate_deep_references,
    validate_integrated_references,
)


NUMBER_LITERAL = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:[.,]\d+)?\s*%?")


def _parse(value: Mapping[str, Any] | str | bytes) -> dict[str, Any]:
    parsed = strict_loads(value) if isinstance(value, (str, bytes)) else copy.deepcopy(dict(value))
    if not isinstance(parsed, dict):
        raise ContractError("draft must be a JSON object")
    return parsed


def _identifier(prefix: str, value: Any) -> str:
    return prefix + hashlib.sha256(canonical_bytes(value)).hexdigest()[:24]


def _reject_forbidden_keys(value: Any, forbidden: set[str]) -> None:
    if isinstance(value, dict):
        overlap = set(value) & forbidden
        if overlap:
            raise ContractError(f"draft attempts to set runtime-owned fields: {sorted(overlap)}")
        for child in value.values():
            _reject_forbidden_keys(child, forbidden)
    elif isinstance(value, list):
        for child in value:
            _reject_forbidden_keys(child, forbidden)


def _reject_numeric_templates(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if (key.endswith("template") or key == "template") and isinstance(child, str) and NUMBER_LITERAL.search(child):
                raise ContractError("numeric literal is forbidden in writer template")
            _reject_numeric_templates(child)
    elif isinstance(value, list):
        for child in value:
            _reject_numeric_templates(child)


def normalize_integrated_draft(
    job: Mapping[str, Any],
    draft: Mapping[str, Any] | str | bytes,
    *,
    allowed_card_refs: set[str],
    allowed_claim_refs: set[str] | None = None,
    allowed_problem_family_refs: set[str] | None = None,
    allowed_response_refs: set[str] | None = None,
    allowed_condition_refs: set[str] | None = None,
    allowed_data_request_refs: set[str] | None = None,
) -> dict[str, Any]:
    if job.get("stage") != "integrated":
        raise ContractError("integrated normalizer requires integrated Job")
    payload = _parse(draft)
    SchemaStore().validate("integrated-draft.schema.json", payload)
    _reject_forbidden_keys(payload, {"primary_grade", "grade", "final_recommendation", "action_template"})
    _reject_numeric_templates(payload)
    if payload.get("join_manifest_ref") != job.get("join_manifest_ref"):
        raise ContractError("integrated draft uses stale Join manifest")
    if not set(payload.get("card_refs", [])).issubset(allowed_card_refs):
        raise ContractError("integrated draft references a card outside the Join result")
    validate_integrated_references(
        job,
        payload,
        allowed_claim_refs=allowed_claim_refs,
        allowed_problem_family_refs=allowed_problem_family_refs,
        allowed_response_refs=allowed_response_refs,
        allowed_condition_refs=allowed_condition_refs,
        allowed_data_request_refs=allowed_data_request_refs,
    )
    body = {"job_id": job["job_id"], "payload": payload, "materialized_by": "runtime_integrator"}
    body["integrated_assessment_id"] = _identifier("integrated_", body)
    return body


def normalize_deep_dive_draft(
    job: Mapping[str, Any],
    draft: Mapping[str, Any] | str | bytes,
    *,
    allowed_issue_refs: set[str] | None = None,
    allowed_claim_refs: set[str] | None = None,
    allowed_response_refs: set[str] | None = None,
    allowed_condition_refs: set[str] | None = None,
    allowed_monitoring_metric_refs: set[str] | None = None,
) -> dict[str, Any]:
    if job.get("stage") != "deep_dive":
        raise ContractError("deep-dive normalizer requires deep_dive Job")
    payload = _parse(draft)
    SchemaStore().validate("deep-dive-draft.schema.json", payload)
    _reject_forbidden_keys(payload, {"primary_grade", "grade", "decision_required"})
    _reject_numeric_templates(payload)
    if payload.get("approved_scope_ref") != job.get("approved_scope_ref"):
        raise ContractError("deep-dive draft uses an unapproved scope")
    if sorted(payload.get("component_run_refs", [])) != sorted(job.get("component_run_refs", [])):
        raise ContractError("deep-dive draft uses unapproved component runs")
    validate_deep_references(
        job,
        payload,
        allowed_issue_refs=allowed_issue_refs,
        allowed_claim_refs=allowed_claim_refs,
        allowed_response_refs=allowed_response_refs,
        allowed_condition_refs=allowed_condition_refs,
        allowed_monitoring_metric_refs=allowed_monitoring_metric_refs,
    )
    body = {"job_id": job["job_id"], "payload": payload, "materialized_by": "runtime_integrator"}
    body["deep_dive_result_id"] = _identifier("deep_", body)
    return body


def normalize_writer_draft(job: Mapping[str, Any], draft: Mapping[str, Any] | str | bytes) -> dict[str, Any]:
    if job.get("stage") != "writer":
        raise ContractError("writer normalizer requires writer Job")
    payload = _parse(draft)
    if payload.get("structured_output_ref") != job.get("structured_output_ref"):
        raise ContractError("writer draft uses stale structured output")
    _reject_forbidden_keys(payload, {"primary_grade", "grade", "evidence_proposals", "evidence_link_ids", "new_claim"})
    _reject_numeric_templates(payload)
    allowed = set(job.get("allowed_claim_ids", []))
    referenced = {
        item.get("claim_id") for item in payload.get("claim_templates", [])
    }
    referenced.update(item.get("claim_id") for item in payload.get("expert_packet_templates", []))
    if None in referenced or not referenced.issubset(allowed):
        raise ContractError("writer draft references a claim outside its allowlist")
    body = {"job_id": job["job_id"], "payload": payload, "materialized_by": "runtime_normalizer"}
    body["writer_result_id"] = _identifier("writer_", body)
    return body
