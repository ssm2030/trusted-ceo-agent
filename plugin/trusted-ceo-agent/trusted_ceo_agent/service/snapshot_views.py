from __future__ import annotations

from trusted_ceo_agent.application.models import ApplicationResult
from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.service.contracts import (
    HitlCard,
    RunSnapshot,
    ServiceErrorBody,
    UploadedFileSummary,
)
from trusted_ceo_agent.service.run_store import ServiceManifest


def build_run_snapshot(
    manifest: ServiceManifest,
    result: ApplicationResult,
    *,
    hitl_card: HitlCard | None,
    uploaded_files: list[UploadedFileSummary],
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
        hitl_card=hitl_card if human else None,
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
        uploaded_files=uploaded_files,
    )
