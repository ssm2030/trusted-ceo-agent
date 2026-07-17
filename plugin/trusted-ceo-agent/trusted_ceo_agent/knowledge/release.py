from __future__ import annotations

import copy
import hashlib
import hmac
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, RevisionConflict


_ACTION_BY_STAGE = {
    "feedback_submit": frozenset({"submit_feedback"}),
    "patch_approve": frozenset({"approve_patch"}),
    "release_deploy": frozenset({"deploy_release", "rollback_release"}),
}
_ARTIFACT_TYPES = frozenset({
    "kernel", "pack", "card", "component", "prompt", "parser", "mapping",
    "procedure", "norm", "method", "presentation",
})


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


def _sha256(value: Any, field: str) -> str:
    text = _text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ContractError(f"{field} must be a lowercase SHA-256")
    return text


def _integer(value: Any, field: str, *, minimum: int = 0) -> int:
    value = _native(value)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContractError(f"{field} must be an integer >= {minimum}")
    return value


def _time(value: Any, field: str) -> datetime:
    text = _text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(f"{field} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ContractError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _stage_action(stage: Any, action: Any) -> tuple[str, str]:
    stage = _text(stage, "approval_stage")
    action = _text(action, "requested_action")
    if stage not in _ACTION_BY_STAGE or action not in _ACTION_BY_STAGE[stage]:
        raise ContractError("approval stage and action do not match")
    return stage, action


def _approval_ref(approval: Mapping[str, Any]) -> dict[str, str]:
    return {
        "knowledge_approval_id": str(approval["knowledge_approval_id"]),
        "approval_hash": str(approval["approval_hash"]),
        "approved_by": str(approval["approved_by"]),
        "approver_role": str(approval["approver_role"]),
    }


def _artifact_manifest(values: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    if not isinstance(values, (list, tuple)) or not values:
        raise ContractError("artifact_manifest must not be empty")
    result: list[dict[str, str]] = []
    for value in values:
        if not isinstance(value, Mapping) or set(value) != {
            "artifact_ref", "artifact_hash", "artifact_type"
        }:
            raise ContractError("artifact manifest entry fields are invalid")
        artifact_type = _text(value["artifact_type"], "artifact_type")
        if artifact_type not in _ARTIFACT_TYPES:
            raise ContractError(f"unsupported artifact_type: {artifact_type}")
        result.append({
            "artifact_ref": _text(value["artifact_ref"], "artifact_ref"),
            "artifact_hash": _sha256(value["artifact_hash"], "artifact_hash"),
            "artifact_type": artifact_type,
        })
    result.sort(key=lambda item: (item["artifact_ref"], item["artifact_hash"], item["artifact_type"]))
    if len({canonical_bytes(item) for item in result}) != len(result):
        raise ContractError("artifact_manifest contains duplicates")
    return result


def build_knowledge_approval_request(
    *,
    approval_stage: str,
    object_id: str,
    object_hash: str,
    expected_revision: int,
    requested_action: str,
    requested_by: str,
    required_role: str,
    requested_at: str,
    expires_at: str,
    nonce: str,
) -> dict[str, Any]:
    stage, action = _stage_action(approval_stage, requested_action)
    if stage == "release_deploy" and required_role != "release_manager":
        raise ContractError("release deployment requires release_manager role")
    requested_time = _time(requested_at, "requested_at")
    expires_time = _time(expires_at, "expires_at")
    if expires_time <= requested_time:
        raise ContractError("approval request expiry must be after requested_at")
    nonce = _text(nonce, "nonce")
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "approval_stage": stage,
        "object_id": _text(object_id, "object_id"),
        "object_hash": _sha256(object_hash, "object_hash"),
        "expected_revision": _integer(expected_revision, "expected_revision"),
        "requested_action": action,
        "requested_by": _text(requested_by, "requested_by"),
        "required_role": _text(required_role, "required_role"),
        "nonce_hash": hashlib.sha256(nonce.encode("utf-8")).hexdigest(),
        "requested_at": requested_at,
        "expires_at": expires_at,
        "status": "pending",
    }
    body["approval_request_id"] = "knowledgeapprovalrequest_" + _digest(body)[:24]
    body["request_hash"] = _hash_without(body, "request_hash")
    verify_knowledge_approval_request(body)
    return body


def verify_knowledge_approval_request(request: Mapping[str, Any]) -> None:
    value = _native(copy.deepcopy(dict(request)))
    SchemaStore().validate("knowledge-approval-request.schema.json", value)
    _stage_action(value["approval_stage"], value["requested_action"])
    if value["approval_stage"] == "release_deploy" and value["required_role"] != "release_manager":
        raise ContractError("release deployment requires release_manager role")
    if _time(value["expires_at"], "expires_at") <= _time(value["requested_at"], "requested_at"):
        raise ContractError("approval request expiry must be after requested_at")
    if not hmac.compare_digest(str(value["request_hash"]), _hash_without(value, "request_hash")):
        raise ContractError("knowledge approval request hash is invalid")


def record_knowledge_approval(
    request: Mapping[str, Any],
    *,
    object_id: str,
    object_hash: str,
    current_revision: int,
    approved_by: str,
    approver_role: str,
    nonce: str,
    approved_at: str,
) -> dict[str, Any]:
    request = _native(copy.deepcopy(dict(request)))
    verify_knowledge_approval_request(request)
    if request["object_id"] != object_id:
        raise ContractError("approval object ID does not match request")
    if not hmac.compare_digest(str(request["object_hash"]), _sha256(object_hash, "object_hash")):
        raise ContractError("approval object hash does not match request")
    current_revision = _integer(current_revision, "current_revision")
    if current_revision != request["expected_revision"]:
        raise RevisionConflict("knowledge approval request is stale")
    if approver_role != request["required_role"]:
        raise ContractError("approver role does not satisfy required role")
    nonce_hash = hashlib.sha256(_text(nonce, "nonce").encode("utf-8")).hexdigest()
    if not hmac.compare_digest(nonce_hash, str(request["nonce_hash"])):
        raise ContractError("knowledge approval nonce is invalid")
    approved_time = _time(approved_at, "approved_at")
    if approved_time < _time(request["requested_at"], "requested_at"):
        raise ContractError("approval predates its request")
    if approved_time > _time(request["expires_at"], "expires_at"):
        raise ContractError("knowledge approval request expired")
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "approval_request_id": request["approval_request_id"],
        "approval_stage": request["approval_stage"],
        "object_id": object_id,
        "object_hash": object_hash,
        "expected_revision": current_revision,
        "requested_action": request["requested_action"],
        "approved_by": _text(approved_by, "approved_by"),
        "approver_role": approver_role,
        "approved_at": approved_at,
        "request_hash": request["request_hash"],
        "nonce_hash": request["nonce_hash"],
        "status": "approved",
    }
    body["knowledge_approval_id"] = "knowledgeapproval_" + _digest(body)[:24]
    body["approval_hash"] = _hash_without(body, "approval_hash")
    verify_knowledge_approval(body)
    return body


