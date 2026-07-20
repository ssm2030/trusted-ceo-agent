from __future__ import annotations

import json
import unicodedata
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ServiceErrorCode = Literal[
    "INPUT_POLICY_FAILURE",
    "HUMAN_RESPONSE_REQUIRED",
    "AI_AUTH_FAILURE",
    "AI_TRANSIENT_FAILURE",
    "AI_REFUSAL",
    "AI_OUTPUT_INVALID",
    "VALIDATION_FAILURE",
    "STALE_REVISION",
    "ENGINE_FAILURE",
    "STOPPED",
    "CANCELLED",
    "IDEMPOTENCY_CONFLICT",
]
ERROR_CODES = frozenset({
    "INPUT_POLICY_FAILURE",
    "HUMAN_RESPONSE_REQUIRED",
    "AI_AUTH_FAILURE",
    "AI_TRANSIENT_FAILURE",
    "AI_REFUSAL",
    "AI_OUTPUT_INVALID",
    "VALIDATION_FAILURE",
    "STALE_REVISION",
    "ENGINE_FAILURE",
    "STOPPED",
    "CANCELLED",
    "IDEMPOTENCY_CONFLICT",
})

HitlDecision = Literal["approve", "approve_with_edits", "reanalyze", "stop"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _normalized_text(
    value: str,
    *,
    label: str,
    maximum: int,
    strip: bool = True,
) -> str:
    normalized = unicodedata.normalize("NFC", value)
    if strip:
        normalized = normalized.strip()
    if not normalized.strip():
        raise ValueError(f"{label} must not be empty")
    if len(normalized) > maximum:
        raise ValueError(f"{label} exceeds {maximum} characters")
    if any(unicodedata.category(character) == "Cc" for character in normalized):
        raise ValueError(f"{label} contains control characters")
    return normalized


def _normalized_json(value: Any, *, depth: int = 0) -> Any:
    if depth > 16:
        raise ValueError("edits exceed the maximum nesting depth")
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        raise ValueError("binary floating-point edit values are forbidden")
    if isinstance(value, str):
        return _normalized_text(
            value,
            label="edit text",
            maximum=4_000,
            strip=False,
        )
    if isinstance(value, list):
        return [_normalized_json(item, depth=depth + 1) for item in value]
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("edit object keys must be strings")
            normalized_key = _normalized_text(key, label="edit field", maximum=200)
            if normalized_key in normalized:
                raise ValueError("normalized edit field names must be unique")
            normalized[normalized_key] = _normalized_json(item, depth=depth + 1)
        return normalized
    raise ValueError("edits must contain only JSON values")


class ServiceErrorBody(StrictModel):
    code: ServiceErrorCode
    message: str = Field(min_length=1, max_length=500)
    retryable: bool = False

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        return _normalized_text(value, label="error message", maximum=500)


def _validated_ref(value: str, *, label: str) -> str:
    normalized = _normalized_text(value, label=label, maximum=500)
    if "\\" in normalized or normalized.casefold().startswith("file:"):
        raise ValueError(f"{label} must not contain a filesystem path")
    if len(normalized) >= 3 and normalized[1:3] == ":/":
        raise ValueError(f"{label} must not contain a drive path")
    if normalized.startswith("/") and not normalized.startswith("/api/analysis/"):
        raise ValueError(f"{label} must be an opaque or same-origin reference")
    if ".." in normalized.split("/"):
        raise ValueError(f"{label} must not traverse parents")
    return normalized


class HitlSection(StrictModel):
    kind: Literal[
        "mission",
        "source_summary",
        "mapping",
        "risk",
        "facts",
        "diagnostic",
        "priorities",
        "verification",
        "final_wording",
    ]
    title: str = Field(min_length=1, max_length=200)
    items: list[str] = Field(max_length=64)
    target_refs: list[str] = Field(max_length=64)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _normalized_text(value, label="HITL section title", maximum=200)

    @field_validator("items")
    @classmethod
    def validate_items(cls, value: list[str]) -> list[str]:
        return [
            _normalized_text(item, label="HITL section item", maximum=1_000)
            for item in value
        ]

    @field_validator("target_refs")
    @classmethod
    def validate_section_refs(cls, value: list[str]) -> list[str]:
        normalized = [_validated_ref(item, label="HITL target") for item in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError("HITL section targets must be unique")
        return normalized


class HitlCard(StrictModel):
    hitl_kind: Literal["context_data", "diagnostic_final"]
    request_id: str = Field(min_length=1, max_length=200)
    base_revision: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=4_000)
    target_refs: list[str] = Field(max_length=256)
    allowed_decisions: list[HitlDecision] = Field(min_length=1, max_length=4)
    editable_fields: list[str] = Field(max_length=128)
    sections: list[HitlSection] = Field(default_factory=list, max_length=16)

    @field_validator("request_id", "title", "summary")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _normalized_text(value, label="HITL text", maximum=4_000)

    @field_validator("target_refs", "editable_fields")
    @classmethod
    def validate_string_lists(cls, value: list[str]) -> list[str]:
        normalized = [
            _validated_ref(item, label="HITL reference")
            for item in value
        ]
        if len(normalized) != len(set(normalized)):
            raise ValueError("HITL references must be unique")
        return normalized

    @field_validator("allowed_decisions")
    @classmethod
    def validate_decisions(cls, value: list[HitlDecision]) -> list[HitlDecision]:
        if len(value) != len(set(value)):
            raise ValueError("allowed decisions must be unique")
        return value

class UploadedFileSummary(StrictModel):
    source_id: str = Field(pattern=r'^source_[0-9a-f]{24}$')
    logical_path: str = Field(min_length=1, max_length=512)
    display_name: str = Field(min_length=1, max_length=512)
    media_type: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(ge=0)
    collection_label: str = Field(min_length=1, max_length=512)


class RunSnapshot(StrictModel):
    provider_kind: Literal["service"] = "service"
    display_badge: Literal["실시간 AI 분석"] = "실시간 AI 분석"
    run_id: str = Field(pattern=r"^run_[A-Za-z0-9_-]{8,200}$")
    revision: int = Field(ge=0)
    workflow_status: str = Field(min_length=1, max_length=200)
    ui_phase: Literal[1, 2, 3, 4, 5, 6, 7]
    pending_action: Literal[
        "human_response", "provider_work", "retry", "resume", "terminal"
    ]
    allowed_actions: list[str] = Field(max_length=32)
    latest_event: str = Field(min_length=1, max_length=500)
    progress: int = Field(ge=0, le=100)
    result_ref: str | None = Field(default=None, max_length=500)
    hitl_card: HitlCard | None = None
    error: ServiceErrorBody | None = None
    uploaded_files: list[UploadedFileSummary] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def validate_browser_state(self) -> RunSnapshot:
        if self.pending_action == "human_response":
            if self.hitl_card is None:
                raise ValueError("human_response snapshot requires a HITL card")
            if self.hitl_card.base_revision != self.revision:
                raise ValueError("HITL card revision must match snapshot revision")
        elif self.hitl_card is not None:
            raise ValueError("HITL card is allowed only for human_response")
        return self

    @field_validator(
        "workflow_status",
        "latest_event",
        mode="before",
    )
    @classmethod
    def validate_optional_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("snapshot text must be a string")
        return _normalized_text(value, label="snapshot text", maximum=500)

    @field_validator("result_ref", mode="before")
    @classmethod
    def validate_result_ref(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("result_ref must be a string")
        normalized = _validated_ref(value, label="result_ref")
        if normalized.startswith("/api/analysis/"):
            return normalized
        if not normalized.startswith("result_"):
            raise ValueError("result_ref must be opaque or same-origin")
        return normalized

    @field_validator("allowed_actions")
    @classmethod
    def validate_actions(cls, value: list[str]) -> list[str]:
        normalized = [
            _normalized_text(item, label="allowed action", maximum=100)
            for item in value
        ]
        if len(normalized) != len(set(normalized)):
            raise ValueError("allowed actions must be unique")
        return normalized


class MutationBase(StrictModel):
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,128}$")


class HitlDecisionRequest(MutationBase):
    decision: HitlDecision
    edits: dict[str, Any] = Field(default_factory=dict)
    rationale: str | None = Field(default=None, max_length=2_000)

    @field_validator("edits", mode="before")
    @classmethod
    def validate_edits(cls, value: Any) -> dict[str, Any]:
        normalized = _normalized_json(value)
        if not isinstance(normalized, dict):
            raise ValueError("edits must be an object")
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > 32 * 1024:
            raise ValueError("edits exceed 32 KiB")
        return normalized

    @field_validator("rationale", mode="before")
    @classmethod
    def validate_rationale(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("rationale must be a string")
        return _normalized_text(value, label="rationale", maximum=2_000)

    @model_validator(mode="after")
    def require_reason_for_nonapproval(self) -> HitlDecisionRequest:
        if self.decision in {"reanalyze", "stop"} and self.rationale is None:
            raise ValueError(f"{self.decision} requires rationale")
        if self.decision != "approve_with_edits" and self.edits:
            raise ValueError("edits are allowed only with approve_with_edits")
        if self.decision == "approve_with_edits" and not self.edits:
            raise ValueError("approve_with_edits requires at least one edit")
        return self
