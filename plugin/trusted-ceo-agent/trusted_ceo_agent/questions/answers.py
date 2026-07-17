from __future__ import annotations

import copy
import re
from decimal import Decimal
from typing import Any, Mapping

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.questions.index import QuestionIndex
from trusted_ceo_agent.questions.jobs import build_result_question_job


NOT_SUPPORTED_TEXT = "현재 실행본의 근거로는 확인할 수 없습니다"
VALIDATION_LABEL = "스키마·참조 검증 통과"
VALUE_TOKEN = re.compile(r"\{\{value:(value_[0-9a-f]{24})\}\}")
NUMBER_LITERAL = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:[.,]\d+)?\s*%?")


def _native_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value != value.to_integral_value():
            return value
        return int(value)
    if isinstance(value, Mapping):
        return {str(key): _native_json(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_native_json(child) for child in value]
    return copy.deepcopy(value)


def _object(value: Mapping[str, Any], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} must be an object")
    return _native_json(value)


def _reject_controls(text: str) -> None:
    for character in text:
        code = ord(character)
        if (code < 32 and character not in {"\t", "\n"}) or code == 127:
            raise ContractError("answer text contains a forbidden control character")


def _require_allowed(
    values: Any,
    allowed: set[str],
    label: str,
) -> list[str]:
    if not isinstance(values, list):
        raise ContractError(f"{label} must be an array")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or value not in allowed:
            raise ContractError(f"{label} contains an out-of-scope reference")
        normalized.append(value)
    return sorted(normalized)


def _current_job(
    job: Mapping[str, Any],
    index: QuestionIndex,
) -> dict[str, Any]:
    scope = job.get("scope")
    caps = job.get("context_caps")
    if not isinstance(scope, Mapping) or not isinstance(caps, Mapping):
        raise ContractError("result question Job scope is invalid")
    maximum = caps.get("max_context_bytes")
    if isinstance(maximum, bool) or not isinstance(maximum, int):
        raise ContractError("result question Job context cap is invalid")
    return build_result_question_job(
        index=index,
        question=str(job.get("question", "")),
        scope_kind=str(scope.get("scope_kind", "")),
        scope_instance_id=str(scope.get("scope_instance_id", "")),
        privacy_classification=str(job.get("privacy_classification", "")),
        maximum_context_bytes=maximum,
    )


def _supported_block(
    *,
    block: Mapping[str, Any],
    job: Mapping[str, Any],
    index: QuestionIndex,
) -> dict[str, Any]:
    text_template = block.get("text_template")
    if not isinstance(text_template, str):
        raise ContractError("supported answer text template is invalid")
    _reject_controls(text_template)
    token_refs = VALUE_TOKEN.findall(text_template)
    without_tokens = VALUE_TOKEN.sub("", text_template)
    if "{" in without_tokens or "}" in without_tokens:
        raise ContractError("answer contains an invalid value token")
    if NUMBER_LITERAL.search(without_tokens):
        raise ContractError("answer contains a numeric literal")

    allowed_values = set(job["allowed_value_refs"])
    declared_values = _require_allowed(
        block.get("value_refs"),
        allowed_values,
        "value refs",
    )
    if set(token_refs) != set(declared_values):
        raise ContractError("declared value refs differ from answer value tokens")

    claims = _require_allowed(
        block.get("claim_refs"),
        set(job["allowed_claim_refs"]),
        "claim refs",
    )
    evidence = _require_allowed(
        block.get("evidence_link_ids"),
        set(job["allowed_evidence_link_ids"]),
        "Evidence Link refs",
    )
    sources = _require_allowed(
        block.get("source_refs"),
        set(job["allowed_source_refs"]),
        "Source refs",
    )
    if not claims or not evidence:
        raise ContractError(
            "supported answer requires an allowed claim and Evidence Link"
        )

    job_values = {
        item["value_ref"]: item
        for item in job["value_table"]
        if isinstance(item, Mapping) and isinstance(item.get("value_ref"), str)
    }
    resolved_values: list[dict[str, str]] = []
    rendered = text_template
    for value_ref in declared_values:
        job_value = job_values.get(value_ref)
        current_value = index.value_table.get(value_ref)
        if job_value is None or current_value is None:
            raise ContractError("answer value is unavailable in the current snapshot")
        if canonical_bytes(job_value) != canonical_bytes(dict(current_value)):
            raise ContractError("answer value differs from the current snapshot")
        display_text = current_value.get("display_text")
        if not isinstance(display_text, str):
            raise ContractError("answer value display text is invalid")
        rendered = rendered.replace(
            f"{{{{value:{value_ref}}}}}",
            display_text,
        )
        resolved_values.append(
            {"value_ref": value_ref, "display_text": display_text}
        )
    for forbidden in job.get("forbidden_conclusions", []):
        if isinstance(forbidden, str) and forbidden and forbidden in rendered:
            raise ContractError("answer contains a forbidden conclusion")
    _reject_controls(rendered)
    return {
        "block_id": block["block_id"],
        "support_status": "supported",
        "text": rendered,
        "resolved_values": resolved_values,
        "claim_refs": claims,
        "evidence_link_ids": evidence,
        "source_refs": sources,
    }


def _not_supported_block(block: Mapping[str, Any]) -> dict[str, Any]:
    if block.get("text_template") != NOT_SUPPORTED_TEXT:
        raise ContractError("not-supported answer must use the fixed Korean text")
    for field in (
        "value_refs",
        "claim_refs",
        "evidence_link_ids",
        "source_refs",
    ):
        if block.get(field) != []:
            raise ContractError("not-supported answer cannot contain references")
    return {
        "block_id": block["block_id"],
        "support_status": "not_supported",
        "text": NOT_SUPPORTED_TEXT,
        "resolved_values": [],
        "claim_refs": [],
        "evidence_link_ids": [],
        "source_refs": [],
    }


def validate_and_render_answer(
    job: Mapping[str, Any],
    draft: Mapping[str, Any],
    index: QuestionIndex,
) -> dict[str, Any]:
    normalized_job = _object(job, "result question Job")
    normalized_draft = _object(draft, "result answer draft")
    schemas = SchemaStore()
    schemas.validate("result-question-job.schema.json", normalized_job)
    schemas.validate("result-answer-draft.schema.json", normalized_draft)

    expected_job = _current_job(normalized_job, index)
    if canonical_bytes(expected_job) != canonical_bytes(normalized_job):
        raise ContractError(
            "result question Job hash, identity, or scope differs from the snapshot"
        )
    if (
        normalized_draft.get("job_id") != normalized_job["job_id"]
        or normalized_draft.get("run_id") != index.run_id
        or normalized_draft.get("run_id") != normalized_job["run_id"]
        or normalized_draft.get("revision") != index.revision
        or normalized_draft.get("revision") != normalized_job["revision"]
    ):
        raise ContractError("result answer draft identity differs from the Job")

    answer_blocks: list[dict[str, Any]] = []
    seen_block_ids: set[str] = set()
    for block in normalized_draft["answer_blocks"]:
        block_id = block.get("block_id")
        if not isinstance(block_id, str) or block_id in seen_block_ids:
            raise ContractError("result answer block IDs must be unique")
        seen_block_ids.add(block_id)
        if block.get("support_status") == "supported":
            answer_blocks.append(
                _supported_block(
                    block=block,
                    job=normalized_job,
                    index=index,
                )
            )
        elif block.get("support_status") == "not_supported":
            answer_blocks.append(_not_supported_block(block))
        else:
            raise ContractError("unknown answer support status")

    answer = {
        "answer_version": "1.0.0",
        "job_id": normalized_job["job_id"],
        "run_id": index.run_id,
        "revision": index.revision,
        "scope": copy.deepcopy(normalized_job["scope"]),
        "validation": {
            "schema_valid": True,
            "references_valid": True,
            "values_valid": True,
            "semantic_entailment_verified": False,
            "label_ko": VALIDATION_LABEL,
        },
        "answer_blocks": answer_blocks,
    }
    schemas.validate("result-answer.schema.json", answer)
    return answer
