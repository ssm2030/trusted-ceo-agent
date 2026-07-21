from __future__ import annotations

import hashlib
from typing import Any, Mapping

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, IntegrityError
from trusted_ceo_agent.grading.grader import grade
from trusted_ceo_agent.packs.runtime_index import RuntimePackIndex
from trusted_ceo_agent.reasoning.attempts import next_attempt_action
from trusted_ceo_agent.reasoning.jobs import compile_stage_jobs
from trusted_ceo_agent.reasoning.normalizer import normalize_lens_draft
from trusted_ceo_agent.reasoning.stage_drafts import (
    normalize_deep_dive_draft,
    normalize_integrated_draft,
    normalize_writer_draft,
)
from trusted_ceo_agent.application.mutation_support import advance as _advance

def _pack_reasoning_context(files: Mapping[str, bytes]) -> dict[str, Any]:
    index = RuntimePackIndex.from_files(files)
    core = strict_loads(files.get("evidence/core.json", b"{}"))
    if not isinstance(core, Mapping):
        raise ContractError("Evidence Core is missing for reasoning")
    mission = strict_loads(files.get(
        "mission/effective-mission-contract.json",
        files.get("mission/mission-contract.json", b"{}"),
    ))
    selection = strict_loads(files.get("packs/selection.json", b"{}"))
    selected_refs = set(selection.get("selected_problem_refs", [])) if isinstance(selection, Mapping) else set()
    selected_packs = tuple(
        pack for pack in index.problem_packs
        if f"{pack['pack_id']}@{pack['pack_version']}" in selected_refs
    )
    facts = [
        item for item in core.get("fact_register", [])
        if isinstance(item, Mapping) and isinstance(item.get("fact_id"), str)
    ]
    signals = [
        item for item in core.get("signal_register", [])
        if isinstance(item, Mapping) and isinstance(item.get("signal_id"), str)
    ]
    documents = [
        item for item in core.get('document_evidence_register', [])
        if isinstance(item, Mapping)
        and isinstance(item.get('document_evidence_id'), str)
    ]
    capabilities = [
        item for item in core.get("capability_map", {}).get("capabilities", [])
        if isinstance(item, Mapping) and isinstance(item.get("capability_id"), str)
    ]
    domain_content = index.domain_pack["content"]
    mechanisms = {
        str(item["mechanism_ref"])
        for item in domain_content.get("mechanism_catalog", [])
    }
    tests = {
        str(reference)
        for item in domain_content.get("mechanism_catalog", [])
        for reference in item.get("distinguishing_test_refs", [])
    }
    experts = {
        str(item["expert_trigger_ref"])
        for item in domain_content.get("expert_triggers", [])
    }
    families: set[str] = set()
    responses: set[str] = set()
    conditions: set[str] = set()
    decision_types: set[str] = set()
    for pack in selected_packs:
        content = pack["content"]
        families.update({
            str(content["problem_family_code"]),
            str(pack["pack_id"]),
            f"{pack['pack_id']}@{pack['pack_version']}",
        })
        for item in content.get("distinguishing_tests", []):
            tests.add(str(item["test_ref"]))
        for item in content.get("conditional_response_catalog", []):
            responses.add(str(item["response_ref"]))
            conditions.update(str(value) for value in item.get("preconditions", []))
            conditions.update(str(value) for value in item.get("disqualifiers", []))
        for item in content.get("blocking_counter_evidence_conditions", []):
            conditions.add(str(item["condition_ref"]))
        experts.update(str(value) for value in content.get("expert_trigger_refs", []))
        decision_types.update(
            str(item["decision_type_ref"])
            for item in content.get("decision_type_catalog", [])
        )
    decision_units = {
        str(item["decision_unit_ref"])
        for item in mission.get("decision_units", [])
        if isinstance(item, Mapping) and isinstance(item.get("decision_unit_ref"), str)
    } if isinstance(mission, Mapping) else set()
    claim_refs: set[str] = set()
    data_request_refs: set[str] = set()
    for path, payload in files.items():
        if not path.startswith("tasks/") or not path.endswith("/card.json"):
            continue
        card = strict_loads(payload)
        normalized = card.get("normalized_payload", {}) if isinstance(card, Mapping) else {}
        if not isinstance(normalized, Mapping):
            continue
        for field in (
            "business_meanings", "problem_candidates", "cause_hypotheses",
            "counter_hypotheses", "expert_trigger_candidates",
        ):
            for item in normalized.get(field, []):
                if isinstance(item, Mapping) and isinstance(item.get("claim_id"), str):
                    claim_refs.add(str(item["claim_id"]))
        for item in normalized.get("data_requests", []):
            if isinstance(item, Mapping) and isinstance(item.get("local_key"), str):
                data_request_refs.add(str(item["local_key"]))
    return {
        "index": index,
        "core": core,
        "mission": mission,
        "selected_packs": selected_packs,
        "facts": facts,
        "signals": signals,
        'documents': documents,
        "capabilities": capabilities,
        "allowed_mechanism_refs": sorted(mechanisms),
        "allowed_test_refs": sorted(tests),
        "allowed_expert_trigger_refs": sorted(experts),
        "allowed_problem_family_refs": sorted(families),
        "allowed_response_refs": sorted(responses),
        "allowed_condition_refs": sorted(conditions),
        "allowed_decision_type_refs": sorted(decision_types),
        "allowed_decision_unit_refs": sorted(decision_units),
        "allowed_claim_refs": sorted(claim_refs),
        "allowed_data_request_refs": sorted(data_request_refs),
        "allowed_monitoring_metric_refs": sorted({
            str(item.get("metric_code") or item.get("fact_code"))
            for item in facts
            if item.get("metric_code") or item.get("fact_code")
        }),
    }


