from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, TextIO

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.errors import ContractError, RevisionConflict
from trusted_ceo_agent.workflow.revisions import RevisionManager


ROLE_BY_GATE = {
    "context": {"ceo", "delegated_executive", "business_owner"},
    "data": {"data_owner", "business_owner"},
    "scope_narrowing": {"ceo", "delegated_executive", "business_owner"},
    "diagnostic": {"ceo", "delegated_executive"},
    "final": {"ceo", "delegated_executive"},
    "expert_packet": {"profession_expert"},
}

INVALIDATION_GATES = frozenset({"diagnostic", "deep_authorization", "final"})
_AUTHORIZING_DECISIONS = frozenset({"approve", "approve_with_edits"})
_NONAPPROVAL_CONFIRMATIONS = {
    "request_changes": "REQUEST_CHANGES",
    "reject": "REJECT",
}
_APPROVAL_RECORD_PREFIX = "approvals/records/"
_REVISION_SUFFIX = re.compile(r"@r[0-9]{4,}$")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ContractError("approval clock must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _digest(prefix: str, value: Any) -> str:
    return prefix + hashlib.sha256(canonical_bytes(value)).hexdigest()[:24]


def _approval_hash(record: Mapping[str, Any]) -> str:
    body = dict(record)
    body.pop("approval_hash", None)
    invalidated_revision = body.get("invalidated_by_revision")
    if (
        isinstance(invalidated_revision, Decimal)
        and invalidated_revision == invalidated_revision.to_integral_value()
    ):
        body["invalidated_by_revision"] = int(invalidated_revision)
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def _approval_records(files: Mapping[str, bytes]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for path, payload in files.items():
        if not path.startswith(_APPROVAL_RECORD_PREFIX) or not path.endswith(".json"):
            continue
        value = strict_loads(payload)
        if not isinstance(value, dict):
            raise ContractError(f"stored Approval Record is invalid: {path}")
        approval_id = value.get("approval_id")
        expected_id = path[len(_APPROVAL_RECORD_PREFIX):-5]
        if not isinstance(approval_id, str) or approval_id != expected_id:
            raise ContractError(f"Approval Record ID does not match its path: {path}")
        status = value.get("status", "current")
        if status not in {"current", "invalidated"}:
            raise ContractError(f"Approval Record has an invalid status: {approval_id}")
        if not hmac.compare_digest(str(value.get("approval_hash", "")), _approval_hash(value)):
            raise ContractError(f"Approval Record hash is invalid: {approval_id}")
        records[approval_id] = value
    return records


def current_approval_ids(files: Mapping[str, bytes], gates: Sequence[str]) -> list[str]:
    """Resolve invalidation categories to actual current Approval Record IDs."""

    requested = set(gates)
    unsupported = requested - INVALIDATION_GATES
    if unsupported:
        raise ContractError(f"unsupported approval invalidation gates: {sorted(unsupported)}")
    matched: list[str] = []
    for approval_id, record in _approval_records(files).items():
        if record.get("status", "current") != "current":
            continue
        if record.get("decision") not in _AUTHORIZING_DECISIONS:
            continue
        gate = record.get("gate")
        diagnostic_scope = bool(record.get("authorized_component_ids") or record.get("target_refs"))
        if (
            ("diagnostic" in requested and gate == "diagnostic")
            or ("final" in requested and gate == "final")
            or ("deep_authorization" in requested and gate == "diagnostic" and diagnostic_scope)
        ):
            matched.append(approval_id)
    return sorted(set(matched))


def current_approvals(
    files: Mapping[str, bytes], *, gate: str | None = None,
) -> tuple[dict[str, Any], ...]:
    records = _approval_records(files)
    current = [
        dict(record)
        for record in records.values()
        if record.get("status", "current") == "current"
        and record.get("decision") in _AUTHORIZING_DECISIONS
        and (gate is None or record.get("gate") == gate)
    ]
    return tuple(sorted(current, key=lambda record: str(record["approval_id"])))


def approval_invalidation_updates(
    files: Mapping[str, bytes],
    approval_ids: Sequence[str],
    *,
    invalidated_by_revision: int,
) -> dict[str, bytes]:
    """Build immutable-snapshot updates that retain and invalidate current records."""

    if invalidated_by_revision < 1:
        raise ContractError("invalidated_by_revision must be positive")
    records = _approval_records(files)
    updates: dict[str, bytes] = {}
    for approval_id in sorted(set(approval_ids)):
        record = records.get(approval_id)
        if record is None:
            raise ContractError(f"Approval Record does not exist: {approval_id}")
        if record.get("status", "current") != "current":
            raise ContractError(f"Approval Record is not current: {approval_id}")
        if record.get("decision") not in _AUTHORIZING_DECISIONS:
            raise ContractError(f"Approval Record is not an authorization: {approval_id}")
        invalidated = dict(record)
        invalidated["status"] = "invalidated"
        invalidated["invalidated_by_revision"] = invalidated_by_revision
        invalidated["approval_hash"] = _approval_hash(invalidated)
        updates[f"{_APPROVAL_RECORD_PREFIX}{approval_id}.json"] = canonical_bytes(invalidated)
    return updates


def _resolve_invalidation_targets(files: Mapping[str, bytes], targets: Sequence[str]) -> list[str]:
    if not targets:
        return []
    gate_tokens = sorted({target for target in targets if target in INVALIDATION_GATES})
    explicit_ids = sorted({target for target in targets if target not in INVALIDATION_GATES})
    resolved = set(current_approval_ids(files, gate_tokens))
    if explicit_ids:
        records = _approval_records(files)
        for approval_id in explicit_ids:
            record = records.get(approval_id)
            if record is None:
                raise ContractError(f"Approval Record does not exist: {approval_id}")
            if record.get("status", "current") != "current":
                raise ContractError(f"Approval Record is not current: {approval_id}")
            if record.get("decision") not in _AUTHORIZING_DECISIONS:
                raise ContractError(f"Approval Record is not an authorization: {approval_id}")
            resolved.add(approval_id)
    return sorted(resolved)


def _result_artifact_ref(base_artifact_ref: str, result_revision: int) -> str:
    if not isinstance(base_artifact_ref, str) or not base_artifact_ref:
        raise ContractError("base artifact ref is invalid")
    base = _REVISION_SUFFIX.sub("", base_artifact_ref)
    return f"{base}@r{result_revision:04d}"


def _diagnostic_scope(patch_operations: Sequence[Mapping[str, Any]]) -> tuple[list[str], list[str]]:
    values: dict[str, list[str]] = {
        "/deep_dive_scope/component_ids": [],
        "/deep_dive_scope/issue_ids": [],
    }
    for operation in patch_operations:
        path = operation.get("path")
        if operation.get("op") not in {"add", "replace"} or path not in values:
            continue
        proposed = operation.get("value")
        if not isinstance(proposed, list) or any(not isinstance(item, str) or not item for item in proposed):
            raise ContractError(f"diagnostic scope must be a list of non-empty IDs: {path}")
        values[str(path)] = sorted(set(proposed))
    return values["/deep_dive_scope/component_ids"], values["/deep_dive_scope/issue_ids"]


class ApprovalService:
    def __init__(
        self,
        revisions: RevisionManager,
        *,
        clock: Callable[[], datetime] | None = None,
        nonce_factory: Callable[[], str] | None = None,
    ) -> None:
        self.revisions = revisions
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.nonce_factory = nonce_factory or (lambda: secrets.token_urlsafe(24))

    def request(
        self,
        *,
        expected_revision: int,
        gate: str,
        base_artifact_ref: str,
        base_artifact_hash: str,
        patch_operations: Sequence[Mapping[str, Any]],
        invalidated_approval_ids: Sequence[str],
        result_preview_hash: str,
        additional_updates: Mapping[str, bytes | None] | None = None,
    ) -> tuple[dict[str, Any], str, int]:
        if gate not in ROLE_BY_GATE:
            raise ContractError(f"unsupported approval gate: {gate}")
        if self.revisions.current_revision() != expected_revision:
            raise RevisionConflict("approval request base revision is stale")
        resolved_invalidations = _resolve_invalidation_targets(
            self.revisions.files(expected_revision), invalidated_approval_ids
        )
        nonce = self.nonce_factory()
        if not isinstance(nonce, str) or not nonce:
            raise ContractError("nonce factory returned an invalid nonce")
        now = _utc(self.clock())
        body: dict[str, Any] = {
            "gate": gate,
            "base_revision": expected_revision,
            "base_artifact_ref": base_artifact_ref,
            "base_artifact_hash": base_artifact_hash,
            "patch_operations": [dict(item) for item in patch_operations],
            "invalidated_approval_ids": resolved_invalidations,
            "result_preview_hash": result_preview_hash,
            "allowed_roles": sorted(ROLE_BY_GATE[gate]),
            "nonce_hash": hashlib.sha256(nonce.encode("utf-8")).hexdigest(),
            "created_at": _timestamp(now),
            "expires_at": _timestamp(now + timedelta(minutes=10)),
            "status": "pending",
        }
        body["approval_request_id"] = _digest("approvalrequest_", body)
        path = f"approvals/requests/{body['approval_request_id']}.json"
        updates = dict(additional_updates or {})
        protected = {path} | {
            f"{_APPROVAL_RECORD_PREFIX}{approval_id}.json"
            for approval_id in resolved_invalidations
        }
        if protected & set(updates):
            raise ContractError("additional updates cannot replace approval security records")
        updates[path] = canonical_bytes(body)
        revision = self.revisions.commit(expected_revision, updates)
        return body, nonce, revision

    def _load_request(self, request_id: str, revision: int) -> tuple[str, dict[str, Any]]:
        if self.revisions.current_revision() != revision:
            raise RevisionConflict(f"expected revision {revision}, current is {self.revisions.current_revision()}")
        path = f"approvals/requests/{request_id}.json"
        value = strict_loads(self.revisions.read(path, revision=revision))
        if not isinstance(value, dict):
            raise ContractError("stored Approval Request is invalid")
        base_revision = value.get("base_revision")
        if (
            isinstance(base_revision, Decimal)
            and base_revision == base_revision.to_integral_value()
        ):
            value = dict(value)
            value["base_revision"] = int(base_revision)
        return path, value

    def approve_interactive(
        self,
        request_id: str,
        *,
        expected_revision: int,
        input_stream: TextIO,
        output_stream: TextIO,
        additional_updates: Mapping[str, bytes | None] | None = None,
    ) -> tuple[dict[str, Any], int]:
        if not input_stream.isatty() or not output_stream.isatty():
            raise ContractError("approval requires stdin and stdout TTY")
        path, request = self._load_request(request_id, expected_revision)
        if request.get("status") != "pending":
            raise ContractError("Approval Request nonce was already consumed")
        if request.get("base_revision") != expected_revision - 1:
            raise RevisionConflict("approval request base revision is stale")
        now = _utc(self.clock())
        if now > _parse_timestamp(str(request.get("expires_at"))):
            raise ContractError("Approval Request nonce expired")

        output_stream.write(f"GATE: {request['gate']}\n")
        output_stream.write(f"BASE HASH: {request['base_artifact_hash']}\n")
        output_stream.write(f"PATCH DIFF: {request['patch_operations']}\n")
        output_stream.write(f"INVALIDATED APPROVALS: {request['invalidated_approval_ids']}\n")
        output_stream.write(f"RESULT PREVIEW HASH: {request['result_preview_hash']}\n")
        output_stream.write("Actor ID: ")
        output_stream.flush()
        actor_id = input_stream.readline().rstrip("\r\n")
        output_stream.write("Actor role: ")
        output_stream.flush()
        actor_role = input_stream.readline().rstrip("\r\n")
        output_stream.write("Nonce: ")
        output_stream.flush()
        nonce = input_stream.readline().rstrip("\r\n")
        output_stream.write("Type APPROVE: ")
        output_stream.flush()
        confirmation = input_stream.readline().rstrip("\r\n")

        if not actor_id:
            raise ContractError("actor ID is required")
        if actor_role not in request.get("allowed_roles", []):
            raise ContractError(f"actor role is not allowed for {request.get('gate')}")
        supplied_hash = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(supplied_hash, str(request.get("nonce_hash"))):
            raise ContractError("approval nonce is invalid")
        if confirmation != "APPROVE":
            raise ContractError("exact APPROVE confirmation is required")

        result_revision = expected_revision + 1
        authorized_component_ids, target_refs = _diagnostic_scope(request.get("patch_operations", []))
        approval: dict[str, Any] = {
            "approval_request_id": request_id,
            "gate": request["gate"],
            "base_artifact_ref": request["base_artifact_ref"],
            "result_artifact_ref": _result_artifact_ref(request["base_artifact_ref"], result_revision),
            "decision": "approve_with_edits" if request.get("patch_operations") else "approve",
            "confirmed": True,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "target_refs": target_refs if request["gate"] == "diagnostic" else [],
            "authorized_component_ids": authorized_component_ids if request["gate"] == "diagnostic" else [],
            "patch_operations": request.get("patch_operations", []),
            "rationale": "interactive approval",
            "created_at": _timestamp(now),
            "input_method": "interactive_tty",
            "nonce_hash": request["nonce_hash"],
            "tty_session_fingerprint": hashlib.sha256(
                f"{type(input_stream).__name__}:{type(output_stream).__name__}".encode("utf-8")
            ).hexdigest(),
            "supersedes_approval_id": None,
            "status": "current",
        }
        approval["approval_id"] = _digest("approval_", approval)
        approval["approval_hash"] = _approval_hash(approval)
        consumed = dict(request)
        consumed["status"] = "used"
        consumed["used_at"] = _timestamp(now)
        consumed["approval_id"] = approval["approval_id"]
        updates = dict(additional_updates or {})
        invalidation_updates = approval_invalidation_updates(
            self.revisions.files(expected_revision),
            request.get("invalidated_approval_ids", []),
            invalidated_by_revision=result_revision,
        )
        protected = {
            path,
            f"approvals/records/{approval['approval_id']}.json",
        } | set(invalidation_updates)
        if protected & set(updates):
            raise ContractError("additional updates cannot replace approval security records")
        updates.update(invalidation_updates)
        updates.update({
            path: canonical_bytes(consumed),
            f"approvals/records/{approval['approval_id']}.json": canonical_bytes(approval),
        })
        revision = self.revisions.commit(expected_revision, updates)
        return approval, revision

    def decide_interactive(
        self,
        request_id: str,
        *,
        decision: str,
        expected_revision: int,
        input_stream: TextIO,
        output_stream: TextIO,
        additional_updates: Mapping[str, bytes | None] | None = None,
    ) -> tuple[dict[str, Any], int]:
        """Record a human request-changes or reject decision without authorization."""

        confirmation_text = _NONAPPROVAL_CONFIRMATIONS.get(decision)
        if confirmation_text is None:
            raise ContractError(f"unsupported interactive decision: {decision}")
        if not input_stream.isatty() or not output_stream.isatty():
            raise ContractError("approval decision requires stdin and stdout TTY")
        path, request = self._load_request(request_id, expected_revision)
        if request.get("status") != "pending":
            raise ContractError("Approval Request nonce was already consumed")
        if request.get("base_revision") != expected_revision - 1:
            raise RevisionConflict("approval request base revision is stale")
        now = _utc(self.clock())
        if now > _parse_timestamp(str(request.get("expires_at"))):
            raise ContractError("Approval Request nonce expired")

        output_stream.write(f"GATE: {request['gate']}\n")
        output_stream.write(f"BASE HASH: {request['base_artifact_hash']}\n")
        output_stream.write(f"PATCH DIFF: {request['patch_operations']}\n")
        output_stream.write(f"INVALIDATED APPROVALS: {request['invalidated_approval_ids']}\n")
        output_stream.write(f"RESULT PREVIEW HASH: {request['result_preview_hash']}\n")
        output_stream.write(f"DECISION: {decision}\n")
        output_stream.write("Actor ID: ")
        output_stream.flush()
        actor_id = input_stream.readline().rstrip("\r\n")
        output_stream.write("Actor role: ")
        output_stream.flush()
        actor_role = input_stream.readline().rstrip("\r\n")
        output_stream.write("Nonce: ")
        output_stream.flush()
        nonce = input_stream.readline().rstrip("\r\n")
        output_stream.write("Rationale: ")
        output_stream.flush()
        rationale = input_stream.readline().rstrip("\r\n")
        output_stream.write(f"Type {confirmation_text}: ")
        output_stream.flush()
        confirmation = input_stream.readline().rstrip("\r\n")

        if not actor_id:
            raise ContractError("actor ID is required")
        if actor_role not in request.get("allowed_roles", []):
            raise ContractError(f"actor role is not allowed for {request.get('gate')}")
        supplied_hash = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(supplied_hash, str(request.get("nonce_hash"))):
            raise ContractError("approval nonce is invalid")
        if not rationale.strip():
            raise ContractError("decision rationale is required")
        if confirmation != confirmation_text:
            raise ContractError(f"exact {confirmation_text} confirmation is required")

        decision_record: dict[str, Any] = {
            "approval_request_id": request_id,
            "gate": request["gate"],
            "base_artifact_ref": request["base_artifact_ref"],
            "result_artifact_ref": request["base_artifact_ref"],
            "decision": decision,
            "confirmed": True,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "target_refs": [],
            "authorized_component_ids": [],
            "patch_operations": request.get("patch_operations", []),
            "rationale": rationale,
            "created_at": _timestamp(now),
            "input_method": "interactive_tty",
            "nonce_hash": request["nonce_hash"],
            "tty_session_fingerprint": hashlib.sha256(
                f"{type(input_stream).__name__}:{type(output_stream).__name__}".encode("utf-8")
            ).hexdigest(),
            "supersedes_approval_id": None,
            "status": "current",
        }
        decision_record["approval_id"] = _digest("approval_", decision_record)
        decision_record["approval_hash"] = _approval_hash(decision_record)
        consumed = dict(request)
        consumed["status"] = "used"
        consumed["used_at"] = _timestamp(now)
        consumed["approval_id"] = decision_record["approval_id"]

        record_path = f"{_APPROVAL_RECORD_PREFIX}{decision_record['approval_id']}.json"
        updates = dict(additional_updates or {})
        protected = {path, record_path} | {
            f"{_APPROVAL_RECORD_PREFIX}{approval_id}.json"
            for approval_id in request.get("invalidated_approval_ids", [])
        }
        if protected & set(updates):
            raise ContractError("additional updates cannot replace approval security records")
        updates.update({
            path: canonical_bytes(consumed),
            record_path: canonical_bytes(decision_record),
        })
        revision = self.revisions.commit(expected_revision, updates)
        return decision_record, revision
