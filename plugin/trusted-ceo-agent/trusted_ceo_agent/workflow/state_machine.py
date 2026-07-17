from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from trusted_ceo_agent.errors import ContractError


TERMINAL = {"finalized", "failed", "stopped_by_human", "cancelled"}
STATUSES = {
    "created", "context_confirmation_required", "context_ready", "schema_mapping_job_ready",
    "mapping_proposal_ready", "data_confirmation_required", "evidence_ready", "scope_narrowing_required",
    "lens_jobs_ready", "lens_ready", "integrated_draft", "diagnostic_approval_required",
    "deep_dive_authorized", "deep_dive_jobs_ready", "deep_dive_ready", "finalization_jobs_ready",
    "writer_ready", "final_approval_required", "delivery_approved", "finalized", "blocked",
    "stopped_by_human", "failed", "cancelled",
}


def _truth(field: str) -> Callable[[Mapping[str, Any]], bool]:
    return lambda context: context.get(field) is True


def _always(_: Mapping[str, Any]) -> bool:
    return True


Rule = tuple[Callable[[Mapping[str, Any]], bool], str | Callable[[Mapping[str, Any]], str]]


TABLE: dict[tuple[str, str], list[Rule]] = {
    ("created", "start"): [
        (lambda c: c.get("mission_confirmed") is True, "context_ready"),
        (_always, "context_confirmation_required"),
    ],
    ("context_confirmation_required", "approve_context"): [(_truth("approval_valid"), "context_ready")],
    ("context_confirmation_required", "reject_context"): [(_always, "stopped_by_human")],
    ("context_ready", "scan"): [
        (_truth("mapping_ambiguous"), "schema_mapping_job_ready"),
        (_truth("scan_passed"), "evidence_ready"),
    ],
    ("schema_mapping_job_ready", "ingest_schema_mapping"): [(_truth("draft_or_fallback_valid"), "mapping_proposal_ready")],
    ("mapping_proposal_ready", "request_data_approval"): [(_truth("proposal_diff_valid"), "data_confirmation_required")],
    ("data_confirmation_required", "approve_data"): [(_truth("mapping_patch_valid"), "evidence_ready")],
    ("data_confirmation_required", "request_data_changes"): [(_always, "data_confirmation_required")],
    ("evidence_ready", "prepare_lens"): [
        (lambda c: isinstance(c.get("estimated_card_count"), int) and c["estimated_card_count"] <= 6, "lens_jobs_ready"),
        (lambda c: isinstance(c.get("estimated_card_count"), int) and c["estimated_card_count"] > 6, "scope_narrowing_required"),
    ],
    ("scope_narrowing_required", "approve_scope"): [(_truth("scope_valid"), "evidence_ready")],
    ("scope_narrowing_required", "reject_scope"): [(_always, "stopped_by_human")],
    ("lens_jobs_ready", "reduce_lens"): [(_truth("required_tasks_accepted"), "lens_ready")],
    ("lens_jobs_ready", "contract_failure"): [(_always, "blocked")],
    ("lens_ready", "ingest_integrated"): [(_truth("barrier_and_draft_valid"), "integrated_draft")],
    ("integrated_draft", "request_diagnostic_approval"): [(_truth("issues_valid"), "diagnostic_approval_required")],
    ("diagnostic_approval_required", "request_diagnostic_changes"): [
        (lambda c: c.get("change_scope") in {"data", "scan"}, "evidence_ready"),
        (lambda c: c.get("change_scope") == "reasoning", "lens_jobs_ready"),
    ],
    ("diagnostic_approval_required", "approve_diagnostic"): [
        (lambda c: c.get("approval_valid") is True and c.get("deep_scope_empty") is True, "finalization_jobs_ready"),
        (lambda c: c.get("approval_valid") is True and c.get("deep_scope_empty") is False, "deep_dive_authorized"),
    ],
    ("diagnostic_approval_required", "reject_run"): [(_always, "stopped_by_human")],
    ("deep_dive_authorized", "run_deep_components"): [(_truth("authorized_components_only"), "deep_dive_jobs_ready")],
    ("deep_dive_jobs_ready", "ingest_deep_result"): [(_truth("required_deep_valid"), "deep_dive_ready")],
    ("deep_dive_jobs_ready", "deep_failure"): [(_always, "blocked")],
    ("deep_dive_ready", "prepare_finalization"): [(_truth("deep_result_valid"), "finalization_jobs_ready")],
    ("finalization_jobs_ready", "ingest_writer"): [(_truth("grade_and_writer_valid"), "writer_ready")],
    ("finalization_jobs_ready", "writer_fallback"): [(_truth("fallback_valid_after_two_attempts"), "writer_ready")],
    ("writer_ready", "request_final_approval"): [(_truth("output_valid"), "final_approval_required")],
    ("final_approval_required", "request_final_changes"): [
        (lambda c: c.get("change_scope") == "deep", "deep_dive_authorized"),
        (lambda c: c.get("change_scope") in {"wording", "routing"}, "finalization_jobs_ready"),
    ],
    ("final_approval_required", "approve_final"): [(_truth("all_dispositions_complete"), "delivery_approved")],
    ("final_approval_required", "reject_run"): [(_always, "stopped_by_human")],
    ("delivery_approved", "finalize"): [(_truth("final_validator_passed"), "finalized")],
}


def transition(state: Mapping[str, Any], event: str, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    current = state.get("status")
    if current not in STATUSES:
        raise ContractError(f"unknown workflow state: {current}")
    if current in TERMINAL:
        raise ContractError(f"terminal state cannot transition: {current}")
    ctx = dict(context or {})
    if event == "integrity_failure":
        result = dict(state)
        result["status"] = "failed"
        result["failure_reason"] = ctx.get("reason", "integrity_failure")
        return result
    if event == "cancel":
        result = dict(state)
        result["status"] = "cancelled"
        return result
    if event == "stop":
        result = dict(state)
        result["status"] = "stopped_by_human"
        return result
    if current == "blocked" and event == "resume":
        if ctx.get("blocker_resolved") is not True:
            raise ContractError("blocked workflow cannot resume before blocker resolution")
        if ctx.get("expected_revision") != state.get("revision"):
            raise ContractError("blocked workflow resume revision is stale")
        resume_state = state.get("resume_state")
        if resume_state not in STATUSES or resume_state in TERMINAL | {"blocked"}:
            raise ContractError("blocked workflow lacks a valid resume_state")
        result = dict(state)
        result["status"] = resume_state
        result.pop("resume_state", None)
        result.pop("blocker", None)
        return result
    rules = TABLE.get((str(current), event))
    if not rules:
        raise ContractError(f"event {event} is invalid from {current}")
    for guard, target in rules:
        if guard(ctx):
            target_status = target(ctx) if callable(target) else target
            result = dict(state)
            result["status"] = target_status
            if target_status == "blocked":
                result["resume_state"] = current
                result["blocker"] = ctx.get("blocker", event)
            return result
    raise ContractError(f"guard rejected event {event} from {current}")