def _reasoning_jobs(
    stage: str,
    *,
    files: Mapping[str, bytes],
    pointer: Mapping[str, Any],
    run_id: str,
    revision: int,
) -> list[dict[str, Any]]:
    context = _pack_reasoning_context(files)
    mission = context["mission"]
    mission_hash = str(mission.get("confirmation", {}).get("contract_hash", ""))
    if len(mission_hash) != 64:
        mission_hash = hashlib.sha256(canonical_bytes(mission)).hexdigest()
    pack_hash = str(context["index"].manifest["manifest_hash"])
    artifact_ref = f"{run_id}@r{revision:04d}:{pointer.get('manifest_hash', '')}"
    common = {
        "artifact_ref": artifact_ref,
        "mission_contract_hash": mission_hash,
        "pack_manifest_hash": pack_hash,
        "prompt_template_hash": hashlib.sha256(f"trusted-ceo-{stage}-v1".encode("utf-8")).hexdigest(),
        "model_profile": "balanced_structured" if stage in {"schema_mapping", "lens"} else "strong_structured",
        "output_schema_ref": (
            "lens-card-draft.schema.json"
            if stage == "lens"
            else f"{stage.replace('_', '-')}-draft.schema.json"
        ),
        "capability_ids": [item["capability_id"] for item in context["capabilities"]],
        "allowed_fact_ids": [item["fact_id"] for item in context["facts"]],
        "allowed_signal_ids": [item["signal_id"] for item in context["signals"]],
        "allowed_mechanism_refs": context["allowed_mechanism_refs"],
        "allowed_test_refs": context["allowed_test_refs"],
        "allowed_expert_trigger_refs": context["allowed_expert_trigger_refs"],
        "allowed_decision_type_refs": context["allowed_decision_type_refs"],
        "allowed_decision_unit_refs": context["allowed_decision_unit_refs"],
        "allowed_problem_family_refs": context["allowed_problem_family_refs"],
        "allowed_response_refs": context["allowed_response_refs"],
    }
    if stage == "schema_mapping":
        proposal = strict_loads(files.get("intake/canonical-mapping-proposal.json", b"{}"))
        references = sorted(
            item["mapping_question_ref"]
            for item in proposal.get("mappings", [])
            if isinstance(item, Mapping) and isinstance(item.get("mapping_question_ref"), str)
        )
        if not references:
            raise ContractError("canonical mapping proposal has no questions")
        return compile_stage_jobs(stage, **common, mapping_question_refs=references)
    if stage == "lens":
        facts = context["facts"]
        signals = context["signals"]
        work_items = [
            {
                "id": item["fact_id"],
                "scope": item.get("scope", []),
                "period": item.get("time_context", {}),
                "component_id": (item.get("derivation") or {}).get("component_id", "intake"),
            }
            for item in facts
            if isinstance(item, dict) and isinstance(item.get("fact_id"), str)
        ] + [
            {
                'id': item['document_evidence_id'],
                'kind': 'document',
                'context': item,
                'scope': item.get('logical_path', ''),
                'period': item.get('line_start', 0),
            }
            for item in context['documents']
        ]
        signal_ids = sorted(
            item["signal_id"] for item in signals
            if isinstance(item, dict) and isinstance(item.get("signal_id"), str)
        )
        required_signal_ids = sorted(
            item["signal_id"] for item in signals
            if isinstance(item, dict)
            and isinstance(item.get("signal_id"), str)
            and item.get("outcome") in {"triggered", "not_assessable"}
        )
        jobs: list[dict[str, Any]] = []
        for pack in context["selected_packs"]:
            content = pack["content"]
            family_refs = sorted({
                str(content["problem_family_code"]),
                str(pack["pack_id"]),
                f"{pack['pack_id']}@{pack['pack_version']}",
            })
            response_refs = sorted(
                str(item["response_ref"])
                for item in content.get("conditional_response_catalog", [])
            )
            decision_refs = sorted(
                str(item["decision_type_ref"])
                for item in content.get("decision_type_catalog", [])
            )
            for lens in content.get("lens_plan", []):
                lens_common = dict(common)
                lens_common.update({
                    "allowed_signal_ids": signal_ids,
                    "required_signal_ids": required_signal_ids,
                    "allowed_problem_family_refs": family_refs,
                    "allowed_mechanism_refs": sorted(set(lens.get("allowed_mechanism_refs", []))),
                    "allowed_response_refs": response_refs,
                    "allowed_decision_type_refs": decision_refs,
                })
                jobs.extend(compile_stage_jobs(
                    stage, **lens_common, work_items=work_items,
                    lens_id=str(lens["lens_id"]),
                ))
        if not jobs:
            boundary_common = dict(common)
            boundary_common.update({
                "allowed_signal_ids": signal_ids,
                "required_signal_ids": required_signal_ids,
                "allowed_problem_family_refs": [],
                "allowed_mechanism_refs": [],
                "allowed_test_refs": [],
                "allowed_expert_trigger_refs": [],
                "allowed_response_refs": [],
                "allowed_decision_type_refs": [],
            })
            jobs.extend(compile_stage_jobs(
                stage, **boundary_common, work_items=work_items,
                lens_id="bounded_not_assessable",
            ))
        return sorted(jobs, key=lambda item: item["job_id"])
    if stage == "integrated":
        join = strict_loads(files["reasoning/join-manifest.json"])
        joined = strict_loads(files["reasoning/join-result.json"])
        return compile_stage_jobs(
            stage,
            **common,
            join_manifest_ref=join["join_manifest_id"],
            allowed_card_refs=joined.get("card_refs", []),
        )
    if stage == "deep_dive":
        scope = strict_loads(files.get("components/scope.json", b"{}"))
        return compile_stage_jobs(
            stage, **common, approved_scope_ref=scope.get("scope_ref", ""),
            component_run_refs=scope.get("component_run_ids", []),
        )
    if stage == "writer":
        structured = strict_loads(files.get("final/structured-output.json", b"{}"))
        return compile_stage_jobs(
            stage, **common, structured_output_ref="final/structured-output.json",
            allowed_claim_ids=sorted(
                item["issue_id"] for item in structured.get("issues", [])
                if isinstance(item, dict) and isinstance(item.get("issue_id"), str)
            ),
        )
    raise ContractError(f"unsupported stage: {stage}")
