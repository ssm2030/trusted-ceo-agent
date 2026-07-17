from __future__ import annotations

import copy
import hashlib
import hmac
from collections.abc import Mapping, Sequence
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, RevisionConflict
from trusted_ceo_agent.evaluation.non_inferiority import (
    verify_concurrency_profile,
    verify_non_inferiority_report,
)
from trusted_ceo_agent.evaluation.performance import verify_performance_policy
from trusted_ceo_agent.knowledge.depth_gate import (
    verify_professional_depth_assessment,
)
from trusted_ceo_agent.knowledge.release import verify_knowledge_release
from trusted_ceo_agent.orchestration.budget import verify_work_budget_policy


_AUTHORITY_ORDER = {
    "machine_draft": 0,
    "boundary": 1,
    "provisional": 2,
    "full": 3,
}
_PRODUCT_DISPLAY = {
    "machine_draft": "machine_draft",
    "boundary": "Boundary",
    "provisional": "Provisional",
    "full": "Full",
}
_BINDING_FIELDS = frozenset({
    "schema_version",
    "run_id",
    "revision",
    "policy_release_id",
    "policy_hash",
    "release_id",
    "release_hash",
    "binding_hash",
})
_ACTIVATION_FIELDS = frozenset({
    "event_type",
    "from_profile_id",
    "to_profile_id",
    "profile_hash",
    "non_inferiority_report_id",
    "non_inferiority_report_hash",
    "performance_policy_id",
    "performance_policy_hash",
    "approval_ref",
    "reason",
    "effective_for_runs_after_revision",
    "event_id",
    "event_hash",
})


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must be a non-empty string")
    return value


def _run_id(value: Any) -> str:
    value = _text(value, "run_id")
    if not value.startswith("run_"):
        raise ContractError("run_id must begin with run_")
    return value


