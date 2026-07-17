from __future__ import annotations

import argparse
import getpass
import hashlib
import importlib.util
import json
import mimetypes
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.contracts.cli_response import response
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, IntegrityError, RevisionConflict
from trusted_ceo_agent.evidence.core import EvidenceCoreValidator
from trusted_ceo_agent.evidence.revalidation import revalidate_component_artifacts
from trusted_ceo_agent.filesystem import ensure_within
from trusted_ceo_agent.grading.grader import grade
from trusted_ceo_agent.mission import (
    is_confirmed_mission,
    materialize_confirmed_mission,
    validate_confirmed_mission,
)
from trusted_ceo_agent.outputs.validation import revalidate_package
from trusted_ceo_agent.outputs.render import render_package
from trusted_ceo_agent.packs.runtime_index import RuntimePackIndex
from trusted_ceo_agent.runtime_scan import build_scan_artifacts
from trusted_ceo_agent.runtime_components import (
    component_input_documents,
    execute_authorized_scope,
    merge_component_runs,
)
from trusted_ceo_agent.runtime_finalization import build_delivery_package, prepare_finalization
from trusted_ceo_agent.reasoning.attempts import next_attempt_action
from trusted_ceo_agent.reasoning.jobs import compile_stage_jobs
from trusted_ceo_agent.reasoning.join import freeze_join_manifest, reduce_join
from trusted_ceo_agent.reasoning.normalizer import normalize_lens_draft
from trusted_ceo_agent.reasoning.stage_drafts import (
    normalize_deep_dive_draft,
    normalize_integrated_draft,
    normalize_writer_draft,
)
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from trusted_ceo_agent.trust.revision_validation import validate_revision
from trusted_ceo_agent.web_report.eligibility import decide_viewer_eligibility
from trusted_ceo_agent.web_report.exporter import export_web_report
from trusted_ceo_agent.web_report.output import publish_web_report_output
from trusted_ceo_agent.workflow.approvals import ApprovalService, current_approvals
from trusted_ceo_agent.workflow.human_actions import (
    pending_action_for_state,
    verify_action_card,
)
from trusted_ceo_agent.workflow.human_response_policy import (
    verify_human_response_policy,
)
from trusted_ceo_agent.workflow.overlays import apply_overlay, invalidated_gates
from trusted_ceo_agent.workflow.responses import HumanResponseService
from trusted_ceo_agent.workflow.revisions import RevisionManager
from trusted_ceo_agent.workflow.snapshot_validation import validate_snapshot_files
from trusted_ceo_agent.workflow.state_machine import TERMINAL, transition


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
EXIT_CONTRACT = 3
EXIT_INTEGRITY = 4
EXIT_INTERNAL = 5
EXIT_CONFLICT = 6
STAGES = ("schema_mapping", "lens", "integrated", "deep_dive", "writer")
GATES = ("context", "data", "scope_narrowing", "diagnostic", "final")


def _add_run(parser: argparse.ArgumentParser, *, mutation: bool = False) -> None:
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    if mutation:
        parser.add_argument("--expected-revision", type=int, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trusted-ceo-agent", description="Trusted CEO Agent")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")

    start = commands.add_parser("start")
    start.add_argument("--artifact-root", type=Path, required=True)
    start.add_argument("--mission-contract", type=Path, required=True)
    start.add_argument("--input", type=Path, action="append", required=True)
    start.add_argument("--run-owner-actor-id")

    for name in ("scan", "prepare-finalization", "finalize", "resume", "stop", "cancel"):
        _add_run(commands.add_parser(name), mutation=True)

    prepare = commands.add_parser("prepare-jobs")
    _add_run(prepare, mutation=True)
    prepare.add_argument("--stage", choices=STAGES, required=True)

    ingest = commands.add_parser("ingest-result")
    _add_run(ingest, mutation=True)
    ingest.add_argument("--job-id", required=True)
    ingest.add_argument("--draft", type=Path, required=True)

    reduce_stage = commands.add_parser("reduce-stage")
    _add_run(reduce_stage, mutation=True)
    reduce_stage.add_argument("--stage", choices=STAGES, required=True)

    approval_request = commands.add_parser("approval-request")
    _add_run(approval_request, mutation=True)
    approval_request.add_argument("--gate", choices=GATES, required=True)
    approval_request.add_argument("--overlay", type=Path, required=True)

    approve = commands.add_parser("approve-interactive")
    _add_run(approve, mutation=True)
    approve.add_argument("--request-id", required=True)

    decide = commands.add_parser("decide-interactive")
    _add_run(decide, mutation=True)
    decide.add_argument("--request-id", required=True)
    decide.add_argument("--decision", choices=("request_changes", "reject"), required=True)
    decide.add_argument(
        "--change-scope",
        choices=("data", "scan", "reasoning", "deep", "wording", "routing"),
    )

    components = commands.add_parser("run-components")
    _add_run(components, mutation=True)
    components.add_argument("--scope-ref", required=True)

    status = commands.add_parser("status")
    _add_run(status)

    validate = commands.add_parser("validate")
    _add_run(validate)
    validate.add_argument("--revision", type=int, required=True)

    render = commands.add_parser("render")
    _add_run(render)
    render.add_argument("--revision", type=int, required=True)

    export_web_report = commands.add_parser("export-web-report")
    _add_run(export_web_report)
    export_web_report.add_argument("--revision", type=int, required=True)
    export_web_report.add_argument("--output", type=Path, required=True)

    validate_web_report = commands.add_parser("validate-web-report")
    _add_run(validate_web_report)
    validate_web_report.add_argument("--revision", type=int, required=True)
    validate_web_report.add_argument("--bundle", type=Path, required=True)

    pending_action = commands.add_parser("pending-action")
    _add_run(pending_action)

    for name in ("preview-human-response", "submit-human-response"):
        human_response = commands.add_parser(name)
        _add_run(human_response, mutation=True)
        human_response.add_argument("--action-id", required=True)
        human_response.add_argument("--action-content-hash", required=True)
        human_response.add_argument("--response", type=Path, required=True)
        if name == "submit-human-response":
            human_response.add_argument("--idempotency-key", required=True)
    return parser


def _emit(value: Mapping[str, Any]) -> None:
    payload = canonical_bytes(value).decode("utf-8") + "\n"
    sys.stdout.write(payload)
    sys.stdout.flush()


def _run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"run_{timestamp}_{secrets.token_hex(8)}"


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _validate_start_paths(artifact_root: Path, mission: Path, inputs: Sequence[Path]) -> Path:
    workspace = Path.cwd().resolve()
    root = artifact_root.resolve()
    if not _is_relative_to(root, workspace):
        raise ContractError("artifact root must be inside the current workspace")
    if _is_relative_to(root, PLUGIN_ROOT) or _is_relative_to(PLUGIN_ROOT, root):
        raise ContractError("artifact root cannot overlap plugin root")
    if any(part.lower() == "logs" for part in root.parts):
        raise ContractError("artifact root cannot be logs")
    for supplied in (mission, *inputs):
        resolved = supplied.resolve(strict=True)
        if resolved.is_dir():
            raise ContractError(f"input must be a file: {supplied}")
        if any(part.lower() == "logs" for part in resolved.parts):
            raise ContractError("logs cannot be an input")
        if _is_relative_to(resolved, root):
            raise ContractError("input cannot be inside artifact root")
    return root