def verify_knowledge_approval(approval: Mapping[str, Any]) -> None:
    value = _native(copy.deepcopy(dict(approval)))
    SchemaStore().validate("knowledge-approval.schema.json", value)
    _stage_action(value["approval_stage"], value["requested_action"])
    if value["approval_stage"] == "release_deploy" and value["approver_role"] != "release_manager":
        raise ContractError("release deployment requires release_manager role")
    if not hmac.compare_digest(str(value["approval_hash"]), _hash_without(value, "approval_hash")):
        raise ContractError("knowledge approval hash is invalid")


def build_initial_release(
    *, release_sequence: int, artifact_manifest: Sequence[Mapping[str, Any]], deployed_at: str,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "release_sequence": _integer(release_sequence, "release_sequence", minimum=1),
        "base_release_id": None,
        "base_release_hash": None,
        "candidate_id": None,
        "candidate_hash": None,
        "patch_refs": [],
        "artifact_manifest": _artifact_manifest(artifact_manifest),
        "stage2_approval_refs": [],
        "stage3_approval_ref": None,
        "activated_for_runs_after_revision": 0,
        "rollback_release_id": None,
        "deployed_at": _text(deployed_at, "deployed_at"),
        "status": "published",
    }
    _time(deployed_at, "deployed_at")
    body["release_id"] = "knowledge_release_" + _digest(body)[:24]
    body["release_hash"] = _hash_without(body, "release_hash")
    verify_knowledge_release(body)
    return body


