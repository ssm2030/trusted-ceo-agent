from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError


STAGES = {"schema_mapping", "lens", "integrated", "deep_dive", "writer"}
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
}
SET_FIELDS = {
    "capability_ids", "allowed_fact_ids", "allowed_signal_ids", "allowed_mechanism_refs",
    "allowed_test_refs", "allowed_expert_trigger_refs", "allowed_decision_type_refs",
    "allowed_decision_unit_refs", "allowed_problem_family_refs", "allowed_response_refs",
    "required_signal_ids", "untrusted_text_markers",
    "mapping_question_refs", "component_run_refs", "allowed_claim_ids", "allowed_card_refs",
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
    body["job_id"] = _job_id(body)
    return body


def shard_reasoning_items(items: Sequence[Mapping[str, Any]], *, limit: int = 48) -> list[list[dict[str, Any]]]:
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
        fields["allowed_fact_ids"] = [str(item["id"]) for item in shard]
        jobs.append(build_reasoning_job(**fields))
    return sorted(jobs, key=lambda item: item["job_id"])
