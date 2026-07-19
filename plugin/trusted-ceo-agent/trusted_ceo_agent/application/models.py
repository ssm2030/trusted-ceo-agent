from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


DocumentInput = Path | Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ApplicationResult:
    command: str
    ok: bool
    code: int
    message: str
    run_id: str | None
    revision: int | None
    state: str | None
    data: Mapping[str, Any] = field(default_factory=dict)

    def to_cli_payload(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "ok": self.ok,
            "code": self.code,
            "message": self.message,
            "run_id": self.run_id,
            "revision": self.revision,
            "state": self.state,
            "data": dict(self.data),
        }


@dataclass(frozen=True, slots=True)
class SourceUpload:
    path: Path
    opaque_token: str


@dataclass(frozen=True, slots=True)
class CreateRunRequest:
    mission: DocumentInput
    inputs: tuple[Path, ...] = ()
    run_owner_actor_id: str | None = None
    run_id: str | None = None


@dataclass(frozen=True, slots=True)
class RunRequest:
    run_id: str


@dataclass(frozen=True, slots=True)
class RevisionRequest(RunRequest):
    revision: int


@dataclass(frozen=True, slots=True)
class AttachSourcesRequest(RunRequest):
    expected_revision: int
    sources: tuple[SourceUpload, ...]


@dataclass(frozen=True, slots=True)
class HumanResponseRequest(RunRequest):
    expected_revision: int
    action_id: str
    action_content_hash: str
    response: DocumentInput


@dataclass(frozen=True, slots=True)
class SubmitHumanResponseRequest(HumanResponseRequest):
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ExportWebReportRequest(RevisionRequest):
    output: Path
    input_manifest: DocumentInput


@dataclass(frozen=True, slots=True)
class PrepareResultQuestionRequest(RevisionRequest):
    question: Path | str
    scope_kind: str
    scope_instance_id: str
    privacy_classification: str


@dataclass(frozen=True, slots=True)
class ValidateResultAnswerRequest(RevisionRequest):
    job: DocumentInput
    draft: DocumentInput
