from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import threading
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError, IntegrityError
from trusted_ceo_agent.filesystem import atomic_write, ensure_within, replace_with_retry
from trusted_ceo_agent.service.contracts import ServiceErrorCode, StrictModel


_RUN_ID = re.compile(r"^run_[A-Za-z0-9_-]{8,200}$")
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}


def _lock_for(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve()))
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("RunStore clock must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_timestamp(value: str, *, label: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be RFC3339") from error
    if parsed.tzinfo is None or _timestamp(parsed) != value:
        raise ValueError(f"{label} must be canonical UTC RFC3339")
    return value


def _hash_document(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(value))).hexdigest()


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON number: {token}")


def _canonical_json(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise IntegrityError(f"{label} is invalid JSON") from error
    if not isinstance(value, dict) or canonical_bytes(value) != payload:
        raise IntegrityError(f"{label} is not a canonical JSON object")
    return value


class ServiceStoreError(ContractError):
    def __init__(self, code: ServiceErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


ManifestStatus = Literal[
    "created",
    "running",
    "awaiting_human",
    "retryable_failure",
    "stopped",
    "cancelled",
    "finalized",
]


class ServiceManifest(StrictModel):
    run_id: str = Field(pattern=r"^run_[A-Za-z0-9_-]{8,200}$")
    generation: int = Field(default=0, ge=0)
    engine_revision: int = Field(ge=0)
    status: ManifestStatus = "created"
    stage: str | None = Field(default=None, max_length=200)
    job_ids: tuple[str, ...] = Field(default=(), max_length=512)
    attempt: int = Field(default=0, ge=0, le=100)
    last_checkpoint_revision: int = Field(ge=0)
    error_code: ServiceErrorCode | None = None
    pending_approval_request_id: str | None = Field(default=None, max_length=200)
    pending_approval_nonce: str | None = Field(default=None, max_length=512)
    result_ref: str | None = Field(default=None, max_length=500)
    bundle_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    updated_at: str = Field(min_length=20, max_length=40)

    @field_validator("updated_at")
    @classmethod
    def validate_updated_at(cls, value: str) -> str:
        return _validate_timestamp(value, label="manifest updated_at")

    @model_validator(mode="after")
    def validate_checkpoint(self) -> ServiceManifest:
        if self.last_checkpoint_revision > self.engine_revision:
            raise ValueError("checkpoint revision cannot exceed engine revision")
        if self.status == "awaiting_human" and not self.pending_approval_request_id:
            raise ValueError("awaiting_human manifest requires an approval request")
        if self.status != "awaiting_human" and self.pending_approval_nonce is not None:
            raise ValueError("approval nonce may exist only while awaiting_human")
        if len(self.job_ids) != len(set(self.job_ids)):
            raise ValueError("manifest job IDs must be unique")
        return self


class IdempotencyReceipt(StrictModel):
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,128}$")
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status_code: int = Field(ge=100, le=599)
    response: dict[str, Any]
    created_at: str = Field(min_length=20, max_length=40)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: str) -> str:
        return _validate_timestamp(value, label="receipt created_at")


class DeleteReceipt(StrictModel):
    run_id: str = Field(pattern=r"^run_[A-Za-z0-9_-]{8,200}$")
    revision: int = Field(ge=0)
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,128}$")
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_body: dict[str, Any]
    status_code: Literal[204] = 204
    response: dict[str, Any]
    created_at: str = Field(min_length=20, max_length=40)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: str) -> str:
        return _validate_timestamp(value, label="delete receipt created_at")

    @model_validator(mode="after")
    def validate_request(self) -> DeleteReceipt:
        expected_body = {
            "confirmed": True,
            "expected_revision": self.revision,
            "run_id": self.run_id,
        }
        if self.request_body != expected_body:
            raise ValueError("delete receipt request body is invalid")
        if not hmac.compare_digest(self.request_hash, _hash_document(expected_body)):
            raise ValueError("delete receipt request hash is invalid")
        if self.response:
            raise ValueError("delete receipt response must be empty")
        return self


