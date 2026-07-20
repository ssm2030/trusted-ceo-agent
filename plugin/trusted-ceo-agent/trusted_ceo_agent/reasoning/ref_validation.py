from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from trusted_ceo_agent.errors import ContractError


INTEGRATED_ARRAY_FIELDS = (
    "issue_clusters",
    "integrated_issues",
    "causal_relation_hypotheses",
    "cross_issue_conflicts",
    "blind_spots",
    "response_type_candidates",
    "expert_review_candidates",
)
DEEP_ARRAY_FIELDS = (
    "updated_cause_hypotheses",
    "updated_counter_hypotheses",
    "distinguishing_test_results",
    "conditional_response_candidates",
    "expert_review_candidates",
    "remaining_uncertainties",
    "additional_data_requests",
)


def _as_set(values: Sequence[str] | set[str] | None) -> set[str]:
    if values is None:
        return set()
    return {str(value) for value in values}


def _job_set(job: Mapping[str, Any], field: str) -> set[str]:
    value = job.get(field, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ContractError(f"Reasoning Job {field} must be an array of strings")
    return set(value)


def _require_allowed(values: Sequence[str] | set[str], allowed: set[str], label: str) -> None:
    outside = set(values) - allowed
    if outside:
        raise ContractError(f"draft references {label} outside runtime allowlist: {sorted(outside)}")


def _index(document: Mapping[str, Any], fields: Sequence[str]) -> dict[str, tuple[str, Mapping[str, Any]]]:
    result: dict[str, tuple[str, Mapping[str, Any]]] = {}
    for field in fields:
        entries = document.get(field, [])
        if not isinstance(entries, list):
            raise ContractError(f"{field} must be an array")
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ContractError(f"{field} entries must be objects")
            local_key = entry.get("local_key")
            payload = entry.get("payload")
            if not isinstance(local_key, str) or not local_key or not isinstance(payload, Mapping):
                raise ContractError(f"{field} entries require local_key and payload")
            if local_key in result:
                raise ContractError(f"duplicate stage local_key: {local_key}")
            result[local_key] = (field, payload)
    return result


def _evidence_ref(
    reference: Any,
    facts: set[str],
    signals: set[str],
    label: str,
    documents: set[str] | None = None,
) -> None:
    if not isinstance(reference, str):
        raise ContractError(f"{label} must be a string")
    if reference.startswith("fact_"):
        _require_allowed({reference}, facts, "Fact")
    elif reference.startswith("signal_"):
        _require_allowed({reference}, signals, "Signal")
    elif reference.startswith('document_') and documents is not None:
        _require_allowed({reference}, documents, 'Document Evidence')
    else:
        raise ContractError(f"{label} is not an allowed Evidence ref: {reference}")


def _evidence_refs(values: Any, facts: set[str], signals: set[str], label: str) -> None:
    if not isinstance(values, list):
        raise ContractError(f"{label} must be an array")
    for reference in values:
        _evidence_ref(reference, facts, signals, label)


def _proposals(
    values: Any,
    facts: set[str],
    signals: set[str],
    label: str,
    documents: set[str] | None = None,
) -> None:
    if not isinstance(values, list):
        raise ContractError(f"{label} must be an array")
    for proposal in values:
        if not isinstance(proposal, Mapping):
            raise ContractError(f"{label} entries must be objects")
        _evidence_ref(
            proposal.get("evidence_ref"), facts, signals, label, documents,
        )


def validate_lens_references(
    job: Mapping[str, Any],
    draft: Mapping[str, Any],
) -> None:
    facts = _job_set(job, 'allowed_fact_ids')
    signals = _job_set(job, 'allowed_signal_ids')
    documents = _job_set(job, 'allowed_document_evidence_ids')
    for observation in draft.get('observations', []):
        _require_allowed(observation.get('fact_ids', []), facts, 'Fact')
        _require_allowed(observation.get('signal_ids', []), signals, 'Signal')
        _require_allowed(
            observation.get('document_evidence_ids', []),
            documents,
            'Document Evidence',
        )
        _value_refs(observation.get('value_refs', []), facts, signals, 'observation value ref')
    for field in (
        'business_meanings',
        'problem_candidates',
        'cause_hypotheses',
        'counter_hypotheses',
        'expert_trigger_candidates',
    ):
        for claim in draft.get(field, []):
            _value_refs(claim.get('value_refs', []), facts, signals, f'{field} value ref')
            _proposals(
                claim.get('evidence_proposals', []),
                facts,
                signals,
                f'{field} evidence',
                documents,
            )


def _value_refs(values: Any, facts: set[str], signals: set[str], label: str) -> None:
    if not isinstance(values, list):
        raise ContractError(f"{label} must be an array")
    for value_ref in values:
        if not isinstance(value_ref, Mapping):
            raise ContractError(f"{label} entries must be objects")
        _evidence_ref(value_ref.get("fact_or_signal_id"), facts, signals, label)


def validate_integrated_references(
    job: Mapping[str, Any],
    draft: Mapping[str, Any],
    *,
    allowed_claim_refs: set[str] | None = None,
    allowed_problem_family_refs: set[str] | None = None,
    allowed_response_refs: set[str] | None = None,
    allowed_condition_refs: set[str] | None = None,
    allowed_data_request_refs: set[str] | None = None,
) -> None:
    facts = _job_set(job, "allowed_fact_ids")
    signals = _job_set(job, "allowed_signal_ids")
    mechanisms = _job_set(job, "allowed_mechanism_refs")
    tests = _job_set(job, "allowed_test_refs")
    experts = _job_set(job, "allowed_expert_trigger_refs")
    decision_types = _job_set(job, "allowed_decision_type_refs")
    decision_units = _job_set(job, "allowed_decision_unit_refs")
    capabilities = _job_set(job, "capability_ids")
    claims = _as_set(allowed_claim_refs)
    families = _as_set(allowed_problem_family_refs)
    responses = _as_set(allowed_response_refs)
    conditions = _as_set(allowed_condition_refs)
    data_requests = _as_set(allowed_data_request_refs)

    index = _index(draft, INTEGRATED_ARRAY_FIELDS)
    issue_keys = {key for key, (field, _) in index.items() if field == "integrated_issues"}
    conflict_keys = {key for key, (field, _) in index.items() if field == "cross_issue_conflicts"}

    for entry in draft.get("issue_clusters", []):
        payload = entry["payload"]
        _require_allowed({payload["problem_family_ref"]}, families, "Problem family")
        _require_allowed({payload["decision_unit_ref"]}, decision_units, "decision unit")
        _require_allowed(payload["source_candidate_ids"], claims, "source candidate claim")

    for entry in draft.get("integrated_issues", []):
        payload = entry["payload"]
        _require_allowed({payload["problem_family_ref"]}, families, "Problem family")
        _require_allowed({payload["decision_unit_ref"]}, decision_units, "decision unit")
        for field in (
            "source_candidate_ids", "observation_claim_refs", "cause_hypothesis_refs",
            "counter_hypothesis_refs",
        ):
            _require_allowed(payload[field], claims, field)
        _require_allowed(payload["unresolved_conflict_refs"], conflict_keys, "unresolved conflict")
        _evidence_refs(payload["impact_evidence_refs"], facts, signals, "impact evidence")
        _evidence_refs(payload["urgency_evidence_refs"], facts, signals, "urgency evidence")
        _evidence_refs(payload["counter_evidence_refs"], facts, signals, "counter evidence")
        proposal = payload.get("decision_need_proposal")
        if proposal is not None:
            _require_allowed({proposal["decision_type_ref"]}, decision_types, "decision type")
            _require_allowed({proposal["decision_unit_ref"]}, decision_units, "decision unit")
            _require_allowed(proposal["basis_claim_refs"], claims, "decision basis claim")
        _require_allowed(payload["verification_requirement_refs"], tests, "verification test")
        _require_allowed(payload["response_type_refs"], responses, "response")
        _require_allowed(payload["expert_trigger_refs"], experts, "expert trigger")

    for entry in draft.get("causal_relation_hypotheses", []):
        payload = entry["payload"]
        _require_allowed(
            {payload["from_issue_local_key"], payload["to_issue_local_key"]},
            issue_keys,
            "causal relation issue",
        )
        _require_allowed({payload["mechanism_ref"]}, mechanisms, "mechanism")
        _proposals(payload["supports_evidence_proposals"], facts, signals, "causal support evidence")
        _proposals(payload["contradicts_evidence_proposals"], facts, signals, "causal counter evidence")
        _require_allowed(payload["distinguishing_test_refs"], tests, "distinguishing test")

    for entry in draft.get("cross_issue_conflicts", []):
        payload = entry["payload"]
        _require_allowed(payload["target_refs"], issue_keys | claims, "conflict target")
        _proposals(payload["side_a_evidence_proposals"], facts, signals, "conflict side A evidence")
        _proposals(payload["side_b_evidence_proposals"], facts, signals, "conflict side B evidence")
        _require_allowed(payload["resolution_test_refs"], tests, "conflict resolution test")

    for entry in draft.get("blind_spots", []):
        payload = entry["payload"]
        _require_allowed({payload["capability_ref"]}, capabilities, "capability")
        _require_allowed(payload["data_request_refs"], data_requests, "data request")

    for entry in draft.get("response_type_candidates", []):
        payload = entry["payload"]
        _require_allowed({payload["target_issue_local_key"]}, issue_keys, "response target issue")
        _require_allowed({payload["response_ref"]}, responses, "response")
        _require_allowed(payload["precondition_refs"], conditions, "response precondition")
        _require_allowed(payload["disqualifier_refs"], conditions, "response disqualifier")
        _require_allowed(payload["verification_requirement_refs"], tests, "response verification test")

    for entry in draft.get("expert_review_candidates", []):
        payload = entry["payload"]
        _require_allowed({payload["target_issue_local_key"]}, issue_keys, "expert target issue")
        _require_allowed({payload["expert_trigger_ref"]}, experts, "expert trigger")
        _proposals(payload["evidence_proposals"], facts, signals, "expert evidence")


def validate_deep_references(
    job: Mapping[str, Any],
    draft: Mapping[str, Any],
    *,
    allowed_issue_refs: set[str] | None = None,
    allowed_claim_refs: set[str] | None = None,
    allowed_response_refs: set[str] | None = None,
    allowed_condition_refs: set[str] | None = None,
    allowed_monitoring_metric_refs: set[str] | None = None,
) -> None:
    facts = _job_set(job, "allowed_fact_ids")
    signals = _job_set(job, "allowed_signal_ids")
    mechanisms = _job_set(job, "allowed_mechanism_refs")
    tests = _job_set(job, "allowed_test_refs")
    experts = _job_set(job, "allowed_expert_trigger_refs")
    issues = _as_set(allowed_issue_refs)
    claims = _as_set(allowed_claim_refs)
    responses = _as_set(allowed_response_refs)
    conditions = _as_set(allowed_condition_refs)
    metrics = _as_set(allowed_monitoring_metric_refs)

    _index(draft, DEEP_ARRAY_FIELDS)
    for field in DEEP_ARRAY_FIELDS:
        for entry in draft.get(field, []):
            _require_allowed({entry["payload"]["target_issue_ref"]}, issues, "approved issue")

    for entry in draft.get("updated_cause_hypotheses", []):
        payload = entry["payload"]
        _require_allowed({payload["claim_ref"]}, claims, "cause claim")
        _require_allowed({payload["mechanism_ref"]}, mechanisms, "mechanism")
        _value_refs(payload["value_refs"], facts, signals, "cause value ref")
        _proposals(payload["evidence_proposals"], facts, signals, "cause evidence")
        _require_allowed(payload["support_condition_refs"], conditions, "support condition")
        _require_allowed(payload["rejection_condition_refs"], conditions, "rejection condition")
        _require_allowed(payload["distinguishing_test_refs"], tests, "distinguishing test")

    for entry in draft.get("updated_counter_hypotheses", []):
        payload = entry["payload"]
        _require_allowed(
            {payload["claim_ref"], payload["challenged_hypothesis_ref"]}, claims, "counter claim"
        )
        _require_allowed({payload["mechanism_ref"]}, mechanisms, "mechanism")
        _value_refs(payload["value_refs"], facts, signals, "counter value ref")
        _proposals(payload["evidence_proposals"], facts, signals, "counter evidence")

    for entry in draft.get("distinguishing_test_results", []):
        payload = entry["payload"]
        _require_allowed({payload["test_ref"]}, tests, "distinguishing test")
        _require_allowed(payload["result_fact_ids"], facts, "test result Fact")
        _require_allowed(payload["result_signal_ids"], signals, "test result Signal")

    for entry in draft.get("conditional_response_candidates", []):
        payload = entry["payload"]
        _require_allowed({payload["response_ref"]}, responses, "response")
        _value_refs(payload["value_refs"], facts, signals, "response value ref")
        _require_allowed(payload["precondition_refs"], conditions, "response precondition")
        _require_allowed(payload["disqualifier_refs"], conditions, "response disqualifier")
        _require_allowed(payload["monitoring_metric_refs"], metrics, "monitoring metric")
        _require_allowed(payload["expert_review_refs"], experts, "expert trigger")

    for entry in draft.get("expert_review_candidates", []):
        payload = entry["payload"]
        _require_allowed({payload["expert_trigger_ref"]}, experts, "expert trigger")
        _proposals(payload["evidence_proposals"], facts, signals, "expert evidence")