def verify_knowledge_release(release: Mapping[str, Any]) -> None:
    value = _native(copy.deepcopy(dict(release)))
    SchemaStore().validate("knowledge-release.schema.json", value)
    if not hmac.compare_digest(str(value["release_hash"]), _hash_without(value, "release_hash")):
        raise ContractError("knowledge release hash is invalid")


def _verify_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    value = _native(copy.deepcopy(dict(candidate)))
    SchemaStore().validate("release-candidate.schema.json", value)
    if not hmac.compare_digest(str(value["candidate_hash"]), _hash_without(value, "candidate_hash")):
        raise ContractError("release candidate hash is invalid")
    return value


def _verify_bound_approval(
    approval: Mapping[str, Any],
    *,
    stage: str,
    action: str,
    object_id: str,
    object_hash: str,
    current_revision: int,
) -> dict[str, Any]:
    value = _native(copy.deepcopy(dict(approval)))
    verify_knowledge_approval(value)
    if value["approval_stage"] != stage or value["requested_action"] != action:
        raise ContractError("knowledge approval stage or action is invalid")
    if value["object_id"] != object_id or not hmac.compare_digest(
        str(value["object_hash"]), object_hash
    ):
        raise ContractError("knowledge approval is bound to another object")
    if value["expected_revision"] != current_revision:
        raise RevisionConflict("knowledge approval revision is stale")
    return value