class RunStore:
    def __init__(
        self,
        service_root: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        service_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.service_root = ensure_within(service_root, service_root)
        self.runs_root = ensure_within(
            self.service_root,
            self.service_root / "runs",
        )
        self.runs_root.mkdir(mode=0o700, exist_ok=True)
        self.trash_root = ensure_within(
            self.service_root,
            self.service_root / "trash",
        )
        self.trash_root.mkdir(mode=0o700, exist_ok=True)
        self.tombstone_root = ensure_within(
            self.service_root,
            self.service_root / "tombstones",
        )
        self.tombstone_root.mkdir(mode=0o700, exist_ok=True)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._recover_delete_transactions()

    def run_root(self, run_id: str) -> Path:
        if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
            raise ServiceStoreError("ENGINE_FAILURE", "invalid run ID")
        return ensure_within(self.runs_root, self.runs_root / run_id)

    def _manifest_path(self, run_id: str) -> Path:
        return ensure_within(
            self.run_root(run_id),
            self.run_root(run_id) / "service-manifest.json",
        )

    def create_manifest(
        self,
        run_id: str,
        *,
        engine_revision: int,
    ) -> ServiceManifest:
        run_root = self.run_root(run_id)
        lock = _lock_for(run_root)
        with lock:
            if self._deleted_receipt(run_id) is not None:
                raise ServiceStoreError("ENGINE_FAILURE", "deleted run ID cannot be reused")
            trash = ensure_within(self.trash_root, self.trash_root / run_id)
            if trash.exists():
                raise IntegrityError("run ID has an unfinished delete transaction")
            run_root.mkdir(mode=0o700, exist_ok=True)
            path = self._manifest_path(run_id)
            if path.exists():
                raise ServiceStoreError("ENGINE_FAILURE", "service manifest already exists")
            manifest = ServiceManifest(
                run_id=run_id,
                engine_revision=engine_revision,
                last_checkpoint_revision=engine_revision,
                updated_at=_timestamp(self.clock()),
            )
            atomic_write(path, canonical_bytes(manifest.model_dump(mode="json")))
            return manifest

    def read_manifest(self, run_id: str) -> ServiceManifest:
        path = self._manifest_path(run_id)
        if not path.is_file():
            raise FileNotFoundError(run_id)
        try:
            payload = path.read_bytes()
            _canonical_json(payload, label="service manifest")
            return ServiceManifest.model_validate_json(payload)
        except (ValueError, TypeError) as error:
            raise IntegrityError("service manifest is invalid") from error

    def _engine_revision(self, run_id: str) -> int | None:
        state_path = ensure_within(
            self.run_root(run_id),
            self.run_root(run_id) / "state.json",
        )
        if not state_path.exists():
            return None
        try:
            state = _canonical_json(state_path.read_bytes(), label="engine state")
            if state.get("run_id") != run_id:
                raise IntegrityError("engine state run ID does not match target run")
            revision = state["revision"]
            if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
                raise ValueError("engine revision is invalid")
            return revision
        except (KeyError, TypeError, ValueError) as error:
            raise IntegrityError("engine state is invalid") from error

    def assert_revision(self, run_id: str, *, expected_revision: int) -> ServiceManifest:
        manifest = self.read_manifest(run_id)
        engine_revision = self._engine_revision(run_id)
        if manifest.engine_revision != expected_revision or (
            engine_revision is not None and engine_revision != expected_revision
        ):
            raise ServiceStoreError(
                "STALE_REVISION",
                f"expected revision {expected_revision}, current is {manifest.engine_revision}",
            )
        return manifest

    def save_manifest(
        self,
        manifest: ServiceManifest,
        *,
        expected_revision: int,
    ) -> ServiceManifest:
        run_root = self.run_root(manifest.run_id)
        lock = _lock_for(run_root)
        with lock:
            current = self.read_manifest(manifest.run_id)
            if current.engine_revision != expected_revision:
                raise ServiceStoreError(
                    "STALE_REVISION",
                    f"expected revision {expected_revision}, current is {current.engine_revision}",
                )
            if manifest.generation != current.generation:
                raise ServiceStoreError(
                    "STALE_REVISION",
                    "service manifest generation is stale",
                )
            engine_revision = self._engine_revision(manifest.run_id)
            if engine_revision is not None and engine_revision != manifest.engine_revision:
                raise ServiceStoreError(
                    "STALE_REVISION",
                    "service manifest does not match the engine revision",
                )
            candidate = ServiceManifest.model_validate({
                **manifest.model_dump(mode="python"),
                "generation": current.generation + 1,
                "updated_at": _timestamp(self.clock()),
            })
            atomic_write(
                self._manifest_path(manifest.run_id),
                canonical_bytes(candidate.model_dump(mode="json")),
            )
            return candidate

    def store_idempotency_receipt(
        self,
        run_id: str,
        *,
        idempotency_key: str,
        request_body: Mapping[str, Any],
        status_code: int,
        response: Mapping[str, Any],
    ) -> IdempotencyReceipt:
        if _IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None:
            raise ServiceStoreError("IDEMPOTENCY_CONFLICT", "invalid idempotency key")
        request_hash = _hash_document(request_body)
        key_hash = hashlib.sha256(idempotency_key.encode("ascii")).hexdigest()
        run_root = self.run_root(run_id)
        receipt_path = ensure_within(
            run_root,
            run_root / "service" / "idempotency" / f"{key_hash}.json",
        )
        lock = _lock_for(run_root)
        with lock:
            if receipt_path.exists():
                try:
                    existing_payload = receipt_path.read_bytes()
                    _canonical_json(existing_payload, label="idempotency receipt")
                    existing = IdempotencyReceipt.model_validate_json(existing_payload)
                except (TypeError, ValueError) as error:
                    raise IntegrityError("idempotency receipt is invalid") from error
                if not hmac.compare_digest(existing.request_hash, request_hash):
                    raise ServiceStoreError(
                        "IDEMPOTENCY_CONFLICT",
                        "idempotency key was reused for a different request",
                    )
                return existing
            receipt = IdempotencyReceipt(
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                status_code=status_code,
                response=dict(response),
                created_at=_timestamp(self.clock()),
            )
            canonical = canonical_bytes(receipt.model_dump(mode="json"))
            atomic_write(receipt_path, canonical)
            return receipt

    def read_idempotency_receipt(
        self,
        run_id: str,
        *,
        idempotency_key: str,
        request_body: Mapping[str, Any],
    ) -> IdempotencyReceipt | None:
        """Return a matching completed request without repeating its mutation."""
        if _IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None:
            raise ServiceStoreError("IDEMPOTENCY_CONFLICT", "invalid idempotency key")
        request_hash = _hash_document(request_body)
        key_hash = hashlib.sha256(idempotency_key.encode("ascii")).hexdigest()
        run_root = self.run_root(run_id)
        receipt_path = ensure_within(
            run_root,
            run_root / "service" / "idempotency" / f"{key_hash}.json",
        )
        lock = _lock_for(run_root)
        with lock:
            if not receipt_path.exists():
                return None
            try:
                payload = receipt_path.read_bytes()
                _canonical_json(payload, label="idempotency receipt")
                receipt = IdempotencyReceipt.model_validate_json(payload)
            except (TypeError, ValueError) as error:
                raise IntegrityError("idempotency receipt is invalid") from error
            if not hmac.compare_digest(receipt.request_hash, request_hash):
                raise ServiceStoreError(
                    "IDEMPOTENCY_CONFLICT",
                    "idempotency key was reused for a different request",
                )
            return receipt

    def recover_interrupted(self) -> list[str]:
        recovered: list[str] = []
        for path in sorted(self.runs_root.glob("run_*/service-manifest.json")):
            run_id = path.parent.name
            manifest = self.read_manifest(run_id)
            engine_revision = self._engine_revision(run_id)
            if engine_revision is not None and engine_revision < manifest.engine_revision:
                raise IntegrityError("engine revision is behind the service manifest")
            if engine_revision is not None and engine_revision > manifest.engine_revision:
                updated = manifest.model_copy(update={
                    "engine_revision": engine_revision,
                    "last_checkpoint_revision": engine_revision,
                    "status": "retryable_failure",
                    "error_code": "ENGINE_FAILURE",
                    "pending_approval_request_id": None,
                    "pending_approval_nonce": None,
                })
                self.save_manifest(updated, expected_revision=manifest.engine_revision)
                recovered.append(run_id)
                continue
            if manifest.status == "running":
                updated = manifest.model_copy(update={
                    "status": "retryable_failure",
                    "error_code": "AI_TRANSIENT_FAILURE",
                })
                self.save_manifest(updated, expected_revision=manifest.engine_revision)
                recovered.append(run_id)
        return recovered

    def _tombstone_path(self, run_id: str) -> Path:
        return ensure_within(
            self.tombstone_root,
            self.tombstone_root / f"{run_id}.json",
        )

    def _read_delete_receipt(self, path: Path, *, label: str) -> DeleteReceipt:
        try:
            payload = path.read_bytes()
            _canonical_json(payload, label=label)
            return DeleteReceipt.model_validate_json(payload)
        except (OSError, TypeError, ValueError) as error:
            raise IntegrityError(f"{label} is invalid") from error

    def _deleted_receipt(self, run_id: str) -> DeleteReceipt | None:
        path = self._tombstone_path(run_id)
        if not path.exists():
            return None
        receipt = self._read_delete_receipt(path, label="delete tombstone")
        if receipt.run_id != run_id:
            raise IntegrityError("delete tombstone is invalid")
        return receipt

    def _delete_intent_path(self, root: Path) -> Path:
        return ensure_within(root, root / "service" / "delete-intent.json")

    def _write_tombstone(self, receipt: DeleteReceipt) -> None:
        atomic_write(
            self._tombstone_path(receipt.run_id),
            canonical_bytes(receipt.model_dump(mode="json")),
        )

    def _validate_delete_replay(
        self,
        receipt: DeleteReceipt,
        *,
        run_id: str,
        expected_revision: int,
        idempotency_key: str,
        request_hash: str,
    ) -> None:
        if receipt.run_id != run_id:
            raise IntegrityError("delete receipt run ID does not match target run")
        if receipt.revision != expected_revision:
            raise ServiceStoreError(
                "STALE_REVISION",
                f"deleted revision is {receipt.revision}",
            )
        if (
            not hmac.compare_digest(receipt.idempotency_key, idempotency_key)
            or not hmac.compare_digest(receipt.request_hash, request_hash)
        ):
            raise ServiceStoreError(
                "IDEMPOTENCY_CONFLICT",
                "delete idempotency key or request does not match",
            )

    def _recover_delete_transactions(self) -> None:
        for trash in sorted(self.trash_root.glob("run_*")):
            if not trash.is_dir():
                raise IntegrityError("delete trash contains an invalid entry")
            ensure_within(self.trash_root, trash)
            intent_path = self._delete_intent_path(trash)
            if not intent_path.is_file():
                raise IntegrityError("delete trash is missing its intent receipt")
            receipt = self._read_delete_receipt(intent_path, label="delete intent")
            if receipt.run_id != trash.name:
                raise IntegrityError("delete intent run ID does not match trash target")
            tombstone = self._deleted_receipt(receipt.run_id)
            if tombstone is None:
                self._write_tombstone(receipt)
            elif tombstone != receipt:
                raise IntegrityError("delete tombstone does not match trash intent")
            shutil.rmtree(trash)

    def delete_run(
        self,
        run_id: str,
        *,
        expected_revision: int,
        confirmed: bool,
        idempotency_key: str,
    ) -> None:
        if confirmed is not True:
            raise ServiceStoreError("ENGINE_FAILURE", "explicit delete confirmation is required")
        if _IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None:
            raise ServiceStoreError("IDEMPOTENCY_CONFLICT", "invalid idempotency key")
        request_body = {
            "confirmed": True,
            "expected_revision": expected_revision,
            "run_id": run_id,
        }
        request_hash = _hash_document(request_body)
        run_root = self.run_root(run_id)
        lock = _lock_for(run_root)
        with lock:
            trash = ensure_within(self.trash_root, self.trash_root / run_id)
            deleted = self._deleted_receipt(run_id)
            if deleted is not None:
                self._validate_delete_replay(
                    deleted,
                    run_id=run_id,
                    expected_revision=expected_revision,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                )
                if trash.exists():
                    intent = self._read_delete_receipt(
                        self._delete_intent_path(trash),
                        label="delete intent",
                    )
                    if intent != deleted:
                        raise IntegrityError("delete tombstone does not match trash intent")
                    shutil.rmtree(trash)
                return
            if not run_root.exists() and trash.exists():
                intent = self._read_delete_receipt(
                    self._delete_intent_path(trash),
                    label="delete intent",
                )
                self._validate_delete_replay(
                    intent,
                    run_id=run_id,
                    expected_revision=expected_revision,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                )
                self._write_tombstone(intent)
                shutil.rmtree(trash)
                return
            self.assert_revision(run_id, expected_revision=expected_revision)
            for candidate in sorted(run_root.rglob("*")):
                ensure_within(run_root, candidate)
            if trash.exists():
                raise IntegrityError("delete trash target already exists")
            receipt = DeleteReceipt(
                run_id=run_id,
                revision=expected_revision,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                request_body=request_body,
                status_code=204,
                response={},
                created_at=_timestamp(self.clock()),
            )
            atomic_write(
                self._delete_intent_path(run_root),
                canonical_bytes(receipt.model_dump(mode="json")),
            )
            replace_with_retry(run_root, trash, target_must_not_exist=True)
            self._write_tombstone(receipt)
            shutil.rmtree(trash)
