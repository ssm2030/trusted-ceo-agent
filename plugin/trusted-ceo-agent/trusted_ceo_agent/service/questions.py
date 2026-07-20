from __future__ import annotations

import hashlib
import json
import re
import threading
import unicodedata
from collections.abc import Mapping
from concurrent.futures import Executor, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import Field, ValidationError, field_validator, model_validator

from trusted_ceo_agent.application.models import (
    ApplicationResult,
    PrepareResultQuestionRequest,
    ValidateResultAnswerRequest,
)
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, IntegrityError
from trusted_ceo_agent.filesystem import atomic_write, ensure_within
from trusted_ceo_agent.service.contracts import StrictModel
from trusted_ceo_agent.service.openai_gateway import AIServiceError
from trusted_ceo_agent.service.run_store import (
    RunStore,
    ServiceManifest,
    ServiceStoreError,
)


QuestionState = Literal[
    "queued",
    "preparing",
    "asking",
    "validating",
    "completed",
    "failed",
    "scope_required",
    "cancelled",
]
QuestionScopeKind = Literal[
    "run",
    "issue",
    "section",
    "claim",
    "evidence",
    "source",
    "expert_packet",
    "revision_diff",
]
PrivacyClassification = Literal["poc_deidentified", "company_restricted"]

_ACTIVE_STATES = frozenset({"queued", "preparing", "asking", "validating"})
_TERMINAL_STATES = frozenset(
    {"completed", "failed", "scope_required", "cancelled"}
)
_REQUEST_ID = re.compile(r"^questionrequest_[0-9a-f]{24}$")
_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}


def _question_lock(store: RunStore, run_id: str) -> threading.RLock:
    key = str(store.run_root(run_id).resolve()).casefold()
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON number: {token}")


def _canonical_object(payload: bytes, *, label: str) -> dict[str, Any]:
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


class QuestionDraftGateway(Protocol):
    def execute_question(self, job: Mapping[str, Any]) -> dict[str, Any]:
        """Return an untrusted result-answer draft for local validation."""


class QuestionApplication(Protocol):
    def prepare_result_question(
        self,
        request: PrepareResultQuestionRequest,
    ) -> ApplicationResult:
        pass

    def validate_result_answer(
        self,
        request: ValidateResultAnswerRequest,
    ) -> ApplicationResult:
        pass


class QuestionRequest(StrictModel):
    expected_revision: int = Field(ge=1)
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,128}$")
    question: str = Field(min_length=1, max_length=2_000)
    scope_kind: QuestionScopeKind
    scope_instance_id: str = Field(min_length=1, max_length=500)
    privacy_classification: PrivacyClassification

    @field_validator("question", "scope_instance_id")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFC", value).strip()
        if not normalized:
            raise ValueError("question fields must not be empty")
        if any(unicodedata.category(character) == "Cc" for character in normalized):
            raise ValueError("question fields contain control characters")
        return normalized


class ScopeSuggestion(StrictModel):
    scope_kind: QuestionScopeKind
    scope_instance_id: str = Field(min_length=1, max_length=500)


