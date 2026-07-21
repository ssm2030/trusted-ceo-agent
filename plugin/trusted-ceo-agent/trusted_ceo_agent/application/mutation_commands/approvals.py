from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from trusted_ceo_agent.application.models import ApplicationResult
from trusted_ceo_agent.application.mutation_session import MutationSession
from trusted_ceo_agent.application.mutation_support import (
    advance as _advance,
    application_result as _application_result,
    effective_mission as _effective_mission,
    overlay_status as _overlay_status,
)
from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.evidence.core import EvidenceCoreValidator
from trusted_ceo_agent.mission import materialize_confirmed_mission
from trusted_ceo_agent.runtime_scan import build_scan_artifacts
from trusted_ceo_agent.workflow.approvals import ApprovalService
from trusted_ceo_agent.workflow.overlays import apply_overlay, invalidated_gates
from trusted_ceo_agent.workflow.revisions import RevisionManager


COMMANDS = frozenset({"approval-request", "approve-web", "decide-web"})
CommandResult = bool | tuple[int, ApplicationResult]


def handle(session: MutationSession) -> CommandResult:
    if session.args.command not in COMMANDS:
        return False
    args = session.args
    store = session.store
    pointer = session.pointer
    current = session.current
    files = session.files
    state = session.state
    if args.command == "approval-request":
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
            if state["state"] == "integrated_draft":
                state = _advance(state, "request_diagnostic_approval", {"issues_valid": True})
            elif state["state"] != "diagnostic_approval_required":
                raise ContractError(f"diagnostic approval is not allowed from {state['state']}")
        elif args.gate == "final":
            if state["state"] == "writer_ready":
                state = _advance(state, "request_final_approval", {"output_valid": True})
            elif state["state"] != "final_approval_required":
                raise ContractError(f"final approval is not allowed from {state['state']}")
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
        return 2, _application_result(
            command=args.command, ok=True, code=2, message="human action required",
            run_id=args.run_id, revision=revision, state=next_state["state"],
            data={"approval_request_id": request_record["approval_request_id"], "nonce": nonce},
        )
    elif args.command == "approve-web":
        revisions = RevisionManager(store)
        request_path = f"approvals/requests/{args.request_id}.json"
        request_record = strict_loads(revisions.read(request_path, revision=current))
        base_overlay = strict_loads(files.get("workflow/hitl-overlay.json", b"{}"))
        runtime_context = strict_loads(
            files.get("workflow/pending-runtime-context.json", b"{}")
        )
        materialized = apply_overlay(
            base_overlay,
            request_record["gate"],
            request_record.get("patch_operations", []),
            runtime_context=runtime_context,
        )
        gate = request_record["gate"]
        scan_updates: dict[str, bytes] = {}
        if gate == "context":
            base_mission = strict_loads(files["mission/mission-contract.json"])
            if not isinstance(base_mission, Mapping):
                raise ContractError("Mission Contract must be an object")
            materialize_confirmed_mission(
                base_mission,
                materialized,
                actor_id=args.actor_id,
                actor_role=args.actor_role,
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
                candidate_core,
                source_root=store.verify_revision(current),
            )
            next_state = _advance(state, "approve_data", {"mapping_patch_valid": True})
        elif gate == "scope_narrowing":
            next_state = _advance(state, "approve_scope", {"scope_valid": True})
        elif gate == "diagnostic":
            integrated = strict_loads(
                files.get("reasoning/integrated-assessment.json", b"{}")
            )
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
                if (
                    issue_status != "rejected"
                    and decision_status not in {"needed", "not_needed", "disputed"}
                ):
                    raise ContractError(f"Decision disposition is incomplete: {local_key}")
                if issue_status == "disputed" and not bool(authorizations.get(local_key, False)):
                    raise ContractError(
                        f"Disputed issue lacks verification authorization: {local_key}"
                    )
            deep_scope = materialized.get("deep_dive_scope", {})
            next_state = _advance(state, "approve_diagnostic", {
                "approval_valid": True,
                "deep_scope_empty": not bool(
                    deep_scope.get("component_ids") or deep_scope.get("issue_ids")
                ),
            })
        elif gate == "final":
            delivery_scope = materialized.get("delivery_scope")
            if not isinstance(delivery_scope, dict) or not delivery_scope:
                raise ContractError("Final approval requires a non-empty delivery scope")
            next_state = _advance(
                state,
                "approve_final",
                {"all_dispositions_complete": True},
            )
        else:
            raise ContractError(f"unsupported approval gate: {gate}")
        next_state["revision"] = current + 1
        additional = {
            "workflow/state.json": canonical_bytes(next_state),
            "workflow/hitl-overlay.json": canonical_bytes(materialized),
            "workflow/pending-overlay.json": None,
            "workflow/pending-runtime-context.json": None,
            f"audit/events/r{current + 1:04d}-approve-web.json": canonical_bytes({
                "command": "approve-web",
                "gate": gate,
                "from_revision": current,
                "to_revision": current + 1,
            }),
        }
        if gate == "data":
            additional.update(scan_updates)
        approval, revision = ApprovalService(revisions).approve_web(
            args.request_id,
            expected_revision=current,
            actor_id=args.actor_id,
            actor_role=args.actor_role,
            nonce=args.nonce,
            rationale=args.rationale,
            browser_session_fingerprint=args.browser_session_fingerprint,
            response_hash=args.response_hash,
            additional_updates=additional,
        )
        return 0, _application_result(
            command=args.command,
            ok=True,
            code=0,
            message="approval committed",
            run_id=args.run_id,
            revision=revision,
            state=next_state["state"],
            data={"approval_id": approval["approval_id"], "gate": approval["gate"]},
        )
    elif args.command == "decide-web":
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
                raise ContractError(
                    "Diagnostic request_changes requires data, scan, or reasoning scope"
                )
            next_state = _advance(
                state,
                "request_diagnostic_changes",
                {"change_scope": args.change_scope},
            )
        elif gate == "final":
            if args.change_scope not in {"deep", "wording", "routing"}:
                raise ContractError(
                    "Final request_changes requires deep, wording, or routing scope"
                )
            next_state = _advance(
                state,
                "request_final_changes",
                {"change_scope": args.change_scope},
            )
        else:
            raise ContractError(f"request_changes is not supported for {gate}")
        next_state["revision"] = current + 1
        additional = {
            "workflow/state.json": canonical_bytes(next_state),
            "workflow/pending-overlay.json": None,
            "workflow/pending-runtime-context.json": None,
            f"audit/events/r{current + 1:04d}-decide-web.json": canonical_bytes({
                "command": "decide-web",
                "decision": args.decision,
                "gate": gate,
                "change_scope": args.change_scope,
                "from_revision": current,
                "to_revision": current + 1,
            }),
        }
        decision_record, revision = ApprovalService(revisions).decide_web(
            args.request_id,
            decision=args.decision,
            expected_revision=current,
            actor_id=args.actor_id,
            actor_role=args.actor_role,
            nonce=args.nonce,
            rationale=args.rationale,
            browser_session_fingerprint=args.browser_session_fingerprint,
            response_hash=args.response_hash,
            additional_updates=additional,
        )
        return 0, _application_result(
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
    session.files = files
    session.state = state
    return True
