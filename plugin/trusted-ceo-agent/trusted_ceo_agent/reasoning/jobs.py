from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


STAGES = {"schema_mapping", "lens", "integrated", "deep_dive", "writer"}
MAX_JOB_ITEMS = 48
MAX_DOCUMENT_CONTEXT_CHARACTERS = 96_000
STAGE_FIELDS = {
    "schema_mapping": {"mapping_question_refs"},
    "lens": {"lens_id", "shard_index", "shard_count"},
    "integrated": {"join_manifest_ref", "allowed_card_refs"},
    "deep_dive": {"approved_scope_ref", "component_run_refs"},
    "writer": {"structured_output_ref", "allowed_claim_ids"},
}
COMMON_FIELDS = {
    "contract_version", "stage", "artifact_ref", "mission_contract_hash", "pack_manifest_hash",
    "prompt_template_hash", "model_profile", "capability_ids", "allowed_fact_ids",
    "allowed_signal_ids", "allowed_mechanism_refs", "allowed_test_refs",
    "allowed_expert_trigger_refs", "allowed_decision_type_refs", "allowed_decision_unit_refs",
    "allowed_problem_family_refs", "allowed_response_refs",
    "required_signal_ids", "output_schema_ref", "limits_ref", "untrusted_text_markers",
    "allowed_document_evidence_ids", "document_evidence_context",
}
SET_FIELDS = {
    "capability_ids", "allowed_fact_ids", "allowed_signal_ids", "allowed_mechanism_refs",
    "allowed_test_refs", "allowed_expert_trigger_refs", "allowed_decision_type_refs",
    "allowed_decision_unit_refs", "allowed_problem_family_refs", "allowed_response_refs",
    "required_signal_ids", "untrusted_text_markers",
    "mapping_question_refs", "component_run_refs", "allowed_claim_ids", "allowed_card_refs",
    "allowed_document_evidence_ids",
}


def _sorted_unique(values: Iterable[str] | None, field: str) -> list[str]:
    result = list(values or [])
    if any(not isinstance(value, str) or not value for value in result):
        raise ContractError(f"{field} must contain non-empty strings")
    if len(result) != len(set(result)):
        raise ContractError(f"{field} contains duplicates")
    return sorted(result)


def _job_id(body: Mapping[str, Any]) -> str:
    return "job_" + hashlib.sha256(canonical_bytes(dict(body))).hexdigest()[:24]