class ReleaseRegistry:
    """Immutable release objects with a mutable, audited default pointer."""

    def __init__(self, initial_release: Mapping[str, Any]) -> None:
        initial = _native(copy.deepcopy(dict(initial_release)))
        verify_knowledge_release(initial)
        if initial["base_release_id"] is not None:
            raise ContractError("ReleaseRegistry requires an initial root release")
        self._releases: dict[str, dict[str, Any]] = {initial["release_id"]: initial}
        self._active_release_id = str(initial["release_id"])
        self._run_releases: dict[str, str] = {}
        self._revoked: set[str] = set()
        self._consumed_approvals: set[str] = set()
        self._events: list[dict[str, Any]] = []

    @property
    def active_release_id(self) -> str:
        return self._active_release_id

    def get_release(self, release_id: str) -> dict[str, Any]:
        if release_id not in self._releases:
            raise ContractError(f"unknown Knowledge Release: {release_id}")
        return copy.deepcopy(self._releases[release_id])

    def start_run(self, run_id: str) -> dict[str, Any]:
        run_id = _text(run_id, "run_id")
        if run_id not in self._run_releases:
            if self._active_release_id in self._revoked:
                raise ContractError("active Knowledge Release is revoked")
            self._run_releases[run_id] = self._active_release_id
        return self.get_release(self._run_releases[run_id])

    def release_for_run(self, run_id: str) -> dict[str, Any]:
        run_id = _text(run_id, "run_id")
        if run_id not in self._run_releases:
            raise ContractError(f"run is not pinned to a Knowledge Release: {run_id}")
        return self.get_release(self._run_releases[run_id])

    def rerun(self, original_run_id: str, new_run_id: str) -> dict[str, Any]:
        original = self.release_for_run(original_run_id)
        if new_run_id in self._run_releases:
            raise ContractError("rerun target already exists")
        selected = self.start_run(new_run_id)
        return {
            "run_id": new_run_id,
            "rerun_of": original_run_id,
            "previous_release_id": original["release_id"],
            "knowledge_release_id": selected["release_id"],
        }

    def deploy(
        self,
        candidate: Mapping[str, Any],
        approval: Mapping[str, Any],
        *,
        current_revision: int,
    ) -> dict[str, Any]:
        candidate_value = _verify_candidate(candidate)
        current_revision = _integer(current_revision, "current_revision")
        if current_revision != candidate_value["base_revision"] + 1:
            raise RevisionConflict("release candidate revision is stale")
        if candidate_value["base_release_id"] != self._active_release_id:
            raise RevisionConflict("release candidate base is no longer active")
        base = self._releases[self._active_release_id]
        if not hmac.compare_digest(candidate_value["base_release_hash"], base["release_hash"]):
            raise ContractError("release candidate base hash is invalid")
        if (
            candidate_value["rollback_release_id"] != base["release_id"]
            or not hmac.compare_digest(candidate_value["rollback_release_hash"], base["release_hash"])
        ):
            raise ContractError("release candidate rollback target is invalid")
        stage3 = _verify_bound_approval(
            approval,
            stage="release_deploy",
            action="deploy_release",
            object_id=candidate_value["candidate_id"],
            object_hash=candidate_value["candidate_hash"],
            current_revision=current_revision,
        )
        approval_id = stage3["knowledge_approval_id"]
        if approval_id in self._consumed_approvals:
            raise ContractError("knowledge approval was already consumed")
        stage2_actors = {item["approved_by"] for item in candidate_value["stage2_approval_refs"]}
        if stage3["approved_by"] in stage2_actors:
            raise ContractError("Stage 2 and Stage 3 role separation is required")

        release: dict[str, Any] = {
            "schema_version": "1.0.0",
            "release_sequence": max(item["release_sequence"] for item in self._releases.values()) + 1,
            "base_release_id": base["release_id"],
            "base_release_hash": base["release_hash"],
            "candidate_id": candidate_value["candidate_id"],
            "candidate_hash": candidate_value["candidate_hash"],
            "patch_refs": copy.deepcopy(candidate_value["patch_refs"]),
            "artifact_manifest": copy.deepcopy(candidate_value["artifact_manifest"]),
            "stage2_approval_refs": [{
                "knowledge_approval_id": item["knowledge_approval_id"],
                "approval_hash": item["approval_hash"],
                "approved_by": item["approved_by"],
                "approver_role": item["approver_role"],
            } for item in candidate_value["stage2_approval_refs"]],
            "stage3_approval_ref": _approval_ref(stage3),
            "activated_for_runs_after_revision": current_revision + 1,
            "rollback_release_id": base["release_id"],
            "deployed_at": stage3["approved_at"],
            "status": "published",
        }
        release["release_id"] = "knowledge_release_" + _digest(release)[:24]
        release["release_hash"] = _hash_without(release, "release_hash")
        verify_knowledge_release(release)
        self._releases[release["release_id"]] = copy.deepcopy(release)
        self._active_release_id = release["release_id"]
        self._consumed_approvals.add(approval_id)
        return copy.deepcopy(release)

    def rollback(
        self,
        *,
        revoked_release_id: str,
        target_release_id: str,
        approval: Mapping[str, Any],
        current_revision: int,
    ) -> dict[str, Any]:
        current_revision = _integer(current_revision, "current_revision")
        if revoked_release_id != self._active_release_id:
            raise RevisionConflict("only the active Knowledge Release can be rolled back")
        if target_release_id not in self._releases or target_release_id in self._revoked:
            raise ContractError("rollback target is unavailable")
        revoked = self._releases[revoked_release_id]
        stage3 = _verify_bound_approval(
            approval,
            stage="release_deploy",
            action="rollback_release",
            object_id=revoked["release_id"],
            object_hash=revoked["release_hash"],
            current_revision=current_revision,
        )
        approval_id = stage3["knowledge_approval_id"]
        if approval_id in self._consumed_approvals:
            raise ContractError("knowledge approval was already consumed")
        event: dict[str, Any] = {
            "event_type": "rollback",
            "from_release_id": revoked_release_id,
            "to_release_id": target_release_id,
            "approval_id": approval_id,
            "approval_hash": stage3["approval_hash"],
            "effective_for_runs_after_revision": current_revision + 1,
            "created_at": stage3["approved_at"],
        }
        event["event_id"] = "knowledgerollback_" + _digest(event)[:24]
        event["event_hash"] = _hash_without(event, "event_hash")
        self._revoked.add(revoked_release_id)
        self._active_release_id = target_release_id
        self._consumed_approvals.add(approval_id)
        self._events.append(copy.deepcopy(event))
        return event
