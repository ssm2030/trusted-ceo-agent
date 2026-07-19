from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from trusted_ceo_agent.application.models import (
    CreateRunRequest,
    ExportWebReportRequest,
    HumanResponseRequest,
    MutationRequest,
    PrepareResultQuestionRequest,
    RevisionRequest,
    RunRequest,
    SubmitHumanResponseRequest,
    ValidateResultAnswerRequest,
)
from trusted_ceo_agent.application.run_application import TrustedCeoApplication
from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.contracts.cli_response import response
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, IntegrityError, RevisionConflict
from trusted_ceo_agent.evidence.core import EvidenceCoreValidator
from trusted_ceo_agent.filesystem import ensure_within
from trusted_ceo_agent.mission import (
    is_confirmed_mission,
    materialize_confirmed_mission,
    validate_confirmed_mission,
)
from trusted_ceo_agent.outputs.validation import revalidate_package
from trusted_ceo_agent.outputs.render import render_package
from trusted_ceo_agent.questions.scope import SCOPE_KINDS
from trusted_ceo_agent.runtime_scan import build_scan_artifacts
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from trusted_ceo_agent.web_report.eligibility import decide_viewer_eligibility
from trusted_ceo_agent.workflow.approvals import ApprovalService, current_approvals
from trusted_ceo_agent.workflow.overlays import apply_overlay
from trusted_ceo_agent.workflow.revisions import RevisionManager
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
    components.add_argument("--accounting-input", type=Path)
    components.add_argument("--professional-input", type=Path)

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
    export_web_report.add_argument("--input-manifest", type=Path, required=True)

    validate_web_report = commands.add_parser("validate-web-report")
    _add_run(validate_web_report)
    validate_web_report.add_argument("--revision", type=int, required=True)
    validate_web_report.add_argument("--bundle", type=Path, required=True)

    prepare_question = commands.add_parser("prepare-result-question")
    _add_run(prepare_question)
    prepare_question.add_argument("--revision", type=int, required=True)
    prepare_question.add_argument("--question-file", type=Path, required=True)
    prepare_question.add_argument("--scope-kind", choices=sorted(SCOPE_KINDS), required=True)
    prepare_question.add_argument("--scope-instance-id", required=True)
    prepare_question.add_argument(
        "--privacy-classification",
        choices=("poc_deidentified", "company_restricted"),
        required=True,
    )

    validate_answer = commands.add_parser("validate-result-answer")
    _add_run(validate_answer)
    validate_answer.add_argument("--revision", type=int, required=True)
    validate_answer.add_argument("--job", type=Path, required=True)
    validate_answer.add_argument("--draft", type=Path, required=True)

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


def _application_payload(result: Any) -> tuple[int, dict[str, Any]]:
    return result.code, {"contract_version": "1.0.0", **result.to_cli_payload()}


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


def _start(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    result = TrustedCeoApplication(args.artifact_root).create_run(CreateRunRequest(
        mission=args.mission_contract,
        inputs=tuple(args.input),
        run_owner_actor_id=args.run_owner_actor_id,
        run_id=None,
    ))
    return _application_payload(result)


def _status(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    result = TrustedCeoApplication(args.artifact_root).status(RunRequest(args.run_id))
    return _application_payload(result)


def _pending_action(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    result = TrustedCeoApplication(args.artifact_root).pending_action(RunRequest(args.run_id))
    return _application_payload(result)


def _preview_human_response(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    result = TrustedCeoApplication(args.artifact_root).preview_human_response(
        HumanResponseRequest(
            run_id=args.run_id,
            expected_revision=args.expected_revision,
            action_id=args.action_id,
            action_content_hash=args.action_content_hash,
            response=args.response,
        )
    )
    return _application_payload(result)


def _submit_human_response(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    result = TrustedCeoApplication(args.artifact_root).submit_human_response(
        SubmitHumanResponseRequest(
            run_id=args.run_id,
            expected_revision=args.expected_revision,
            action_id=args.action_id,
            action_content_hash=args.action_content_hash,
            response=args.response,
            idempotency_key=args.idempotency_key,
        )
    )
    return _application_payload(result)


def _validate(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    result = TrustedCeoApplication(args.artifact_root).validate(
        RevisionRequest(run_id=args.run_id, revision=args.revision)
    )
    return _application_payload(result)


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
    result = TrustedCeoApplication(args.artifact_root).export_web_report(
        ExportWebReportRequest(
            run_id=args.run_id,
            revision=args.revision,
            output=args.output,
            input_manifest=args.input_manifest,
        )
    )
    return _application_payload(result)


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


def _prepare_result_question(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    result = TrustedCeoApplication(args.artifact_root).prepare_result_question(
        PrepareResultQuestionRequest(
            run_id=args.run_id,
            revision=args.revision,
            question=args.question_file,
            scope_kind=args.scope_kind,
            scope_instance_id=args.scope_instance_id,
            privacy_classification=args.privacy_classification,
        )
    )
    return _application_payload(result)


def _validate_result_answer(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    result = TrustedCeoApplication(args.artifact_root).validate_result_answer(
        ValidateResultAnswerRequest(
            run_id=args.run_id,
            revision=args.revision,
            job=args.job,
            draft=args.draft,
        )
    )
    return _application_payload(result)


def _mutation(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    if args.command not in {"approve-interactive", "decide-interactive"}:
        parameters: dict[str, Any] = {}
        if args.command == "run-components":
            parameters = {
                "scope_ref": args.scope_ref,
                "accounting_input": args.accounting_input,
                "professional_input": args.professional_input,
            }
        elif args.command in {"prepare-jobs", "reduce-stage"}:
            parameters = {"stage": args.stage}
        elif args.command == "ingest-result":
            _, draft_payload = _stable_read(args.draft.resolve(strict=True))
            parameters = {
                "job_id": args.job_id,
                "draft_document": draft_payload,
            }
        elif args.command == "approval-request":
            _, overlay_payload = _stable_read(args.overlay.resolve(strict=True))
            parameters = {
                "gate": args.gate,
                "overlay_document": overlay_payload,
            }
        result = TrustedCeoApplication(args.artifact_root).mutate(MutationRequest(
            artifact_root=args.artifact_root,
            run_id=args.run_id,
            expected_revision=args.expected_revision,
            command=args.command,
            parameters=parameters,
        ))
        return _application_payload(result)

    store = _store_for(args)
    pointer = store.state()
    current = int(pointer["revision"])
    if current != args.expected_revision:
        raise RevisionConflict(f"expected revision {args.expected_revision}, current is {current}")
    files = _snapshot_payloads(store, current)
    state = _workflow_state(files)
    if state["state"] in TERMINAL:
        raise ContractError(f"terminal state cannot mutate: {state['state']}")

    if args.command == "approve-interactive":
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
            scan_updates, _ = build_scan_artifacts(
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
    if args.command == "prepare-result-question":
        return _prepare_result_question(args)
    if args.command == "validate-result-answer":
        return _validate_result_answer(args)
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