def _revision(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError("revision must be a positive integer")
    return value


def _hash(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ContractError(f"{label} must be lowercase SHA-256")
    return value


def build_knowledge_release_binding(
    *,
    run_id: str,
    revision: int,
    policy_release_id: str,
    work_budget_policy: Mapping[str, Any],
    knowledge_release: Mapping[str, Any],
) -> dict[str, Any]:
    """Pin one verified Knowledge Foundry release to one run generation."""

    run_id = _run_id(run_id)
    revision = _revision(revision)
    policy_release_id = _text(policy_release_id, "policy_release_id")
    policy = copy.deepcopy(dict(work_budget_policy))
    release = copy.deepcopy(dict(knowledge_release))
    verify_work_budget_policy(policy)
    verify_knowledge_release(release)
    if int(release["activated_for_runs_after_revision"]) > revision:
        raise ContractError("Knowledge Release is not active for this revision")
    body = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "revision": revision,
        "policy_release_id": policy_release_id,
        "policy_hash": policy["content_hash"],
        "release_id": release["release_id"],
        "release_hash": release["release_hash"],
    }
    return {**body, "binding_hash": _digest(body)}


def _verify_release_binding(
    value: Mapping[str, Any],
    *,
    run_id: str,
    revision: int,
    policy_release_id: str,
    policy_hash: str,
    release_id: str,
    release_hash: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise ContractError("Knowledge Release binding fields do not match the contract")
    binding = copy.deepcopy(dict(value))
    if binding["schema_version"] != "1.0.0":
        raise ContractError("unsupported Knowledge Release binding version")
    _run_id(binding["run_id"])
    _revision(binding["revision"])
    _hash(binding["policy_hash"], "binding policy_hash")
    _hash(binding["release_hash"], "binding release_hash")
    _hash(binding["binding_hash"], "binding_hash")
    expected_hash = _digest({
        key: binding[key] for key in binding if key != "binding_hash"
    })
    if not hmac.compare_digest(str(binding["binding_hash"]), expected_hash):
        raise ContractError("Knowledge Release binding hash mismatch")
    if binding["run_id"] != run_id:
        raise ContractError("Knowledge Release binding run mismatch")
    if binding["revision"] != revision:
        raise RevisionConflict("Knowledge Release binding revision is stale")
    expected = {
        "policy_release_id": policy_release_id,
        "policy_hash": policy_hash,
        "release_id": release_id,
        "release_hash": release_hash,
    }
    for field, expected_value in expected.items():
        if binding[field] != expected_value:
            raise ContractError(f"Knowledge Release binding {field} mismatch")
    return binding


def _verify_activation_receipt(
    value: Mapping[str, Any],
    *,
    revision: int,
    profile: Mapping[str, Any],
    report: Mapping[str, Any],
    performance_policy: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    if not isinstance(value, Mapping) or set(value) != _ACTIVATION_FIELDS:
        raise ContractError("profile activation receipt fields do not match the contract")
    receipt = copy.deepcopy(dict(value))
    body = {
        key: receipt[key]
        for key in receipt
        if key not in {"event_id", "event_hash"}
    }
    expected_id = "profileevent_" + _digest(body)[:24]
    if receipt["event_id"] != expected_id:
        raise ContractError("profile activation receipt ID mismatch")
    expected_hash = _digest({
        key: receipt[key] for key in receipt if key != "event_hash"
    })
    if not hmac.compare_digest(str(receipt["event_hash"]), expected_hash):
        raise ContractError("profile activation receipt hash mismatch")
    expected = {
        "event_type": "activation",
        "from_profile_id": "sequential",
        "to_profile_id": profile["profile_id"],
        "profile_hash": profile["profile_hash"],
        "non_inferiority_report_id": report["report_id"],
        "non_inferiority_report_hash": report["report_hash"],
        "performance_policy_id": performance_policy["policy_id"],
        "performance_policy_hash": performance_policy["policy_hash"],
        "reason": "approved_quality_and_performance_gates",
    }
    for field, expected_value in expected.items():
        if receipt[field] != expected_value:
            raise ContractError(f"profile activation receipt {field} mismatch")
    _text(receipt["approval_ref"], "profile activation approval_ref")
    effective_revision = _revision(receipt["effective_for_runs_after_revision"])
    return receipt, effective_revision <= revision


def _minimum_authority(values: Sequence[str]) -> str:
    return min(values, key=lambda value: _AUTHORITY_ORDER[value])


def evaluate_execution_authority(
    *,
    run_id: str,
    revision: int,
    policy_release_id: str,
    expected_policy_release_id: str,
    work_budget_policy: Mapping[str, Any],
    depth_assessments: Sequence[Mapping[str, Any]],
    knowledge_release: Mapping[str, Any],
    knowledge_release_binding: Mapping[str, Any] | None,
    concurrency_profile: Mapping[str, Any],
    requested_authority: str,
    non_inferiority_report: Mapping[str, Any] | None = None,
    performance_policy: Mapping[str, Any] | None = None,
    profile_activation_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a deterministic pre-runtime authority decision.

    Invalid or cross-bound artifacts raise. Missing approval evidence is represented
    as an explicit Boundary downgrade or an execution-blocking decision.
    """

    run_id = _run_id(run_id)
    revision = _revision(revision)
    policy_release_id = _text(policy_release_id, "policy_release_id")
    expected_policy_release_id = _text(
        expected_policy_release_id, "expected_policy_release_id"
    )
    if policy_release_id != expected_policy_release_id:
        raise ContractError("policy release mismatch")
    if requested_authority not in _AUTHORITY_ORDER:
        raise ContractError("unsupported requested authority")

    policy = copy.deepcopy(dict(work_budget_policy))
    profile = copy.deepcopy(dict(concurrency_profile))
    release = copy.deepcopy(dict(knowledge_release))
    verify_work_budget_policy(policy)
    verify_concurrency_profile(profile)
    verify_knowledge_release(release)
    if policy["approved_concurrency_profile_id"] != profile["profile_id"]:
        raise ContractError("WorkBudgetPolicy concurrency profile mismatch")
    if int(policy["max_parallel_workers"]) != int(profile["max_workers"]):
        raise ContractError("WorkBudgetPolicy worker ceiling does not match profile")

    if (
        isinstance(depth_assessments, (str, bytes, bytearray))
        or not isinstance(depth_assessments, Sequence)
        or not depth_assessments
    ):
        raise ContractError("ExecutionAuthorityGate requires depth assessments")
    depth_records: list[dict[str, Any]] = []
    depth_authorities: list[str] = []
    depth_active = True
    blockers: set[str] = set()
    assessment_ids: set[str] = set()
    issue_family_ids: set[str] = set()
    for raw in depth_assessments:
        if not isinstance(raw, Mapping):
            raise ContractError("depth assessment must be an object")
        assessment = copy.deepcopy(dict(raw))
        verify_professional_depth_assessment(assessment)
        assessment_id = str(assessment["assessment_id"])
        family_id = str(assessment["issue_family_id"])
        if assessment_id in assessment_ids or family_id in issue_family_ids:
            raise ContractError("duplicate professional depth assessment")
        assessment_ids.add(assessment_id)
        issue_family_ids.add(family_id)
        authority = str(assessment["effective_authority"])
        depth_authorities.append(authority)
        depth_active = depth_active and bool(assessment["activation_allowed"])
        blockers.update(
            f"depth:{family_id}:{blocker}"
            for blocker in assessment["blockers"]
        )
        depth_records.append({
            "assessment_id": assessment_id,
            "assessment_hash": assessment["assessment_hash"],
            "issue_family_id": family_id,
            "effective_authority": authority,
            "activation_allowed": assessment["activation_allowed"],
        })
    depth_records.sort(key=lambda item: item["issue_family_id"])
    if not depth_active:
        blockers.add("professional_depth_activation_blocked")

    binding: dict[str, Any] | None = None
    binding_ready = knowledge_release_binding is not None
    if knowledge_release_binding is None:
        blockers.add("knowledge_release_binding_missing")
    else:
        binding = _verify_release_binding(
            knowledge_release_binding,
            run_id=run_id,
            revision=revision,
            policy_release_id=policy_release_id,
            policy_hash=str(policy["content_hash"]),
            release_id=str(release["release_id"]),
            release_hash=str(release["release_hash"]),
        )
    if int(release["activated_for_runs_after_revision"]) > revision:
        binding_ready = False
        blockers.add("knowledge_release_not_active_for_revision")
    release_approved = bool(release["stage2_approval_refs"]) and (
        release["stage3_approval_ref"] is not None
    )
    if not release_approved:
        blockers.add("knowledge_release_approval_missing")
    release_authority = "full" if release_approved else "boundary"

    profile_id = str(profile["profile_id"])
    report: dict[str, Any] | None = None
    performance: dict[str, Any] | None = None
    activation: dict[str, Any] | None = None
    concurrency_ready = True
    activation_effective = profile_id == "sequential"
    if profile_id != "sequential":
        if non_inferiority_report is None:
            concurrency_ready = False
            blockers.add("non_inferiority_report_missing")
        else:
            report = copy.deepcopy(dict(non_inferiority_report))
            verify_non_inferiority_report(report)
            if report["candidate_profile_id"] != profile_id:
                raise ContractError("non-inferiority report profile mismatch")
            if report["quality_policy_hash"] != profile["quality_policy_hash"]:
                raise ContractError("non-inferiority report policy hash mismatch")
            if (
                report["gate_status"] != "pass"
                or report["eligible_for_activation"] is not True
            ):
                concurrency_ready = False
                blockers.add("non_inferiority_not_passed")

        if performance_policy is None:
            concurrency_ready = False
            blockers.add("performance_policy_missing")
        else:
            performance = copy.deepcopy(dict(performance_policy))
            verify_performance_policy(performance)
            if performance["selected_profile_id"] != profile_id:
                raise ContractError("PerformancePolicy profile mismatch")
            if (
                performance["status"] != "approved"
                or performance["activation_eligible"] is not True
            ):
                concurrency_ready = False
                blockers.add("performance_policy_not_approved")
            if report is not None:
                refs = {
                    (item["report_id"], item["report_hash"])
                    for item in performance["quality_report_refs"]
                }
                if (report["report_id"], report["report_hash"]) not in refs:
                    raise ContractError(
                        "PerformancePolicy is not bound to non-inferiority report"
                    )

        if profile_activation_receipt is None:
            concurrency_ready = False
            blockers.add("profile_activation_receipt_missing")
        elif report is None or performance is None:
            raise ContractError(
                "profile activation receipt requires report and PerformancePolicy"
            )
        else:
            activation, activation_effective = _verify_activation_receipt(
                profile_activation_receipt,
                revision=revision,
                profile=profile,
                report=report,
                performance_policy=performance,
            )
            if not activation_effective:
                concurrency_ready = False
                blockers.add("profile_activation_not_effective")

    effective_authority = _minimum_authority(
        [*depth_authorities, release_authority]
    )
    if not depth_active or not binding_ready:
        effective_authority = "machine_draft"
    elif not concurrency_ready:
        effective_authority = _minimum_authority(
            [effective_authority, "boundary"]
        )
    execution_allowed = depth_active and binding_ready and concurrency_ready
    requested_authority_allowed = (
        execution_allowed
        and _AUTHORITY_ORDER[effective_authority]
        >= _AUTHORITY_ORDER[requested_authority]
    )
    if execution_allowed and not requested_authority_allowed:
        blockers.add(
            f"requested_authority_downgraded:{requested_authority}"
            f"->{effective_authority}"
        )
    full_allowed = execution_allowed and effective_authority == "full"

    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "revision": revision,
        "policy_release_id": policy_release_id,
        "policy_hash": policy["content_hash"],
        "requested_authority": requested_authority,
        "depth_assessments": depth_records,
        "knowledge_release": {
            "release_id": release["release_id"],
            "release_hash": release["release_hash"],
            "binding_hash": binding["binding_hash"] if binding is not None else None,
            "approval_complete": release_approved,
            "active_for_revision": (
                int(release["activated_for_runs_after_revision"]) <= revision
            ),
        },
        "concurrency": {
            "profile_id": profile_id,
            "profile_hash": profile["profile_hash"],
            "quality_policy_id": profile["quality_policy_id"],
            "quality_policy_hash": profile["quality_policy_hash"],
            "report_id": report["report_id"] if report is not None else None,
            "report_hash": report["report_hash"] if report is not None else None,
            "performance_policy_id": (
                performance["policy_id"] if performance is not None else None
            ),
            "performance_policy_hash": (
                performance["policy_hash"] if performance is not None else None
            ),
            "activation_id": (
                activation["event_id"] if activation is not None else None
            ),
            "activation_hash": (
                activation["event_hash"] if activation is not None else None
            ),
            "activation_effective": activation_effective,
        },
        "effective_authority": effective_authority,
        "product_display": _PRODUCT_DISPLAY[effective_authority],
        "execution_allowed": execution_allowed,
        "requested_authority_allowed": requested_authority_allowed,
        "full_allowed": full_allowed,
        "blockers": sorted(blockers),
    }
    gate = dict(body)
    gate["gate_id"] = "executionauthority_" + _digest(body)[:24]
    gate["content_hash"] = _digest(gate)
    verify_execution_authority_gate(gate)
    return gate


def verify_execution_authority_gate(value: Mapping[str, Any]) -> None:
    gate = copy.deepcopy(dict(value))
    SchemaStore().validate("execution-authority-gate.schema.json", gate)
    if gate["blockers"] != sorted(set(gate["blockers"])):
        raise ContractError("ExecutionAuthorityGate blockers must be sorted and unique")
    body = {
        key: gate[key]
        for key in gate
        if key not in {"gate_id", "content_hash"}
    }
    expected_id = "executionauthority_" + _digest(body)[:24]
    if gate["gate_id"] != expected_id:
        raise ContractError("ExecutionAuthorityGate ID mismatch")
    unhashed = {
        key: gate[key] for key in gate if key != "content_hash"
    }
    if not hmac.compare_digest(str(gate["content_hash"]), _digest(unhashed)):
        raise ContractError("ExecutionAuthorityGate content hash mismatch")
    if gate["full_allowed"] and (
        not gate["execution_allowed"]
        or gate["effective_authority"] != "full"
    ):
        raise ContractError("Full authority requires an allowed full execution")
    if gate["requested_authority_allowed"] and not gate["execution_allowed"]:
        raise ContractError("blocked execution cannot satisfy requested authority")


__all__ = [
    "build_knowledge_release_binding",
    "evaluate_execution_authority",
    "verify_execution_authority_gate",
]
