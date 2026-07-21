from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from trusted_ceo_agent.accounting.input_adapter import build_accounting_request
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
from trusted_ceo_agent.cli_context import (
    PLUGIN_ROOT,
    advance as _advance,
    bootstrap_preflight as _bootstrap_preflight,
    effective_mission as _effective_mission,
    overlay_status as _overlay_status,
    snapshot_payloads as _snapshot_payloads,
    stable_read as _stable_read,
    store_for as _store_for,
    workflow_state as _workflow_state,
)
from trusted_ceo_agent.contracts.cli_response import response
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, IntegrityError, RevisionConflict
from trusted_ceo_agent.evidence.core import EvidenceCoreValidator
from trusted_ceo_agent.filesystem import ensure_within
from trusted_ceo_agent.mission import materialize_confirmed_mission
from trusted_ceo_agent.outputs.render import render_package
from trusted_ceo_agent.outputs.validation import revalidate_package
from trusted_ceo_agent.runtime_components import normalize_authorized_scope
from trusted_ceo_agent.runtime_scan import build_scan_artifacts
from trusted_ceo_agent.web_report.eligibility import decide_viewer_eligibility
from trusted_ceo_agent.web_report.output import publish_web_report_output
from trusted_ceo_agent.workflow.approvals import ApprovalService
from trusted_ceo_agent.workflow.overlays import apply_overlay
from trusted_ceo_agent.workflow.revisions import RevisionManager
from trusted_ceo_agent.workflow.state_machine import TERMINAL

EXIT_INTEGRITY = 4


def _application_payload(result: Any) -> tuple[int, dict[str, Any]]:
    return result.code, {"contract_version": "1.0.0", **result.to_cli_payload()}


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


def _prepare_accounting_input(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    store = _store_for(args)
    current = int(store.state()["revision"])
    if args.revision != current:
        raise RevisionConflict(
            f"expected revision {args.revision}, current is {current}"
        )
    store.verify_revision(current)
    files = _snapshot_payloads(store, current)
    state = _workflow_state(files)
    if state["state"] != "deep_dive_authorized":
        raise ContractError(
            "prepare-accounting-input requires deep_dive_authorized state"
        )

    overlay = strict_loads(files.get("workflow/hitl-overlay.json", b"{}"))
    scope = overlay.get("deep_dive_scope") if isinstance(overlay, Mapping) else None
    if not isinstance(scope, Mapping):
        raise ContractError("approved deep-dive scope is missing")
    normalized_scope = normalize_authorized_scope(scope)
    expected_scope_ref = make_id("scope", normalized_scope)
    if args.scope_ref != expected_scope_ref:
        raise ContractError("scope ref does not match the approved diagnostic scope")
    if "accounting" not in normalized_scope["required_inputs"]:
        raise ContractError("approved scope does not require accounting input")

    registry_payload = files.get("sources/registry.json")
    if registry_payload is None:
        raise ContractError("Source Registry is missing")
    strict_loads(registry_payload)
    registry = json.loads(registry_payload.decode("utf-8"))
    if not isinstance(registry, list):
        raise ContractError("Source Registry must be an array")
    matching_sources = [
        item
        for item in registry
        if isinstance(item, Mapping) and item.get("source_id") == args.source_id
    ]
    if len(matching_sources) != 1:
        raise ContractError("Source Registry must contain exactly one matching source")
    source = dict(matching_sources[0])
    SchemaStore().validate("source.schema.json", source)
    if source["access_policy"] != "permitted":
        raise ContractError("accounting source must be permitted")
    if source["evidence_usage"] != "primary":
        raise ContractError("accounting source must be primary evidence")

    registered_digest = str(source["sha256"])
    if source["source_id"] != f"source_{registered_digest[:24]}":
        raise IntegrityError("Source ID does not bind to the registered snapshot hash")
    expected_snapshot_ref = f"sources/blobs/{registered_digest}"
    if source["snapshot_ref"] != expected_snapshot_ref:
        raise IntegrityError("Source snapshot ref does not bind to the registered hash")
    blob = files.get(expected_snapshot_ref)
    if blob is None:
        raise IntegrityError("registered Source snapshot is missing")
    if int(source["size_bytes"]) != len(blob):
        raise IntegrityError("Source snapshot size mismatch")
    digest = hashlib.sha256(blob).hexdigest()
    if digest != registered_digest:
        raise IntegrityError("Source snapshot hash mismatch")

    document = strict_loads(blob)
    if not isinstance(document, Mapping):
        raise ContractError("accounting source snapshot must be an object")
    request = build_accounting_request(
        document,
        run_id=args.run_id,
        revision=current + 1,
        scope_ref=args.scope_ref,
        source_id=args.source_id,
        snapshot_sha256=digest,
    )
    payload = canonical_bytes(request)
    destination = ensure_within(Path.cwd(), args.output)
    run_dir = store.open_run(args.run_id)
    publish_web_report_output(
        destination,
        payload,
        workspace=Path.cwd(),
        run_dir=run_dir,
        plugin_root=PLUGIN_ROOT,
    )
    return 0, response(
        command=args.command,
        ok=True,
        code=0,
        message="accounting input prepared",
        run_id=args.run_id,
        revision=current,
        state=state["state"],
        data={
            "source_id": args.source_id,
            "source_sha256": digest,
            "scope_ref": args.scope_ref,
            "target_revision": current + 1,
            "request_hash": hashlib.sha256(payload).hexdigest(),
        },
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


def dispatch(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
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
    if args.command == "prepare-accounting-input":
        return _prepare_accounting_input(args)
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
