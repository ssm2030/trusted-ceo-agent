from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from trusted_ceo_agent.application.models import (
    ApplicationResult,
    AttachSourcesRequest,
    CreateRunRequest,
    ExportWebReportRequest,
    MutationRequest,
    RevisionRequest,
    RunRequest,
    SourceUpload,
)
from trusted_ceo_agent.application.mutations import validate_reasoning_draft
from trusted_ceo_agent.application.run_application import TrustedCeoApplication
from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.errors import ContractError, IntegrityError
from trusted_ceo_agent.mission import (
    CONTEXT_EDITABLE_FIELDS,
    materialize_confirmed_mission,
)
from trusted_ceo_agent.service.contracts import (
    HitlCard,
    HitlDecisionRequest,
    HitlSection,
    MutationBase,
    RunSnapshot,
    ServiceErrorBody,
    UploadedFileSummary,
)
from trusted_ceo_agent.service.file_policy import IncomingUpload, UploadPolicy
from trusted_ceo_agent.service.openai_gateway import AIServiceError
from trusted_ceo_agent.service.run_store import (
    RunStore,
    ServiceManifest,
    ServiceStoreError,
)
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from trusted_ceo_agent.workflow.overlays import apply_overlay
from trusted_ceo_agent.web_report.contracts import load_bundle_bytes
from trusted_ceo_agent.web_report.eligibility import decide_viewer_eligibility


STATE_HANDLERS = {
    "context_confirmation_required": "_await_context",
    "context_ready": "_scan",
    "schema_mapping_job_ready": "_run_schema_mapping",
    "mapping_proposal_ready": "_await_data",
    "data_confirmation_required": "_await_data",
    "evidence_ready": "_prepare_lens",
    "lens_jobs_ready": "_run_lens",
    "lens_ready": "_run_integrated",
    "integrated_draft": "_await_diagnostic",
    "diagnostic_approval_required": "_await_diagnostic",
    "finalization_jobs_ready": "_run_writer",
    "writer_ready": "_await_final",
    "final_approval_required": "_await_final",
    "delivery_approved": "_finalize_and_export",
    "finalized": "_export_finalized",
}

_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_DATA_FIELDS = (
    "observation_role",
    "unit_code",
    "scale",
    "time_role",
    "dimension_code",
)
_ACTIVE_JOB_LOCK = threading.Lock()


def _registry_upload_usage(
    registry: list[Any],
) -> tuple[dict[str, str], dict[str, int]]:
    source_id_by_path: dict[str, str] = {}
    size_by_sha256: dict[str, int] = {}
    for item in registry:
        if not isinstance(item, Mapping):
            raise IntegrityError('source registry entry is invalid')
        source_id = item.get('source_id')
        digest = item.get('sha256')
        size = item.get('size_bytes')
        display_name = item.get('display_name')
        aliases = item.get('aliases', [])
        if (
            not isinstance(source_id, str)
            or not isinstance(digest, str)
            or re.fullmatch(r'[0-9a-f]{64}', digest) is None
            or isinstance(size, bool)
            or not isinstance(size, (int, Decimal))
            or size != int(size)
            or size < 0
            or not isinstance(display_name, str)
            or not isinstance(aliases, list)
        ):
            raise IntegrityError('source registry upload metadata is invalid')
        normalized_size = int(size)
        known_size = size_by_sha256.get(digest)
        if known_size is not None and known_size != normalized_size:
            raise IntegrityError('source registry digest size is ambiguous')
        size_by_sha256[digest] = normalized_size
        for logical_path in [display_name, *aliases]:
            if not isinstance(logical_path, str):
                raise IntegrityError('source registry logical path is invalid')
            claimed = source_id_by_path.get(logical_path)
            if claimed is not None and claimed != source_id:
                raise IntegrityError('source registry logical path is ambiguous')
            source_id_by_path[logical_path] = source_id
    return source_id_by_path, size_by_sha256