def _reasoning_attempt_records(
    files: Mapping[str, bytes], job_id: str, stage: str,
) -> list[dict[str, Any]]:
    prefix = f"tasks/{job_id}/attempts/attempt-"
    records: list[dict[str, Any]] = []
    for path, payload in files.items():
        if not path.startswith(prefix) or not path.endswith(".json"):
            continue
        record = strict_loads(payload)
        if not isinstance(record, Mapping):
            raise IntegrityError(f"Reasoning attempt record is invalid: {path}")
        if record.get("job_id") != job_id or record.get("stage") != stage:
            raise IntegrityError(f"Reasoning attempt record identity mismatch: {path}")
        try:
            attempt = int(record["attempt"])
        except (KeyError, TypeError, ValueError) as error:
            raise IntegrityError(f"Reasoning attempt number is invalid: {path}") from error
        normalized = dict(record)
        normalized["attempt"] = attempt
        records.append(normalized)
    records.sort(key=lambda item: item["attempt"])
    if [item["attempt"] for item in records] != list(range(1, len(records) + 1)):
        raise IntegrityError(f"Reasoning attempt history is not contiguous: {job_id}")
    return records


def _reasoning_attempt_record(
    job: Mapping[str, Any], draft: bytes, attempt: int, *,
    valid: bool, action: str, failure_kind: str | None = None,
    validation_errors: Sequence[str] = (),
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "job_id": str(job["job_id"]),
        "stage": str(job["stage"]),
        "attempt": attempt,
        "valid": valid,
        "action": action,
        "draft_sha256": hashlib.sha256(draft).hexdigest(),
        "validation_errors": list(validation_errors),
    }
    if failure_kind is not None:
        record["failure_kind"] = failure_kind
    return record


