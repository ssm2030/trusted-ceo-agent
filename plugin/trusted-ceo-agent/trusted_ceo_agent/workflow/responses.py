from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, RevisionConflict
from trusted_ceo_agent.workflow.approvals import (
    approval_invalidation_updates,
    current_approval_ids,
)
from trusted_ceo_agent.workflow.human_actions import (
    pending_action_for_state,
    verify_action_card,
)
from trusted_ceo_agent.workflow.human_response_policy import (
    evaluate_human_response_policy,
)
from trusted_ceo_agent.workflow.overlays import apply_overlay, invalidated_gates
from trusted_ceo_agent.workflow.revisions import RevisionManager


_TERMINAL = {"finalized", "failed", "stopped_by_human", "cancelled"}
_SEMANTIC_ROOT = {
    "context": "/mission_contract",
    "data": "/mapping",
    "scope_narrowing": "/scope_narrowing",
    "diagnostic": "/issue_dispositions",
    "final": "/ceo_wording",
}


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _timestamp(value: datetime) -> str:
    normalized = _utc(value)
    return normalized.isoformat().replace("+00:00", "Z")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractError("Human Response clock must include a timezone")
    return value.astimezone(timezone.utc)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ContractError("Human Action Card expiry must include a timezone")
    return parsed.astimezone(timezone.utc)


