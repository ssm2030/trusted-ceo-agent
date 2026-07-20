from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from trusted_ceo_agent.application.models import (
    ApplicationResult,
    AttachSourcesRequest,
    CreateRunRequest,
    DocumentInput,
    ExportWebReportRequest,
    HumanResponseRequest,
    MutationRequest,
    PrepareResultQuestionRequest,
    RevisionRequest,
    RunRequest,
    SubmitHumanResponseRequest,
    ValidateResultAnswerRequest,
)
from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, IntegrityError, RevisionConflict
from trusted_ceo_agent.filesystem import ensure_within
from trusted_ceo_agent.mission import is_confirmed_mission, validate_confirmed_mission
from trusted_ceo_agent.questions import (
    QuestionIndex,
    ScopeRequired,
    build_result_question_job,
    validate_and_render_answer,
)
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from trusted_ceo_agent.trust.revision_validation import validate_revision
from trusted_ceo_agent.web_report.contracts import load_bundle_bytes
from trusted_ceo_agent.web_report.converter import convert_final_revision
from trusted_ceo_agent.web_report.output import publish_web_report_output
from trusted_ceo_agent.workflow.human_actions import pending_action_for_state, verify_action_card
from trusted_ceo_agent.workflow.human_response_policy import verify_human_response_policy
from trusted_ceo_agent.workflow.responses import HumanResponseService
from trusted_ceo_agent.workflow.revisions import RevisionManager
from trusted_ceo_agent.workflow.snapshot_validation import validate_snapshot_files


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
GATES = ("context", "data", "scope_narrowing", "diagnostic", "final")
_OPAQUE_TOKEN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_INITIAL_STATES = {"context_confirmation_required", "context_ready"}
_MODEL_ARTIFACT_PREFIXES = ("tasks/", "reasoning/", "components/", "grading/", "final/")
_MEDIA_TYPES = {
    ".csv": "text/csv",
    ".json": "application/json",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"run_{timestamp}_{secrets.token_hex(8)}"


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _validate_artifact_root(artifact_root: Path) -> Path:
    workspace = Path.cwd().resolve()
    root = artifact_root.resolve()
    if not _is_relative_to(root, workspace):
        raise ContractError("artifact root must be inside the current workspace")
    if _is_relative_to(root, PLUGIN_ROOT) or _is_relative_to(PLUGIN_ROOT, root):
        raise ContractError("artifact root cannot overlap plugin root")
    if any(part.lower() == "logs" for part in root.parts):
        raise ContractError("artifact root cannot be logs")
    return root


def _safe_file_path(path: Path) -> Path:
    raw = path if path.is_absolute() else Path.cwd() / path
    safe = ensure_within(Path(raw.anchor), raw)
    if not safe.exists():
        raise FileNotFoundError(path)
    if safe.is_dir():
        raise ContractError(f"input must be a file: {path}")
    return safe


def _validate_input_path(path: Path, artifact_root: Path) -> Path:
    safe = _safe_file_path(path)
    if any(part.lower() == "logs" for part in safe.parts):
        raise ContractError("logs cannot be an input")
    if _is_relative_to(safe, artifact_root):
        raise ContractError("input cannot be inside artifact root")
    return safe


def _file_identity(details: os.stat_result) -> tuple[int, int, int, int]:
    return (
        int(getattr(details, "st_dev", 0)),
        int(getattr(details, "st_ino", 0)),
        int(details.st_size),
        int(details.st_mtime_ns),
    )


def stable_read(path: Path) -> tuple[Path, bytes]:
    safe = ensure_within(path.parent.resolve(strict=True), path)
    with safe.open("rb") as handle:
        before_handle = _file_identity(os.fstat(handle.fileno()))
        before_path = _file_identity(safe.stat())
        chunks: list[bytes] = []
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after_handle = _file_identity(os.fstat(handle.fileno()))
        after_path = _file_identity(safe.stat())
    if before_handle != after_handle or before_path != after_path or after_handle != after_path:
        raise IntegrityError(f"input changed while being read: {safe.name}")
    return safe, b"".join(chunks)


def snapshot_payloads(store: ArtifactStore, revision: int) -> dict[str, bytes]:
    snapshot = store.verify_revision(revision)
    manifest = json.loads((snapshot / "snapshot-manifest.json").read_text("utf-8"))
    return {
        item["path"]: (snapshot / Path(item["path"])).read_bytes()
        for item in manifest["files"]
    }


def workflow_state(files: Mapping[str, bytes]) -> dict[str, Any]:
    raw = files.get("workflow/state.json")
    if raw is None:
        raise IntegrityError("workflow state is missing")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise IntegrityError("workflow state is invalid")
    return value


def _document(
    value: DocumentInput,
    *,
    label: str,
    native_numbers: bool = False,
    invalid_json_message: str | None = None,
    object_error: str | None = None,
) -> dict[str, Any]:
    if isinstance(value, Path):
        safe = _safe_file_path(value)
        if any(part.lower() == "logs" for part in safe.parts):
            raise ContractError(f"logs cannot be a {label} input")
        _, payload = stable_read(safe)
        try:
            parsed = strict_loads(payload)
            if native_numbers:
                parsed = json.loads(payload.decode("utf-8"))
        except (UnicodeError, ValueError) as error:
            if invalid_json_message is not None:
                raise ContractError(invalid_json_message) from error
            raise
    else:
        try:
            parsed = dict(value) if native_numbers else strict_loads(json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ))
        except (TypeError, ValueError) as error:
            if invalid_json_message is not None:
                raise ContractError(invalid_json_message) from error
            raise ContractError(f"{label} is not valid JSON") from error
    if not isinstance(parsed, Mapping):
        raise ContractError(object_error or f"{label} must be an object")
    return dict(parsed)