def _accepted_validation(
    job: Mapping[str, Any], attempt: int, *, source: str, action: str,
) -> dict[str, Any]:
    return {
        "job_id": str(job["job_id"]),
        "stage": str(job["stage"]),
        "attempt": attempt,
        "valid": True,
        "source": source,
        "action": action,
        "validation_errors": [],
    }


def _deterministic_writer_fallback(job: Mapping[str, Any]) -> dict[str, Any]:
    draft = {
        "structured_output_ref": job.get("structured_output_ref"),
        "claim_templates": [],
        "expert_packet_templates": [],
        "ceo_brief_section_order": [],
    }
    SchemaStore().validate("writer-draft.schema.json", draft)
    normalized = normalize_writer_draft(job, draft)
    normalized.pop("writer_result_id", None)
    normalized["materialized_by"] = "deterministic_template_fallback"
    normalized["writer_result_id"] = (
        "writer_" + hashlib.sha256(canonical_bytes(normalized)).hexdigest()[:24]
    )
    return normalized


def _materialize_reasoning_draft(
    job: Mapping[str, Any], draft_document: Mapping[str, Any], files: Mapping[str, bytes],
) -> tuple[dict[str, bytes], dict[str, Any]]:
    job_id = str(job["job_id"])
    stage = str(job["stage"])
    updates: dict[str, bytes] = {
        f"tasks/{job_id}/draft.json": canonical_bytes(draft_document),
    }
    data: dict[str, Any] = {"job_id": job_id}
    if stage == "schema_mapping":
        SchemaStore().validate("schema-mapping-draft.schema.json", draft_document)
        canonical_proposal = strict_loads(files["intake/canonical-mapping-proposal.json"])
        if canonical_bytes(draft_document) != canonical_bytes(canonical_proposal):
            raise ContractError(
                "schema mapping draft differs from the deterministic canonical proposal"
            )
    elif stage == "lens":
        normalized = normalize_lens_draft(job, draft_document)
        SchemaStore().validate("normalized-card.schema.json", normalized)
        updates[f"tasks/{job_id}/card.json"] = canonical_bytes(normalized)
        data["card_id"] = normalized["card_id"]
    elif stage == "integrated":
        SchemaStore().validate("integrated-draft.schema.json", draft_document)
        joined = strict_loads(files["reasoning/join-result.json"])
        runtime_context = _pack_reasoning_context(files)
        normalized = normalize_integrated_draft(
            job,
            draft_document,
            allowed_card_refs=set(joined.get("card_refs", [])),
            allowed_claim_refs=set(runtime_context["allowed_claim_refs"]),
            allowed_problem_family_refs=set(runtime_context["allowed_problem_family_refs"]),
            allowed_response_refs=set(runtime_context["allowed_response_refs"]),
            allowed_condition_refs=set(runtime_context["allowed_condition_refs"]),
            allowed_data_request_refs=set(runtime_context["allowed_data_request_refs"]),
        )
        updates[f"tasks/{job_id}/integrated.json"] = canonical_bytes(normalized)
        data["integrated_assessment_id"] = normalized["integrated_assessment_id"]
    elif stage == "deep_dive":
        SchemaStore().validate("deep-dive-draft.schema.json", draft_document)
        runtime_context = _pack_reasoning_context(files)
        integrated = strict_loads(files.get("reasoning/integrated-assessment.json", b"{}"))
        integrated_claim_refs: set[str] = set(runtime_context["allowed_claim_refs"])
        for issue in integrated.get("payload", {}).get("integrated_issues", []):
            payload = issue.get("payload", {}) if isinstance(issue, Mapping) else {}
            for field in (
                "source_candidate_ids", "observation_claim_refs",
                "cause_hypothesis_refs", "counter_hypothesis_refs",
            ):
                integrated_claim_refs.update(
                    str(value) for value in payload.get(field, [])
                    if isinstance(value, str)
                )
        scope = strict_loads(files.get("components/scope.json", b"{}"))
        normalized = normalize_deep_dive_draft(
            job,
            draft_document,
            allowed_issue_refs=set(scope.get("issue_ids", [])),
            allowed_claim_refs=integrated_claim_refs,
            allowed_response_refs=set(runtime_context["allowed_response_refs"]),
            allowed_condition_refs=set(runtime_context["allowed_condition_refs"]),
            allowed_monitoring_metric_refs=set(runtime_context["allowed_monitoring_metric_refs"]),
        )
        updates[f"tasks/{job_id}/deep-dive.json"] = canonical_bytes(normalized)
        data["deep_dive_result_id"] = normalized["deep_dive_result_id"]
    elif stage == "writer":
        SchemaStore().validate("writer-draft.schema.json", draft_document)
        normalized = normalize_writer_draft(job, draft_document)
        updates[f"tasks/{job_id}/writer.json"] = canonical_bytes(normalized)
        data["writer_result_id"] = normalized["writer_result_id"]
    else:
        raise ContractError(f"unsupported reasoning stage: {stage}")
    return updates, data


def validate_reasoning_draft(
    job: Mapping[str, Any],
    draft_document: Mapping[str, Any],
    files: Mapping[str, bytes],
) -> None:
    _materialize_reasoning_draft(job, draft_document, files)


def _block_reasoning_failure(
    state: Mapping[str, Any], stage: str,
) -> dict[str, Any]:
    if stage == "lens":
        return _advance(
            state, "contract_failure", {"blocker": "reasoning_contract_failure"},
        )
    if stage == "deep_dive":
        return _advance(
            state, "deep_failure", {"blocker": "reasoning_contract_failure"},
        )
    blocked = dict(state)
    blocked["resume_state"] = state["state"]
    blocked["state"] = "blocked"
    blocked["blocker"] = "reasoning_contract_failure"
    return blocked


_ACCOUNTING_INPUT_KEYS = frozenset({
    "scope_ref",
    "suite",
    "tier_zero_input",
    "raw_core_population",
    "revenue_input",
    "cashflow_input",
    "project_cost_inputs",
})