def _json(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ContractError(f"stored {label} is invalid") from error
    if not isinstance(value, dict):
        raise ContractError(f"stored {label} must be an object")
    return value


def _normalize_response(value: Mapping[str, Any]) -> dict[str, Any]:
    if set(value) != {"response_type", "payload", "actor_id"}:
        raise ContractError("Human Response input has unknown or missing fields")
    response_type = value.get("response_type")
    payload = value.get("payload")
    actor_id = value.get("actor_id")
    if not isinstance(response_type, str):
        raise ContractError("Human Response type is required")
    if not isinstance(payload, Mapping):
        raise ContractError("Human Response payload must be an object")
    if not isinstance(actor_id, str) or not actor_id:
        raise ContractError("Human Response actor ID is required")
    return {
        "response_type": response_type,
        "payload": deepcopy(dict(payload)),
        "actor_id": actor_id,
    }


def _verify_resolution(value: Mapping[str, Any]) -> None:
    document = deepcopy(dict(value))
    SchemaStore().validate("human-action-resolution.schema.json", document)
    claimed = document.pop("resolution_hash")
    if _hash(document) != claimed:
        raise ContractError("Human Action resolution hash is invalid")


def _verify_cache_entry(value: Mapping[str, Any]) -> None:
    document = deepcopy(dict(value))
    if set(document) != {"schema_version", "request_hash", "receipt", "entry_hash"}:
        raise ContractError("Human Response operational receipt is invalid")
    if document.get("schema_version") != "1.0.0":
        raise ContractError("Human Response operational receipt version is invalid")
    claimed = document.pop("entry_hash")
    if not isinstance(claimed, str) or _hash(document) != claimed:
        raise ContractError("Human Response operational receipt hash is invalid")
    receipt = document.get("receipt")
    if not isinstance(receipt, dict):
        raise ContractError("Human Response operational receipt is invalid")
    SchemaStore().validate("human-response-receipt.schema.json", receipt)


class HumanResponseService:
    """Validate and atomically materialize one revision-bound human response."""

    def __init__(
        self,
        revisions: RevisionManager,
        *,
        clock: Callable[[], datetime] | None = None,
        trusted_principal: Mapping[str, Any] | None = None,
    ) -> None:
        self.revisions = revisions
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.schemas = SchemaStore()
        self.trusted_principal = deepcopy(dict(trusted_principal or {}))

    def _active_context(
        self,
        expected_revision: int,
        action: Mapping[str, Any],
    ) -> tuple[dict[str, bytes], dict[str, Any]]:
        if action.get("base_revision") != expected_revision:
            raise RevisionConflict("Human Action Card base revision is stale")
        files = self.revisions.files(expected_revision)
        state_payload = files.get("workflow/state.json")
        if state_payload is None:
            raise ContractError("workflow state is missing")
        state = _json(state_payload, label="workflow state")
        if state.get("revision") != expected_revision:
            raise RevisionConflict("workflow state revision is stale")
        if state.get("run_id") != action.get("run_id"):
            raise ContractError("Human Action Card run ID does not match the workflow")
        if state.get("state") != action.get("workflow_state"):
            raise RevisionConflict("Human Action Card workflow state is stale")
        if state.get("state") in _TERMINAL:
            raise ContractError("terminal workflow cannot accept a Human Response")
        stored_payload = files.get("workflow/pending-action.json")
        if stored_payload is not None:
            stored = _json(stored_payload, label="pending Human Action Card")
            if canonical_bytes(stored) != canonical_bytes(action):
                raise RevisionConflict("Human Action Card is not the active card")
        else:
            resolution_payload = files.get("workflow/human-action-resolution.json")
            if resolution_payload is not None:
                resolution = _json(resolution_payload, label="Human Action resolution")
                _verify_resolution(resolution)
                if (
                    resolution.get("result_revision") == expected_revision
                    and resolution.get("workflow_state") == state.get("state")
                ):
                    raise ContractError("no Human Action Card is active for this workflow state")
            derived = pending_action_for_state(
                run_id=str(state["run_id"]),
                revision=expected_revision,
                workflow_state=str(state["state"]),
                evidence_refs=[],
                expires_at=None,
            )
            if derived is None or canonical_bytes(derived) != canonical_bytes(action):
                raise RevisionConflict("Human Action Card is not the active card")
        expires_at = action.get("expires_at")
        if isinstance(expires_at, str) and _utc(self.clock()) >= _parse_timestamp(expires_at):
            raise ContractError("Human Action Card expired")
        return files, state

    @staticmethod
    def _validate_references(files: Mapping[str, bytes], record: Mapping[str, Any]) -> None:
        response_type = record["response_type"]
        if response_type == "provide_data":
            registry_payload = files.get("sources/registry.json")
            if registry_payload is None:
                raise ContractError("Source registry is missing")
            registry = json.loads(registry_payload.decode("utf-8"))
            if not isinstance(registry, list):
                raise ContractError("Source registry is invalid")
            known = {
                item.get("source_id")
                for item in registry
                if isinstance(item, dict) and isinstance(item.get("source_id"), str)
            }
            missing = sorted(set(record["payload"]["source_refs"]) - known)
            if missing:
                raise ContractError(f"Human Response references unknown Source IDs: {missing}")
        if response_type == "provide_alternative_evidence":
            core_payload = files.get("evidence/core.json")
            if core_payload is None:
                raise ContractError("Evidence Core is missing")
            core = json.loads(core_payload.decode("utf-8"))
            if not isinstance(core, dict) or not isinstance(core.get("evidence_links"), list):
                raise ContractError("Evidence Core is invalid")
            known = {
                item.get("evidence_link_id")
                for item in core["evidence_links"]
                if isinstance(item, dict) and isinstance(item.get("evidence_link_id"), str)
            }
            missing = sorted(set(record["payload"]["evidence_refs"]) - known)
            if missing:
                raise ContractError(f"Human Response references unknown Evidence IDs: {missing}")

    def _record(
        self,
        *,
        action: Mapping[str, Any],
        response: Mapping[str, Any],
        idempotency_key_hash: str,
        created_at: str,
    ) -> dict[str, Any]:
        normalized = _normalize_response(response)
        response_type = normalized["response_type"]
        if response_type not in action.get("allowed_response_types", []):
            raise ContractError("Human Response type is not allowed by the Action Card")
        semantic = {
            "schema_version": "1.0.0",
            "run_id": action["run_id"],
            "base_revision": action["base_revision"],
            "action_id": action["action_id"],
            "action_content_hash": action["content_hash"],
            "response_type": response_type,
            "payload": normalized["payload"],
            "actor_id": normalized["actor_id"],
        }
        response_id = make_id("response", semantic)
        record = {
            "response_id": response_id,
            **semantic,
            "response_hash": _hash(semantic),
            "idempotency_key_hash": idempotency_key_hash,
            "created_at": created_at,
        }
        self.schemas.validate("human-response.schema.json", record)
        self._validate_option_binding(action, record)
        return record

    @staticmethod
    def _validate_option_binding(
        action: Mapping[str, Any],
        record: Mapping[str, Any],
    ) -> None:
        response_type = record["response_type"]
        if response_type not in {"choose_one", "choose_many"}:
            return
        declared = {
            str(option.get("option_id")): str(option.get("response_type"))
            for option in action.get("options", [])
            if isinstance(option, Mapping)
        }
        selected = (
            [record["payload"]["option_id"]]
            if response_type == "choose_one"
            else list(record["payload"]["option_ids"])
        )
        invalid = sorted(
            str(option_id)
            for option_id in selected
            if declared.get(str(option_id)) != response_type
        )
        if invalid:
            raise ContractError(f"Human Response option is not declared for {response_type}: {invalid}")

    @staticmethod
    def _affected_paths(action: Mapping[str, Any], record: Mapping[str, Any]) -> list[str]:
        payload = record["payload"]
        operations = payload.get("patch_operations", [])
        paths = sorted({str(item["path"]) for item in operations})
        if paths or record["response_type"] in {"confirm", "request_explanation", "stop"}:
            return paths
        response_type = record["response_type"]
        if response_type in {"provide_data", "provide_alternative_evidence"}:
            return ["/sources"]
        if response_type == "proceed_limited":
            return ["/mapping"]
        if response_type == "exclude_scope":
            return ["/scope_narrowing"]
        return [_SEMANTIC_ROOT[str(action["gate"])]]

    def _prepare(
        self,
        *,
        expected_revision: int,
        action: Mapping[str, Any],
        response: Mapping[str, Any],
        idempotency_key_hash: str,
    ) -> tuple[
        dict[str, bytes], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]
    ]:
        verify_action_card(action)
        files, state = self._active_context(expected_revision, action)
        created_at = _timestamp(self.clock())
        record = self._record(
            action=action,
            response=response,
            idempotency_key_hash=idempotency_key_hash,
            created_at=created_at,
        )
        self._validate_references(files, record)
        affected_paths = self._affected_paths(action, record)
        policy_decision = evaluate_human_response_policy(
            files=files,
            action=action,
            normalized_response=_normalize_response(response),
            response_record=record,
            trusted_principal=self.trusted_principal,
            created_at=created_at,
        )
        if policy_decision.get("allowed") is not True:
            reasons = policy_decision.get("reason_codes", ["policy_denied"])
            raise ContractError(f"Human Response policy denied: {reasons}")
        approval_refs = list(current_approval_ids(
            files,
            sorted(invalidated_gates(affected_paths)),
        ))
        result_revision = (
            expected_revision
            if record["response_type"] == "request_explanation"
            else expected_revision + 1
        )
        workflow_state = (
            "stopped_by_human"
            if record["response_type"] == "stop"
            else str(state["state"])
        )
        receipt = {
            "response_id": record["response_id"],
            "run_id": action["run_id"],
            "base_revision": expected_revision,
            "result_revision": result_revision,
            "action_id": action["action_id"],
            "response_hash": record["response_hash"],
            "affected_paths": affected_paths,
            "invalidated_approval_refs": approval_refs,
            "workflow_state": workflow_state,
            "pending_action_ref": (
                "workflow/pending-action.json"
                if record["response_type"] == "request_changes"
                or (
                    record["response_type"] == "request_explanation"
                    and "workflow/pending-action.json" in files
                )
                else None
            ),
            "terminal_approval_required": record["response_type"] == "confirm",
            "created_at": created_at,
        }
        self.schemas.validate("human-response-receipt.schema.json", receipt)
        return files, state, record, receipt, policy_decision

    def preview(
        self,
        *,
        expected_revision: int,
        action: Mapping[str, Any],
        response: Mapping[str, Any],
    ) -> dict[str, Any]:
        if self.revisions.current_revision() != expected_revision:
            raise RevisionConflict(
                f"expected revision {expected_revision}, current is {self.revisions.current_revision()}"
            )
        _, _, _, receipt, _ = self._prepare(
            expected_revision=expected_revision,
            action=action,
            response=response,
            idempotency_key_hash=_hash({"preview": True}),
        )
        return receipt

    def _operational_receipt(
        self,
        *,
        key_hash: str,
        request_hash: str,
    ) -> dict[str, Any] | None:
        name = f"human-response-idempotency/{key_hash}.json"
        payload = self.revisions.store.read_operational(name)
        if payload is None:
            return None
        entry = _json(payload, label="Human Response operational receipt")
        _verify_cache_entry(entry)
        if entry.get("request_hash") != request_hash:
            raise ContractError("Human Response idempotency key conflicts with another payload")
        return deepcopy(entry["receipt"])

    def _store_operational_receipt(
        self,
        *,
        key_hash: str,
        request_hash: str,
        receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        body = {
            "schema_version": "1.0.0",
            "request_hash": request_hash,
            "receipt": deepcopy(dict(receipt)),
        }
        entry = {**body, "entry_hash": _hash(body)}
        payload = self.revisions.store.put_operational_once(
            f"human-response-idempotency/{key_hash}.json",
            canonical_bytes(entry),
        )
        stored = _json(payload, label="Human Response operational receipt")
        _verify_cache_entry(stored)
        if stored.get("request_hash") != request_hash:
            raise ContractError("Human Response idempotency key conflicts with another payload")
        return deepcopy(stored["receipt"])

    def submit(
        self,
        *,
        expected_revision: int,
        action: Mapping[str, Any],
        response: Mapping[str, Any],
        idempotency_key: str,
    ) -> tuple[dict[str, Any], int]:
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise ContractError("Human Response idempotency key is required")
        verify_action_card(action)
        normalized_response = _normalize_response(response)
        key_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        request_hash = _hash({
            "expected_revision": expected_revision,
            "action_id": action["action_id"],
            "action_content_hash": action["content_hash"],
            "response": normalized_response,
        })
        operational = self._operational_receipt(
            key_hash=key_hash,
            request_hash=request_hash,
        )
        if operational is not None:
            return operational, int(operational["result_revision"])
        idempotency_path = f"workflow/idempotency/human-responses/{key_hash}.json"
        current = self.revisions.current_revision()
        current_files = self.revisions.files(current)
        existing_payload = current_files.get(idempotency_path)
        if existing_payload is not None:
            existing = _json(existing_payload, label="Human Response idempotency receipt")
            if existing.get("request_hash") != request_hash:
                raise ContractError("Human Response idempotency key conflicts with another payload")
            receipt = existing.get("receipt")
            if not isinstance(receipt, dict):
                raise ContractError("stored Human Response idempotency receipt is invalid")
            self.schemas.validate("human-response-receipt.schema.json", receipt)
            response_ref = existing.get("response_ref")
            receipt_ref = existing.get("receipt_ref")
            if not isinstance(response_ref, str) or not isinstance(receipt_ref, str):
                raise ContractError("stored Human Response idempotency references are invalid")
            if current_files.get(receipt_ref) != canonical_bytes(receipt):
                raise ContractError("stored Human Response receipt reference is invalid")
            response_record = _json(
                current_files.get(response_ref, b""),
                label="Human Response record",
            )
            self.schemas.validate("human-response.schema.json", response_record)
            if response_record.get("response_hash") != receipt.get("response_hash"):
                raise ContractError("stored Human Response record reference is invalid")
            return receipt, int(receipt["result_revision"])
        if current != expected_revision:
            raise RevisionConflict(f"expected revision {expected_revision}, current is {current}")

        files, state, record, receipt, policy_decision = self._prepare(
            expected_revision=expected_revision,
            action=action,
            response=normalized_response,
            idempotency_key_hash=key_hash,
        )
        if record["response_type"] == "request_explanation":
            stored_receipt = self._store_operational_receipt(
                key_hash=key_hash,
                request_hash=request_hash,
                receipt=receipt,
            )
            return stored_receipt, expected_revision

        result_revision = expected_revision + 1
        response_path = f"workflow/human-responses/{record['response_id']}.json"
        receipt_path = f"workflow/human-response-receipts/{record['response_id']}.json"
        decision_path = (
            f"workflow/human-response-policy-decisions/{record['response_id']}.json"
        )
        next_card = None
        if record["response_type"] == "request_changes":
            next_card = pending_action_for_state(
                run_id=str(action["run_id"]),
                revision=result_revision,
                workflow_state=str(state["state"]),
                evidence_refs=list(action.get("evidence_refs", [])),
                expires_at=None,
            )
            if next_card is None:
                receipt["pending_action_ref"] = None
                self.schemas.validate("human-response-receipt.schema.json", receipt)
        resolution_body = {
            "schema_version": "1.0.0",
            "action_id": action["action_id"],
            "action_content_hash": action["content_hash"],
            "response_id": record["response_id"],
            "result_revision": result_revision,
            "workflow_state": receipt["workflow_state"],
            "disposition": (
                "stopped"
                if record["response_type"] == "stop"
                else "terminal_approval_required"
                if record["response_type"] == "confirm"
                else "resolved"
            ),
            "created_at": record["created_at"],
        }
        resolution = {**resolution_body, "resolution_hash": _hash(resolution_body)}
        _verify_resolution(resolution)
        updates: dict[str, bytes | None] = {
            f"workflow/actions/{action['action_id']}.json": canonical_bytes(action),
            "workflow/pending-action.json": (
                canonical_bytes(next_card) if next_card is not None else None
            ),
            "workflow/human-action-resolution.json": canonical_bytes(resolution),
            response_path: canonical_bytes(record),
            receipt_path: canonical_bytes(receipt),
            decision_path: canonical_bytes(policy_decision),
            idempotency_path: canonical_bytes({
                "request_hash": request_hash,
                "response_ref": response_path,
                "receipt_ref": receipt_path,
                "receipt": receipt,
            }),
            f"audit/events/r{result_revision:04d}-submit-human-response.json": canonical_bytes({
                "command": "submit-human-response",
                "action_id": action["action_id"],
                "response_id": record["response_id"],
                "policy_decision_ref": decision_path,
                "from_revision": expected_revision,
                "to_revision": result_revision,
            }),
        }
        operations = record["payload"].get("patch_operations", [])
        if operations:
            base_overlay = _json(
                files.get("workflow/hitl-overlay.json", b"{}"),
                label="HITL overlay",
            )
            materialized = apply_overlay(
                base_overlay,
                str(action["gate"]),
                operations,
                runtime_context=record["payload"].get("runtime_context", {}),
            )
            updates["workflow/hitl-overlay.json"] = canonical_bytes(materialized)
        updates.update(approval_invalidation_updates(
            files,
            receipt["invalidated_approval_refs"],
            invalidated_by_revision=result_revision,
        ))
        next_state = dict(state)
        next_state["revision"] = result_revision
        if record["response_type"] == "stop":
            next_state["state"] = "stopped_by_human"
        updates["workflow/state.json"] = canonical_bytes(next_state)
        revision = self.revisions.commit(expected_revision, updates)
        return receipt, revision