def _trusted_local_principal() -> dict[str, Any]:
    subject = getpass.getuser().strip()
    if not subject:
        raise ContractError("local transport principal is unavailable")
    return {"subject": subject, "roles": ["run_owner"]}


def _human_response_policy(mission: Mapping[str, Any], *, owner_actor_id: str | None) -> dict[str, Any]:
    principal = _trusted_local_principal()
    confirmation = mission.get("confirmation")
    confirmed_actor = confirmation.get("actor_id") if isinstance(confirmation, Mapping) else None
    actor_id = owner_actor_id or (
        str(confirmed_actor) if isinstance(confirmed_actor, str) and confirmed_actor else None
    ) or str(principal["subject"])
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "policy_id": "human-response-local-owner",
        "policy_version": "1.0.0",
        "transport_principal": principal["subject"],
        "authorized_actors": [{
            "actor_id": actor_id,
            "roles": ["run_owner"],
            "allowed_gates": list(GATES),
        }],
        "restricted_source_allowlist": [],
        "privacy_policy": {
            "direct_identifier_reasoning": "forbidden",
            "minimum_group_size": 5,
        },
    }
    policy = {**body, "policy_hash": hashlib.sha256(canonical_bytes(body)).hexdigest()}
    verify_human_response_policy(policy)
    return policy


def _source_document(
    path: Path,
    payload: bytes,
    *,
    received_at: str,
) -> tuple[str, str, dict[str, Any]]:
    digest = hashlib.sha256(payload).hexdigest()
    token = make_id("path", {"name": path.name, "sha256": digest})
    source_id = f"source_{digest[:24]}"
    return source_id, token, {
        "source_id": source_id,
        "source_type": "uploaded_file",
        "access_policy": "permitted",
        "evidence_usage": "primary",
        "observation_roles": [],
        "display_name": path.name,
        "media_type": _MEDIA_TYPES.get(
            path.suffix.lower(),
            "application/octet-stream",
        ),
        "sha256": digest,
        "size_bytes": len(payload),
        "received_at": received_at,
        "snapshot_ref": f"sources/blobs/{digest}",
        "original_path_token": token,
        "aliases": [],
        "metadata": {"extension": path.suffix.lower()},
    }