class ReasoningGateway(Protocol):
    def execute(
        self,
        job: Mapping[str, Any],
        *,
        validator: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        pass


def _pointer_segment(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _json_value(payload: bytes | None, *, label: str, default: Any) -> Any:
    if payload is None:
        return default
    value = strict_loads(payload)
    if not isinstance(value, (dict, list)):
        raise IntegrityError(f"{label} is invalid")
    return value


class AnalysisOrchestrator:
    def __init__(
        self,
        application: TrustedCeoApplication,
        run_store: RunStore,
        gateway: ReasoningGateway,
        *,
        clock: Callable[[], datetime] | None = None,
        report_root: Path | None = None,
    ) -> None:
        if application.artifact_root.resolve() != run_store.runs_root.resolve():
            raise ValueError("application and service store must share the runs root")
        self.application = application
        self.run_store = run_store
        self.gateway = gateway
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.upload_policy = UploadPolicy(run_store.service_root)
        self.report_root = (
            report_root.resolve()
            if report_root is not None
            else (Path.cwd() / ".trusted-ceo-agent-reports").resolve()
        )

    def create_run(
        self,
        request: CreateRunRequest,
        *,
        idempotency_key: str | None = None,
        request_body: Mapping[str, Any] | None = None,
    ) -> RunSnapshot:
        receipt_body: dict[str, Any] | None = None
        if idempotency_key is not None:
            if request_body is None:
                raise ValueError("idempotent creation requires a request body")
            receipt_body = dict(request_body)
            run_id = request.run_id or (
                "run_20000101T000000Z_"
                + hashlib.sha256(idempotency_key.encode("ascii")).hexdigest()[:16]
            )
            request = CreateRunRequest(
                mission=request.mission,
                inputs=request.inputs,
                run_owner_actor_id=request.run_owner_actor_id,
                run_id=run_id,
            )
            if self.run_store.run_root(run_id).is_dir():
                replay = self.run_store.read_idempotency_receipt(
                    run_id,
                    idempotency_key=idempotency_key,
                    request_body=receipt_body,
                )
                if replay is not None:
                    return RunSnapshot.model_validate(replay.response)
        result = self.application.create_run(request)
        if result.run_id is None or result.revision is None:
            raise IntegrityError("created run did not return an identity")
        manifest = self.run_store.create_manifest(
            result.run_id,
            engine_revision=result.revision,
        )
        self.run_store.save_manifest(
            manifest.model_copy(update={
                "status": "running",
                "stage": result.state,
            }),
            expected_revision=result.revision,
        )
        snapshot = self.snapshot(result.run_id)
        if idempotency_key is not None and receipt_body is not None:
            self.run_store.store_idempotency_receipt(
                result.run_id,
                idempotency_key=idempotency_key,
                request_body=receipt_body,
                status_code=200,
                response=snapshot.model_dump(mode="json"),
            )
        return snapshot

    def attach_files(
        self,
        run_id: str,
        request: MutationBase,
        uploads: tuple[IncomingUpload, ...],
    ) -> RunSnapshot:
        expected_files = self._files(run_id, request.expected_revision)
        registry = _json_value(
            expected_files.get("sources/registry.json"),
            label="source registry",
            default=[],
        )
        if not isinstance(registry, list):
            raise IntegrityError("source registry is invalid")
        source_id_by_path, size_by_sha256 = _registry_upload_usage(registry)
        staged = self.upload_policy.stage_batch(
            uploads,
            existing_file_count=0,
            existing_total_bytes=0,
        )
        try:
            resulting_paths = {
                *source_id_by_path,
                *(item.logical_path for item in staged),
            }
            if len(resulting_paths) > self.upload_policy.limits.max_files:
                raise ContractError('upload file count exceeds the run limit')
            resulting_sizes = dict(size_by_sha256)
            for item in staged:
                known_size = resulting_sizes.get(item.sha256)
                if known_size is not None and known_size != item.size:
                    raise IntegrityError('upload digest size is ambiguous')
                resulting_sizes[item.sha256] = item.size
            if sum(resulting_sizes.values()) > self.upload_policy.limits.max_total_bytes:
                raise ContractError('upload batch exceeds 250 MiB')
            receipt_body = {
                **request.model_dump(mode="json"),
                "files": [
                    {
                        "filename": item.filename,
                        'logical_path': item.logical_path,
                        "content_type": item.content_type,
                        "size": item.size,
                        "sha256": item.sha256,
                    }
                    for item in staged
                ],
            }
            replay = self.run_store.read_idempotency_receipt(
                run_id,
                idempotency_key=request.idempotency_key,
                request_body=receipt_body,
            )
            if replay is not None:
                return RunSnapshot.model_validate(replay.response)
            manifest = self.run_store.assert_revision(
                run_id,
                expected_revision=request.expected_revision,
            )
            result = self.application.attach_sources(AttachSourcesRequest(
                run_id=run_id,
                expected_revision=request.expected_revision,
                sources=tuple(
                    SourceUpload(
                        path=item.private_path,
                        opaque_token=item.opaque_token,
                        expected_sha256=item.sha256,
                        expected_size=item.size,
                        logical_path=item.logical_path,
                    )
                    for item in staged
                ),
            ))
            manifest = self._checkpoint(manifest, result)
            snapshot = self._snapshot(manifest, result)
            self.run_store.store_idempotency_receipt(
                run_id,
                idempotency_key=request.idempotency_key,
                request_body=receipt_body,
                status_code=200,
                response=snapshot.model_dump(mode="json"),
            )
            return snapshot
        finally:
            for item in staged:
                if item.private_path.exists():
                    self.upload_policy.discard(item)

    def snapshot(self, run_id: str) -> RunSnapshot:
        manifest = self._manifest(run_id)
        result = self.application.status(RunRequest(run_id=run_id))
        if result.revision != manifest.engine_revision:
            raise ServiceStoreError(
                "STALE_REVISION",
                "service manifest does not match the workflow revision",
            )
        return self._snapshot(manifest, result)

    def report(self, run_id: str) -> dict[str, Any]:
        manifest = self.run_store.read_manifest(run_id)
        if manifest.status != "finalized" or manifest.bundle_hash is None:
            raise ContractError("run does not have a finalized report")
        path = self._report_path(run_id, manifest.engine_revision)
        if not path.is_file():
            raise IntegrityError("finalized report bundle is missing")
        payload = path.read_bytes()
        bundle = load_bundle_bytes(payload)
        run = bundle.get("run", {})
        if (
            not isinstance(run, Mapping)
            or run.get("run_id") != run_id
            or run.get("revision") != manifest.engine_revision
            or bundle.get("bundle_hash") != manifest.bundle_hash
        ):
            raise IntegrityError("report bundle does not match the service manifest")
        artifact_store = ArtifactStore(self.application.artifact_root)
        artifact_store.open_run(run_id)
        eligibility = decide_viewer_eligibility(
            artifact_store,
            expected_run_id=run_id,
            expected_revision=manifest.engine_revision,
            bundle_payload=payload,
        )
        return {
            "bundle": bundle,
            "eligibility": eligibility,
        }

    def continue_run(self, run_id: str, request: MutationBase) -> RunSnapshot:
        self._manifest(run_id)
        body = request.model_dump(mode="json")
        replay = self.run_store.read_idempotency_receipt(
            run_id,
            idempotency_key=request.idempotency_key,
            request_body=body,
        )
        if replay is not None:
            return RunSnapshot.model_validate(replay.response)
        manifest = self.run_store.assert_revision(
            run_id,
            expected_revision=request.expected_revision,
        )
        if manifest.status == "retryable_failure":
            raise ServiceStoreError(
                manifest.error_code or "AI_TRANSIENT_FAILURE",
                "retry the failed step before continuing",
            )
        if not _ACTIVE_JOB_LOCK.acquire(blocking=False):
            raise ServiceStoreError(
                "AI_TRANSIENT_FAILURE",
                "another analysis step is active",
            )
        try:
            state = self.application.status(RunRequest(run_id=run_id))
            handler_name = STATE_HANDLERS.get(str(state.state))
            if handler_name is None:
                result_snapshot = self._snapshot(manifest, state)
            else:
                result_snapshot = getattr(self, handler_name)(manifest, state)
        except AIServiceError as error:
            current_manifest = self.run_store.read_manifest(run_id)
            failed = current_manifest.model_copy(update={
                "status": "retryable_failure",
                "error_code": error.code,
                "attempt": min(100, current_manifest.attempt + 1),
                "pending_approval_request_id": None,
                "pending_approval_nonce": None,
            })
            self.run_store.save_manifest(
                failed,
                expected_revision=current_manifest.engine_revision,
            )
            raise
        finally:
            _ACTIVE_JOB_LOCK.release()
        self.run_store.store_idempotency_receipt(
            run_id,
            idempotency_key=request.idempotency_key,
            request_body=body,
            status_code=200,
            response=result_snapshot.model_dump(mode="json"),
        )
        return result_snapshot

    def control_run(
        self,
        run_id: str,
        action: str,
        request: MutationBase,
    ) -> RunSnapshot:
        if action not in {"retry", "resume", "stop", "cancel"}:
            raise ValueError("unsupported run action")
        body = {**request.model_dump(mode="json"), "action": action}
        replay = self.run_store.read_idempotency_receipt(
            run_id,
            idempotency_key=request.idempotency_key,
            request_body=body,
        )
        if replay is not None:
            return RunSnapshot.model_validate(replay.response)
        manifest = self.run_store.assert_revision(
            run_id,
            expected_revision=request.expected_revision,
        )
        current = self.application.status(RunRequest(run_id=run_id))
        if action == "retry":
            if manifest.status != "retryable_failure":
                raise ContractError("run does not have a retryable failure")
            manifest = self.run_store.save_manifest(
                manifest.model_copy(update={
                    "status": "running",
                    "error_code": None,
                }),
                expected_revision=manifest.engine_revision,
            )
            snapshot = self._snapshot(manifest, current)
        elif action == "stop":
            manifest = self.run_store.save_manifest(
                manifest.model_copy(update={
                    "status": "stopped",
                    "stage": current.state,
                    "pending_approval_request_id": None,
                    "pending_approval_nonce": None,
                }),
                expected_revision=manifest.engine_revision,
            )
            snapshot = self._snapshot(manifest, current)
        elif action == "resume" and manifest.status == "stopped":
            manifest = self.run_store.save_manifest(
                manifest.model_copy(update={
                    "status": "running",
                    "pending_approval_request_id": None,
                    "pending_approval_nonce": None,
                }),
                expected_revision=manifest.engine_revision,
            )
            snapshot = self._snapshot(manifest, current)
        else:
            result = self._mutate(
                run_id,
                manifest.engine_revision,
                action,
                {},
            )
            status = "cancelled" if action == "cancel" else "running"
            manifest = self._checkpoint(manifest, result, status=status)
            snapshot = self._snapshot(manifest, result)
        self.run_store.store_idempotency_receipt(
            run_id,
            idempotency_key=request.idempotency_key,
            request_body=body,
            status_code=200,
            response=snapshot.model_dump(mode="json"),
        )
        return snapshot

    def delete_run(
        self,
        run_id: str,
        request: MutationBase,
        *,
        confirmed: bool,
    ) -> None:
        self.run_store.delete_run(
            run_id,
            expected_revision=request.expected_revision,
            confirmed=confirmed,
            idempotency_key=request.idempotency_key,
        )

    def submit_hitl(
        self,
        run_id: str,
        request: HitlDecisionRequest,
        *,
        browser_session_fingerprint: str,
    ) -> RunSnapshot:
        body = request.model_dump(mode="json")
        replay = self.run_store.read_idempotency_receipt(
            run_id,
            idempotency_key=request.idempotency_key,
            request_body=body,
        )
        if replay is not None:
            return RunSnapshot.model_validate(replay.response)
        if _FINGERPRINT.fullmatch(browser_session_fingerprint) is None:
            raise ValueError("browser session fingerprint must be lowercase SHA-256")
        manifest = self.run_store.assert_revision(
            run_id,
            expected_revision=request.expected_revision,
        )
        if (
            manifest.status != "awaiting_human"
            or manifest.pending_approval_request_id is None
            or manifest.pending_approval_nonce is None
        ):
            raise ContractError("no web approval is pending")
        current = self.application.status(RunRequest(run_id=run_id))
        card = self._hitl_card(manifest, current)
        if request.decision not in card.allowed_decisions:
            raise ValueError(f"{request.decision} is not allowed for this approval")
        gate = self._pending_gate(manifest)
        response_hash = hashlib.sha256(canonical_bytes(body)).hexdigest()
        rationale = request.rationale or "웹 승인"

        if request.decision == "approve_with_edits":
            operations = self._edited_operations(
                run_id,
                current.revision or 0,
                gate,
                request.edits,
            )
            replacement = self._mutate(
                run_id,
                manifest.engine_revision,
                "approval-request",
                {
                    "gate": gate,
                    "overlay_document": {"patch_operations": operations},
                },
            )
            manifest = self._checkpoint(
                manifest,
                replacement,
                status="awaiting_human",
                stage=f"{gate}_hitl",
                pending_request_id=str(replacement.data["approval_request_id"]),
                pending_nonce=str(replacement.data["nonce"]),
            )

        actor_role = "business_owner" if gate in {"context", "data"} else "ceo"
        common = {
            "request_id": manifest.pending_approval_request_id,
            "actor_id": "local-browser-user",
            "actor_role": actor_role,
            "nonce": manifest.pending_approval_nonce,
            "rationale": rationale,
            "browser_session_fingerprint": browser_session_fingerprint,
            "response_hash": response_hash,
        }
        if request.decision in {"approve", "approve_with_edits"}:
            result = self._mutate(
                run_id,
                manifest.engine_revision,
                "approve-web",
                common,
            )
            status = "running"
        else:
            result = self._mutate(
                run_id,
                manifest.engine_revision,
                "decide-web",
                {
                    **common,
                    "decision": (
                        "request_changes"
                        if request.decision == "reanalyze"
                        else "reject"
                    ),
                    "change_scope": (
                        {"data": "data", "diagnostic": "reasoning", "final": "wording"}.get(gate)
                        if request.decision == "reanalyze"
                        else None
                    ),
                },
            )
            status = "running" if request.decision == "reanalyze" else "stopped"
        manifest = self._checkpoint(
            manifest,
            result,
            status=status,
            stage=result.state,
        )
        result_snapshot = self._snapshot(manifest, result)
        self.run_store.store_idempotency_receipt(
            run_id,
            idempotency_key=request.idempotency_key,
            request_body=body,
            status_code=200,
            response=result_snapshot.model_dump(mode="json"),
        )
        return result_snapshot

    def _manifest(self, run_id: str) -> ServiceManifest:
        try:
            return self.run_store.read_manifest(run_id)
        except FileNotFoundError:
            status = self.application.status(RunRequest(run_id=run_id))
            if status.revision is None:
                raise IntegrityError("workflow revision is missing")
            return self.run_store.create_manifest(
                run_id,
                engine_revision=status.revision,
            )

    def _mutate(
        self,
        run_id: str,
        revision: int,
        command: str,
        parameters: Mapping[str, Any],
    ) -> ApplicationResult:
        return self.application.mutate(MutationRequest(
            artifact_root=self.application.artifact_root,
            run_id=run_id,
            expected_revision=revision,
            command=command,
            parameters=parameters,
        ))

    def _checkpoint(
        self,
        manifest: ServiceManifest,
        result: ApplicationResult,
        *,
        status: str = "running",
        stage: str | None = None,
        job_ids: tuple[str, ...] | None = None,
        pending_request_id: str | None = None,
        pending_nonce: str | None = None,
    ) -> ServiceManifest:
        if result.revision is None:
            raise IntegrityError("workflow mutation did not return a revision")
        update: dict[str, Any] = {
            "engine_revision": result.revision,
            "last_checkpoint_revision": result.revision,
            "status": status,
            "stage": stage or result.state,
            "error_code": None,
            "pending_approval_request_id": pending_request_id,
            "pending_approval_nonce": pending_nonce,
        }
        if job_ids is not None:
            update["job_ids"] = job_ids
        return self.run_store.save_manifest(
            manifest.model_copy(update=update),
            expected_revision=manifest.engine_revision,
        )

    def _await_context(
        self,
        manifest: ServiceManifest,
        state: ApplicationResult,
    ) -> RunSnapshot:
        if manifest.status == "awaiting_human" and not self._pending_expired(manifest):
            return self._snapshot(manifest, state)
        if manifest.status == "awaiting_human":
            return self._renew_hitl(manifest, gate="context")
        return self._request_hitl(manifest, gate="context", operations=[])

    def _scan(
        self,
        manifest: ServiceManifest,
        _state: ApplicationResult,
    ) -> RunSnapshot:
        result = self._mutate(manifest.run_id, manifest.engine_revision, "scan", {})
        manifest = self._checkpoint(manifest, result)
        return self._snapshot(manifest, result)

    def _execute_reasoning_job(
        self,
        job: Mapping[str, Any],
        files: Mapping[str, bytes],
    ) -> dict[str, Any]:
        return self.gateway.execute(
            job,
            validator=lambda draft: validate_reasoning_draft(job, draft, files),
        )

    def _run_schema_mapping(
        self,
        manifest: ServiceManifest,
        state: ApplicationResult,
    ) -> RunSnapshot:
        files = self._files(manifest.run_id, manifest.engine_revision)
        jobs = self._jobs(files, "schema_mapping")
        if not jobs:
            result = self._mutate(
                manifest.run_id,
                manifest.engine_revision,
                "prepare-jobs",
                {"stage": "schema_mapping"},
            )
            ids = tuple(str(value) for value in result.data.get("job_ids", []))
            manifest = self._checkpoint(manifest, result, job_ids=ids)
            return self._snapshot(manifest, result)
        pending = [
            job
            for job in jobs
            if not self._accepted(files, str(job["job_id"]))
        ]
        if pending:
            proposal = strict_loads(
                files.get("intake/canonical-mapping-proposal.json", b"{}")
            )
            if not isinstance(proposal, Mapping):
                raise IntegrityError("canonical mapping proposal is invalid")
            result = state
            for job in pending:
                result = self._mutate(
                    manifest.run_id,
                    manifest.engine_revision,
                    "ingest-result",
                    {
                        "job_id": str(job["job_id"]),
                        "draft_document": proposal,
                        "draft_source": "deterministic_canonical",
                    },
                )
                manifest = self._checkpoint(manifest, result)
            return self._snapshot(manifest, result)
        result = self._mutate(
            manifest.run_id,
            manifest.engine_revision,
            "reduce-stage",
            {"stage": "schema_mapping"},
        )
        manifest = self._checkpoint(manifest, result)
        return self._snapshot(manifest, result)

    def _await_data(
        self,
        manifest: ServiceManifest,
        state: ApplicationResult,
    ) -> RunSnapshot:
        if manifest.status == "awaiting_human" and not self._pending_expired(manifest):
            return self._snapshot(manifest, state)
        if manifest.status == "awaiting_human":
            return self._renew_hitl(manifest, gate="data")
        operations = self._default_data_operations(
            manifest.run_id,
            manifest.engine_revision,
        )
        return self._request_hitl(manifest, gate="data", operations=operations)

    def _prepare_lens(
        self,
        manifest: ServiceManifest,
        _state: ApplicationResult,
    ) -> RunSnapshot:
        result = self._mutate(
            manifest.run_id,
            manifest.engine_revision,
            "prepare-jobs",
            {"stage": "lens"},
        )
        ids = tuple(str(value) for value in result.data.get("job_ids", []))
        manifest = self._checkpoint(manifest, result, job_ids=ids)
        return self._snapshot(manifest, result)

    def _run_lens(
        self,
        manifest: ServiceManifest,
        state: ApplicationResult,
    ) -> RunSnapshot:
        return self._run_model_stage(manifest, state, stage="lens")

    def _run_integrated(
        self,
        manifest: ServiceManifest,
        state: ApplicationResult,
    ) -> RunSnapshot:
        return self._run_model_stage(manifest, state, stage="integrated")

    def _run_model_stage(
        self,
        manifest: ServiceManifest,
        state: ApplicationResult,
        *,
        stage: str,
    ) -> RunSnapshot:
        files = self._files(manifest.run_id, manifest.engine_revision)
        jobs = self._jobs(files, stage)
        if not jobs:
            result = self._mutate(
                manifest.run_id,
                manifest.engine_revision,
                "prepare-jobs",
                {"stage": stage},
            )
            ids = tuple(str(value) for value in result.data.get("job_ids", []))
            manifest = self._checkpoint(manifest, result, job_ids=ids)
            return self._snapshot(manifest, result)
        pending = [
            job
            for job in jobs
            if not self._accepted(files, str(job["job_id"]))
        ]
        if pending:
            result = state
            for job in pending:
                result = self._mutate(
                    manifest.run_id,
                    manifest.engine_revision,
                    "ingest-result",
                    {
                        "job_id": str(job["job_id"]),
                        "draft_document": self._execute_reasoning_job(job, files),
                    },
                )
                manifest = self._checkpoint(manifest, result)
            return self._snapshot(manifest, result)
        result = self._mutate(
            manifest.run_id,
            manifest.engine_revision,
            "reduce-stage",
            {"stage": stage},
        )
        manifest = self._checkpoint(manifest, result)
        return self._snapshot(manifest, result)

    def _await_diagnostic(
        self,
        manifest: ServiceManifest,
        state: ApplicationResult,
    ) -> RunSnapshot:
        if manifest.status == "awaiting_human" and not self._pending_expired(manifest):
            return self._snapshot(manifest, state)
        if manifest.status == "awaiting_human":
            return self._renew_hitl(manifest, gate="diagnostic")
        return self._request_hitl(
            manifest,
            gate="diagnostic",
            operations=self._default_diagnostic_operations(
                manifest.run_id,
                manifest.engine_revision,
            ),
        )

    def _run_writer(
        self,
        manifest: ServiceManifest,
        state: ApplicationResult,
    ) -> RunSnapshot:
        files = self._files(manifest.run_id, manifest.engine_revision)
        if "final/structured-output.json" not in files:
            result = self._mutate(
                manifest.run_id,
                manifest.engine_revision,
                "prepare-finalization",
                {},
            )
            manifest = self._checkpoint(manifest, result)
            return self._snapshot(manifest, result)
        return self._run_model_stage(manifest, state, stage="writer")

    def _await_final(
        self,
        manifest: ServiceManifest,
        state: ApplicationResult,
    ) -> RunSnapshot:
        if manifest.status == "awaiting_human" and not self._pending_expired(manifest):
            return self._snapshot(manifest, state)
        if manifest.status == "awaiting_human":
            return self._renew_hitl(manifest, gate="final")
        return self._request_hitl(
            manifest,
            gate="final",
            operations=self._default_final_operations(),
        )

    def _finalize_and_export(
        self,
        manifest: ServiceManifest,
        _state: ApplicationResult,
    ) -> RunSnapshot:
        result = self._mutate(
            manifest.run_id,
            manifest.engine_revision,
            "finalize",
            {},
        )
        manifest = self._checkpoint(manifest, result, status="running")
        return self._export_finalized(manifest, result)

    def _report_path(self, run_id: str, revision: int) -> Path:
        return self.report_root / f"{run_id}-r{revision:04d}.json"

    def _export_finalized(
        self,
        manifest: ServiceManifest,
        state: ApplicationResult,
    ) -> RunSnapshot:
        if state.state != "finalized" or state.revision is None:
            raise IntegrityError("report export requires a finalized workflow")
        if manifest.status == "finalized":
            return self._snapshot(manifest, state)
        self.application.validate(RevisionRequest(
            run_id=manifest.run_id,
            revision=state.revision,
        ))
        files = self._files(manifest.run_id, state.revision)
        result_bytes = files.get("final/result.json")
        if result_bytes is None:
            raise IntegrityError("final result is missing")
        input_manifest = {
            "schema_version": "1.0.0",
            "run_id": manifest.run_id,
            "revision": state.revision,
            "files": [{
                "path": "final/result.json",
                "sha256": hashlib.sha256(result_bytes).hexdigest(),
            }],
        }
        self.report_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        output = self._report_path(manifest.run_id, state.revision)
        if not output.exists():
            self.application.export_web_report(ExportWebReportRequest(
                run_id=manifest.run_id,
                revision=state.revision,
                output=output,
                input_manifest=input_manifest,
            ))
        bundle = load_bundle_bytes(output.read_bytes())
        run = bundle.get("run", {})
        if (
            not isinstance(run, Mapping)
            or run.get("run_id") != manifest.run_id
            or run.get("revision") != state.revision
        ):
            raise IntegrityError("exported report identity is invalid")
        bundle_hash = bundle.get("bundle_hash")
        if not isinstance(bundle_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", bundle_hash):
            raise IntegrityError("exported report hash is invalid")
        manifest = self.run_store.save_manifest(
            manifest.model_copy(update={
                "status": "finalized",
                "stage": "finalized",
                "result_ref": f"result_{bundle_hash[:24]}",
                "bundle_hash": bundle_hash,
            }),
            expected_revision=manifest.engine_revision,
        )
        return self._snapshot(manifest, state)

    def _request_hitl(
        self,
        manifest: ServiceManifest,
        *,
        gate: str,
        operations: list[dict[str, Any]],
    ) -> RunSnapshot:
        result = self._mutate(
            manifest.run_id,
            manifest.engine_revision,
            "approval-request",
            {
                "gate": gate,
                "overlay_document": {"patch_operations": operations},
            },
        )
        manifest = self._checkpoint(
            manifest,
            result,
            status="awaiting_human",
            stage=f"{gate}_hitl",
            pending_request_id=str(result.data["approval_request_id"]),
            pending_nonce=str(result.data["nonce"]),
        )
        return self._snapshot(manifest, result)

    def _pending_request(self, manifest: ServiceManifest) -> dict[str, Any]:
        request_id = manifest.pending_approval_request_id
        if request_id is None:
            raise IntegrityError("pending approval request ID is missing")
        files = self._files(manifest.run_id, manifest.engine_revision)
        payload = files.get(f"approvals/requests/{request_id}.json")
        if payload is None:
            raise IntegrityError("pending approval request record is missing")
        value = strict_loads(payload)
        if not isinstance(value, dict) or value.get("approval_request_id") != request_id:
            raise IntegrityError("pending approval request record is invalid")
        return value

    def _pending_expired(self, manifest: ServiceManifest) -> bool:
        request = self._pending_request(manifest)
        try:
            expires_at = datetime.fromisoformat(
                str(request["expires_at"]).replace("Z", "+00:00")
            ).astimezone(timezone.utc)
            now = self.clock()
            if now.tzinfo is None:
                raise ValueError("orchestrator clock must be timezone-aware")
        except (KeyError, TypeError, ValueError) as error:
            raise IntegrityError("approval expiry is invalid") from error
        return now.astimezone(timezone.utc) >= expires_at

    def _renew_hitl(self, manifest: ServiceManifest, *, gate: str) -> RunSnapshot:
        request = self._pending_request(manifest)
        if request.get("gate") != gate:
            raise IntegrityError("pending approval gate does not match workflow")
        operations = request.get("patch_operations", [])
        if not isinstance(operations, list):
            raise IntegrityError("pending approval operations are invalid")
        return self._request_hitl(manifest, gate=gate, operations=operations)

    def _files(self, run_id: str, revision: int) -> dict[str, bytes]:
        store = ArtifactStore(self.application.artifact_root)
        store.open_run(run_id)
        snapshot = store.verify_revision(revision)
        manifest = json.loads((snapshot / "snapshot-manifest.json").read_text("utf-8"))
        return {
            item["path"]: (snapshot / item["path"]).read_bytes()
            for item in manifest["files"]
        }

    @staticmethod
    def _jobs(files: Mapping[str, bytes], stage: str) -> list[dict[str, Any]]:
        jobs = []
        for path, payload in files.items():
            if path.startswith("tasks/") and path.endswith("/job.json"):
                value = strict_loads(payload)
                if isinstance(value, dict) and value.get("stage") == stage:
                    jobs.append(value)
        return sorted(jobs, key=lambda value: str(value["job_id"]))

    @staticmethod
    def _accepted(files: Mapping[str, bytes], job_id: str) -> bool:
        payload = files.get(f"tasks/{job_id}/validation.json")
        if payload is None:
            return False
        value = strict_loads(payload)
        return isinstance(value, Mapping) and value.get("valid") is True

    def _default_data_operations(
        self,
        run_id: str,
        revision: int,
    ) -> list[dict[str, Any]]:
        files = self._files(run_id, revision)
        sources = _json_value(
            files.get("sources/registry.json"),
            label="source registry",
            default=[],
        )
        proposal = _json_value(
            files.get("intake/canonical-mapping-proposal.json"),
            label="mapping proposal",
            default={},
        )
        operations: list[dict[str, Any]] = []
        for source in sources:
            source_id = str(source["source_id"])
            operations.append({
                "op": "add",
                "path": f"/mapping/sources/{_pointer_segment(source_id)}/included",
                "value": True,
            })
        for mapping in proposal.get("mappings", []):
            candidates = mapping.get("candidate_mappings", [])
            if not candidates:
                raise ContractError("mapping proposal has no candidate")
            reference = str(mapping["mapping_question_ref"])
            candidate = candidates[0]
            for field in _DATA_FIELDS:
                operations.append({
                    "op": "add",
                    "path": f"/mapping/columns/{_pointer_segment(reference)}/{field}",
                    "value": candidate[field],
                })
        apply_overlay({}, "data", operations)
        return operations

    def _default_diagnostic_operations(
        self,
        run_id: str,
        revision: int,
    ) -> list[dict[str, Any]]:
        files = self._files(run_id, revision)
        integrated = _json_value(
            files.get("reasoning/integrated-assessment.json"),
            label="integrated assessment",
            default={},
        )
        payload = integrated.get("payload", integrated)
        issues = payload.get("integrated_issues", [])
        operations: list[dict[str, Any]] = []
        for issue in issues:
            local_key = str(issue["local_key"])
            issue_payload = issue.get("payload", {})
            operations.extend([
                {
                    "op": "add",
                    "path": f"/issue_dispositions/{_pointer_segment(local_key)}",
                    "value": "accepted",
                },
                {
                    "op": "add",
                    "path": f"/decision_dispositions/{_pointer_segment(local_key)}",
                    "value": (
                        "needed"
                        if issue_payload.get("decision_need_proposal") is not None
                        else "not_needed"
                    ),
                },
                {
                    "op": "add",
                    "path": f"/verification_authorizations/{_pointer_segment(local_key)}",
                    "value": False,
                },
            ])
        operations.extend([
            {
                "op": "add",
                "path": "/deep_dive_scope/component_ids",
                "value": [],
            },
            {
                "op": "add",
                "path": "/deep_dive_scope/issue_ids",
                "value": [],
            },
        ])
        apply_overlay({}, "diagnostic", operations)
        return operations

    @staticmethod
    def _default_final_operations() -> list[dict[str, Any]]:
        operations = [{
            "op": "add",
            "path": "/delivery_scope/package",
            "value": "ceo_brief",
        }]
        apply_overlay({}, "final", operations)
        return operations

    def _edited_operations(
        self,
        run_id: str,
        revision: int,
        gate: str,
        edits: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        if gate == "context":
            unknown = set(edits) - CONTEXT_EDITABLE_FIELDS
            if unknown:
                raise ValueError(f"forbidden context edit fields: {sorted(unknown)}")
            operations = [
                {
                    "op": "add",
                    "path": f"/mission_contract/{field}",
                    "value": edits[field],
                }
                for field in sorted(edits)
            ]
            overlay = apply_overlay({}, "context", operations)
            files = self._files(run_id, revision)
            mission = strict_loads(files["mission/mission-contract.json"])
            materialize_confirmed_mission(
                mission,
                overlay,
                actor_id="local-browser-user",
                actor_role="business_owner",
                confirmed_at="1970-01-01T00:00:00Z",
            )
            return operations
        if gate == "diagnostic":
            unknown = set(edits) - {
                "issue_dispositions",
                "decision_dispositions",
                "verification_authorizations",
                "deep_dive_scope",
            }
            if unknown:
                raise ValueError(f"forbidden diagnostic edit fields: {sorted(unknown)}")
            files = self._files(run_id, revision)
            integrated = _json_value(
                files.get("reasoning/integrated-assessment.json"),
                label="integrated assessment",
                default={},
            )
            payload = integrated.get("payload", integrated)
            issue_ids = {
                str(item["local_key"])
                for item in payload.get("integrated_issues", [])
            }
            defaults = self._default_diagnostic_operations(run_id, revision)
            by_path = {str(item["path"]): item for item in defaults}
            specifications = {
                "issue_dispositions": {"accepted", "rejected", "disputed"},
                "decision_dispositions": {"needed", "not_needed", "disputed"},
            }
            for field, allowed in specifications.items():
                values = edits.get(field, {})
                if not isinstance(values, Mapping):
                    raise ValueError(f"{field} edit must be an object")
                for issue_id, value in values.items():
                    if issue_id not in issue_ids or value not in allowed:
                        raise ValueError(f"invalid {field} edit: {issue_id}")
                    path = f"/{field}/{_pointer_segment(issue_id)}"
                    by_path[path] = {"op": "add", "path": path, "value": value}
            authorizations = edits.get("verification_authorizations", {})
            if not isinstance(authorizations, Mapping):
                raise ValueError("verification_authorizations edit must be an object")
            for issue_id, value in authorizations.items():
                if issue_id not in issue_ids or not isinstance(value, bool):
                    raise ValueError(f"invalid verification authorization: {issue_id}")
                path = f"/verification_authorizations/{_pointer_segment(issue_id)}"
                by_path[path] = {"op": "add", "path": path, "value": value}
            scope = edits.get("deep_dive_scope", {})
            if not isinstance(scope, Mapping) or set(scope) - {"component_ids", "issue_ids"}:
                raise ValueError("deep_dive_scope edit is invalid")
            for field, values in scope.items():
                if (
                    not isinstance(values, list)
                    or any(not isinstance(value, str) or not value for value in values)
                    or len(values) != len(set(values))
                ):
                    raise ValueError(f"deep_dive_scope {field} must be a string set")
                if field == "issue_ids" and not set(values).issubset(issue_ids):
                    raise ValueError("deep_dive_scope contains an unknown issue")
                path = f"/deep_dive_scope/{field}"
                by_path[path] = {"op": "add", "path": path, "value": sorted(values)}
            result = [by_path[path] for path in sorted(by_path)]
            apply_overlay({}, "diagnostic", result)
            return result
        if gate == "final":
            if set(edits) != {"delivery_scope"}:
                raise ValueError("final edits support only delivery_scope")
            scope = edits["delivery_scope"]
            if not isinstance(scope, Mapping) or not scope:
                raise ValueError("delivery_scope edit must be a non-empty object")
            by_path = {
                str(item["path"]): item
                for item in self._default_final_operations()
            }
            for field, value in scope.items():
                if not isinstance(field, str) or not field or not isinstance(value, str) or not value:
                    raise ValueError("delivery_scope values must be non-empty strings")
                path = f"/delivery_scope/{_pointer_segment(field)}"
                by_path[path] = {"op": "add", "path": path, "value": value}
            result = [by_path[path] for path in sorted(by_path)]
            apply_overlay({}, "final", result)
            return result
        if gate != "data":
            raise ValueError(f"edits are not supported for {gate}")
        unknown = set(edits) - {"columns", "sources"}
        if unknown:
            raise ValueError(f"forbidden data edit fields: {sorted(unknown)}")
        columns = edits.get("columns", {})
        sources = edits.get("sources", {})
        if not isinstance(columns, Mapping) or not isinstance(sources, Mapping):
            raise ValueError("data edits require columns and sources objects")
        files = self._files(run_id, revision)
        registry = _json_value(
            files.get("sources/registry.json"),
            label="source registry",
            default=[],
        )
        source_ids = {str(source["source_id"]) for source in registry}
        proposal = _json_value(
            files.get("intake/canonical-mapping-proposal.json"),
            label="mapping proposal",
            default={},
        )
        mappings = {
            str(item["mapping_question_ref"]): item
            for item in proposal.get("mappings", [])
        }
        operations = self._default_data_operations(run_id, revision)
        by_path = {str(item["path"]): item for item in operations}
        for source_id, edit in sources.items():
            if source_id not in source_ids or not isinstance(edit, Mapping):
                raise ValueError(f"unknown data source edit: {source_id}")
            if set(edit) != {"included"} or not isinstance(edit["included"], bool):
                raise ValueError("source edit must contain one boolean included field")
            path = f"/mapping/sources/{_pointer_segment(source_id)}/included"
            by_path[path] = {"op": "add", "path": path, "value": edit["included"]}
        for reference, edit in columns.items():
            if reference not in mappings or not isinstance(edit, Mapping):
                raise ValueError(f"unknown mapping edit: {reference}")
            if set(edit) - set(_DATA_FIELDS):
                raise ValueError(f"mapping edit has forbidden fields: {reference}")
            for field, value in edit.items():
                path = f"/mapping/columns/{_pointer_segment(reference)}/{field}"
                by_path[path] = {"op": "add", "path": path, "value": value}
            selected = {
                field: by_path[
                    f"/mapping/columns/{_pointer_segment(reference)}/{field}"
                ]["value"]
                for field in _DATA_FIELDS
            }
            candidates = mappings[reference].get("candidate_mappings", [])
            if not any(
                all(candidate.get(field) == selected[field] for field in _DATA_FIELDS)
                for candidate in candidates
            ):
                raise ValueError(f"mapping edit is not a verified candidate: {reference}")
        result = [by_path[path] for path in sorted(by_path)]
        apply_overlay({}, "data", result)
        return result

    @staticmethod
    def _pending_gate(manifest: ServiceManifest) -> str:
        if manifest.stage == "context_hitl":
            return "context"
        if manifest.stage == "data_hitl":
            return "data"
        if manifest.stage == "diagnostic_hitl":
            return "diagnostic"
        if manifest.stage == "final_hitl":
            return "final"
        raise ContractError("pending approval gate is unsupported")

    def _hitl_card(
        self,
        manifest: ServiceManifest,
        state: ApplicationResult,
    ) -> HitlCard:
        if manifest.pending_approval_request_id is None or state.revision is None:
            raise IntegrityError("pending approval metadata is incomplete")
        gate = self._pending_gate(manifest)
        files = self._files(manifest.run_id, state.revision)
        mission = _json_value(
            files.get("mission/mission-contract.json"),
            label="mission contract",
            default={},
        )
        sources = _json_value(
            files.get("sources/registry.json"),
            label="source registry",
            default=[],
        )
        source_refs = [str(source["source_id"]) for source in sources]
        source_items = [
            (
                f"{source.get('display_name', '이름 없는 파일')} · "
                f"{source.get('media_type', 'unknown')} · "
                f"{source.get('size_bytes', 0)} bytes"
            )
            for source in sources
        ] or ["첨부된 데이터 파일이 없습니다."]
        sections = [
            HitlSection(
                kind="source_summary",
                title="파일과 테이블 요약",
                items=source_items,
                target_refs=source_refs,
            ),
        ]
        target_refs = list(source_refs)
        if gate == "context":
            mission_ref = str(mission.get("mission_contract_id", "mission_draft"))
            sections.insert(0, HitlSection(
                kind="mission",
                title="목표와 판단 기준 초안",
                items=[
                    f"핵심 질문: {mission.get('business_question', '미정')}",
                    f"판단 맥락: {mission.get('decision_context', '미정')}",
                    (
                        "분석 기간: "
                        + json.dumps(
                            mission.get("analysis_horizon", {}),
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                    ),
                ],
                target_refs=[mission_ref],
            ))
            sections.append(HitlSection(
                kind="risk",
                title="승인 전 확인",
                items=["이 승인이 기록되기 전에는 데이터 분석을 시작하지 않습니다."],
                target_refs=[mission_ref],
            ))
            target_refs.insert(0, mission_ref)
            return HitlCard(
                hitl_kind="context_data",
                request_id=manifest.pending_approval_request_id,
                base_revision=state.revision,
                title="분석 목표와 범위를 확인해 주세요",
                summary="검증된 Mission 초안과 첨부 파일 요약입니다.",
                target_refs=target_refs,
                allowed_decisions=["approve", "approve_with_edits", "stop"],
                editable_fields=sorted(CONTEXT_EDITABLE_FIELDS),
                sections=sections,
            )
        if gate == "diagnostic":
            integrated = _json_value(
                files.get("reasoning/integrated-assessment.json"),
                label="integrated assessment",
                default={},
            )
            payload = integrated.get("payload", integrated)
            issues = payload.get("integrated_issues", [])
            issue_refs = [str(issue["local_key"]) for issue in issues]
            issue_items = [
                (
                    f"{issue['local_key']}: "
                    f"{issue.get('payload', {}).get('problem_family_ref', '검증된 이슈')}"
                )
                for issue in issues
            ] or ["통합 분석에서 승인할 이슈가 없습니다."]
            verification_items = [
                (
                    f"{issue['local_key']}: "
                    + ", ".join(
                        issue.get("payload", {}).get("verification_requirement_refs", [])
                    )
                )
                for issue in issues
                if issue.get("payload", {}).get("verification_requirement_refs")
            ] or ["추가 심층 검증 범위는 기본적으로 비어 있습니다."]
            sections.extend([
                HitlSection(
                    kind="diagnostic",
                    title="문제와 원인 진단",
                    items=issue_items,
                    target_refs=issue_refs,
                ),
                HitlSection(
                    kind="priorities",
                    title="의사결정 우선순위",
                    items=["승인된 이슈를 최종 보고서 작성 대상으로 사용합니다."],
                    target_refs=issue_refs,
                ),
                HitlSection(
                    kind="verification",
                    title="검증 계획",
                    items=verification_items,
                    target_refs=issue_refs,
                ),
            ])
            target_refs.extend(issue_refs)
            editable = [
                token
                for issue_ref in issue_refs
                for token in (
                    f"issue_dispositions.{issue_ref}",
                    f"decision_dispositions.{issue_ref}",
                    f"verification_authorizations.{issue_ref}",
                )
            ] + ["deep_dive_scope.component_ids", "deep_dive_scope.issue_ids"]
            return HitlCard(
                hitl_kind="diagnostic_final",
                request_id=manifest.pending_approval_request_id,
                base_revision=state.revision,
                title="진단 결과와 검증 범위를 확인해 주세요",
                summary="검증된 카드와 통합 validator를 통과한 진단만 표시합니다.",
                target_refs=target_refs,
                allowed_decisions=["approve", "approve_with_edits", "reanalyze", "stop"],
                editable_fields=editable,
                sections=sections,
            )
        if gate == "final":
            writer = _json_value(
                files.get("reasoning/writer-result.json"),
                label="writer result",
                default={},
            )
            payload = writer.get("payload", writer)
            templates = payload.get("claim_templates", [])
            claim_refs = [str(item["claim_id"]) for item in templates]
            claim_items = [
                f"{item['claim_id']}: {item.get('template', '')}"
                for item in templates
            ] or ["승인된 구조화 결과를 결정론적 기본 문구로 전달합니다."]
            sections.extend([
                HitlSection(
                    kind="final_wording",
                    title="최종 문구",
                    items=claim_items,
                    target_refs=claim_refs,
                ),
                HitlSection(
                    kind="verification",
                    title="전달 범위",
                    items=["CEO 브리프 패키지를 최종 전달 대상으로 승인합니다."],
                    target_refs=claim_refs,
                ),
            ])
            target_refs.extend(claim_refs)
            return HitlCard(
                hitl_kind="diagnostic_final",
                request_id=manifest.pending_approval_request_id,
                base_revision=state.revision,
                title="최종 문구와 전달 범위를 확인해 주세요",
                summary="등급과 근거는 수정하지 않고 승인 가능한 문구와 전달 범위만 표시합니다.",
                target_refs=target_refs,
                allowed_decisions=["approve", "approve_with_edits", "reanalyze", "stop"],
                editable_fields=["delivery_scope.package"],
                sections=sections,
            )
        proposal = _json_value(
            files.get("intake/canonical-mapping-proposal.json"),
            label="mapping proposal",
            default={},
        )
        mappings = proposal.get("mappings", [])
        mapping_refs = [str(item["mapping_question_ref"]) for item in mappings]
        mapping_items = [
            (
                f"{item.get('source_field_ref', '필드')} → "
                f"{item.get('candidate_mappings', [{}])[0].get('observation_role', '미정')}"
            )
            for item in mappings
        ] or ["검토할 스키마 매핑이 없습니다."]
        quality = _json_value(
            files.get("evidence/data-quality-register.json"),
            label="data quality register",
            default=[],
        )
        risk_items = [
            str(item.get("message", item.get("reason_code", "데이터 품질 경고")))
            for item in quality
            if isinstance(item, Mapping)
        ] or ["추가로 감지된 데이터 품질 경고가 없습니다."]
        facts = _json_value(
            files.get("evidence/fact-register.json"),
            label="fact register",
            default=[],
        )
        fact_refs = [str(item["fact_id"]) for item in facts]
        fact_items = [
            (
                f"{item.get('fact_code', 'fact')}: "
                f"{item.get('value', {}).get('canonical_value', '확인됨')}"
            )
            for item in facts[:20]
        ] or ["데이터 승인 후 결정론적 Fact를 생성합니다."]
        sections.extend([
            HitlSection(
                kind="mapping",
                title="스키마 매핑 제안",
                items=mapping_items,
                target_refs=mapping_refs,
            ),
            HitlSection(
                kind="risk",
                title="누락 및 품질 경고",
                items=risk_items,
                target_refs=mapping_refs,
            ),
            HitlSection(
                kind="facts",
                title="현재 근거 Fact 요약",
                items=fact_items,
                target_refs=fact_refs,
            ),
        ])
        target_refs.extend(mapping_refs)
        target_refs.extend(fact_refs)
        editable = [
            f"columns.{reference}.{field}"
            for reference in mapping_refs
            for field in _DATA_FIELDS
        ] + [f"sources.{source_id}.included" for source_id in source_refs]
        return HitlCard(
            hitl_kind="context_data",
            request_id=manifest.pending_approval_request_id,
            base_revision=state.revision,
            title="데이터 해석과 매핑을 확인해 주세요",
            summary="검증된 파일 요약과 후보 매핑만 표시합니다.",
            target_refs=target_refs,
            allowed_decisions=["approve", "approve_with_edits", "reanalyze", "stop"],
            editable_fields=editable,
            sections=sections,
        )

    def _uploaded_file_summaries(
        self,
        run_id: str,
        revision: int,
    ) -> list[UploadedFileSummary]:
        files = self._files(run_id, revision)
        registry = _json_value(
            files.get('sources/registry.json'),
            label='source registry',
            default=[],
        )
        if not isinstance(registry, list):
            raise IntegrityError('source registry is invalid')
        _registry_upload_usage(registry)
        summaries: list[UploadedFileSummary] = []
        for item in registry:
            source_id = str(item['source_id'])
            media_type = str(item['media_type'])
            size_bytes = int(item['size_bytes'])
            logical_paths = [item['display_name'], *item.get('aliases', [])]
            for logical_path in logical_paths:
                collection_label = (
                    logical_path.split('/', 1)[0]
                    if '/' in logical_path
                    else '\uac1c\ubcc4 \ud30c\uc77c'
                )
                summaries.append(UploadedFileSummary(
                    source_id=source_id,
                    logical_path=logical_path,
                    display_name=logical_path.rsplit('/', 1)[-1],
                    media_type=media_type,
                    size_bytes=size_bytes,
                    collection_label=collection_label,
                ))
        return sorted(summaries, key=lambda item: item.logical_path)

    def _snapshot(
        self,
        manifest: ServiceManifest,
        result: ApplicationResult,
    ) -> RunSnapshot:
        if result.revision is None or result.state is None:
            raise IntegrityError("workflow status is incomplete")
        human = manifest.status == "awaiting_human"
        retryable = manifest.status == "retryable_failure"
        blocked = result.state == "blocked"
        stopped = manifest.status == "stopped"
        terminal = manifest.status in {"cancelled", "finalized"}
        attach_allowed = (
            manifest.status == 'running'
            and not human
            and result.state in {'context_confirmation_required', 'context_ready'}
        )
        phases = {
            "context_confirmation_required": 1,
            "context_ready": 2,
            "schema_mapping_job_ready": 2,
            "mapping_proposal_ready": 3,
            "data_confirmation_required": 3,
            "evidence_ready": 4,
            "lens_jobs_ready": 4,
            "scope_narrowing_required": 4,
            "blocked": 4,
            "stopped_by_human": 7,
            "stopped": 7,
            "cancelled": 7,
            "finalized": 7,
        }
        progress = {
            "context_confirmation_required": 10,
            "context_ready": 18,
            "schema_mapping_job_ready": 28,
            "mapping_proposal_ready": 38,
            "data_confirmation_required": 42,
            "evidence_ready": 50,
            "lens_jobs_ready": 58,
            "scope_narrowing_required": 52,
            "blocked": 60,
            "stopped_by_human": 100,
            "stopped": 100,
            "cancelled": 100,
            "finalized": 100,
        }
        latest = {
            "blocked": "The analysis is blocked until its prerequisite is resolved.",
            "stopped_by_human": "The analysis was stopped by the user.",
            "context_confirmation_required": "분석 목표 확인을 기다리고 있습니다.",
            "context_ready": "분석 목표가 확인되었습니다.",
            "schema_mapping_job_ready": "데이터 스키마를 해석하고 있습니다.",
            "mapping_proposal_ready": "스키마 매핑 제안이 준비되었습니다.",
            "data_confirmation_required": "데이터 해석 승인을 기다리고 있습니다.",
            "evidence_ready": "검증된 근거 데이터가 준비되었습니다.",
            "lens_jobs_ready": "심층 분석 작업이 준비되었습니다.",
            "scope_narrowing_required": "분석 범위 확인이 필요합니다.",
            "stopped": "사용자 요청으로 분석을 중지했습니다.",
            "cancelled": "분석이 취소되었습니다.",
            "finalized": "검증된 보고서가 준비되었습니다.",
        }
        allowed_actions = (
            ["submit_hitl"]
            if human
            else []
            if terminal
            else ["retry"]
            if retryable
            else ["resume"]
            if stopped or blocked
            else ["continue"]
        )
        if attach_allowed:
            allowed_actions.append('attach_data')
        return RunSnapshot(
            run_id=manifest.run_id,
            revision=result.revision,
            workflow_status=(
                "stopped_by_human"
                if stopped
                else result.state
            ),
            ui_phase=phases.get(result.state, 4),
            pending_action=(
                "human_response"
                if human
                else "terminal"
                if terminal
                else "retry"
                if retryable
                else "resume"
                if stopped or blocked
                else "provider_work"
            ),
            allowed_actions=allowed_actions,
            latest_event=latest.get(result.state, "분석 상태가 갱신되었습니다."),
            progress=progress.get(result.state, 60),
            result_ref=manifest.result_ref,
            hitl_card=self._hitl_card(manifest, result) if human else None,
            error=(
                ServiceErrorBody(
                    code=manifest.error_code or "AI_TRANSIENT_FAILURE",
                    message=(
                        "OpenAI API key is required"
                        if manifest.error_code == "AI_AUTH_FAILURE"
                        else "The AI step can be retried"
                    ),
                    retryable=True,
                )
                if retryable
                else None
            ),
            uploaded_files=self._uploaded_file_summaries(
                manifest.run_id,
                result.revision,
            ),
        )