def _document_context(fields: Mapping[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    identifiers = _sorted_unique(
        fields.get('allowed_document_evidence_ids'),
        'allowed_document_evidence_ids',
    )
    raw_contexts = fields.get('document_evidence_context', [])
    if isinstance(raw_contexts, (str, bytes)) or not isinstance(raw_contexts, Sequence):
        raise ContractError('document_evidence_context must be an array')
    contexts = [dict(item) if isinstance(item, Mapping) else {} for item in raw_contexts]
    context_ids = [str(item.get('document_evidence_id', '')) for item in contexts]
    if (
        context_ids != sorted(context_ids)
        or len(context_ids) != len(set(context_ids))
        or set(context_ids) != set(identifiers)
    ):
        raise ContractError('document context IDs must match their allowlist')
    if sum(len(str(item.get('content', ''))) for item in contexts) > MAX_DOCUMENT_CONTEXT_CHARACTERS:
        raise ContractError('document context exceeds 96,000 characters')
    schemas = SchemaStore()
    for item in contexts:
        schemas.validate('document-evidence.schema.json', item)
        content = str(item['content'])
        if hashlib.sha256(content.encode('utf-8')).hexdigest() != item['content_sha256']:
            raise ContractError('document context content hash mismatch')
        body = {key: value for key, value in item.items() if key != 'integrity'}
        if (
            hashlib.sha256(canonical_bytes(body)).hexdigest()
            != item['integrity']['payload_hash']
        ):
            raise ContractError('document context payload hash mismatch')
    return identifiers, contexts


def build_reasoning_job(**fields: Any) -> dict[str, Any]:
    stage = fields.get("stage")
    if stage not in STAGES:
        raise ContractError(f"unsupported reasoning stage: {stage}")
    allowed = COMMON_FIELDS | STAGE_FIELDS[stage]
    extras = set(fields) - allowed
    if extras:
        raise ContractError(f"fields are not allowed for {stage}: {sorted(extras)}")
    required_common = {
        "stage", "artifact_ref", "mission_contract_hash", "pack_manifest_hash",
        "prompt_template_hash", "model_profile", "output_schema_ref",
    }
    missing = (required_common | STAGE_FIELDS[stage]) - set(fields)
    if missing:
        raise ContractError(f"missing fields for {stage}: {sorted(missing)}")
    document_fields_present = any(
        field in fields
        for field in ('allowed_document_evidence_ids', 'document_evidence_context')
    )
    if stage != 'lens' and document_fields_present:
        raise ContractError(f'document context is not allowed for {stage}')

    body: dict[str, Any] = {
        "contract_version": fields.get("contract_version", "1.0"),
        "stage": stage,
        "artifact_ref": fields["artifact_ref"],
        "mission_contract_hash": fields["mission_contract_hash"],
        "pack_manifest_hash": fields["pack_manifest_hash"],
        "prompt_template_hash": fields["prompt_template_hash"],
        "model_profile": fields["model_profile"],
        "capability_ids": _sorted_unique(fields.get("capability_ids"), "capability_ids"),
        "allowed_fact_ids": _sorted_unique(fields.get("allowed_fact_ids"), "allowed_fact_ids"),
        "allowed_signal_ids": _sorted_unique(fields.get("allowed_signal_ids"), "allowed_signal_ids"),
        "allowed_mechanism_refs": _sorted_unique(fields.get("allowed_mechanism_refs"), "allowed_mechanism_refs"),
        "allowed_test_refs": _sorted_unique(fields.get("allowed_test_refs"), "allowed_test_refs"),
        "allowed_expert_trigger_refs": _sorted_unique(fields.get("allowed_expert_trigger_refs"), "allowed_expert_trigger_refs"),
        "allowed_decision_type_refs": _sorted_unique(fields.get("allowed_decision_type_refs"), "allowed_decision_type_refs"),
        "allowed_decision_unit_refs": _sorted_unique(fields.get("allowed_decision_unit_refs"), "allowed_decision_unit_refs"),
        "allowed_problem_family_refs": _sorted_unique(fields.get("allowed_problem_family_refs"), "allowed_problem_family_refs"),
        "allowed_response_refs": _sorted_unique(fields.get("allowed_response_refs"), "allowed_response_refs"),
        "required_signal_ids": _sorted_unique(fields.get("required_signal_ids"), "required_signal_ids"),
        "output_schema_ref": fields["output_schema_ref"],
        "limits_ref": fields.get("limits_ref", "default"),
        "untrusted_text_markers": _sorted_unique(fields.get("untrusted_text_markers"), "untrusted_text_markers"),
    }
    for field in STAGE_FIELDS[stage]:
        value = fields[field]
        body[field] = _sorted_unique(value, field) if field in SET_FIELDS else value
    if stage == "lens":
        if not isinstance(body["shard_index"], int) or not isinstance(body["shard_count"], int):
            raise ContractError("lens shard indices must be integers")
        if body["shard_count"] < 1 or not 0 <= body["shard_index"] < body["shard_count"]:
            raise ContractError("invalid lens shard bounds")
        document_ids, document_context = _document_context(fields)
        if document_ids:
            body['allowed_document_evidence_ids'] = document_ids
            body['document_evidence_context'] = document_context
            body['untrusted_text_markers'] = sorted(
                set(body['untrusted_text_markers']) | set(document_ids)
            )
    body["job_id"] = _job_id(body)
    return body


def shard_reasoning_items(
    items: Sequence[Mapping[str, Any]],
    *,
    limit: int = MAX_JOB_ITEMS,
) -> list[list[dict[str, Any]]]:
    if limit < 1:
        raise ValueError("limit must be positive")
    ordered = sorted(
        (dict(item) for item in items),
        key=lambda item: (
            str(item.get("scope", "")), str(item.get("period", "")),
            str(item.get("component_id", "")), str(item.get("id", "")),
        ),
    )
    return [ordered[index:index + limit] for index in range(0, len(ordered), limit)] or [[]]


def compile_stage_jobs(
    stage: str,
    *,
    artifact_ref: str,
    mission_contract_hash: str,
    pack_manifest_hash: str,
    prompt_template_hash: str,
    model_profile: str,
    output_schema_ref: str,
    work_items: Sequence[Mapping[str, Any]] | None = None,
    **stage_fields: Any,
) -> list[dict[str, Any]]:
    """Compile deterministic jobs; only lens work is sharded."""
    base = {
        "stage": stage,
        "artifact_ref": artifact_ref,
        "mission_contract_hash": mission_contract_hash,
        "pack_manifest_hash": pack_manifest_hash,
        "prompt_template_hash": prompt_template_hash,
        "model_profile": model_profile,
        "output_schema_ref": output_schema_ref,
    }
    base.update(stage_fields)
    if stage != "lens" or work_items is None:
        return [build_reasoning_job(**base)]
    shards = shard_reasoning_items(work_items)
    if len(shards) > 6:
        raise ContractError("scope_narrowing_required")
    jobs: list[dict[str, Any]] = []
    for index, shard in enumerate(shards):
        fields = dict(base)
        fields["shard_index"] = index
        fields["shard_count"] = len(shards)
        fields['allowed_fact_ids'] = [
            str(item['id']) for item in shard
            if item.get('kind', 'fact') != 'document'
        ]
        document_context = sorted(
            (
                dict(item['context']) for item in shard
                if item.get('kind') == 'document'
                and isinstance(item.get('context'), Mapping)
            ),
            key=lambda item: str(item.get('document_evidence_id', '')),
        )
        if document_context:
            fields['allowed_document_evidence_ids'] = [
                str(item['document_evidence_id']) for item in document_context
            ]
            fields['document_evidence_context'] = document_context
        jobs.append(build_reasoning_job(**fields))
    return sorted(jobs, key=lambda item: item["job_id"])