def _bootstrap_preflight() -> dict[str, Any]:
    path = PLUGIN_ROOT / "scripts" / "bootstrap.py"
    spec = importlib.util.spec_from_file_location("trusted_ceo_bootstrap", path)
    if spec is None or spec.loader is None:
        raise ContractError("bootstrap module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check_project(PLUGIN_ROOT)


def _file_identity(details: os.stat_result) -> tuple[int, int, int, int]:
    return (
        int(getattr(details, "st_dev", 0)),
        int(getattr(details, "st_ino", 0)),
        int(details.st_size),
        int(details.st_mtime_ns),
    )


def _stable_read(path: Path) -> tuple[Path, bytes]:
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


def _snapshot_payloads(store: ArtifactStore, revision: int) -> dict[str, bytes]:
    snapshot = store.verify_revision(revision)
    manifest = json.loads((snapshot / "snapshot-manifest.json").read_text("utf-8"))
    return {item["path"]: (snapshot / Path(item["path"])).read_bytes() for item in manifest["files"]}


def _workflow_state(files: Mapping[str, bytes]) -> dict[str, Any]:
    raw = files.get("workflow/state.json")
    if raw is None:
        raise IntegrityError("workflow state is missing")
    return json.loads(raw.decode("utf-8"))


def _effective_mission(files: Mapping[str, bytes]) -> dict[str, Any]:
    stored = strict_loads(files.get("mission/effective-mission-contract.json", files["mission/mission-contract.json"]))
    if not isinstance(stored, Mapping):
        raise ContractError("Mission Contract must be an object")
    if is_confirmed_mission(stored):
        validate_confirmed_mission(stored)
        return dict(stored)
    approvals = current_approvals(files, gate="context")
    if len(approvals) != 1:
        raise ContractError("exactly one current Context approval is required")
    overlay = strict_loads(files.get("workflow/hitl-overlay.json", b"{}"))
    if not isinstance(overlay, Mapping):
        raise ContractError("HITL overlay must be an object")
    approval = approvals[0]
    return materialize_confirmed_mission(
        stored,
        overlay,
        actor_id=str(approval["actor_id"]),
        actor_role=str(approval["actor_role"]),
        confirmed_at=str(approval["created_at"]),
    )


def _advance(state: Mapping[str, Any], event: str, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    machine = dict(state)
    machine["status"] = machine.pop("state")
    advanced = transition(machine, event, context or {})
    result = dict(state)
    result["state"] = advanced["status"]
    for key in ("resume_state", "blocker", "failure_reason"):
        if key in advanced:
            result[key] = advanced[key]
        elif key in result and key not in advanced:
            result[key] = None
    return result


def _recorded_blocker_is_resolved(files: Mapping[str, bytes], state: Mapping[str, Any]) -> bool:
    blocker = state.get("blocker")
    if blocker == "component_contract_failure":
        component_runs = [
            strict_loads(payload)
            for path, payload in files.items()
            if path.startswith("components/runs/") and path.endswith(".json")
        ]
        return bool(component_runs) and all(
            isinstance(run, Mapping) and run.get("status") != "failed"
            for run in component_runs
        )
    return False


def _overlay_status(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        raw = value.get("status", value.get("diagnostic_disposition"))
        return str(raw) if raw is not None else None
    return None


def _store_for(args: argparse.Namespace) -> ArtifactStore:
    store = ArtifactStore(args.artifact_root)
    store.open_run(args.run_id)
    return store


def _trusted_local_principal() -> dict[str, Any]:
    subject = getpass.getuser().strip()
    if not subject:
        raise ContractError("local transport principal is unavailable")
    return {"subject": subject, "roles": ["run_owner"]}


def _human_response_manager(store: ArtifactStore) -> RevisionManager:
    return RevisionManager(store, validator=validate_snapshot_files)


def _human_response_policy(
    mission: Mapping[str, Any],
    *,
    owner_actor_id: str | None,
) -> dict[str, Any]:
    principal = _trusted_local_principal()
    confirmation = mission.get("confirmation")
    confirmed_actor = (
        confirmation.get("actor_id")
        if isinstance(confirmation, Mapping)
        else None
    )
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


def _start(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    root = _validate_start_paths(args.artifact_root, args.mission_contract, args.input)
    _, mission_payload = _stable_read(args.mission_contract.resolve(strict=True))
    mission = strict_loads(mission_payload)
    if not isinstance(mission, dict):
        raise ContractError("Mission Contract must be an object")
    mission_confirmed = is_confirmed_mission(mission)
    if mission_confirmed:
        validate_confirmed_mission(mission)
    run_id = _run_id()
    store = ArtifactStore(root)
    store.create_run(run_id)
    state_name = "context_ready" if mission_confirmed else "context_confirmation_required"
    files: dict[str, bytes] = {
        "mission/mission-contract.json": canonical_bytes(mission),
        "workflow/human-response-policy.json": canonical_bytes(_human_response_policy(
            mission,
            owner_actor_id=args.run_owner_actor_id,
        )),
    }
    sources_by_id: dict[str, dict[str, Any]] = {}
    resolver: dict[str, str] = {}
    received_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for input_path in args.input:
        resolved, payload = _stable_read(input_path.resolve(strict=True))
        digest = hashlib.sha256(payload).hexdigest()
        token = make_id("path", {"name": resolved.name, "sha256": digest})
        files[f"sources/blobs/{digest}"] = payload
        resolver[token] = str(resolved)
        source_id = f"source_{digest[:24]}"
        existing = sources_by_id.get(source_id)
        if existing is not None:
            if resolved.name != existing["display_name"] and resolved.name not in existing["aliases"]:
                existing["aliases"].append(resolved.name)
                existing["aliases"].sort()
            continue
        sources_by_id[source_id] = {
            "source_id": source_id,
            "source_type": "uploaded_file",
            "access_policy": "permitted",
            "evidence_usage": "primary",
            "observation_roles": [],
            "display_name": resolved.name,
            "media_type": mimetypes.guess_type(resolved.name)[0] or "application/octet-stream",
            "sha256": digest,
            "size_bytes": len(payload),
            "received_at": received_at,
            "snapshot_ref": f"sources/blobs/{digest}",
            "original_path_token": token,
            "aliases": [],
            "metadata": {"extension": resolved.suffix.lower()},
        }
    sources = [sources_by_id[key] for key in sorted(sources_by_id)]
    files["sources/registry.json"] = canonical_bytes(sorted(sources, key=lambda item: item["source_id"]))
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
    store.publish(0, files)
    return 0, response(
        command="start", ok=True, code=0, message="run created",
        run_id=run_id, revision=1, state=state_name,
        data={"source_count": len(sources)},
    )


def _status(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    store = _store_for(args)
    pointer = store.state()
    revision = int(pointer["revision"])
    files = _snapshot_payloads(store, revision)
    state = _workflow_state(files)
    return 0, response(
        command="status", ok=True, code=0, message="status read",
        run_id=args.run_id, revision=revision, state=state["state"], data=state,
    )


def _pending_action_document(
    store: ArtifactStore,
    *,
    run_id: str,
    revision: int,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    files = _snapshot_payloads(store, revision)
    state = _workflow_state(files)
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


def _action_from_args(
    store: ArtifactStore,
    args: argparse.Namespace,
) -> dict[str, Any]:
    card, _ = _pending_action_document(
        store,
        run_id=args.run_id,
        revision=args.expected_revision,
    )
    if card is None:
        raise ContractError("no Human Action Card is pending at the expected revision")
    if card["action_id"] != args.action_id:
        raise RevisionConflict("Human Action Card ID is stale")
    if card["content_hash"] != args.action_content_hash:
        raise RevisionConflict("Human Action Card content hash is stale")
    return card


def _human_response_input(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    if any(part.lower() == "logs" for part in resolved.parts):
        raise ContractError("logs cannot be a Human Response input")
    _, payload = _stable_read(resolved)
    value = strict_loads(payload)
    if not isinstance(value, Mapping):
        raise ContractError("Human Response input must be an object")
    return dict(value)


def _pending_action(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    store = _store_for(args)
    revision = int(store.state()["revision"])
    card, state = _pending_action_document(
        store,
        run_id=args.run_id,
        revision=revision,
    )
    code = 2 if card is not None else 0
    return code, response(
        command=args.command,
        ok=True,
        code=code,
        message="human action required" if card is not None else "no human action pending",
        run_id=args.run_id,
        revision=revision,
        state=state["state"],
        data={"action": card},
    )


def _preview_human_response(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    store = _store_for(args)
    current = int(store.state()["revision"])
    if current != args.expected_revision:
        raise RevisionConflict(f"expected revision {args.expected_revision}, current is {current}")
    card = _action_from_args(store, args)
    receipt = HumanResponseService(
        _human_response_manager(store),
        trusted_principal=_trusted_local_principal(),
    ).preview(
        expected_revision=args.expected_revision,
        action=card,
        response=_human_response_input(args.response),
    )
    return 0, response(
        command=args.command,
        ok=True,
        code=0,
        message="human response previewed",
        run_id=args.run_id,
        revision=current,
        state=receipt["workflow_state"],
        data={"receipt": receipt},
    )


def _submit_human_response(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    store = _store_for(args)
    card = _action_from_args(store, args)
    receipt, revision = HumanResponseService(
        _human_response_manager(store),
        trusted_principal=_trusted_local_principal(),
    ).submit(
        expected_revision=args.expected_revision,
        action=card,
        response=_human_response_input(args.response),
        idempotency_key=args.idempotency_key,
    )
    code = 2 if receipt["terminal_approval_required"] else 0
    return code, response(
        command=args.command,
        ok=True,
        code=code,
        message=(
            "terminal approval required"
            if receipt["terminal_approval_required"]
            else "human response committed"
        ),
        run_id=args.run_id,
        revision=revision,
        state=receipt["workflow_state"],
        data={"receipt": receipt},
    )


def _validate(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    validation = validate_revision(_store_for(args), args.revision)
    return 0, response(
        command="validate", ok=True, code=0, message="revision valid",
        run_id=args.run_id, revision=args.revision,
        data={"validated": True, "checks": list(validation.checks)},
    )


def _render(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    store = _store_for(args)
    files = _snapshot_payloads(store, args.revision)
    if "final/result.json" not in files:
        raise ContractError("revision has no Final Result")
    result = json.loads(files["final/result.json"].decode("utf-8"))
    rendered = render_package(result)
    mismatches = [path for path, payload in rendered.items() if files.get(path) != payload]
    if mismatches:
        raise IntegrityError(f"rendered output differs: {', '.join(sorted(mismatches))}")
    core = json.loads(files.get("evidence/core.json", b"{}").decode("utf-8"))
    revalidate_package(
        result, {path: files[path] for path in rendered},
        evidence_links={item["evidence_link_id"]: item for item in core.get("evidence_links", [])},
    )
    return 0, response(
        command="render", ok=True, code=0, message="render is byte-equivalent",
        run_id=args.run_id, revision=args.revision, data={"files": sorted(rendered)},
    )


def _export_web_report(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    store = _store_for(args)
    exported = export_web_report(store, run_id=args.run_id, revision=args.revision)
    run_dir = store.open_run(args.run_id)
    publish_web_report_output(
        args.output.resolve(strict=False), exported.payload,
        workspace=Path.cwd(), run_dir=run_dir, plugin_root=PLUGIN_ROOT,
    )
    return 0, response(
        command="export-web-report", ok=True, code=0,
        message="web report exported", run_id=args.run_id,
        revision=args.revision,
        data={
            "bundle_hash": exported.bundle["bundle_hash"],
            "viewer_mode": exported.bundle["viewer_eligibility_receipt"]["claimed_viewer_mode"],
            "checks": list(exported.checks),
        },
    )


def _validate_web_report(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    _, payload = _stable_read(args.bundle.resolve(strict=True))
    decision = decide_viewer_eligibility(
        _store_for(args), expected_run_id=args.run_id,
        expected_revision=args.revision, bundle_payload=payload,
    )
    code = 0 if decision["eligible"] else EXIT_INTEGRITY
    return code, response(
        command="validate-web-report", ok=decision["eligible"], code=code,
        message="web report eligible" if decision["eligible"] else decision["failure_message"],
        run_id=args.run_id, revision=args.revision,
        data=decision,
    )


def _pack_reasoning_context(files: Mapping[str, bytes]) -> dict[str, Any]:
    index = RuntimePackIndex.from_files(files)
    core = strict_loads(files.get("evidence/core.json", b"{}"))
    if not isinstance(core, Mapping):
        raise ContractError("Evidence Core is missing for reasoning")
    mission = strict_loads(files.get(
        "mission/effective-mission-contract.json",
        files.get("mission/mission-contract.json", b"{}"),
    ))
    selection = strict_loads(files.get("packs/selection.json", b"{}"))
    selected_refs = set(selection.get("selected_problem_refs", [])) if isinstance(selection, Mapping) else set()
    selected_packs = tuple(
        pack for pack in index.problem_packs
        if f"{pack['pack_id']}@{pack['pack_version']}" in selected_refs
    )
    facts = [
        item for item in core.get("fact_register", [])
        if isinstance(item, Mapping) and isinstance(item.get("fact_id"), str)
    ]
    signals = [
        item for item in core.get("signal_register", [])
        if isinstance(item, Mapping) and isinstance(item.get("signal_id"), str)
    ]
    capabilities = [
        item for item in core.get("capability_map", {}).get("capabilities", [])
        if isinstance(item, Mapping) and isinstance(item.get("capability_id"), str)
    ]
    domain_content = index.domain_pack["content"]
    mechanisms = {
        str(item["mechanism_ref"])
        for item in domain_content.get("mechanism_catalog", [])
    }
    tests = {
        str(reference)
        for item in domain_content.get("mechanism_catalog", [])
        for reference in item.get("distinguishing_test_refs", [])
    }
    experts = {
        str(item["expert_trigger_ref"])
        for item in domain_content.get("expert_triggers", [])
    }
    families: set[str] = set()
    responses: set[str] = set()
    conditions: set[str] = set()
    decision_types: set[str] = set()
    for pack in selected_packs:
        content = pack["content"]
        families.update({
            str(content["problem_family_code"]),
            str(pack["pack_id"]),
            f"{pack['pack_id']}@{pack['pack_version']}",
        })
        for item in content.get("distinguishing_tests", []):
            tests.add(str(item["test_ref"]))
        for item in content.get("conditional_response_catalog", []):
            responses.add(str(item["response_ref"]))
            conditions.update(str(value) for value in item.get("preconditions", []))
            conditions.update(str(value) for value in item.get("disqualifiers", []))
        for item in content.get("blocking_counter_evidence_conditions", []):
            conditions.add(str(item["condition_ref"]))
        experts.update(str(value) for value in content.get("expert_trigger_refs", []))
        decision_types.update(
            str(item["decision_type_ref"])
            for item in content.get("decision_type_catalog", [])
        )
    decision_units = {
        str(item["decision_unit_ref"])
        for item in mission.get("decision_units", [])
        if isinstance(item, Mapping) and isinstance(item.get("decision_unit_ref"), str)
    } if isinstance(mission, Mapping) else set()
    claim_refs: set[str] = set()
    data_request_refs: set[str] = set()
    for path, payload in files.items():
        if not path.startswith("tasks/") or not path.endswith("/card.json"):
            continue
        card = strict_loads(payload)
        normalized = card.get("normalized_payload", {}) if isinstance(card, Mapping) else {}
        if not isinstance(normalized, Mapping):
            continue
        for field in (
            "business_meanings", "problem_candidates", "cause_hypotheses",
            "counter_hypotheses", "expert_trigger_candidates",
        ):
            for item in normalized.get(field, []):
                if isinstance(item, Mapping) and isinstance(item.get("claim_id"), str):
                    claim_refs.add(str(item["claim_id"]))
        for item in normalized.get("data_requests", []):
            if isinstance(item, Mapping) and isinstance(item.get("local_key"), str):
                data_request_refs.add(str(item["local_key"]))
    return {
        "index": index,
        "core": core,
        "mission": mission,
        "selected_packs": selected_packs,
        "facts": facts,
        "signals": signals,
        "capabilities": capabilities,
        "allowed_mechanism_refs": sorted(mechanisms),
        "allowed_test_refs": sorted(tests),
        "allowed_expert_trigger_refs": sorted(experts),
        "allowed_problem_family_refs": sorted(families),
        "allowed_response_refs": sorted(responses),
        "allowed_condition_refs": sorted(conditions),
        "allowed_decision_type_refs": sorted(decision_types),
        "allowed_decision_unit_refs": sorted(decision_units),
        "allowed_claim_refs": sorted(claim_refs),
        "allowed_data_request_refs": sorted(data_request_refs),
        "allowed_monitoring_metric_refs": sorted({
            str(item.get("metric_code") or item.get("fact_code"))
            for item in facts
            if item.get("metric_code") or item.get("fact_code")
        }),
    }


def _reasoning_jobs(
    stage: str,
    *,
    files: Mapping[str, bytes],
    pointer: Mapping[str, Any],
    run_id: str,
    revision: int,
) -> list[dict[str, Any]]:
    context = _pack_reasoning_context(files)
    mission = context["mission"]
    mission_hash = str(mission.get("confirmation", {}).get("contract_hash", ""))
    if len(mission_hash) != 64:
        mission_hash = hashlib.sha256(canonical_bytes(mission)).hexdigest()
    pack_hash = str(context["index"].manifest["manifest_hash"])
    artifact_ref = f"{run_id}@r{revision:04d}:{pointer.get('manifest_hash', '')}"
    common = {
        "artifact_ref": artifact_ref,
        "mission_contract_hash": mission_hash,
        "pack_manifest_hash": pack_hash,
        "prompt_template_hash": hashlib.sha256(f"trusted-ceo-{stage}-v1".encode("utf-8")).hexdigest(),
        "model_profile": "balanced_structured" if stage in {"schema_mapping", "lens"} else "strong_structured",
        "output_schema_ref": f"{stage.replace('_', '-')}-draft.schema.json",
        "capability_ids": [item["capability_id"] for item in context["capabilities"]],
        "allowed_fact_ids": [item["fact_id"] for item in context["facts"]],
        "allowed_signal_ids": [item["signal_id"] for item in context["signals"]],
        "allowed_mechanism_refs": context["allowed_mechanism_refs"],
        "allowed_test_refs": context["allowed_test_refs"],
        "allowed_expert_trigger_refs": context["allowed_expert_trigger_refs"],
        "allowed_decision_type_refs": context["allowed_decision_type_refs"],
        "allowed_decision_unit_refs": context["allowed_decision_unit_refs"],
        "allowed_problem_family_refs": context["allowed_problem_family_refs"],
        "allowed_response_refs": context["allowed_response_refs"],
    }
    if stage == "schema_mapping":
        proposal = strict_loads(files.get("intake/canonical-mapping-proposal.json", b"{}"))
        references = sorted(
            item["mapping_question_ref"]
            for item in proposal.get("mappings", [])
            if isinstance(item, Mapping) and isinstance(item.get("mapping_question_ref"), str)
        )
        if not references:
            raise ContractError("canonical mapping proposal has no questions")
        return compile_stage_jobs(stage, **common, mapping_question_refs=references)
    if stage == "lens":
        facts = context["facts"]
        signals = context["signals"]
        work_items = [
            {
                "id": item["fact_id"],
                "scope": item.get("scope", []),
                "period": item.get("time_context", {}),
                "component_id": (item.get("derivation") or {}).get("component_id", "intake"),
            }
            for item in facts
            if isinstance(item, dict) and isinstance(item.get("fact_id"), str)
        ]
        signal_ids = sorted(
            item["signal_id"] for item in signals
            if isinstance(item, dict) and isinstance(item.get("signal_id"), str)
        )
        required_signal_ids = sorted(
            item["signal_id"] for item in signals
            if isinstance(item, dict)
            and isinstance(item.get("signal_id"), str)
            and item.get("outcome") in {"triggered", "not_assessable"}
        )
        jobs: list[dict[str, Any]] = []
        for pack in context["selected_packs"]:
            content = pack["content"]
            family_refs = sorted({
                str(content["problem_family_code"]),
                str(pack["pack_id"]),
                f"{pack['pack_id']}@{pack['pack_version']}",
            })
            response_refs = sorted(
                str(item["response_ref"])
                for item in content.get("conditional_response_catalog", [])
            )
            decision_refs = sorted(
                str(item["decision_type_ref"])
                for item in content.get("decision_type_catalog", [])
            )
            for lens in content.get("lens_plan", []):
                lens_common = dict(common)
                lens_common.update({
                    "allowed_signal_ids": signal_ids,
                    "required_signal_ids": required_signal_ids,
                    "allowed_problem_family_refs": family_refs,
                    "allowed_mechanism_refs": sorted(set(lens.get("allowed_mechanism_refs", []))),
                    "allowed_response_refs": response_refs,
                    "allowed_decision_type_refs": decision_refs,
                })
                jobs.extend(compile_stage_jobs(
                    stage, **lens_common, work_items=work_items,
                    lens_id=str(lens["lens_id"]),
                ))
        if not jobs:
            boundary_common = dict(common)
            boundary_common.update({
                "allowed_signal_ids": signal_ids,
                "required_signal_ids": required_signal_ids,
                "allowed_problem_family_refs": [],
                "allowed_mechanism_refs": [],
                "allowed_test_refs": [],
                "allowed_expert_trigger_refs": [],
                "allowed_response_refs": [],
                "allowed_decision_type_refs": [],
            })
            jobs.extend(compile_stage_jobs(
                stage, **boundary_common, work_items=work_items,
                lens_id="bounded_not_assessable",
            ))
        return sorted(jobs, key=lambda item: item["job_id"])
    if stage == "integrated":
        join = strict_loads(files["reasoning/join-manifest.json"])
        return compile_stage_jobs(stage, **common, join_manifest_ref=join["join_manifest_id"])
    if stage == "deep_dive":
        scope = strict_loads(files.get("components/scope.json", b"{}"))
        return compile_stage_jobs(
            stage, **common, approved_scope_ref=scope.get("scope_ref", ""),
            component_run_refs=scope.get("component_run_ids", []),
        )
    if stage == "writer":
        structured = strict_loads(files.get("final/structured-output.json", b"{}"))
        return compile_stage_jobs(
            stage, **common, structured_output_ref="final/structured-output.json",
            allowed_claim_ids=sorted(
                item["issue_id"] for item in structured.get("issues", [])
                if isinstance(item, dict) and isinstance(item.get("issue_id"), str)
            ),
        )
    raise ContractError(f"unsupported stage: {stage}")


def _reasoning_attempt_records(
    files: Mapping[str, bytes], job_id: str, stage: str,
) -> list[dict[str, Any]]:
    prefix = f"tasks/{job_id}/attempts/attempt-"
    records: list[dict[str, Any]] = []
    for path, payload in files.items():
        if not path.startswith(prefix) or not path.endswith(".json"):
            continue
        record = strict_loads(payload)
        if not isinstance(record, Mapping):
            raise IntegrityError(f"Reasoning attempt record is invalid: {path}")
        if record.get("job_id") != job_id or record.get("stage") != stage:
            raise IntegrityError(f"Reasoning attempt record identity mismatch: {path}")
        try:
            attempt = int(record["attempt"])
        except (KeyError, TypeError, ValueError) as error:
            raise IntegrityError(f"Reasoning attempt number is invalid: {path}") from error
        normalized = dict(record)
        normalized["attempt"] = attempt
        records.append(normalized)
    records.sort(key=lambda item: item["attempt"])
    if [item["attempt"] for item in records] != list(range(1, len(records) + 1)):
        raise IntegrityError(f"Reasoning attempt history is not contiguous: {job_id}")
    return records


def _reasoning_attempt_record(
    job: Mapping[str, Any], draft: bytes, attempt: int, *,
    valid: bool, action: str, failure_kind: str | None = None,
    validation_errors: Sequence[str] = (),
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "job_id": str(job["job_id"]),
        "stage": str(job["stage"]),
        "attempt": attempt,
        "valid": valid,
        "action": action,
        "draft_sha256": hashlib.sha256(draft).hexdigest(),
        "validation_errors": list(validation_errors),
    }
    if failure_kind is not None:
        record["failure_kind"] = failure_kind
    return record


def _accepted_validation(
    job: Mapping[str, Any], attempt: int, *, source: str, action: str,
) -> dict[str, Any]:
    return {
        "job_id": str(job["job_id"]),
        "stage": str(job["stage"]),
        "attempt": attempt,
        "valid": True,
        "source": source,
        "action": action,
        "validation_errors": [],
    }


def _deterministic_writer_fallback(job: Mapping[str, Any]) -> dict[str, Any]:
    draft = {
        "structured_output_ref": job.get("structured_output_ref"),
        "claim_templates": [],
        "expert_packet_templates": [],
        "ceo_brief_section_order": [],
    }
    SchemaStore().validate("writer-draft.schema.json", draft)
    normalized = normalize_writer_draft(job, draft)
    normalized.pop("writer_result_id", None)
    normalized["materialized_by"] = "deterministic_template_fallback"
    normalized["writer_result_id"] = (
        "writer_" + hashlib.sha256(canonical_bytes(normalized)).hexdigest()[:24]
    )
    return normalized


def _materialize_reasoning_draft(
    job: Mapping[str, Any], draft_document: Mapping[str, Any], files: Mapping[str, bytes],
) -> tuple[dict[str, bytes], dict[str, Any]]:
    job_id = str(job["job_id"])
    stage = str(job["stage"])
    updates: dict[str, bytes] = {
        f"tasks/{job_id}/draft.json": canonical_bytes(draft_document),
    }
    data: dict[str, Any] = {"job_id": job_id}
    if stage == "schema_mapping":
        SchemaStore().validate("schema-mapping-draft.schema.json", draft_document)
        canonical_proposal = strict_loads(files["intake/canonical-mapping-proposal.json"])
        if canonical_bytes(draft_document) != canonical_bytes(canonical_proposal):
            raise ContractError(
                "schema mapping draft differs from the deterministic canonical proposal"
            )
    elif stage == "lens":
        normalized = normalize_lens_draft(job, draft_document)
        SchemaStore().validate("normalized-card.schema.json", normalized)
        updates[f"tasks/{job_id}/card.json"] = canonical_bytes(normalized)
        data["card_id"] = normalized["card_id"]
    elif stage == "integrated":
        SchemaStore().validate("integrated-draft.schema.json", draft_document)
        joined = strict_loads(files["reasoning/join-result.json"])
        runtime_context = _pack_reasoning_context(files)
        normalized = normalize_integrated_draft(
            job,
            draft_document,
            allowed_card_refs=set(joined.get("card_refs", [])),
            allowed_claim_refs=set(runtime_context["allowed_claim_refs"]),
            allowed_problem_family_refs=set(runtime_context["allowed_problem_family_refs"]),
            allowed_response_refs=set(runtime_context["allowed_response_refs"]),
            allowed_condition_refs=set(runtime_context["allowed_condition_refs"]),
            allowed_data_request_refs=set(runtime_context["allowed_data_request_refs"]),
        )
        updates[f"tasks/{job_id}/integrated.json"] = canonical_bytes(normalized)
        data["integrated_assessment_id"] = normalized["integrated_assessment_id"]
    elif stage == "deep_dive":
        SchemaStore().validate("deep-dive-draft.schema.json", draft_document)
        runtime_context = _pack_reasoning_context(files)
        integrated = strict_loads(files.get("reasoning/integrated-assessment.json", b"{}"))
        integrated_claim_refs: set[str] = set(runtime_context["allowed_claim_refs"])
        for issue in integrated.get("payload", {}).get("integrated_issues", []):
            payload = issue.get("payload", {}) if isinstance(issue, Mapping) else {}
            for field in (
                "source_candidate_ids", "observation_claim_refs",
                "cause_hypothesis_refs", "counter_hypothesis_refs",
            ):
                integrated_claim_refs.update(
                    str(value) for value in payload.get(field, [])
                    if isinstance(value, str)
                )
        scope = strict_loads(files.get("components/scope.json", b"{}"))
        normalized = normalize_deep_dive_draft(
            job,
            draft_document,
            allowed_issue_refs=set(scope.get("issue_ids", [])),
            allowed_claim_refs=integrated_claim_refs,
            allowed_response_refs=set(runtime_context["allowed_response_refs"]),
            allowed_condition_refs=set(runtime_context["allowed_condition_refs"]),
            allowed_monitoring_metric_refs=set(runtime_context["allowed_monitoring_metric_refs"]),
        )
        updates[f"tasks/{job_id}/deep-dive.json"] = canonical_bytes(normalized)
        data["deep_dive_result_id"] = normalized["deep_dive_result_id"]
    elif stage == "writer":
        SchemaStore().validate("writer-draft.schema.json", draft_document)
        normalized = normalize_writer_draft(job, draft_document)
        updates[f"tasks/{job_id}/writer.json"] = canonical_bytes(normalized)
        data["writer_result_id"] = normalized["writer_result_id"]
    else:
        raise ContractError(f"unsupported reasoning stage: {stage}")
    return updates, data


def _block_reasoning_failure(
    state: Mapping[str, Any], stage: str,
) -> dict[str, Any]:
    if stage == "lens":
        return _advance(
            state, "contract_failure", {"blocker": "reasoning_contract_failure"},
        )
    if stage == "deep_dive":
        return _advance(
            state, "deep_failure", {"blocker": "reasoning_contract_failure"},
        )
    blocked = dict(state)
    blocked["resume_state"] = state["state"]
    blocked["state"] = "blocked"
    blocked["blocker"] = "reasoning_contract_failure"
    return blocked


def _mutation(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    store = _store_for(args)
    pointer = store.state()
    current = int(pointer["revision"])
    if current != args.expected_revision:
        raise RevisionConflict(f"expected revision {args.expected_revision}, current is {current}")
    files = _snapshot_payloads(store, current)
    state = _workflow_state(files)
    if state["state"] in TERMINAL:
        raise ContractError(f"terminal state cannot mutate: {state['state']}")
    data: dict[str, Any] = {}
    exit_code = 0
    command_ok = True
    command_message = "mutation committed"
    if args.command == "scan":
        if state["state"] not in {"context_ready", "data_confirmation_required", "mapping_proposal_ready"}:
            raise ContractError(f"scan is not allowed from {state['state']}")
        effective_mission = _effective_mission(files)
        scan_files = dict(files)
        scan_files["mission/effective-mission-contract.json"] = canonical_bytes(effective_mission)
        updates, scan_data = build_scan_artifacts(
            files=scan_files,
            pointer=pointer,
            run_id=args.run_id,
            current_revision=current,
            source_root=store.verify_revision(current),
            mission=effective_mission,
        )
        updates["mission/effective-mission-contract.json"] = canonical_bytes(effective_mission)
        files.update(updates)
        data.update(scan_data)
        if scan_data["mapping_question_count"] and not scan_data["mapping_applied"]:
            state = _advance(state, "scan", {"mapping_ambiguous": True})
            exit_code = 2
        else:
            state = _advance(state, "scan", {"scan_passed": True})
    elif args.command == "run-components":
        if state["state"] != "deep_dive_authorized":
            raise ContractError(f"run-components is not allowed from {state['state']}")
        overlay = strict_loads(files.get("workflow/hitl-overlay.json", b"{}"))
        scope = overlay.get("deep_dive_scope") if isinstance(overlay, dict) else None
        if not isinstance(scope, dict):
            raise ContractError("approved deep-dive scope is missing")
        core = json.loads(files["evidence/core.json"].decode("utf-8"))
        integrated = strict_loads(files.get("reasoning/integrated-assessment.json", b"{}"))
        plan, runs = execute_authorized_scope(
            files, core, integrated, scope, args.scope_ref,
        )
        files[f"components/plans/deep-dive-{args.scope_ref}.json"] = canonical_bytes(plan.to_dict())
        for run in runs:
            files[f"components/runs/{run['component_run_id']}.json"] = canonical_bytes(run)
        for run_id, document in component_input_documents(plan, runs).items():
            files[f"components/inputs/{run_id}.json"] = canonical_bytes(document)
        updated_core = merge_component_runs(
            core, runs, run_id=args.run_id, revision=current + 1,
            parent_artifact_hash=str(pointer.get("manifest_hash", "")),
        )
        EvidenceCoreValidator().validate(updated_core, source_root=store.verify_revision(current))
        files["evidence/core.json"] = canonical_bytes(updated_core)
        scope_doc = {
            "scope_ref": args.scope_ref,
            "component_ids": sorted(set(scope.get("component_ids", []))),
            "issue_ids": sorted(set(scope.get("issue_ids", []))),
            "component_run_ids": [run["component_run_id"] for run in runs],
        }
        files["components/scope.json"] = canonical_bytes(scope_doc)
        data["component_run_ids"] = scope_doc["component_run_ids"]
        state = _advance(state, "run_deep_components", {"authorized_components_only": True})
        failed_run_ids = [
            str(run["component_run_id"])
            for run in runs
            if run.get("status") == "failed"
        ]
        if failed_run_ids:
            state = _advance(
                state,
                "deep_failure",
                {"blocker": "component_contract_failure"},
            )
            data["failed_component_run_ids"] = failed_run_ids
            exit_code = EXIT_CONTRACT
            command_ok = False
            command_message = "component execution failed; workflow blocked"
    elif args.command == "prepare-finalization":
        if state["state"] not in {"deep_dive_ready", "finalization_jobs_ready"}:
            raise ContractError(f"prepare-finalization is not allowed from {state['state']}")
        revalidate_component_artifacts(files)
        updates, finalization_data = prepare_finalization(
            files, run_id=args.run_id, revision=current + 1,
            parent_artifact_hash=str(pointer.get("manifest_hash", "")),
        )
        candidate_core = json.loads(updates["evidence/core.json"].decode("utf-8"))
        EvidenceCoreValidator().validate(candidate_core, source_root=store.verify_revision(current))
        files.update(updates)
        data.update(finalization_data)
        if state["state"] == "deep_dive_ready":
            state = _advance(state, "prepare_finalization", {"deep_result_valid": True})
    elif args.command == "prepare-jobs":
        allowed_states = {
            "schema_mapping": {"schema_mapping_job_ready"},
            "integrated": {"lens_ready"},
            "deep_dive": {"deep_dive_jobs_ready"},
            "writer": {"finalization_jobs_ready"},
        }
        if args.stage != "lens" and state["state"] not in allowed_states[args.stage]:
            raise ContractError(f"prepare-jobs:{args.stage} is not allowed from {state['state']}")
        jobs = _reasoning_jobs(
            args.stage, files=files, pointer=pointer, run_id=args.run_id, revision=current,
        )
        if args.stage == "lens":
            state = _advance(state, "prepare_lens", {"estimated_card_count": len(jobs)})
            if state["state"] == "scope_narrowing_required":
                jobs = []
                exit_code = 2
        for job in jobs:
            SchemaStore().validate("reasoning-job.schema.json", job)
            files[f"tasks/{job['job_id']}/job.json"] = canonical_bytes(job)
        data["job_ids"] = [job["job_id"] for job in jobs]
    elif args.command == "ingest-result":
        job_path = f"tasks/{args.job_id}/job.json"
        if job_path not in files:
            raise ContractError(f"unknown Reasoning Job: {args.job_id}")
        job = strict_loads(files[job_path])
        if not isinstance(job, Mapping):
            raise IntegrityError(f"Reasoning Job is invalid: {args.job_id}")
        stage = job["stage"]
        expected_states = {
            "schema_mapping": {"schema_mapping_job_ready"},
            "lens": {"lens_jobs_ready"},
            "integrated": {"lens_ready"},
            "deep_dive": {"deep_dive_jobs_ready"},
            "writer": {"finalization_jobs_ready"},
        }
        if state["state"] not in expected_states.get(stage, set()):
            raise ContractError(f"ingest-result:{stage} is not allowed from {state['state']}")
        validation_path = f"tasks/{args.job_id}/validation.json"
        if validation_path in files:
            current_validation = strict_loads(files[validation_path])
            if isinstance(current_validation, Mapping) and current_validation.get("valid") is True:
                raise ContractError(f"Reasoning Job already has an accepted result: {args.job_id}")
        attempts = _reasoning_attempt_records(files, args.job_id, stage)
        if len(attempts) >= 2:
            raise ContractError(f"Reasoning Job exhausted two attempts: {args.job_id}")
        attempt = len(attempts) + 1
        draft = args.draft.read_bytes()
        attempt_root = f"tasks/{args.job_id}/attempts/attempt-{attempt}"
        files[f"{attempt_root}.draft"] = draft

        failure_kind: str | None = None
        validation_error: str | None = None
        materialized_updates: dict[str, bytes] = {}
        materialized_data: dict[str, Any] = {}
        try:
            draft_document = strict_loads(draft)
        except (UnicodeError, ValueError) as error:
            failure_kind = "invalid_json"
            validation_error = str(error)
        else:
            try:
                if not isinstance(draft_document, Mapping):
                    raise ContractError("Reasoning draft must be an object")
                materialized_updates, materialized_data = _materialize_reasoning_draft(
                    job, draft_document, files,
                )
            except ContractError as error:
                failure_kind = "contract"
                validation_error = str(error)

        if failure_kind is None:
            action = "accepted"
            attempt_record = _reasoning_attempt_record(
                job, draft, attempt, valid=True, action=action,
            )
            files.update(materialized_updates)
            data.update(materialized_data)
            files[validation_path] = canonical_bytes(_accepted_validation(
                job, attempt, source="model_draft", action=action,
            ))
        else:
            action = next_attempt_action(
                stage, attempt, required=True, failure_kind=failure_kind,
            )
            attempt_record = _reasoning_attempt_record(
                job,
                draft,
                attempt,
                valid=False,
                action=action,
                failure_kind=failure_kind,
                validation_errors=(validation_error or "draft validation failed",),
            )
            data["validation_errors"] = attempt_record["validation_errors"]
            files[validation_path] = canonical_bytes(attempt_record)
            if action == "deterministic_mapping":
                fallback = strict_loads(files["intake/canonical-mapping-proposal.json"])
                SchemaStore().validate("schema-mapping-draft.schema.json", fallback)
                files[f"tasks/{args.job_id}/draft.json"] = canonical_bytes(fallback)
                files[validation_path] = canonical_bytes(_accepted_validation(
                    job, attempt, source="deterministic_fallback", action=action,
                ))
            elif action == "fallback":
                fallback = _deterministic_writer_fallback(job)
                files[f"tasks/{args.job_id}/writer.json"] = canonical_bytes(fallback)
                files[validation_path] = canonical_bytes(_accepted_validation(
                    job, attempt, source="deterministic_fallback", action=action,
                ))
                data["writer_result_id"] = fallback["writer_result_id"]
            elif action == "blocked":
                state = _block_reasoning_failure(state, stage)
                exit_code = EXIT_CONTRACT
                command_ok = False
                command_message = "reasoning draft failed twice; workflow blocked"
            elif action == "retry":
                exit_code = EXIT_CONTRACT
                command_ok = False
                command_message = "reasoning draft validation failed; one retry remains"
            else:
                raise ContractError(f"unsupported Reasoning attempt action: {action}")
        files[f"{attempt_root}.json"] = canonical_bytes(attempt_record)
        data.update({
            "job_id": args.job_id,
            "attempt": attempt,
            "attempt_action": action,
        })
    elif args.command == "reduce-stage" and args.stage == "lens":
        jobs = []
        for path, payload in files.items():
            if path.startswith("tasks/") and path.endswith("/job.json"):
                job = strict_loads(payload)
                if job.get("stage") == "lens":
                    jobs.append(job)
        if not jobs:
            raise ContractError("no lens Jobs are prepared")
        tasks = [
            {
                "job_id": job["job_id"],
                "required": True,
                "required_signal_ids": job.get("required_signal_ids", []),
            }
            for job in jobs
        ]
        first = sorted(jobs, key=lambda item: item["job_id"])[0]
        manifest = freeze_join_manifest(
            first["artifact_ref"], first["mission_contract_hash"], first["pack_manifest_hash"],
            tasks, "1970-01-01T00:00:00Z",
        )
        results = []
        for job in jobs:
            card_path = f"tasks/{job['job_id']}/card.json"
            validation_path = f"tasks/{job['job_id']}/validation.json"
            validation = strict_loads(files.get(validation_path, b"{}"))
            if (
                card_path not in files
                or not isinstance(validation, Mapping)
                or validation.get("valid") is not True
                or validation.get("source") != "model_draft"
            ):
                raise ContractError(f"lens Job lacks a validated card: {job['job_id']}")
            card = strict_loads(files[card_path])
            status = "valid_not_assessable" if card.get("assessment_status") == "not_assessable" else "completed"
            results.append({"job_id": job["job_id"], "status": status, "card": card})
        joined = reduce_join(manifest, results)
        files["reasoning/join-manifest.json"] = canonical_bytes(manifest)
        files["reasoning/join-result.json"] = canonical_bytes(joined)
        data.update({"join_manifest_id": manifest["join_manifest_id"], "join_result_id": joined["join_result_id"]})
        state = _advance(state, "reduce_lens", {"required_tasks_accepted": True})
    elif args.command == "reduce-stage" and args.stage == "schema_mapping":
        candidates: list[tuple[bytes, Mapping[str, Any]]] = []
        for path, payload in files.items():
            if not path.startswith("tasks/") or not path.endswith("/draft.json"):
                continue
            job_path = path.replace("/draft.json", "/job.json")
            validation_path = path.replace("/draft.json", "/validation.json")
            if job_path not in files or validation_path not in files:
                continue
            candidate_job = strict_loads(files[job_path])
            validation = strict_loads(files[validation_path])
            if (
                isinstance(candidate_job, Mapping)
                and candidate_job.get("stage") == "schema_mapping"
                and isinstance(validation, Mapping)
                and validation.get("valid") is True
                and validation.get("source") in {"model_draft", "deterministic_fallback"}
            ):
                candidates.append((payload, validation))
        if len(candidates) != 1:
            raise ContractError("schema_mapping reducer requires exactly one validated draft")
        proposal = strict_loads(candidates[0][0])
        SchemaStore().validate("schema-mapping-draft.schema.json", proposal)
        canonical_proposal = strict_loads(files["intake/canonical-mapping-proposal.json"])
        if canonical_bytes(proposal) != canonical_bytes(canonical_proposal):
            raise ContractError("schema mapping draft differs from the deterministic canonical proposal")
        files["reasoning/schema-mapping-proposal.json"] = canonical_bytes(proposal)
        data["reduction_source"] = candidates[0][1]["source"]
        state = _advance(state, "ingest_schema_mapping", {"draft_or_fallback_valid": True})
    elif args.command == "reduce-stage" and args.stage in {"integrated", "deep_dive", "writer"}:
        artifact_names = {
            "integrated": ("integrated.json", "reasoning/integrated-assessment.json", "integrated_assessment_id"),
            "deep_dive": ("deep-dive.json", "reasoning/deep-dive-result.json", "deep_dive_result_id"),
            "writer": ("writer.json", "reasoning/writer-result.json", "writer_result_id"),
        }
        leaf, destination, identifier_key = artifact_names[args.stage]
        candidates: list[tuple[dict[str, Any], Mapping[str, Any]]] = []
        for path, payload in files.items():
            if path.startswith("tasks/") and path.endswith(f"/{leaf}"):
                task_root = path.rsplit("/", 1)[0]
                job_path = f"{task_root}/job.json"
                validation_path = f"{task_root}/validation.json"
                if job_path not in files or validation_path not in files:
                    continue
                candidate_job = strict_loads(files[job_path])
                validation = strict_loads(files[validation_path])
                materialized = strict_loads(payload)
                allowed_sources = (
                    {"model_draft", "deterministic_fallback"}
                    if args.stage == "writer" else {"model_draft"}
                )
                if (
                    isinstance(candidate_job, Mapping)
                    and candidate_job.get("stage") == args.stage
                    and isinstance(validation, Mapping)
                    and validation.get("valid") is True
                    and validation.get("source") in allowed_sources
                    and isinstance(materialized, dict)
                ):
                    candidates.append((materialized, validation))
        if len(candidates) != 1:
            raise ContractError(f"{args.stage} reducer requires exactly one validated result")
        materialized, validation = candidates[0]
        files[destination] = canonical_bytes(materialized)
        data[identifier_key] = materialized[identifier_key]
        data["reduction_source"] = validation["source"]
        events = {
            "integrated": ("ingest_integrated", {"barrier_and_draft_valid": True}),
            "deep_dive": ("ingest_deep_result", {"required_deep_valid": True}),
            "writer": ("ingest_writer", {"grade_and_writer_valid": True}),
        }
        if args.stage == "writer" and validation["source"] == "deterministic_fallback":
            event, event_context = (
                "writer_fallback", {"fallback_valid_after_two_attempts": True},
            )
        else:
            event, event_context = events[args.stage]
        state = _advance(state, event, event_context)
    elif args.command == "approval-request":
        overlay = strict_loads(args.overlay.read_bytes())
        if not isinstance(overlay, dict) or not isinstance(overlay.get("patch_operations", []), list):
            raise ContractError("HITL overlay must contain patch_operations")
        operations = overlay.get("patch_operations", [])
        base_overlay = strict_loads(files.get("workflow/hitl-overlay.json", b"{}"))
        preview = apply_overlay(
            base_overlay, args.gate, operations,
            runtime_context=overlay.get("runtime_context", {}),
        )
        paths = [item.get("path", "") for item in operations if isinstance(item, dict)]
        invalidated = sorted(invalidated_gates(paths))
        if args.gate == "context":
            if state["state"] != "context_confirmation_required":
                raise ContractError(f"context approval is not allowed from {state['state']}")
        elif args.gate == "data":
            if state["state"] == "mapping_proposal_ready":
                state = _advance(state, "request_data_approval", {"proposal_diff_valid": True})
            elif state["state"] != "data_confirmation_required":
                raise ContractError(f"data approval is not allowed from {state['state']}")
        elif args.gate == "scope_narrowing":
            if state["state"] != "scope_narrowing_required":
                raise ContractError(f"scope approval is not allowed from {state['state']}")
        elif args.gate == "diagnostic":
            state = _advance(state, "request_diagnostic_approval", {"issues_valid": True})
        elif args.gate == "final":
            state = _advance(state, "request_final_approval", {"output_valid": True})
        next_state = dict(state)
        next_state["revision"] = current + 1
        additional = {
            "workflow/state.json": canonical_bytes(next_state),
            "workflow/pending-overlay.json": canonical_bytes(preview),
            "workflow/pending-runtime-context.json": canonical_bytes(overlay.get("runtime_context", {})),
            f"audit/events/r{current + 1:04d}-approval-request.json": canonical_bytes({
                "command": "approval-request", "gate": args.gate,
                "from_revision": current, "to_revision": current + 1,
            }),
        }
        service = ApprovalService(RevisionManager(store))
        request_record, nonce, revision = service.request(
            expected_revision=current,
            gate=args.gate,
            base_artifact_ref=f"{args.run_id}@r{current:04d}",
            base_artifact_hash=str(pointer.get("manifest_hash", "")),
            patch_operations=operations,
            invalidated_approval_ids=invalidated,
            result_preview_hash=hashlib.sha256(canonical_bytes(preview)).hexdigest(),
            additional_updates=additional,
        )
        return 2, response(
            command=args.command, ok=True, code=2, message="human action required",
            run_id=args.run_id, revision=revision, state=next_state["state"],
            data={"approval_request_id": request_record["approval_request_id"], "nonce": nonce},
        )
    elif args.command == "approve-interactive":
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise IntegrityError("interactive approval requires TTY stdin and stdout")
        revisions = RevisionManager(store)
        request_path = f"approvals/requests/{args.request_id}.json"
        request_record = strict_loads(revisions.read(request_path, revision=current))
        base_overlay = strict_loads(files.get("workflow/hitl-overlay.json", b"{}"))
        runtime_context = strict_loads(files.get("workflow/pending-runtime-context.json", b"{}"))
        materialized = apply_overlay(
            base_overlay, request_record["gate"], request_record.get("patch_operations", []),
            runtime_context=runtime_context,
        )
        gate = request_record["gate"]
        if gate == "context":
            base_mission = strict_loads(files["mission/mission-contract.json"])
            if not isinstance(base_mission, Mapping):
                raise ContractError("Mission Contract must be an object")
            materialize_confirmed_mission(
                base_mission,
                materialized,
                actor_id="pending-context-actor",
                actor_role="business_owner",
                confirmed_at=str(request_record["created_at"]),
            )
            next_state = _advance(state, "approve_context", {"approval_valid": True})
        elif gate == "data":
            effective_mission = _effective_mission(files)
            scan_updates, scan_data = build_scan_artifacts(
                files=files,
                pointer=pointer,
                run_id=args.run_id,
                current_revision=current,
                source_root=store.verify_revision(current),
                mission=effective_mission,
                mapping_overlay=materialized,
            )
            candidate_core = json.loads(scan_updates["evidence/core.json"].decode("utf-8"))
            EvidenceCoreValidator().validate(
                candidate_core, source_root=store.verify_revision(current),
            )
            next_state = _advance(state, "approve_data", {"mapping_patch_valid": True})
        elif gate == "scope_narrowing":
            next_state = _advance(state, "approve_scope", {"scope_valid": True})
        elif gate == "diagnostic":
            integrated = strict_loads(files.get("reasoning/integrated-assessment.json", b"{}"))
            issues = integrated.get("payload", {}).get("integrated_issues", [])
            issue_dispositions = materialized.get("issue_dispositions", {})
            decision_dispositions = materialized.get("decision_dispositions", {})
            authorizations = materialized.get("verification_authorizations", {})
            for issue in issues:
                local_key = issue.get("local_key")
                issue_status = _overlay_status(issue_dispositions.get(local_key))
                decision_status = _overlay_status(decision_dispositions.get(local_key))
                if issue_status not in {"accepted", "rejected", "disputed"}:
                    raise ContractError(f"Diagnostic disposition is incomplete: {local_key}")
                if issue_status != "rejected" and decision_status not in {"needed", "not_needed", "disputed"}:
                    raise ContractError(f"Decision disposition is incomplete: {local_key}")
                if issue_status == "disputed" and not bool(authorizations.get(local_key, False)):
                    raise ContractError(f"Disputed issue lacks verification authorization: {local_key}")
            deep_scope = materialized.get("deep_dive_scope", {})
            next_state = _advance(state, "approve_diagnostic", {
                "approval_valid": True,
                "deep_scope_empty": not bool(deep_scope.get("component_ids") or deep_scope.get("issue_ids")),
            })
        elif gate == "final":
            delivery_scope = materialized.get("delivery_scope")
            if not isinstance(delivery_scope, dict) or not delivery_scope:
                raise ContractError("Final approval requires a non-empty delivery scope")
            next_state = _advance(state, "approve_final", {"all_dispositions_complete": True})
        else:
            raise ContractError(f"unsupported approval gate: {gate}")
        next_state["revision"] = current + 1
        additional = {
            "workflow/state.json": canonical_bytes(next_state),
            "workflow/hitl-overlay.json": canonical_bytes(materialized),
            "workflow/pending-overlay.json": None,
            "workflow/pending-runtime-context.json": None,
            f"audit/events/r{current + 1:04d}-approve-interactive.json": canonical_bytes({
                "command": "approve-interactive", "gate": request_record["gate"],
                "from_revision": current, "to_revision": current + 1,
            }),
        }
        if gate == "data":
            additional.update(scan_updates)
        try:
            approval, revision = ApprovalService(revisions).approve_interactive(
                args.request_id, expected_revision=current,
                input_stream=sys.stdin, output_stream=sys.stderr,
                additional_updates=additional,
            )
        except ContractError as error:
            raise IntegrityError(str(error)) from error
        return 0, response(
            command=args.command, ok=True, code=0, message="approval committed",
            run_id=args.run_id, revision=revision, state=next_state["state"],
            data={"approval_id": approval["approval_id"], "gate": approval["gate"]},
        )
    elif args.command == "decide-interactive":
        revisions = RevisionManager(store)
        request_path = f"approvals/requests/{args.request_id}.json"
        request_record = strict_loads(revisions.read(request_path, revision=current))
        gate = request_record.get("gate")
        expected_states = {
            "context": "context_confirmation_required",
            "data": "data_confirmation_required",
            "scope_narrowing": "scope_narrowing_required",
            "diagnostic": "diagnostic_approval_required",
            "final": "final_approval_required",
        }
        if gate not in expected_states or state["state"] != expected_states[gate]:
            raise ContractError(
                f"{args.decision} for {gate} is not allowed from {state['state']}"
            )
        if args.decision == "reject":
            if args.change_scope is not None:
                raise ContractError("reject does not accept change_scope")
            next_state = _advance(state, "stop", {})
        elif gate == "data":
            if args.change_scope not in {None, "data"}:
                raise ContractError("Data request_changes only accepts change_scope=data")
            next_state = dict(state)
        elif gate == "diagnostic":
            if args.change_scope not in {"data", "scan", "reasoning"}:
                raise ContractError("Diagnostic request_changes requires data, scan, or reasoning scope")
            next_state = _advance(
                state, "request_diagnostic_changes", {"change_scope": args.change_scope},
            )
        elif gate == "final":
            if args.change_scope not in {"deep", "wording", "routing"}:
                raise ContractError("Final request_changes requires deep, wording, or routing scope")
            next_state = _advance(
                state, "request_final_changes", {"change_scope": args.change_scope},
            )
        else:
            raise ContractError(f"request_changes is not supported for {gate}")
        next_state["revision"] = current + 1
        additional = {
            "workflow/state.json": canonical_bytes(next_state),
            "workflow/pending-overlay.json": None,
            "workflow/pending-runtime-context.json": None,
            f"audit/events/r{current + 1:04d}-decide-interactive.json": canonical_bytes({
                "command": "decide-interactive",
                "decision": args.decision,
                "gate": gate,
                "change_scope": args.change_scope,
                "from_revision": current,
                "to_revision": current + 1,
            }),
        }
        try:
            decision_record, revision = ApprovalService(revisions).decide_interactive(
                args.request_id,
                decision=args.decision,
                expected_revision=current,
                input_stream=sys.stdin,
                output_stream=sys.stderr,
                additional_updates=additional,
            )
        except ContractError as error:
            raise IntegrityError(str(error)) from error
        return 0, response(
            command=args.command,
            ok=True,
            code=0,
            message="human decision committed",
            run_id=args.run_id,
            revision=revision,
            state=next_state["state"],
            data={
                "approval_id": decision_record["approval_id"],
                "gate": gate,
                "decision": args.decision,
            },
        )
    elif args.command == "resume":
        blocker_resolved = _recorded_blocker_is_resolved(files, state)
        if not blocker_resolved:
            raise ContractError("recorded blocker is unresolved")
        state = _advance(
            state,
            "resume",
            {"blocker_resolved": blocker_resolved, "expected_revision": current},
        )
    elif args.command == "stop":
        state = _advance(state, "stop", {})
    elif args.command == "cancel":
        state = _advance(state, "cancel", {})
    elif args.command == "finalize":
        if state["state"] != "delivery_approved":
            raise ContractError("finalize requires delivery_approved state")
        revalidate_component_artifacts(files)
        package = build_delivery_package(files, run_id=args.run_id, revision=current + 1)
        files.update(package)
        data["delivery_files"] = sorted(package)
        state = _advance(state, "finalize", {"final_validator_passed": True})

    new_revision = current + 1
    state["revision"] = new_revision
    files["workflow/state.json"] = canonical_bytes(state)
    files[f"audit/events/r{new_revision:04d}-{args.command}.json"] = canonical_bytes(
        {"command": args.command, "from_revision": current, "to_revision": new_revision}
    )
    store.publish(current, files)
    return exit_code, response(
        command=args.command, ok=command_ok, code=exit_code,
        message="human action required" if exit_code == 2 else command_message,
        run_id=args.run_id, revision=new_revision, state=state["state"], data=data,
    )


def _dispatch(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    if args.command == "preflight":
        result = _bootstrap_preflight()
        return 0, response(command="preflight", ok=True, code=0, message="preflight passed", data=result)
    if args.command == "start":
        return _start(args)
    if args.command == "status":
        return _status(args)
    if args.command == "pending-action":
        return _pending_action(args)
    if args.command == "preview-human-response":
        return _preview_human_response(args)
    if args.command == "submit-human-response":
        return _submit_human_response(args)
    if args.command == "validate":
        return _validate(args)
    if args.command == "export-web-report":
        return _export_web_report(args)
    if args.command == "validate-web-report":
        return _validate_web_report(args)
    if args.command == "render":
        return _render(args)
    return _mutation(args)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        code, value = _dispatch(args)
    except RevisionConflict as error:
        code = EXIT_CONFLICT
        value = response(command=args.command, ok=False, code=code, message=str(error))
    except IntegrityError as error:
        code = EXIT_INTEGRITY
        value = response(command=args.command, ok=False, code=code, message=str(error))
    except (ContractError, ValueError, FileNotFoundError, json.JSONDecodeError) as error:
        code = EXIT_CONTRACT
        value = response(command=args.command, ok=False, code=code, message=str(error))
    except Exception as error:  # pragma: no cover - defensive CLI boundary
        print(f"internal error: {error}", file=sys.stderr)
        code = EXIT_INTERNAL
        value = response(command=args.command, ok=False, code=code, message="internal error")
    _emit(value)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
