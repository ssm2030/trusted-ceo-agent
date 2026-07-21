from __future__ import annotations

import json
from typing import Any

from trusted_ceo_agent.application.mutation_components import (
    accounting_component_artifacts as _accounting_component_artifacts,
    professional_component_artifacts as _professional_component_artifacts,
)
from trusted_ceo_agent.application.mutation_session import MutationSession
from trusted_ceo_agent.application.mutation_support import (
    advance as _advance,
    effective_mission as _effective_mission,
)
from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.evidence.core import EvidenceCoreValidator
from trusted_ceo_agent.evidence.revalidation import revalidate_component_artifacts
from trusted_ceo_agent.runtime_components import (
    component_input_documents,
    execute_authorized_scope,
    merge_component_runs,
    normalize_authorized_scope,
)
from trusted_ceo_agent.runtime_finalization import prepare_finalization
from trusted_ceo_agent.runtime_scan import build_scan_artifacts
from trusted_ceo_agent.workflow.completion import verify_completion_assessment


EXIT_CONTRACT = 3
COMMANDS = frozenset({"scan", "run-components", "prepare-finalization"})


def handle(session: MutationSession) -> bool:
    if session.args.command not in COMMANDS:
        return False
    args = session.args
    store = session.store
    pointer = session.pointer
    current = session.current
    files = session.files
    state = session.state
    data = session.data
    exit_code = session.exit_code
    command_ok = session.command_ok
    command_message = session.command_message
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
        normalized_scope = normalize_authorized_scope(scope)
        required_inputs = set(normalized_scope["required_inputs"])
        provided_inputs = {
            name
            for name, value in (
                ("accounting", args.accounting_input),
                ("professional", args.professional_input),
            )
            if value is not None
        }
        missing_inputs = sorted(required_inputs - provided_inputs)
        if missing_inputs:
            raise ContractError(
                f"required input is missing from approved scope: {missing_inputs}"
            )
        core = json.loads(files["evidence/core.json"].decode("utf-8"))
        integrated = strict_loads(files.get("reasoning/integrated-assessment.json", b"{}"))
        plan, runs = execute_authorized_scope(
            files, core, integrated, scope, args.scope_ref,
        )
        accounting_bundle: dict[str, Any] | None = None
        if args.accounting_input is not None:
            accounting_files, accounting_data, accounting_bundle = (
                _accounting_component_artifacts(
                args.accounting_input,
                run_id=args.run_id,
                revision=current + 1,
                approved_scope_ref=args.scope_ref,
                )
            )
            files.update(accounting_files)
            data.update(accounting_data)
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
            "component_ids": normalized_scope["component_ids"],
            "issue_ids": normalized_scope["issue_ids"],
            "required_inputs": normalized_scope["required_inputs"],
            "component_run_ids": [run["component_run_id"] for run in runs],
        }
        files["components/scope.json"] = canonical_bytes(scope_doc)
        files["components/input-requirements.json"] = canonical_bytes({
            "schema_version": "1.0.0",
            "scope_ref": args.scope_ref,
            "required_inputs": normalized_scope["required_inputs"],
            "provided_inputs": sorted(provided_inputs),
        })
        data["component_run_ids"] = scope_doc["component_run_ids"]
        failed_run_ids = [
            str(run["component_run_id"])
            for run in runs
            if run.get("status") == "failed"
        ]
        professional_result: dict[str, Any] | None = None
        if args.professional_input is not None and not failed_run_ids:
            professional_files, professional_data, professional_result = (
                _professional_component_artifacts(
                    args.professional_input,
                    run_id=args.run_id,
                    revision=current + 1,
                    approved_scope_ref=args.scope_ref,
                    evidence_core=updated_core,
                    accounting_bundle=accounting_bundle,
                )
            )
            files.update(professional_files)
            data.update(professional_data)
        state = _advance(
            state,
            "run_deep_components",
            {"authorized_components_only": True},
        )
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
        elif professional_result is not None and not professional_result[
            "finalization_allowed"
        ]:
            state = _advance(
                state,
                "deep_failure",
                {"blocker": "professional_analysis_incomplete"},
            )
            exit_code = EXIT_CONTRACT
            command_ok = False
            command_message = "professional analysis incomplete; workflow blocked"
    elif args.command == "prepare-finalization":
        if state["state"] not in {"deep_dive_ready", "finalization_jobs_ready"}:
            raise ContractError(f"prepare-finalization is not allowed from {state['state']}")
        professional_payload = files.get(
            "analysis/professional/completion-assessment.json"
        )
        if professional_payload is not None:
            strict_loads(professional_payload)
            professional_completion = json.loads(professional_payload.decode("utf-8"))
            verify_completion_assessment(professional_completion)
            if professional_completion["status"] not in {
                "finalization_ready", "limited_completion_ready",
            }:
                raise ContractError("professional completion blocks finalization")
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
    session.files = files
    session.state = state
    session.data = data
    session.exit_code = exit_code
    session.command_ok = command_ok
    session.command_message = command_message
    return True
