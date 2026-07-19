from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any, Protocol

from trusted_ceo_agent.application.models import (
    ApplicationResult,
    CreateRunRequest,
    MutationRequest,
    RunRequest,
)
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
)
from trusted_ceo_agent.service.run_store import (
    RunStore,
    ServiceManifest,
    ServiceStoreError,
)
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from trusted_ceo_agent.workflow.overlays import apply_overlay


STATE_HANDLERS = {
    "context_confirmation_required": "_await_context",
    "context_ready": "_scan",
    "schema_mapping_job_ready": "_run_schema_mapping",
    "mapping_proposal_ready": "_await_data",
    "data_confirmation_required": "_await_data",
    "evidence_ready": "_prepare_lens",
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


class ReasoningGateway(Protocol):
    def execute(self, job: Mapping[str, Any]) -> dict[str, Any]:
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
    ) -> None:
        if application.artifact_root.resolve() != run_store.runs_root.resolve():
            raise ValueError("application and service store must share the runs root")
        self.application = application
        self.run_store = run_store
        self.gateway = gateway
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def create_run(self, request: CreateRunRequest) -> RunSnapshot:
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
        return self.snapshot(result.run_id)

    def snapshot(self, run_id: str) -> RunSnapshot:
        manifest = self._manifest(run_id)
        result = self.application.status(RunRequest(run_id=run_id))
        if result.revision != manifest.engine_revision:
            raise ServiceStoreError(
                "STALE_REVISION",
                "service manifest does not match the workflow revision",
            )
        return self._snapshot(manifest, result)

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

        common = {
            "request_id": manifest.pending_approval_request_id,
            "actor_id": "local-browser-user",
            "actor_role": "business_owner",
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
                    "change_scope": "data" if request.decision == "reanalyze" else None,
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
            result = state
            for job in pending:
                draft = self.gateway.execute(job)
                result = self._mutate(
                    manifest.run_id,
                    manifest.engine_revision,
                    "ingest-result",
                    {
                        "job_id": str(job["job_id"]),
                        "draft_document": draft,
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

    def _snapshot(
        self,
        manifest: ServiceManifest,
        result: ApplicationResult,
    ) -> RunSnapshot:
        if result.revision is None or result.state is None:
            raise IntegrityError("workflow status is incomplete")
        human = manifest.status == "awaiting_human"
        terminal = manifest.status in {"stopped", "cancelled", "finalized"}
        phases = {
            "context_confirmation_required": 1,
            "context_ready": 2,
            "schema_mapping_job_ready": 2,
            "mapping_proposal_ready": 3,
            "data_confirmation_required": 3,
            "evidence_ready": 4,
            "lens_jobs_ready": 4,
            "scope_narrowing_required": 4,
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
            "stopped": 100,
            "cancelled": 100,
            "finalized": 100,
        }
        latest = {
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
        return RunSnapshot(
            run_id=manifest.run_id,
            revision=result.revision,
            workflow_status=result.state,
            ui_phase=phases.get(result.state, 4),
            pending_action=(
                "human_response"
                if human
                else "terminal"
                if terminal
                else "provider_work"
            ),
            allowed_actions=(
                ["submit_hitl"]
                if human
                else []
                if terminal
                else ["continue"]
            ),
            latest_event=latest.get(result.state, "분석 상태가 갱신되었습니다."),
            progress=progress.get(result.state, 60),
            result_ref=manifest.result_ref,
            hitl_card=self._hitl_card(manifest, result) if human else None,
        )
