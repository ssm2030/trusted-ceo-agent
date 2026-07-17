from __future__ import annotations

import copy
import hashlib
import hmac
import re
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, RevisionConflict
from trusted_ceo_agent.knowledge.release import (
    verify_knowledge_approval,
    verify_knowledge_release,
)


_STRUCTURED_FIELDS = frozenset({
    "facts", "criteria", "conclusions", "counter_evidence", "uncertainties",
    "verification_steps",
})
_PRIVACY_FIELDS = frozenset({
    "tenant_id", "contains_personal_data", "contains_confidential_data",
    "retention_class", "evaluation_reuse_consent", "deidentification_status",
    "source_copy_allowed",
})
_FEEDBACK_TYPES = frozenset({
    "false_positive", "false_negative", "wrong_norm", "wrong_procedure",
    "wrong_amount", "mapping_error", "evidence_error", "missing_counter",
    "overconfidence", "underconfidence", "cross_domain_miss", "usability",
    "oracle_error",
})
_SOURCE_TYPES = frozenset({"controlled_evaluation", "field_feedback", "system_candidate"})
_TRUST_STATES = frozenset({
    "machine_verified_failure", "expert_adjudicated", "unverified_feedback",
    "context_provided", "high_priority_unverified", "system_candidate",
})
_FAILURE_TYPES = frozenset({
    "ingestion", "mapping", "fact", "calculation", "expectation", "norm",
    "procedure", "counter", "routing", "cross_domain", "reasoning",
    "presentation", "evaluation",
})
_ARTIFACT_TYPES = frozenset({
    "kernel", "pack", "card", "component", "prompt", "parser", "mapping",
    "procedure", "norm", "method", "presentation",
})
_GATE_FIELDS = frozenset({
    "target_regression_passed", "full_regression_passed", "coverage_non_inferior",
    "security_passed", "determinism_passed", "performance_passed",
    "norm_effective", "jurisdiction_valid",
})
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d .()\-]{7,}\d)(?!\d)")


