from __future__ import annotations

import copy
import hashlib
import re
from collections.abc import Mapping
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


ARRAY_FIELDS = (
    "observations", "business_meanings", "problem_candidates", "cause_hypotheses",
    "counter_hypotheses", "challenge_reviews", "verification_tests", "signal_dispositions",
    "uncertainties", "data_requests", "human_questions", "expert_trigger_candidates", "limitations",
)
MATERIAL_FIELDS = (
    "business_meanings", "problem_candidates", "cause_hypotheses",
    "counter_hypotheses", "expert_trigger_candidates",
)
TEMPLATE_FIELDS = {"statement_template", "rationale_template", "purpose_template", "question_template", "review_question_template"}
NUMBER_LITERAL = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:[.,]\d+)?\s*%?")


def _digest(prefix: str, value: Any) -> str:
    return prefix + hashlib.sha256(canonical_bytes(value)).hexdigest()[:24]


def _parse(value: Mapping[str, Any] | str | bytes) -> dict[str, Any]:
    parsed = strict_loads(value) if isinstance(value, (str, bytes)) else copy.deepcopy(dict(value))
    if not isinstance(parsed, dict):
        raise ContractError("draft must be a JSON object")
    return parsed


def _walk(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _validate_templates(draft: Mapping[str, Any]) -> None:
    for key, value in _walk(draft):
        if key in TEMPLATE_FIELDS and isinstance(value, str) and NUMBER_LITERAL.search(value):
            raise ContractError(f"numeric literal is forbidden in {key}")


def _collect_refs(draft: Mapping[str, Any], allowed_facts: set[str], allowed_signals: set[str]) -> tuple[set[str], set[str]]:
    facts: set[str] = set()
    signals: set[str] = set()
    for key, value in _walk(draft):
        values: list[str] = []
        if key in {"fact_ids", "searched_fact_ids", "result_fact_ids"} and isinstance(value, list):
            values = [item for item in value if isinstance(item, str)]
            facts.update(values)
        elif key in {"signal_ids", "searched_signal_ids", "result_signal_ids"} and isinstance(value, list):
            values = [item for item in value if isinstance(item, str)]
            signals.update(values)
        elif key in {"fact_or_signal_id", "evidence_ref", "signal_id", "duplicate_of_signal_id"} and isinstance(value, str):
            if value.startswith("fact_"):
                facts.add(value)
            elif value.startswith("signal_"):
                signals.add(value)
    outside_facts = facts - allowed_facts
    outside_signals = signals - allowed_signals
    if outside_facts or outside_signals:
        raise ContractError(f"draft references values outside Job allowlist: facts={sorted(outside_facts)}, signals={sorted(outside_signals)}")
    return facts, signals


def _local_key_index(draft: Mapping[str, Any]) -> dict[str, tuple[str, dict[str, Any]]]:
    result: dict[str, tuple[str, dict[str, Any]]] = {}
    for field in ARRAY_FIELDS:
        entries = draft.get(field, [])
        if not isinstance(entries, list):
            raise ContractError(f"{field} must be an array")
        for item in entries:
            if not isinstance(item, dict):
                raise ContractError(f"{field} entries must be objects")
            local_key = item.get("local_key")
            if local_key is None:
                continue
            if not isinstance(local_key, str) or not local_key:
                raise ContractError("local_key must be a non-empty string")
            if local_key in result:
                raise ContractError(f"duplicate local_key: {local_key}")
            result[local_key] = (field, item)
    return result


def _require_parent(index: Mapping[str, tuple[str, dict[str, Any]]], key: Any, fields: set[str], label: str) -> None:
    if not isinstance(key, str) or key not in index or index[key][0] not in fields:
        raise ContractError(f"invalid {label}: {key}")


def _validate_graph(draft: Mapping[str, Any], index: Mapping[str, tuple[str, dict[str, Any]]]) -> None:
    for item in draft.get("business_meanings", []):
        for key in item.get("observation_local_keys", []):
            _require_parent(index, key, {"observations"}, "observation_local_key")
    for item in draft.get("problem_candidates", []):
        for key in item.get("business_meaning_local_keys", []):
            _require_parent(index, key, {"business_meanings"}, "business_meaning_local_key")
    for item in draft.get("cause_hypotheses", []):
        _require_parent(index, item.get("problem_local_key"), {"problem_candidates"}, "problem_local_key")
    for item in draft.get("counter_hypotheses", []):
        _require_parent(index, item.get("challenged_hypothesis_local_key"), {"cause_hypotheses"}, "challenged hypothesis")
    for item in draft.get("signal_dispositions", []):
        for key in item.get("target_local_keys", []):
            _require_parent(index, key, set(ARRAY_FIELDS), "signal disposition target")


def _validate_status(job: Mapping[str, Any], draft: Mapping[str, Any]) -> None:
    status = draft.get("assessment_status")
    if status not in {"complete", "partial", "not_assessable"}:
        raise ContractError("invalid assessment_status")
    if status == "not_assessable":
        if any(draft.get(field) for field in ("problem_candidates", "cause_hypotheses", "counter_hypotheses")):
            raise ContractError("not_assessable draft cannot contain problems or hypotheses")
        if not draft.get("data_requests") and not draft.get("limitations"):
            raise ContractError("not_assessable requires a data request or limitation")
    for field in MATERIAL_FIELDS:
        for item in draft.get(field, []):
            if not item.get("evidence_proposals"):
                raise ContractError(f"material claim lacks evidence: {item.get('local_key')}")
    causes = {item.get("local_key") for item in draft.get("cause_hypotheses", [])}
    challenged = {item.get("challenged_hypothesis_local_key") for item in draft.get("counter_hypotheses", [])}
    challenged.update(item.get("target_hypothesis_local_key") for item in draft.get("challenge_reviews", []))
    if status == "complete" and causes - challenged:
        raise ContractError(f"cause lacks challenge: {sorted(causes - challenged)}")
    required = set(job.get("required_signal_ids", []))
    dispositions = {item.get("signal_id") for item in draft.get("signal_dispositions", [])}
    if status == "complete" and not required.issubset(dispositions):
        raise ContractError(f"required Signal disposition missing: {sorted(required - dispositions)}")


def _validate_pack_allowlists(job: Mapping[str, Any], draft: Mapping[str, Any]) -> None:
    families = {
        str(item.get("problem_family_ref"))
        for item in draft.get("problem_candidates", [])
        if item.get("problem_family_ref") is not None
    }
    mechanisms = {
        str(item.get("mechanism_ref"))
        for field in ("cause_hypotheses", "counter_hypotheses")
        for item in draft.get(field, [])
        if item.get("mechanism_ref") is not None
    }
    tests = {
        str(reference)
        for item in draft.get("cause_hypotheses", [])
        for reference in item.get("distinguishing_test_refs", [])
    } | {
        str(item.get("test_ref"))
        for item in draft.get("verification_tests", [])
        if item.get("test_ref") is not None
    }
    expert_refs = {
        str(item.get("expert_trigger_ref"))
        for item in draft.get("expert_trigger_candidates", [])
        if item.get("expert_trigger_ref") is not None
    }
    checks = (
        ("problem family", families, set(job.get("allowed_problem_family_refs", []))),
        ("mechanism", mechanisms, set(job.get("allowed_mechanism_refs", []))),
        ("test", tests, set(job.get("allowed_test_refs", []))),
        ("expert trigger", expert_refs, set(job.get("allowed_expert_trigger_refs", []))),
    )
    for label, used, allowed in checks:
        outside = used - allowed
        if outside:
            raise ContractError(f"draft references {label} outside Job allowlist: {sorted(outside)}")


def normalize_lens_draft(job: Mapping[str, Any], draft: Mapping[str, Any] | str | bytes) -> dict[str, Any]:
    if job.get("stage") != "lens":
        raise ContractError("lens normalizer requires a lens Job")
    payload = _parse(draft)
    SchemaStore().validate("lens-card-draft.schema.json", payload)
    unknown = set(payload) - ({"assessment_status", "status_reason_codes"} | set(ARRAY_FIELDS))
    if unknown:
        raise ContractError(f"unknown Lens Draft fields: {sorted(unknown)}")
    for field in ARRAY_FIELDS:
        payload.setdefault(field, [])
    payload.setdefault("status_reason_codes", [])
    _validate_templates(payload)
    index = _local_key_index(payload)
    _validate_graph(payload, index)
    _validate_status(job, payload)
    _validate_pack_allowlists(job, payload)
    used_facts, used_signals = _collect_refs(
        payload, set(job.get("allowed_fact_ids", [])), set(job.get("allowed_signal_ids", [])),
    )

    claim_ids: dict[str, str] = {}
    for field in MATERIAL_FIELDS:
        for item in payload.get(field, []):
            claim_ids[item["local_key"]] = _digest("claim_", {
                "job_id": job["job_id"], "local_key": item["local_key"], "payload": item,
            })

    links: list[dict[str, Any]] = []
    for field in MATERIAL_FIELDS:
        target_type = field[:-1] if field.endswith("s") else field
        for item in payload.get(field, []):
            for proposal in item.get("evidence_proposals", []):
                evidence_ref = proposal.get("evidence_ref")
                if evidence_ref not in used_facts | used_signals:
                    raise ContractError(f"invalid evidence proposal ref: {evidence_ref}")
                link_body = {
                    "target_ref": claim_ids[item["local_key"]],
                    "target_type": target_type,
                    "evidence_ref": evidence_ref,
                    "polarity": proposal.get("polarity"),
                    "role": proposal.get("role"),
                    "stage": "lens",
                    "materialized_by": "runtime_normalizer",
                    "origin": {
                        "origin_type": "model_proposal",
                        "origin_job_id": job["job_id"],
                        "model_profile": job.get("model_profile", "host_managed"),
                        "proposal_hash": hashlib.sha256(canonical_bytes(proposal)).hexdigest(),
                    },
                    "independence_group_id": _digest("independence_", {"evidence_ref": evidence_ref}),
                }
                link_body["evidence_link_id"] = _digest("evidence_", link_body)
                links.append(link_body)
    links.sort(key=lambda item: item["evidence_link_id"])
    normalized_payload = copy.deepcopy(payload)
    for field in MATERIAL_FIELDS:
        for item in normalized_payload.get(field, []):
            item["claim_id"] = claim_ids[item["local_key"]]
    body = {
        "schema_version": "1.0",
        "job_id": job["job_id"],
        "artifact_ref": job["artifact_ref"],
        "pack_manifest_hash": job["pack_manifest_hash"],
        "lens_id": job["lens_id"],
        "model_profile": job.get("model_profile", "host_managed"),
        "assessment_status": payload["assessment_status"],
        "used_fact_ids": sorted(used_facts),
        "used_signal_ids": sorted(used_signals),
        "normalized_payload": normalized_payload,
        "evidence_link_ids": [item["evidence_link_id"] for item in links],
        "evidence_links": links,
        "validation_result": {"valid": True, "errors": []},
    }
    body["card_id"] = _digest("card_", body)
    body["integrity"] = {"artifact_hash": hashlib.sha256(canonical_bytes(body)).hexdigest()}
    return body