class QuestionSnapshot(StrictModel):
    request_id: str = Field(pattern=r"^questionrequest_[0-9a-f]{24}$")
    run_id: str = Field(pattern=r"^run_[A-Za-z0-9_-]{8,200}$")
    revision: int = Field(ge=1)
    generation: int = Field(default=0, ge=0)
    state: QuestionState
    scope_kind: QuestionScopeKind
    scope_instance_id: str = Field(min_length=1, max_length=500)
    answer: dict[str, Any] | None = None
    scope_suggestions: list[ScopeSuggestion] = Field(default_factory=list)
    error_code: str | None = Field(default=None, max_length=100)
    retryable: bool = False

    @model_validator(mode="after")
    def validate_state_payload(self) -> QuestionSnapshot:
        if self.state in _ACTIVE_STATES:
            if (
                self.answer is not None
                or self.scope_suggestions
                or self.error_code is not None
                or self.retryable
            ):
                raise ValueError("active question snapshot contains terminal data")
        elif self.state == "completed":
            if (
                self.answer is None
                or self.scope_suggestions
                or self.error_code is not None
                or self.retryable
            ):
                raise ValueError("completed question snapshot is invalid")
        elif self.state == "scope_required":
            if (
                self.answer is not None
                or not self.scope_suggestions
                or self.error_code != "SCOPE_REQUIRED"
                or self.retryable
            ):
                raise ValueError("scope-blocked question snapshot is invalid")
        elif self.state in {"failed", "cancelled"}:
            if (
                self.answer is not None
                or self.scope_suggestions
                or self.error_code is None
            ):
                raise ValueError("failed question snapshot is invalid")
        return self


