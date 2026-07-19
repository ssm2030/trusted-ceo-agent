from __future__ import annotations

import hmac
from typing import Any, Literal

from fastapi import Depends, FastAPI, File, Form, Header, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from trusted_ceo_agent.application.models import CreateRunRequest
from trusted_ceo_agent.application.run_application import TrustedCeoApplication
from trusted_ceo_agent.errors import ContractError, IntegrityError, RevisionConflict
from trusted_ceo_agent.service.contracts import (
    HitlDecisionRequest,
    MutationBase,
    RunSnapshot,
)
from trusted_ceo_agent.service.openai_gateway import AIServiceError
from trusted_ceo_agent.service.orchestrator import AnalysisOrchestrator
from trusted_ceo_agent.service.file_policy import IncomingUpload
from trusted_ceo_agent.service.run_store import ServiceStoreError
from trusted_ceo_agent.service.settings import ServiceSettings


class CreateAnalysisRequest(MutationBase):
    expected_revision: Literal[0] = 0
    mission: dict[str, Any] | None = None


class DeleteRunRequest(MutationBase):
    confirmed: Literal[True]


def _upload_chunks(upload: UploadFile):
    while True:
        chunk = upload.file.read(1024 * 1024)
        if not chunk:
            return
        yield chunk


def _draft_mission() -> dict[str, Any]:
    mission = {
        "mission_contract_id": "mission_111111111111111111111111",
        "contract_version": "1.0.0",
        "business_question": "확인된 데이터에서 중요한 경영 이슈를 찾아 주세요.",
        "business_model": "project_b2b_services",
        "current_symptoms": [],
        "customer_hypotheses": [],
        "decision_context": "로컬 웹 분석",
        "decision_units": [],
        "decision_deadline": None,
        "analysis_horizon": {"start": "2025-01-01", "end": "2026-12-31"},
        "organization_scope": [],
        "priority_dimensions": [],
        "constraints": [],
        "recent_business_changes": [],
        "recent_organization_changes": [],
        "recent_policy_changes": [],
        "included_scopes": [],
        "excluded_scopes": [],
        "comparison_preferences": [],
        "materiality_context": {},
        "data_definitions": [],
        "confidentiality": "confidential",
        "required_human_roles": ["ceo"],
    }
    mission["business_question"] = "Find the most material hidden business issues"
    mission["decision_context"] = "local browser analysis"
    return mission


def _error(code: str, message: str, *, retryable: bool, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message, "retryable": retryable},
    )