def _native(value: Any) -> Any:
    if isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value():
        return int(value)
    if isinstance(value, dict):
        return {key: _native(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_native(child) for child in value]
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _hash_without(value: Mapping[str, Any], field: str) -> str:
    body = dict(value)
    body.pop(field, None)
    return _digest(body)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value


def _nullable_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _integer(value: Any, field: str, *, minimum: int = 0) -> int:
    value = _native(value)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContractError(f"{field} must be an integer >= {minimum}")
    return value


def _sha256(value: Any, field: str) -> str:
    text = _text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ContractError(f"{field} must be a lowercase SHA-256")
    return text


def _string_set(values: Any, field: str, *, non_empty: bool = False) -> list[str]:
    if not isinstance(values, (list, tuple)):
        raise ContractError(f"{field} must be an array")
    result = [_text(item, field) for item in values]
    if len(result) != len(set(result)):
        raise ContractError(f"{field} contains duplicates")
    if non_empty and not result:
        raise ContractError(f"{field} must not be empty")
    return sorted(result)


def _reject_direct_identifier(value: str, field: str) -> None:
    if _EMAIL.search(value) or _PHONE.search(value):
        raise ContractError(f"direct identifier is forbidden in {field}")


def _structured(value: Any, field: str) -> dict[str, list[str]]:
    if not isinstance(value, Mapping) or set(value) != _STRUCTURED_FIELDS:
        raise ContractError(f"{field} must contain only auditable structured_content slots")
    result: dict[str, list[str]] = {}
    for slot in sorted(_STRUCTURED_FIELDS):
        items = _string_set(value[slot], f"{field}.{slot}")
        for item in items:
            _reject_direct_identifier(item, f"{field}.{slot}")
        result[slot] = items
    return result


def _privacy(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _PRIVACY_FIELDS:
        raise ContractError("privacy fields do not match the contract")
    result = {
        "tenant_id": _text(value["tenant_id"], "privacy.tenant_id"),
        "contains_personal_data": value["contains_personal_data"],
        "contains_confidential_data": value["contains_confidential_data"],
        "retention_class": _text(value["retention_class"], "privacy.retention_class"),
        "evaluation_reuse_consent": value["evaluation_reuse_consent"],
        "deidentification_status": value["deidentification_status"],
        "source_copy_allowed": value["source_copy_allowed"],
    }
    for key in (
        "contains_personal_data", "contains_confidential_data",
        "evaluation_reuse_consent", "source_copy_allowed",
    ):
        if not isinstance(result[key], bool):
            raise ContractError(f"privacy.{key} must be boolean")
    if result["contains_personal_data"] and result["deidentification_status"] != "deidentified":
        raise ContractError("personal data must be deidentified before Foundry intake")
    if result["deidentification_status"] not in {"deidentified", "not_applicable"}:
        raise ContractError("privacy.deidentification_status is invalid")
    if result["source_copy_allowed"]:
        raise ContractError("raw source copy is forbidden in Feedback Record")
    return result


def _artifact_manifest(values: Sequence[Mapping[str, Any]], field: str) -> list[dict[str, str]]:
    if not isinstance(values, (list, tuple)) or not values:
        raise ContractError(f"{field} must not be empty")
    result: list[dict[str, str]] = []
    for item in values:
        if not isinstance(item, Mapping) or set(item) != {
            "artifact_ref", "artifact_hash", "artifact_type"
        }:
            raise ContractError(f"{field} entry fields are invalid")
        artifact_type = _text(item["artifact_type"], f"{field}.artifact_type")
        if artifact_type not in _ARTIFACT_TYPES:
            raise ContractError(f"unsupported artifact_type: {artifact_type}")
        result.append({
            "artifact_ref": _text(item["artifact_ref"], f"{field}.artifact_ref"),
            "artifact_hash": _sha256(item["artifact_hash"], f"{field}.artifact_hash"),
            "artifact_type": artifact_type,
        })
    result.sort(key=lambda item: (item["artifact_ref"], item["artifact_hash"], item["artifact_type"]))
    if len({canonical_bytes(item) for item in result}) != len(result):
        raise ContractError(f"{field} contains duplicates")
    return result


def build_feedback_preview(
    *,
    source_type: str,
    run_id: str,
    run_revision: int,
    knowledge_release_id: str,
    issue_id: str | None,
    issue_family_id: str,
    fact_refs: Sequence[str],
    signal_refs: Sequence[str],
    evidence_refs: Sequence[str],
    feedback_type: str,
    structured_content: Mapping[str, Any],
    requested_outcome: str,
    submitter_id: str,
    authenticated_role: str,
    domain_credential_ref: str | None,
    trust_state: str,
    independence_flags: Sequence[str],
    conflict_of_interest_flags: Sequence[str],
    privacy: Mapping[str, Any],
) -> dict[str, Any]:
    if source_type not in _SOURCE_TYPES:
        raise ContractError(f"unsupported source_type: {source_type}")
    if feedback_type not in _FEEDBACK_TYPES:
        raise ContractError(f"unsupported feedback_type: {feedback_type}")
    if trust_state not in _TRUST_STATES:
        raise ContractError(f"unsupported trust_state: {trust_state}")
    requested_outcome = _text(requested_outcome, "requested_outcome")
    _reject_direct_identifier(requested_outcome, "requested_outcome")
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "source_type": source_type,
        "run_id": _text(run_id, "run_id"),
        "run_revision": _integer(run_revision, "run_revision"),
        "knowledge_release_id": _text(knowledge_release_id, "knowledge_release_id"),
        "issue_id": _nullable_text(issue_id, "issue_id"),
        "issue_family_id": _text(issue_family_id, "issue_family_id"),
        "fact_refs": _string_set(fact_refs, "fact_refs"),
        "signal_refs": _string_set(signal_refs, "signal_refs"),
        "evidence_refs": _string_set(evidence_refs, "evidence_refs"),
        "feedback_type": feedback_type,
        "structured_content": _structured(structured_content, "structured_content"),
        "requested_outcome": requested_outcome,
        "submitter_id": _text(submitter_id, "submitter_id"),
        "authenticated_role": _text(authenticated_role, "authenticated_role"),
        "domain_credential_ref": _nullable_text(domain_credential_ref, "domain_credential_ref"),
        "trust_state": trust_state,
        "independence_flags": _string_set(independence_flags, "independence_flags"),
        "conflict_of_interest_flags": _string_set(
            conflict_of_interest_flags, "conflict_of_interest_flags"
        ),
        "privacy": _privacy(privacy),
        "status": "draft_preview",
    }
    body["preview_id"] = "feedbackpreview_" + _digest(body)[:24]
    body["preview_hash"] = _hash_without(body, "preview_hash")
    return body


def _verify_preview(preview: Mapping[str, Any]) -> dict[str, Any]:
    value = _native(copy.deepcopy(dict(preview)))
    expected_fields = {
        "schema_version", "preview_id", "preview_hash", "source_type", "run_id",
        "run_revision", "knowledge_release_id", "issue_id", "issue_family_id",
        "fact_refs", "signal_refs", "evidence_refs", "feedback_type",
        "structured_content", "requested_outcome", "submitter_id",
        "authenticated_role", "domain_credential_ref", "trust_state",
        "independence_flags", "conflict_of_interest_flags", "privacy", "status",
    }
    if set(value) != expected_fields or value.get("status") != "draft_preview":
        raise ContractError("Feedback Preview fields are invalid")
    _structured(value["structured_content"], "structured_content")
    _privacy(value["privacy"])
    if not hmac.compare_digest(str(value["preview_hash"]), _hash_without(value, "preview_hash")):
        raise ContractError("Feedback Preview hash is invalid")
    return value


def submit_feedback(
    preview: Mapping[str, Any],
    stage1_approval: Mapping[str, Any],
    *,
    current_revision: int,
    submitted_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    preview_value = _verify_preview(preview)
    approval = _native(copy.deepcopy(dict(stage1_approval)))
    verify_knowledge_approval(approval)
    current_revision = _integer(current_revision, "current_revision")
    if approval["approval_stage"] != "feedback_submit" or approval["requested_action"] != "submit_feedback":
        raise ContractError("Stage 1 approval is required to submit feedback")
    if approval["expected_revision"] != current_revision:
        raise RevisionConflict("Stage 1 feedback approval is stale")
    if (
        approval["object_id"] != preview_value["preview_id"]
        or not hmac.compare_digest(approval["object_hash"], preview_value["preview_hash"])
    ):
        raise ContractError("Stage 1 approval is bound to another Feedback Preview")
    if approval["approver_role"] != "feedback_submitter":
        raise ContractError("Stage 1 approval requires feedback_submitter role")
    if submitted_at != approval["approved_at"]:
        raise ContractError("Feedback submission time must equal the bound approval time")

    feedback = {
        key: copy.deepcopy(preview_value[key])
        for key in (
            "schema_version", "source_type", "run_id", "run_revision",
            "knowledge_release_id", "issue_id", "issue_family_id", "fact_refs",
            "signal_refs", "evidence_refs", "feedback_type", "structured_content",
            "requested_outcome", "submitter_id", "authenticated_role",
            "domain_credential_ref", "trust_state", "independence_flags",
            "conflict_of_interest_flags", "privacy",
        )
    }
    feedback.update({
        "preview_hash": preview_value["preview_hash"],
        "stage1_approval_id": approval["knowledge_approval_id"],
        "stage1_approval_hash": approval["approval_hash"],
        "status": "submitted",
        "submitted_at": _text(submitted_at, "submitted_at"),
    })
    feedback["feedback_id"] = "feedback_" + _digest(feedback)[:24]
    feedback["feedback_hash"] = _hash_without(feedback, "feedback_hash")
    verify_feedback_record(feedback)
    receipt: dict[str, Any] = {
        "schema_version": "1.0.0",
        "feedback_id": feedback["feedback_id"],
        "feedback_hash": feedback["feedback_hash"],
        "preview_hash": preview_value["preview_hash"],
        "stage1_approval_id": approval["knowledge_approval_id"],
        "accepted_revision": current_revision + 1,
        "status": "submitted",
        "created_at": submitted_at,
    }
    receipt["receipt_id"] = "feedbackreceipt_" + _digest(receipt)[:24]
    receipt["receipt_hash"] = _hash_without(receipt, "receipt_hash")
    SchemaStore().validate("feedback-receipt.schema.json", receipt)
    return feedback, receipt


def verify_feedback_record(feedback: Mapping[str, Any]) -> None:
    value = _native(copy.deepcopy(dict(feedback)))
    SchemaStore().validate("feedback-record.schema.json", value)
    _structured(value["structured_content"], "structured_content")
    _privacy(value["privacy"])
    if not hmac.compare_digest(str(value["feedback_hash"]), _hash_without(value, "feedback_hash")):
        raise ContractError("Feedback Record hash is invalid")


def build_regression_case(
    *,
    source_feedback_refs: Sequence[Mapping[str, Any]],
    fixture_kind: str,
    fixture_ref: str,
    fixture_hash: str,
    consent_ref: str | None,
    expected: Mapping[str, Any],
    negative_control_refs: Sequence[str],
    counterexample_refs: Sequence[str],
    created_at: str,
    trusted_consent_refs: Sequence[str] = (),
) -> dict[str, Any]:
    if fixture_kind not in {"synthetic", "deidentified_real"}:
        raise ContractError("regression fixture must be synthetic or deidentified_real")
    if fixture_kind == "deidentified_real" and not consent_ref:
        raise ContractError("deidentified real fixture requires explicit consent")
    trusted_consents = set(_string_set(trusted_consent_refs, "trusted_consent_refs"))
    if fixture_kind == "deidentified_real" and consent_ref not in trusted_consents:
        raise ContractError("deidentified real fixture requires a trusted consent record")
    if fixture_kind == "synthetic" and consent_ref is not None:
        raise ContractError("synthetic fixture must not claim real-data consent")
    refs: list[dict[str, str]] = []
    for value in source_feedback_refs:
        if not isinstance(value, Mapping) or set(value) != {"feedback_id", "feedback_hash"}:
            raise ContractError("source_feedback_refs entry fields are invalid")
        refs.append({
            "feedback_id": _text(value["feedback_id"], "feedback_id"),
            "feedback_hash": _sha256(value["feedback_hash"], "feedback_hash"),
        })
    refs.sort(key=lambda item: item["feedback_id"])
    if not refs or len({item["feedback_id"] for item in refs}) != len(refs):
        raise ContractError("source_feedback_refs must be non-empty and unique")
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "source_feedback_refs": refs,
        "fixture_kind": fixture_kind,
        "fixture_ref": _text(fixture_ref, "fixture_ref"),
        "fixture_hash": _sha256(fixture_hash, "fixture_hash"),
        "consent_ref": _nullable_text(consent_ref, "consent_ref"),
        "expected": _structured(expected, "expected"),
        "negative_control_refs": _string_set(
            negative_control_refs, "negative_control_refs", non_empty=True
        ),
        "counterexample_refs": _string_set(
            counterexample_refs, "counterexample_refs", non_empty=True
        ),
        "created_at": _text(created_at, "created_at"),
    }
    body["regression_case_id"] = "regressioncase_" + _digest(body)[:24]
    body["regression_case_hash"] = _hash_without(body, "regression_case_hash")
    verify_regression_case(body)
    return body


def verify_regression_case(case: Mapping[str, Any]) -> None:
    value = _native(copy.deepcopy(dict(case)))
    SchemaStore().validate("regression-case.schema.json", value)
    _structured(value["expected"], "expected")
    if value["fixture_kind"] == "deidentified_real" and not value["consent_ref"]:
        raise ContractError("deidentified real fixture requires explicit consent")
    if not hmac.compare_digest(
        str(value["regression_case_hash"]), _hash_without(value, "regression_case_hash")
    ):
        raise ContractError("Regression Case hash is invalid")


def _reproduction(value: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "run_id", "run_revision", "knowledge_release_id", "prompt_hash",
        "pack_hash", "component_hash", "result",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ContractError("reproduction fields are invalid")
    if value["result"] != "reproduced":
        raise ContractError("Patch requires a reproduced failure")
    result = {
        "run_id": _text(value["run_id"], "reproduction.run_id"),
        "run_revision": _integer(value["run_revision"], "reproduction.run_revision"),
        "knowledge_release_id": _text(
            value["knowledge_release_id"], "reproduction.knowledge_release_id"
        ),
        "prompt_hash": _sha256(value["prompt_hash"], "reproduction.prompt_hash"),
        "pack_hash": _sha256(value["pack_hash"], "reproduction.pack_hash"),
        "component_hash": _sha256(value["component_hash"], "reproduction.component_hash"),
        "result": "reproduced",
    }
    result["reproduction_hash"] = _hash_without(result, "reproduction_hash")
    return result


def build_patch_proposal(
    *,
    feedback_records: Sequence[Mapping[str, Any]],
    reproduction: Mapping[str, Any],
    failure_type: str,
    root_cause: str,
    target_artifacts: Sequence[Mapping[str, Any]],
    before_semantics: Mapping[str, Any],
    after_semantics: Mapping[str, Any],
    source_refs: Sequence[str],
    affected_issue_family_ids: Sequence[str],
    affected_domains: Sequence[str],
    risk_classification: str,
    regression_cases: Sequence[Mapping[str, Any]],
    expected_behavior_changes: Sequence[str],
    forbidden_side_effects: Sequence[str],
    rollback_conditions: Sequence[str],
    required_stage2_roles: Sequence[str],
    created_at: str,
) -> dict[str, Any]:
    if not isinstance(feedback_records, (list, tuple)) or not feedback_records:
        raise ContractError("Patch requires Feedback Records")
    feedback_values = [_native(copy.deepcopy(dict(item))) for item in feedback_records]
    for item in feedback_values:
        verify_feedback_record(item)
    tenant_ids = {item["privacy"]["tenant_id"] for item in feedback_values}
    if len(tenant_ids) != 1:
        raise ContractError("Feedback from different tenants cannot share a Patch")
    reproduced = _reproduction(reproduction)
    for item in feedback_values:
        if (
            item["run_id"] != reproduced["run_id"]
            or item["run_revision"] != reproduced["run_revision"]
            or item["knowledge_release_id"] != reproduced["knowledge_release_id"]
        ):
            raise ContractError("reproduction does not match Feedback Record lineage")
    if failure_type not in _FAILURE_TYPES:
        raise ContractError(f"unsupported failure_type: {failure_type}")
    root_cause = _text(root_cause, "root_cause")
    _reject_direct_identifier(root_cause, "root_cause")
    if risk_classification not in {"low", "medium", "high", "critical"}:
        raise ContractError("risk_classification is invalid")
    normalized_targets = _artifact_manifest(target_artifacts, "target_artifacts")
    target_types = {item["artifact_type"] for item in normalized_targets}
    required_roles = set(_string_set(
        required_stage2_roles, "required_stage2_roles", non_empty=True
    ))
    minimum_roles: set[str] = set()
    if target_types & {"norm", "method"}:
        minimum_roles.add("domain_expert")
    if "procedure" in target_types:
        minimum_roles.update({"domain_expert", "maintainer"})
    if target_types & {"kernel", "pack", "card", "prompt"}:
        minimum_roles.update({"domain_expert", "maintainer"})
    if target_types & {"component", "parser", "mapping"}:
        minimum_roles.add("maintainer")
        if risk_classification in {"high", "critical"}:
            minimum_roles.add("domain_expert")
    if not minimum_roles.issubset(required_roles):
        raise ContractError(
            f"required Stage 2 roles cannot be downgraded: {sorted(minimum_roles)}"
        )
    regression_values = [_native(copy.deepcopy(dict(item))) for item in regression_cases]
    if not regression_values:
        raise ContractError("Patch requires a Regression Case")
    for item in regression_values:
        verify_regression_case(item)
    feedback_refs = sorted(
        ({"feedback_id": item["feedback_id"], "feedback_hash": item["feedback_hash"]}
         for item in feedback_values),
        key=lambda item: item["feedback_id"],
    )
    covered_feedback_ids = {
        ref["feedback_id"]
        for case in regression_values
        for ref in case["source_feedback_refs"]
    }
    expected_feedback_ids = {item["feedback_id"] for item in feedback_values}
    if covered_feedback_ids != expected_feedback_ids:
        raise ContractError("each Patch Feedback Record requires a paired Regression Case")
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "feedback_refs": feedback_refs,
        "tenant_id": next(iter(tenant_ids)),
        "reproduction": reproduced,
        "failure_type": failure_type,
        "root_cause": root_cause,
        "target_artifacts": normalized_targets,
        "before_semantics": _structured(before_semantics, "before_semantics"),
        "after_semantics": _structured(after_semantics, "after_semantics"),
        "source_refs": _string_set(source_refs, "source_refs", non_empty=True),
        "affected_issue_family_ids": _string_set(
            affected_issue_family_ids, "affected_issue_family_ids", non_empty=True
        ),
        "affected_domains": _string_set(affected_domains, "affected_domains", non_empty=True),
        "risk_classification": risk_classification,
        "regression_case_refs": sorted(({
            "regression_case_id": item["regression_case_id"],
            "regression_case_hash": item["regression_case_hash"],
        } for item in regression_values), key=lambda item: item["regression_case_id"]),
        "expected_behavior_changes": _string_set(
            expected_behavior_changes, "expected_behavior_changes", non_empty=True
        ),
        "forbidden_side_effects": _string_set(
            forbidden_side_effects, "forbidden_side_effects", non_empty=True
        ),
        "rollback_conditions": _string_set(
            rollback_conditions, "rollback_conditions", non_empty=True
        ),
        "required_stage2_roles": sorted(required_roles),
        "trust_state": "machine_draft",
        "status": "proposed",
        "created_at": _text(created_at, "created_at"),
    }
    body["patch_id"] = "patch_" + _digest(body)[:24]
    body["patch_hash"] = _hash_without(body, "patch_hash")
    verify_patch_proposal(body)
    return body


def verify_patch_proposal(patch: Mapping[str, Any]) -> None:
    value = _native(copy.deepcopy(dict(patch)))
    SchemaStore().validate("patch-proposal.schema.json", value)
    if not hmac.compare_digest(
        str(value["reproduction"]["reproduction_hash"]),
        _hash_without(value["reproduction"], "reproduction_hash"),
    ):
        raise ContractError("Patch reproduction hash is invalid")
    if not hmac.compare_digest(str(value["patch_hash"]), _hash_without(value, "patch_hash")):
        raise ContractError("Patch Proposal hash is invalid")


def build_release_candidate(
    *,
    base_release: Mapping[str, Any],
    patches: Sequence[Mapping[str, Any]],
    regression_cases: Sequence[Mapping[str, Any]],
    stage2_approvals: Sequence[Mapping[str, Any]],
    expected_revision: int,
    artifact_manifest: Sequence[Mapping[str, Any]],
    gate_results: Mapping[str, Any],
    coverage_exception_approval_ref: None,
    rollback_release_id: str,
    rollback_release_hash: str,
    created_at: str,
) -> dict[str, Any]:
    base = _native(copy.deepcopy(dict(base_release)))
    verify_knowledge_release(base)
    expected_revision = _integer(expected_revision, "expected_revision")
    patch_values = [_native(copy.deepcopy(dict(item))) for item in patches]
    if not patch_values:
        raise ContractError("Release Candidate requires a Patch")
    for patch in patch_values:
        verify_patch_proposal(patch)
    case_values = [_native(copy.deepcopy(dict(item))) for item in regression_cases]
    case_by_id: dict[str, dict[str, Any]] = {}
    for case in case_values:
        verify_regression_case(case)
        case_by_id[case["regression_case_id"]] = case
    for patch in patch_values:
        for ref in patch["regression_case_refs"]:
            case = case_by_id.get(ref["regression_case_id"])
            if case is None or not hmac.compare_digest(
                case["regression_case_hash"], ref["regression_case_hash"]
            ):
                raise ContractError("Release Candidate has an invalid Regression Case ref")

    approval_values = [_native(copy.deepcopy(dict(item))) for item in stage2_approvals]
    approval_ids: set[str] = set()
    approval_refs: list[dict[str, str]] = []
    used_approval_ids: set[str] = set()
    for approval in approval_values:
        verify_knowledge_approval(approval)
        approval_id = approval["knowledge_approval_id"]
        if approval_id in approval_ids:
            raise ContractError("duplicate Stage 2 approval")
        approval_ids.add(approval_id)
    for patch in patch_values:
        for role in patch["required_stage2_roles"]:
            matches = [
                approval for approval in approval_values
                if approval["approval_stage"] == "patch_approve"
                and approval["requested_action"] == "approve_patch"
                and approval["object_id"] == patch["patch_id"]
                and hmac.compare_digest(approval["object_hash"], patch["patch_hash"])
                and approval["expected_revision"] == expected_revision
                and approval["approver_role"] == role
            ]
            if len(matches) != 1:
                raise ContractError(f"Stage 2 approval is missing or ambiguous for role: {role}")
            approval = matches[0]
            used_approval_ids.add(approval["knowledge_approval_id"])
            approval_refs.append({
                "knowledge_approval_id": approval["knowledge_approval_id"],
                "approval_hash": approval["approval_hash"],
                "patch_id": patch["patch_id"],
                "approved_by": approval["approved_by"],
                "approver_role": approval["approver_role"],
            })
    if used_approval_ids != approval_ids:
        raise ContractError("Stage 2 approvals include an unrelated or stale approval")

    if not isinstance(gate_results, Mapping) or set(gate_results) != _GATE_FIELDS:
        raise ContractError("Release Candidate gate_results fields are invalid")
    normalized_gates = dict(gate_results)
    for gate in sorted(_GATE_FIELDS):
        if normalized_gates[gate] is not True:
            raise ContractError(f"Release Candidate gate failed: {gate}")
    if coverage_exception_approval_ref is not None:
        raise ContractError("coverage exceptions require a separately verified approval workflow")
    if rollback_release_id != base["release_id"] or not hmac.compare_digest(
        rollback_release_hash, base["release_hash"]
    ):
        raise ContractError("rollback target must be the exact base Knowledge Release")
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "base_release_id": base["release_id"],
        "base_release_hash": base["release_hash"],
        "patch_refs": sorted(({
            "patch_id": patch["patch_id"], "patch_hash": patch["patch_hash"]
        } for patch in patch_values), key=lambda item: item["patch_id"]),
        "stage2_approval_refs": sorted(
            approval_refs,
            key=lambda item: (item["patch_id"], item["approver_role"], item["knowledge_approval_id"]),
        ),
        "base_revision": expected_revision,
        "artifact_manifest": _artifact_manifest(artifact_manifest, "artifact_manifest"),
        "gate_results": normalized_gates,
        "coverage_exception_approval_ref": None,
        "rollback_release_id": rollback_release_id,
        "rollback_release_hash": rollback_release_hash,
        "status": "approved_for_candidate",
        "created_at": _text(created_at, "created_at"),
    }
    body["candidate_id"] = "releasecandidate_" + _digest(body)[:24]
    body["candidate_hash"] = _hash_without(body, "candidate_hash")
    verify_release_candidate(body)
    return body


def verify_release_candidate(candidate: Mapping[str, Any]) -> None:
    value = _native(copy.deepcopy(dict(candidate)))
    SchemaStore().validate("release-candidate.schema.json", value)
    if not hmac.compare_digest(
        str(value["candidate_hash"]), _hash_without(value, "candidate_hash")
    ):
        raise ContractError("release candidate hash is invalid")