class QuestionService:
    def __init__(
        self,
        application: QuestionApplication,
        run_store: RunStore,
        gateway: QuestionDraftGateway,
        *,
        executor: Executor | None = None,
    ) -> None:
        self.application = application
        self.run_store = run_store
        self.gateway = gateway
        self._owns_executor = executor is None
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="trusted-ceo-question",
        )
        self._lifecycle_lock = threading.Lock()
        self._closed = False
        self._schemas = SchemaStore()
        self._recover_active(
            state="failed",
            error_code="ENGINE_FAILURE",
            retryable=True,
        )

    def close(self) -> None:
        with self._lifecycle_lock:
            self._closed = True
        if self._owns_executor:
            self._executor.shutdown(wait=False, cancel_futures=True)
        self._recover_active(
            state="cancelled",
            error_code="CANCELLED",
            retryable=False,
        )

    def _recover_active(
        self,
        *,
        state: Literal["failed", "cancelled"],
        error_code: str,
        retryable: bool,
    ) -> None:
        for run_path in sorted(self.run_store.runs_root.glob("run_*")):
            if not run_path.is_dir():
                continue
            run_id = run_path.name
            with _question_lock(self.run_store, run_id):
                for current in self._list_locked(run_id):
                    if current.state not in _ACTIVE_STATES:
                        continue
                    recovered = current.model_copy(
                        update={
                            "generation": current.generation + 1,
                            "state": state,
                            "answer": None,
                            "scope_suggestions": [],
                            "error_code": error_code,
                            "retryable": retryable,
                        }
                    )
                    QuestionSnapshot.model_validate(
                        recovered.model_dump(mode="python")
                    )
                    self._write_locked(recovered)

    def start(
        self,
        run_id: str,
        request: QuestionRequest,
    ) -> QuestionSnapshot:
        if not isinstance(request, QuestionRequest):
            raise TypeError("request must be a QuestionRequest")
        with self._lifecycle_lock:
            if self._closed:
                raise ContractError("question service is closed")

        request_body = request.model_dump(
            mode="json",
            exclude={"idempotency_key"},
        )
        lock = _question_lock(self.run_store, run_id)
        with lock:
            replay = self.run_store.read_idempotency_receipt(
                run_id,
                idempotency_key=request.idempotency_key,
                request_body=request_body,
            )
            if replay is not None:
                request_id = replay.response.get("request_id")
                if (
                    not isinstance(request_id, str)
                    or _REQUEST_ID.fullmatch(request_id) is None
                ):
                    raise IntegrityError(
                        "question idempotency receipt is invalid"
                    )
                path = self._snapshot_path(run_id, request_id)
                if path.exists():
                    return self._get_locked(run_id, request_id)
            else:
                request_id = self._request_id(run_id, request.idempotency_key)
                path = self._snapshot_path(run_id, request_id)

            self._assert_finalized(
                run_id,
                expected_revision=request.expected_revision,
            )
            snapshots = self._list_locked(run_id)
            if any(item.state in _ACTIVE_STATES for item in snapshots):
                raise ServiceStoreError(
                    "IDEMPOTENCY_CONFLICT",
                    "another result question is active",
                )

            if replay is None:
                if path.exists():
                    raise IntegrityError(
                        "question request exists without an idempotency receipt"
                    )
                self.run_store.store_idempotency_receipt(
                    run_id,
                    idempotency_key=request.idempotency_key,
                    request_body=request_body,
                    status_code=202,
                    response={"request_id": request_id},
                )

            queued = QuestionSnapshot(
                request_id=request_id,
                run_id=run_id,
                revision=request.expected_revision,
                state="queued",
                scope_kind=request.scope_kind,
                scope_instance_id=request.scope_instance_id,
            )
            self._write_locked(queued, create=True)
            try:
                self._executor.submit(
                    self._execute,
                    run_id,
                    request_id,
                    request,
                )
            except Exception:
                failed = queued.model_copy(
                    update={
                        "generation": queued.generation + 1,
                        "state": "failed",
                        "error_code": "ENGINE_FAILURE",
                    }
                )
                self._write_locked(failed)
                return failed
            return queued

    def get(self, run_id: str, request_id: str) -> QuestionSnapshot:
        with _question_lock(self.run_store, run_id):
            return self._get_locked(run_id, request_id)

    def _get_locked(self, run_id: str, request_id: str) -> QuestionSnapshot:
        snapshot = self._read_locked(run_id, request_id)
        if snapshot.run_id != run_id:
            raise IntegrityError("question snapshot run ID does not match its path")
        if snapshot.state in _ACTIVE_STATES or snapshot.state == "completed":
            try:
                manifest = self.run_store.assert_revision(
                    run_id,
                    expected_revision=snapshot.revision,
                )
                current = manifest.status == "finalized"
            except ServiceStoreError as error:
                if error.code != "STALE_REVISION":
                    raise
                current = False
            if not current:
                snapshot = snapshot.model_copy(
                    update={
                        "generation": snapshot.generation + 1,
                        "state": "cancelled",
                        "answer": None,
                        "scope_suggestions": [],
                        "error_code": "STALE_REVISION",
                        "retryable": False,
                    }
                )
                self._write_locked(snapshot)
        return snapshot

    @staticmethod
    def _request_id(run_id: str, idempotency_key: str) -> str:
        key_hash = hashlib.sha256(idempotency_key.encode("ascii")).hexdigest()
        return make_id(
            "questionrequest",
            {"run_id": run_id, "idempotency_key_hash": key_hash},
        )

    def _snapshot_path(self, run_id: str, request_id: str) -> Path:
        if (
            not isinstance(request_id, str)
            or _REQUEST_ID.fullmatch(request_id) is None
        ):
            raise ContractError("invalid question request ID")
        run_root = self.run_store.run_root(run_id)
        return ensure_within(
            run_root,
            run_root / "conversations" / f"{request_id}.json",
        )

    def _write_locked(
        self,
        snapshot: QuestionSnapshot,
        *,
        create: bool = False,
    ) -> None:
        path = self._snapshot_path(snapshot.run_id, snapshot.request_id)
        if create and path.exists():
            raise ServiceStoreError(
                "IDEMPOTENCY_CONFLICT",
                "question request already exists",
            )
        atomic_write(
            path,
            canonical_bytes(snapshot.model_dump(mode="json")),
        )

    def _read_locked(
        self,
        run_id: str,
        request_id: str,
    ) -> QuestionSnapshot:
        path = self._snapshot_path(run_id, request_id)
        if not path.is_file():
            raise FileNotFoundError(request_id)
        payload = _canonical_object(path.read_bytes(), label="question snapshot")
        try:
            snapshot = QuestionSnapshot.model_validate(payload)
            if snapshot.answer is not None:
                self._schemas.validate("result-answer.schema.json", snapshot.answer)
                if (
                    snapshot.answer.get("run_id") != snapshot.run_id
                    or snapshot.answer.get("revision") != snapshot.revision
                ):
                    raise IntegrityError(
                        "question answer identity differs from its snapshot"
                    )
        except ValidationError as error:
            raise IntegrityError("question snapshot is invalid") from error
        except ContractError as error:
            raise IntegrityError("stored question answer is invalid") from error
        return snapshot

    def _list_locked(self, run_id: str) -> list[QuestionSnapshot]:
        run_root = self.run_store.run_root(run_id)
        directory = ensure_within(run_root, run_root / "conversations")
        if not directory.exists():
            return []
        snapshots: list[QuestionSnapshot] = []
        for path in sorted(directory.glob("questionrequest_*.json")):
            safe = ensure_within(run_root, path)
            if _REQUEST_ID.fullmatch(safe.stem) is None:
                continue
            snapshots.append(self._read_locked(run_id, safe.stem))
        return snapshots

    def _assert_finalized(
        self,
        run_id: str,
        *,
        expected_revision: int,
    ) -> ServiceManifest:
        manifest = self.run_store.assert_revision(
            run_id,
            expected_revision=expected_revision,
        )
        if manifest.status != "finalized":
            raise ContractError("result questions require a finalized run")
        return manifest

    def _transition(
        self,
        run_id: str,
        request_id: str,
        state: Literal["preparing", "asking", "validating"],
    ) -> QuestionSnapshot:
        with _question_lock(self.run_store, run_id):
            current = self._read_locked(run_id, request_id)
            if current.state not in _ACTIVE_STATES:
                return current
            updated = current.model_copy(
                update={
                    "generation": current.generation + 1,
                    "state": state,
                }
            )
            self._write_locked(updated)
            return updated

    def _finish(
        self,
        run_id: str,
        request_id: str,
        *,
        state: Literal[
            "completed",
            "failed",
            "scope_required",
            "cancelled",
        ],
        answer: Mapping[str, Any] | None = None,
        suggestions: tuple[ScopeSuggestion, ...] = (),
        error_code: str | None = None,
        retryable: bool = False,
        require_current_revision: bool = False,
    ) -> QuestionSnapshot:
        with _question_lock(self.run_store, run_id):
            current = self._read_locked(run_id, request_id)
            if current.state in _TERMINAL_STATES:
                return current
            if require_current_revision:
                self._assert_finalized(
                    run_id,
                    expected_revision=current.revision,
                )
            updated = current.model_copy(
                update={
                    "generation": current.generation + 1,
                    "state": state,
                    "answer": dict(answer) if answer is not None else None,
                    "scope_suggestions": list(suggestions),
                    "error_code": error_code,
                    "retryable": retryable,
                }
            )
            QuestionSnapshot.model_validate(updated.model_dump(mode="python"))
            self._write_locked(updated)
            return updated

    def _execute(
        self,
        run_id: str,
        request_id: str,
        request: QuestionRequest,
    ) -> None:
        try:
            self._transition(run_id, request_id, "preparing")
            self._assert_finalized(
                run_id,
                expected_revision=request.expected_revision,
            )
            prepared = self.application.prepare_result_question(
                PrepareResultQuestionRequest(
                    run_id=run_id,
                    revision=request.expected_revision,
                    question=request.question,
                    scope_kind=request.scope_kind,
                    scope_instance_id=request.scope_instance_id,
                    privacy_classification=request.privacy_classification,
                )
            )
            if self._scope_required(prepared, run_id, request.expected_revision):
                suggestions = self._scope_suggestions(prepared)
                self._finish(
                    run_id,
                    request_id,
                    state="scope_required",
                    suggestions=suggestions,
                    error_code="SCOPE_REQUIRED",
                    require_current_revision=True,
                )
                return
            job = self._prepared_job(
                prepared,
                run_id=run_id,
                revision=request.expected_revision,
            )
            self._assert_finalized(
                run_id,
                expected_revision=request.expected_revision,
            )
            self._transition(run_id, request_id, "asking")
            draft = self.gateway.execute_question(job)
            if not isinstance(draft, Mapping):
                raise ContractError("question gateway draft must be an object")
            self._assert_finalized(
                run_id,
                expected_revision=request.expected_revision,
            )
            self._transition(run_id, request_id, "validating")
            validated = self.application.validate_result_answer(
                ValidateResultAnswerRequest(
                    run_id=run_id,
                    revision=request.expected_revision,
                    job=job,
                    draft=dict(draft),
                )
            )
            answer = self._validated_answer(
                validated,
                run_id=run_id,
                revision=request.expected_revision,
            )
            self._schemas.validate("result-answer.schema.json", answer)
            self._finish(
                run_id,
                request_id,
                state="completed",
                answer=answer,
                require_current_revision=True,
            )
        except ServiceStoreError as error:
            if error.code == "STALE_REVISION":
                self._finish(
                    run_id,
                    request_id,
                    state="cancelled",
                    error_code="STALE_REVISION",
                )
            else:
                self._finish(
                    run_id,
                    request_id,
                    state="failed",
                    error_code=error.code,
                )
        except AIServiceError as error:
            self._finish(
                run_id,
                request_id,
                state="failed",
                error_code=error.code,
                retryable=error.retryable,
            )
        except (ContractError, IntegrityError, KeyError, TypeError, ValueError):
            self._finish(
                run_id,
                request_id,
                state="failed",
                error_code="VALIDATION_FAILURE",
            )
        except Exception:
            self._finish(
                run_id,
                request_id,
                state="failed",
                error_code="ENGINE_FAILURE",
            )

    @staticmethod
    def _scope_required(
        result: ApplicationResult,
        run_id: str,
        revision: int,
    ) -> bool:
        return (
            result.command == "prepare-result-question"
            and result.ok
            and result.code == 2
            and result.run_id == run_id
            and result.revision == revision
            and result.state == "finalized"
            and result.data.get("error_code") == "SCOPE_REQUIRED"
        )

    @staticmethod
    def _scope_suggestions(
        result: ApplicationResult,
    ) -> tuple[ScopeSuggestion, ...]:
        value = result.data.get("suggestions")
        if not isinstance(value, list) or not value:
            raise IntegrityError("scope-required result has no suggestions")
        try:
            return tuple(ScopeSuggestion.model_validate(item) for item in value)
        except ValidationError as error:
            raise IntegrityError("scope suggestions are invalid") from error

    @staticmethod
    def _prepared_job(
        result: ApplicationResult,
        *,
        run_id: str,
        revision: int,
    ) -> dict[str, Any]:
        if (
            result.command != "prepare-result-question"
            or not result.ok
            or result.code != 0
            or result.run_id != run_id
            or result.revision != revision
            or result.state != "finalized"
        ):
            raise IntegrityError("result question preparation response is invalid")
        job = result.data.get("job")
        if not isinstance(job, Mapping):
            raise IntegrityError("result question preparation returned no Job")
        return dict(job)

    @staticmethod
    def _validated_answer(
        result: ApplicationResult,
        *,
        run_id: str,
        revision: int,
    ) -> dict[str, Any]:
        if (
            result.command != "validate-result-answer"
            or not result.ok
            or result.code != 0
            or result.run_id != run_id
            or result.revision != revision
            or result.state != "finalized"
        ):
            raise IntegrityError("result answer validation response is invalid")
        answer = result.data.get("answer")
        if not isinstance(answer, Mapping):
            raise IntegrityError("result answer validation returned no answer")
        return dict(answer)


__all__ = [
    "QuestionDraftGateway",
    "QuestionRequest",
    "QuestionService",
    "QuestionSnapshot",
    "ScopeSuggestion",
]