def create_app(
    settings: ServiceSettings,
    application: TrustedCeoApplication,
    orchestrator: AnalysisOrchestrator,
    questions: Any | None = None,
) -> FastAPI:
    del questions
    if application.artifact_root.resolve() != orchestrator.application.artifact_root.resolve():
        raise ValueError("application and orchestrator roots must match")

    async def authenticate(
        token: str | None = Header(
            default=None,
            alias="X-Trusted-Ceo-Internal-Token",
        ),
    ) -> None:
        supplied = token or ""
        if not hmac.compare_digest(supplied, settings.internal_token):
            raise ServiceStoreError("ENGINE_FAILURE", "internal authentication failed")

    app = FastAPI(
        title="Trusted CEO Agent Local Service",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        dependencies=[Depends(authenticate)],
    )

    @app.middleware("http")
    async def secure_response_headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(ServiceStoreError)
    async def service_store_error(_request, error: ServiceStoreError):
        if str(error).endswith("internal authentication failed"):
            return _error(
                "ENGINE_FAILURE",
                "authentication required",
                retryable=False,
                status=401,
            )
        status = 409 if error.code in {"STALE_REVISION", "IDEMPOTENCY_CONFLICT"} else 503
        message = (
            "request revision is stale"
            if error.code == "STALE_REVISION"
            else "request could not be completed"
        )
        return _error(error.code, message, retryable=status == 503, status=status)

    @app.exception_handler(AIServiceError)
    async def ai_service_error(_request, error: AIServiceError):
        status = 503 if error.retryable or error.code == "AI_AUTH_FAILURE" else 422
        return _error(
            error.code,
            "AI service is unavailable" if status == 503 else "AI response was rejected",
            retryable=error.retryable,
            status=status,
        )

    @app.exception_handler(FileNotFoundError)
    async def missing_run(_request, _error_value: FileNotFoundError):
        return _error("ENGINE_FAILURE", "run not found", retryable=False, status=404)

    @app.exception_handler(RevisionConflict)
    async def revision_conflict(_request, _error_value: RevisionConflict):
        return _error(
            "STALE_REVISION",
            "request revision is stale",
            retryable=False,
            status=409,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation(_request, _error_value: RequestValidationError):
        return _error(
            "INPUT_POLICY_FAILURE",
            "request body is invalid",
            retryable=False,
            status=422,
        )

    @app.exception_handler(ContractError)
    async def contract_error(_request, _error_value: ContractError):
        return _error(
            "INPUT_POLICY_FAILURE",
            "request could not be processed",
            retryable=False,
            status=422,
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(_request, _error_value: IntegrityError):
        return _error(
            "VALIDATION_FAILURE",
            "trusted artifact validation failed",
            retryable=False,
            status=500,
        )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "ai_ready": settings.ai_ready,
            "model": settings.model,
        }

    @app.post("/v1/runs", response_model=RunSnapshot)
    async def create_run(body: CreateAnalysisRequest) -> RunSnapshot:
        return orchestrator.create_run(
            CreateRunRequest(
                mission=body.mission or _draft_mission(),
                run_owner_actor_id="local-browser-user",
            ),
            idempotency_key=body.idempotency_key,
            request_body=body.model_dump(mode="json"),
        )

    @app.post("/v1/runs/{run_id}/files", response_model=RunSnapshot)
    async def attach_files(
        run_id: str,
        files: list[UploadFile] = File(...),
        expected_revision: int = Form(...),
        idempotency_key: str = Form(...),
    ) -> RunSnapshot:
        request = MutationBase(
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
        )
        uploads = tuple(
            IncomingUpload(
                filename=upload.filename or "",
                content_type=upload.content_type or "",
                chunks=_upload_chunks(upload),
            )
            for upload in files
        )
        return orchestrator.attach_files(run_id, request, uploads)

    @app.get("/v1/runs/{run_id}", response_model=RunSnapshot)
    async def run_status(run_id: str) -> RunSnapshot:
        return orchestrator.snapshot(run_id)

    @app.post("/v1/runs/{run_id}/actions/continue", response_model=RunSnapshot)
    async def continue_run(run_id: str, body: MutationBase) -> RunSnapshot:
        return orchestrator.continue_run(run_id, body)

    @app.post("/v1/runs/{run_id}/actions/retry", response_model=RunSnapshot)
    async def retry_run(run_id: str, body: MutationBase) -> RunSnapshot:
        return orchestrator.control_run(run_id, "retry", body)

    @app.post("/v1/runs/{run_id}/actions/resume", response_model=RunSnapshot)
    async def resume_run(run_id: str, body: MutationBase) -> RunSnapshot:
        return orchestrator.control_run(run_id, "resume", body)

    @app.post("/v1/runs/{run_id}/actions/stop", response_model=RunSnapshot)
    async def stop_run(run_id: str, body: MutationBase) -> RunSnapshot:
        return orchestrator.control_run(run_id, "stop", body)

    @app.post("/v1/runs/{run_id}/actions/cancel", response_model=RunSnapshot)
    async def cancel_run(run_id: str, body: MutationBase) -> RunSnapshot:
        return orchestrator.control_run(run_id, "cancel", body)

    @app.post("/v1/runs/{run_id}/human-responses", response_model=RunSnapshot)
    async def submit_human_response(
        run_id: str,
        body: HitlDecisionRequest,
        browser_fingerprint: str = Header(
            alias="X-Trusted-Ceo-Browser-Fingerprint",
        ),
    ) -> RunSnapshot:
        return orchestrator.submit_hitl(
            run_id,
            body,
            browser_session_fingerprint=browser_fingerprint,
        )

    @app.get("/v1/runs/{run_id}/report")
    async def report(run_id: str) -> dict[str, Any]:
        return orchestrator.report(run_id)

    @app.delete("/v1/runs/{run_id}", status_code=204)
    async def delete_run(run_id: str, body: DeleteRunRequest) -> Response:
        orchestrator.delete_run(
            run_id,
            body,
            confirmed=body.confirmed,
        )
        return Response(status_code=204)

    return app