def _merge_source(
    sources_by_id: dict[str, dict[str, Any]],
    document: dict[str, Any],
) -> bool:
    source_id = str(document["source_id"])
    existing = sources_by_id.get(source_id)
    if existing is None:
        sources_by_id[source_id] = document
        return True
    for field in ("sha256", "size_bytes", "snapshot_ref"):
        if existing.get(field) != document.get(field):
            raise IntegrityError(f"source registry collision: {source_id}")
    name = str(document["display_name"])
    if name != existing.get("display_name") and name not in existing.get("aliases", []):
        existing["aliases"] = sorted({*existing.get("aliases", []), name})
    return False


def _pending_action_document(
    store: ArtifactStore,
    *,
    run_id: str,
    revision: int,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    files = snapshot_payloads(store, revision)
    state = workflow_state(files)
    stored = files.get("workflow/pending-action.json")
    if stored is not None:
        card = json.loads(stored.decode("utf-8"))
        if not isinstance(card, dict):
            raise IntegrityError("stored Human Action Card is invalid")
    else:
        resolution_payload = files.get("workflow/human-action-resolution.json")
        resolved_here = False
        if resolution_payload is not None:
            resolution = json.loads(resolution_payload.decode("utf-8"))
            if not isinstance(resolution, Mapping):
                raise IntegrityError("stored Human Action resolution is invalid")
            value = dict(resolution)
            SchemaStore().validate("human-action-resolution.schema.json", value)
            claimed = value.pop("resolution_hash")
            actual = hashlib.sha256(canonical_bytes(value)).hexdigest()
            if claimed != actual:
                raise IntegrityError("stored Human Action resolution hash is invalid")
            resolved_here = (
                resolution.get("result_revision") == revision
                and resolution.get("workflow_state") == state.get("state")
            )
        card = None if resolved_here else pending_action_for_state(
            run_id=run_id,
            revision=revision,
            workflow_state=str(state["state"]),
            evidence_refs=[],
            expires_at=None,
        )
    if card is not None:
        verify_action_card(card)
        if (
            card.get("run_id") != run_id
            or card.get("base_revision") != revision
            or card.get("workflow_state") != state.get("state")
        ):
            raise IntegrityError("stored Human Action Card does not match current workflow")
    return card, state


class TrustedCeoApplication:
    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = _validate_artifact_root(artifact_root)

    def _store(self, run_id: str) -> ArtifactStore:
        store = ArtifactStore(self.artifact_root)
        store.open_run(run_id)
        return store

    def mutate(self, request: MutationRequest) -> ApplicationResult:
        from trusted_ceo_agent.application.mutations import MutationExecutor

        return MutationExecutor(self.artifact_root).execute(request)

    def create_run(self, request: CreateRunRequest) -> ApplicationResult:
        mission_input = request.mission
        if isinstance(mission_input, Path):
            mission_input = _validate_input_path(mission_input, self.artifact_root)
        mission = _document(mission_input, label="Mission Contract")
        mission_confirmed = is_confirmed_mission(mission)
        if mission_confirmed:
            validate_confirmed_mission(mission)
        run_id = request.run_id or _run_id()
        state_name = "context_ready" if mission_confirmed else "context_confirmation_required"
        files: dict[str, bytes] = {
            "mission/mission-contract.json": canonical_bytes(mission),
            "workflow/human-response-policy.json": canonical_bytes(
                _human_response_policy(mission, owner_actor_id=request.run_owner_actor_id)
            ),
        }
        sources_by_id: dict[str, dict[str, Any]] = {}
        resolver: dict[str, str] = {}
        received_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        prepared_inputs: list[tuple[Path, bytes]] = []
        for input_path in request.inputs:
            resolved = _validate_input_path(input_path, self.artifact_root)
            prepared_inputs.append(stable_read(resolved))
        for resolved, payload in prepared_inputs:
            _, token, document = _source_document(resolved, payload, received_at=received_at)
            files[f"sources/blobs/{document['sha256']}"] = payload
            resolver[token] = str(resolved)
            _merge_source(sources_by_id, document)
        sources = [sources_by_id[key] for key in sorted(sources_by_id)]
        files["sources/registry.json"] = canonical_bytes(sources)
        files["sources/resolver.json"] = canonical_bytes(resolver)
        state = {
            "run_id": run_id,
            "revision": 1,
            "state": state_name,
            "resume_state": None,
            "blocker": None,
            "approvals": [],
        }
        files["workflow/state.json"] = canonical_bytes(state)
        validate_snapshot_files(files)
        store = ArtifactStore(self.artifact_root)
        store.create_run(run_id)
        store.publish(0, files)
        return ApplicationResult(
            command="start",
            ok=True,
            code=0,
            message="run created",
            run_id=run_id,
            revision=1,
            state=state_name,
            data={"source_count": len(sources)},
        )

    def attach_sources(self, request: AttachSourcesRequest) -> ApplicationResult:
        if not request.sources:
            raise ContractError("at least one source is required")
        store = self._store(request.run_id)
        manager = RevisionManager(store, validator=validate_snapshot_files)
        current = manager.current_revision()
        if current != request.expected_revision:
            raise RevisionConflict(
                f"expected revision {request.expected_revision}, current is {current}"
            )
        files = manager.files(current)
        state = workflow_state(files)
        interaction_started = (
            "workflow/pending-action.json" in files
            or any(path.startswith("approvals/requests/") for path in files)
        )
        if (
            state.get("state") not in _INITIAL_STATES
            or interaction_started
            or any(path.startswith(_MODEL_ARTIFACT_PREFIXES) for path in files)
        ):
            raise ContractError("sources cannot be attached after model work starts")

        raw_registry = json.loads(files.get("sources/registry.json", b"[]").decode("utf-8"))
        raw_resolver = json.loads(files.get("sources/resolver.json", b"{}").decode("utf-8"))
        if not isinstance(raw_registry, list) or not isinstance(raw_resolver, Mapping):
            raise IntegrityError("stored source registry or resolver is invalid")
        sources_by_id = {
            str(item["source_id"]): dict(item)
            for item in raw_registry
            if isinstance(item, Mapping) and isinstance(item.get("source_id"), str)
        }
        if len(sources_by_id) != len(raw_registry):
            raise IntegrityError("stored source registry contains invalid or duplicate entries")
        resolver = {str(key): str(value) for key, value in raw_resolver.items()}
        received_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        attached_count = 0
        for upload in request.sources:
            if _OPAQUE_TOKEN.fullmatch(upload.opaque_token) is None:
                raise ContractError("source opaque token is invalid")
            if (upload.expected_sha256 is None) != (upload.expected_size is None):
                raise ContractError("source expected hash and size must be supplied together")
            if upload.expected_sha256 is not None and not re.fullmatch(
                r"[0-9a-f]{64}",
                upload.expected_sha256,
            ):
                raise ContractError("source expected SHA-256 is invalid")
            if upload.expected_size is not None and (
                isinstance(upload.expected_size, bool)
                or not isinstance(upload.expected_size, int)
                or upload.expected_size < 0
            ):
                raise ContractError("source expected size is invalid")
            resolved = _validate_input_path(upload.path, self.artifact_root)
            resolved, payload = stable_read(resolved)
            if upload.expected_size is not None and len(payload) != upload.expected_size:
                raise ContractError("source changed after upload policy validation")
            if upload.expected_sha256 is not None and not hmac.compare_digest(
                hashlib.sha256(payload).hexdigest(),
                upload.expected_sha256,
            ):
                raise ContractError("source changed after upload policy validation")
            _, token, document = _source_document(resolved, payload, received_at=received_at)
            blob_path = f"sources/blobs/{document['sha256']}"
            existing_blob = files.get(blob_path)
            if existing_blob is not None and existing_blob != payload:
                raise IntegrityError(f"source blob collision: {document['sha256']}")
            files[blob_path] = payload
            locator = f"service-upload:{upload.opaque_token}"
            existing_locator = resolver.get(token)
            if existing_locator is None:
                resolver[token] = locator
            if _merge_source(sources_by_id, document):
                attached_count += 1

        new_revision = current + 1
        state["revision"] = new_revision
        files["sources/registry.json"] = canonical_bytes(
            [sources_by_id[key] for key in sorted(sources_by_id)]
        )
        files["sources/resolver.json"] = canonical_bytes(
            {key: resolver[key] for key in sorted(resolver)}
        )
        files["workflow/state.json"] = canonical_bytes(state)
        files[f"audit/events/r{new_revision:04d}-attach-sources.json"] = canonical_bytes({
            "command": "attach-sources",
            "from_revision": current,
            "to_revision": new_revision,
            "source_count": len(sources_by_id),
        })
        revision = manager.commit(current, files)
        return ApplicationResult(
            command="attach-sources",
            ok=True,
            code=0,
            message="sources attached",
            run_id=request.run_id,
            revision=revision,
            state=str(state["state"]),
            data={"source_count": len(sources_by_id), "attached_count": attached_count},
        )

    def status(self, request: RunRequest) -> ApplicationResult:
        store = self._store(request.run_id)
        revision = int(store.state()["revision"])
        state = workflow_state(snapshot_payloads(store, revision))
        return ApplicationResult(
            command="status",
            ok=True,
            code=0,
            message="status read",
            run_id=request.run_id,
            revision=revision,
            state=str(state["state"]),
            data=state,
        )

    def pending_action(self, request: RunRequest) -> ApplicationResult:
        store = self._store(request.run_id)
        revision = int(store.state()["revision"])
        card, state = _pending_action_document(
            store,
            run_id=request.run_id,
            revision=revision,
        )
        code = 2 if card is not None else 0
        return ApplicationResult(
            command="pending-action",
            ok=True,
            code=code,
            message="human action required" if card is not None else "no human action pending",
            run_id=request.run_id,
            revision=revision,
            state=str(state["state"]),
            data={"action": card},
        )

    @staticmethod
    def _human_response(request: HumanResponseRequest) -> dict[str, Any]:
        return _document(request.response, label="Human Response input")

    @staticmethod
    def _action(store: ArtifactStore, request: HumanResponseRequest) -> dict[str, Any]:
        card, _ = _pending_action_document(
            store,
            run_id=request.run_id,
            revision=request.expected_revision,
        )
        if card is None:
            raise ContractError("no Human Action Card is pending at the expected revision")
        if card["action_id"] != request.action_id:
            raise RevisionConflict("Human Action Card ID is stale")
        if card["content_hash"] != request.action_content_hash:
            raise RevisionConflict("Human Action Card content hash is stale")
        return card

    def preview_human_response(self, request: HumanResponseRequest) -> ApplicationResult:
        store = self._store(request.run_id)
        current = int(store.state()["revision"])
        if current != request.expected_revision:
            raise RevisionConflict(
                f"expected revision {request.expected_revision}, current is {current}"
            )
        card = self._action(store, request)
        receipt = HumanResponseService(
            RevisionManager(store, validator=validate_snapshot_files),
            trusted_principal=_trusted_local_principal(),
        ).preview(
            expected_revision=request.expected_revision,
            action=card,
            response=self._human_response(request),
        )
        return ApplicationResult(
            command="preview-human-response",
            ok=True,
            code=0,
            message="human response previewed",
            run_id=request.run_id,
            revision=current,
            state=str(receipt["workflow_state"]),
            data={"receipt": receipt},
        )

    def submit_human_response(self, request: SubmitHumanResponseRequest) -> ApplicationResult:
        store = self._store(request.run_id)
        card = self._action(store, request)
        receipt, revision = HumanResponseService(
            RevisionManager(store, validator=validate_snapshot_files),
            trusted_principal=_trusted_local_principal(),
        ).submit(
            expected_revision=request.expected_revision,
            action=card,
            response=self._human_response(request),
            idempotency_key=request.idempotency_key,
        )
        code = 2 if receipt["terminal_approval_required"] else 0
        return ApplicationResult(
            command="submit-human-response",
            ok=True,
            code=code,
            message=(
                "terminal approval required"
                if receipt["terminal_approval_required"]
                else "human response committed"
            ),
            run_id=request.run_id,
            revision=revision,
            state=str(receipt["workflow_state"]),
            data={"receipt": receipt},
        )

    def validate(self, request: RevisionRequest) -> ApplicationResult:
        validation = validate_revision(self._store(request.run_id), request.revision)
        return ApplicationResult(
            command="validate",
            ok=True,
            code=0,
            message="revision valid",
            run_id=request.run_id,
            revision=request.revision,
            state=None,
            data={"validated": True, "checks": list(validation.checks)},
        )

    def export_web_report(self, request: ExportWebReportRequest) -> ApplicationResult:
        store = self._store(request.run_id)
        manifest = _document(
            request.input_manifest,
            label="web report input manifest",
            native_numbers=True,
            invalid_json_message="web report input manifest is invalid JSON",
        )
        SchemaStore().validate("web-report-input-manifest.schema.json", manifest)
        if (manifest["run_id"], manifest["revision"]) != (
            request.run_id,
            request.revision,
        ):
            raise IntegrityError("web report input manifest run or revision mismatch")
        payload = convert_final_revision(
            store,
            run_id=request.run_id,
            revision=request.revision,
            expected_final_result_hash=manifest["files"][0]["sha256"],
        )
        bundle = load_bundle_bytes(payload)
        publish_web_report_output(
            request.output.resolve(strict=False),
            payload,
            workspace=Path.cwd(),
            run_dir=store.open_run(request.run_id),
            plugin_root=PLUGIN_ROOT,
        )
        receipt = bundle["viewer_eligibility_receipt"]
        return ApplicationResult(
            command="export-web-report",
            ok=True,
            code=0,
            message="web report exported",
            run_id=request.run_id,
            revision=request.revision,
            state=None,
            data={
                "bundle_hash": bundle["bundle_hash"],
                "viewer_mode": receipt["claimed_viewer_mode"],
                "checks": list(receipt["completed_checks"]),
            },
        )

    def prepare_result_question(
        self,
        request: PrepareResultQuestionRequest,
    ) -> ApplicationResult:
        files = snapshot_payloads(self._store(request.run_id), request.revision)
        index = QuestionIndex.from_snapshot(files)
        if isinstance(request.question, Path):
            _, payload = stable_read(_safe_file_path(request.question))
            question = payload.decode("utf-8")
        else:
            question = request.question
        try:
            job = build_result_question_job(
                index=index,
                question=question,
                scope_kind=request.scope_kind,
                scope_instance_id=request.scope_instance_id,
                privacy_classification=request.privacy_classification,
            )
        except ScopeRequired as error:
            return ApplicationResult(
                command="prepare-result-question",
                ok=True,
                code=2,
                message="scope required",
                run_id=request.run_id,
                revision=request.revision,
                state="finalized",
                data={
                    "error_code": error.code,
                    "suggestions": [dict(item) for item in error.suggestions],
                },
            )
        return ApplicationResult(
            command="prepare-result-question",
            ok=True,
            code=0,
            message="result question job prepared",
            run_id=request.run_id,
            revision=request.revision,
            state="finalized",
            data={"job": job},
        )

    def validate_result_answer(
        self,
        request: ValidateResultAnswerRequest,
    ) -> ApplicationResult:
        files = snapshot_payloads(self._store(request.run_id), request.revision)
        index = QuestionIndex.from_snapshot(files)
        object_error = "result question Job and answer draft must be objects"
        job = _document(
            request.job,
            label="result question Job",
            object_error=object_error,
        )
        draft = _document(
            request.draft,
            label="answer draft",
            object_error=object_error,
        )
        answer = validate_and_render_answer(job, draft, index)
        return ApplicationResult(
            command="validate-result-answer",
            ok=True,
            code=0,
            message="result answer validated",
            run_id=request.run_id,
            revision=request.revision,
            state="finalized",
            data={"answer": answer},
        )
