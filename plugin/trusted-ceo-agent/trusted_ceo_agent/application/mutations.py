from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from trusted_ceo_agent.application.models import ApplicationResult, MutationRequest
from trusted_ceo_agent.application.mutation_commands import analysis, execute_command
from trusted_ceo_agent.application.mutation_contracts import (
    GATES,
    SUPPORTED_MUTATIONS,
    DocumentPayload as _DocumentPayload,
    validate_parameters as _validated_parameters,
)
from trusted_ceo_agent.application.mutation_reasoning import validate_reasoning_draft
from trusted_ceo_agent.application.mutation_session import open_mutation_session
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.runtime_components import execute_authorized_scope


def _execute(args: SimpleNamespace) -> tuple[int, ApplicationResult]:
    # Keep the historical patch seam used by integration tests while the
    # implementation lives in the analysis command family.
    analysis.execute_authorized_scope = execute_authorized_scope
    return execute_command(open_mutation_session(args))

class MutationExecutor:
    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = artifact_root.resolve()

    def execute(self, request: MutationRequest) -> ApplicationResult:
        if request.artifact_root.resolve() != self.artifact_root:
            raise ContractError("MutationRequest artifact root does not match application root")
        values = _validated_parameters(request)
        defaults: dict[str, Any] = {
            "stage": None,
            "scope_ref": None,
            "accounting_input": None,
            "professional_input": None,
            "job_id": None,
            "draft": None,
            "draft_source": "model_draft",
            "gate": None,
            "overlay": None,
            "request_id": None,
            "actor_id": None,
            "actor_role": None,
            "nonce": None,
            "rationale": None,
            "browser_session_fingerprint": None,
            "response_hash": None,
            "decision": None,
            "change_scope": None,
        }
        draft_document = values.pop("draft_document", None)
        overlay_document = values.pop("overlay_document", None)
        defaults.update(values)
        if request.command == "ingest-result":
            defaults["draft"] = _DocumentPayload(
                draft_document,
                label="Reasoning draft",
            )
        if request.command == "approval-request":
            defaults["overlay"] = _DocumentPayload(
                overlay_document,
                label="HITL overlay",
            )
        args = SimpleNamespace(
            artifact_root=self.artifact_root,
            run_id=request.run_id,
            expected_revision=request.expected_revision,
            command=request.command,
            **defaults,
        )
        _, result = _execute(args)
        return result
