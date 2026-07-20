from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from trusted_ceo_agent.accounting.dispatcher import dispatch_accounting_suite
from trusted_ceo_agent.analysis.runtime import ProfessionalAnalysisRuntime, TaskExecutionFailure
from trusted_ceo_agent.application.models import ApplicationResult, MutationRequest
from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, IntegrityError, RevisionConflict
from trusted_ceo_agent.evidence.core import EvidenceCoreValidator
from trusted_ceo_agent.evidence.revalidation import revalidate_component_artifacts
from trusted_ceo_agent.grading.grader import grade
from trusted_ceo_agent.mission import is_confirmed_mission, materialize_confirmed_mission, validate_confirmed_mission
from trusted_ceo_agent.packs.runtime_index import RuntimePackIndex
from trusted_ceo_agent.reasoning.attempts import next_attempt_action
from trusted_ceo_agent.reasoning.jobs import compile_stage_jobs
from trusted_ceo_agent.reasoning.join import freeze_join_manifest, reduce_join
from trusted_ceo_agent.reasoning.normalizer import normalize_lens_draft
from trusted_ceo_agent.reasoning.stage_drafts import normalize_deep_dive_draft, normalize_integrated_draft, normalize_writer_draft
from trusted_ceo_agent.runtime_components import bind_accounting_professional_inputs, component_input_documents, execute_authorized_scope, merge_component_runs, normalize_authorized_scope
from trusted_ceo_agent.runtime_finalization import build_delivery_package, prepare_finalization
from trusted_ceo_agent.runtime_scan import build_scan_artifacts
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from trusted_ceo_agent.workflow.approvals import ApprovalService, current_approvals
from trusted_ceo_agent.workflow.completion import verify_completion_assessment
from trusted_ceo_agent.workflow.overlays import apply_overlay, invalidated_gates
from trusted_ceo_agent.workflow.revisions import RevisionManager
from trusted_ceo_agent.workflow.state_machine import TERMINAL, transition


EXIT_CONTRACT = 3
GATES = ("context", "data", "scope_narrowing", "diagnostic", "final")


def _application_result(
    *,
    command: str,
    ok: bool,
    code: int,
    message: str,
    run_id: str | None = None,
    revision: int | None = None,
    state: str | None = None,
    data: Mapping[str, Any] | None = None,
) -> ApplicationResult:
    return ApplicationResult(
        command=command,
        ok=ok,
        code=code,
        message=message,
        run_id=run_id,
        revision=revision,
        state=state,
        data=data or {},
    )


def _snapshot_payloads(store: ArtifactStore, revision: int) -> dict[str, bytes]:
    snapshot = store.verify_revision(revision)
    manifest = json.loads((snapshot / "snapshot-manifest.json").read_text("utf-8"))
    return {
        item["path"]: (snapshot / Path(item["path"])).read_bytes()
        for item in manifest["files"]
    }


def _workflow_state(files: Mapping[str, bytes]) -> dict[str, Any]:
    raw = files.get("workflow/state.json")
    if raw is None:
        raise IntegrityError("workflow state is missing")
    state = json.loads(raw.decode("utf-8"))
    if not isinstance(state, dict):
        raise IntegrityError("workflow state is invalid")
    return state


def _effective_mission(files: Mapping[str, bytes]) -> dict[str, Any]:
    stored = strict_loads(files.get("mission/effective-mission-contract.json", files["mission/mission-contract.json"]))
    if not isinstance(stored, Mapping):
        raise ContractError("Mission Contract must be an object")
    if is_confirmed_mission(stored):
        validate_confirmed_mission(stored)
        return dict(stored)
    approvals = current_approvals(files, gate="context")
    if len(approvals) != 1:
        raise ContractError("exactly one current Context approval is required")
    overlay = strict_loads(files.get("workflow/hitl-overlay.json", b"{}"))
    if not isinstance(overlay, Mapping):
        raise ContractError("HITL overlay must be an object")
    approval = approvals[0]
    return materialize_confirmed_mission(
        stored,
        overlay,
        actor_id=str(approval["actor_id"]),
        actor_role=str(approval["actor_role"]),
        confirmed_at=str(approval["created_at"]),
    )


def _advance(state: Mapping[str, Any], event: str, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    machine = dict(state)
    machine["status"] = machine.pop("state")
    advanced = transition(machine, event, context or {})
    result = dict(state)
    result["state"] = advanced["status"]
    for key in ("resume_state", "blocker", "failure_reason"):
        if key in advanced:
            result[key] = advanced[key]
        elif key in result and key not in advanced:
            result[key] = None
    return result


def _recorded_blocker_is_resolved(files: Mapping[str, bytes], state: Mapping[str, Any]) -> bool:
    if state.get("blocker") != "component_contract_failure":
        return False
    component_runs = [
        strict_loads(payload)
        for path, payload in files.items()
        if path.startswith("components/runs/") and path.endswith(".json")
    ]
    return bool(component_runs) and all(
        isinstance(run, Mapping) and run.get("status") != "failed"
        for run in component_runs
    )


def _overlay_status(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        raw = value.get("status", value.get("diagnostic_disposition"))
        return str(raw) if raw is not None else None
    return None
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
def _accounting_component_artifacts(
    path: Path,
    *,
    run_id: str,
    revision: int,
    approved_scope_ref: str,
) -> tuple[dict[str, bytes], dict[str, Any], dict[str, Any]]:
    raw_bytes = path.read_bytes()
    strict_loads(raw_bytes)
    request = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(request, Mapping):
        raise ContractError("accounting input must be an object")
    actual_keys = frozenset(request)
    if actual_keys != _ACCOUNTING_INPUT_KEYS:
        missing = sorted(_ACCOUNTING_INPUT_KEYS - actual_keys)
        unknown = sorted(actual_keys - _ACCOUNTING_INPUT_KEYS)
        raise ContractError(
            "accounting input must be a closed contract; "
            f"missing={missing}, unknown={unknown}"
        )
    if request["scope_ref"] != approved_scope_ref:
        raise ContractError("accounting input scope_ref does not match approved scope")

    bundle = dispatch_accounting_suite(
        suite=request["suite"],
        tier_zero_input=request["tier_zero_input"],
        raw_core_population=request["raw_core_population"],
        revenue_input=request["revenue_input"],
        cashflow_input=request["cashflow_input"],
        project_cost_inputs=request["project_cost_inputs"],
    )
    if (bundle["run_id"], bundle["revision"]) != (run_id, revision):
        raise ContractError("accounting input must bind to the target run and revision")

    request_bytes = canonical_bytes(request)
    request_hash = hashlib.sha256(request_bytes).hexdigest()
    bundle_hash = str(bundle["content_hash"])
    return (
        {
            f"accounting/requests/{request_hash}.json": request_bytes,
            f"accounting/executions/{bundle_hash}.json": canonical_bytes(bundle),
        },
        {
            "accounting_request_hash": request_hash,
            "accounting_execution_bundle_hash": bundle_hash,
            "accounting_issue_family_count": len(
                bundle["execution_manifest"]["family_records"]
            ),
            "accounting_result_artifact_count": len(bundle["result_artifacts"]),
        },
        bundle,
    )


_PROFESSIONAL_INPUT_KEYS = frozenset({
    "scope_ref",
    "runtime_input",
    "task_results",
    "task_failures",
})
_PROFESSIONAL_RUNTIME_KEYS = frozenset({
    "event_type",
    "field_fact_refs",
    "registered_domains",
    "candidate_sets",
    "screen_results",
    "pack_manifest",
    "pack_catalog",
    "jurisdiction",
    "effective_at",
    "signals",
    "case_plans",
    "work_plans",
    "priority_policy_ref",
    "policy",
    "policy_release_id",
    "concurrency_profile_id",
    "execution_authority_inputs",
    "runtime_control",
    "relation_plans",
    "cluster_plans",
    "boundary_packet_refs",
    "limited_basis",
    "user_confirmed_limitations",
    "final_validator_passed",
    "tty_final_approval_ready",
})


def _closed_keys(
    value: Mapping[str, Any], expected: frozenset[str], label: str,
) -> None:
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise ContractError(
            f"{label} must be a closed contract; "
            f"missing={missing}, unknown={unknown}"
        )


def _professional_component_artifacts(
    path: Path,
    *,
    run_id: str,
    revision: int,
    approved_scope_ref: str,
    evidence_core: Mapping[str, Any],
    accounting_bundle: Mapping[str, Any] | None = None,
) -> tuple[dict[str, bytes], dict[str, Any], dict[str, Any]]:
    raw_bytes = path.read_bytes()
    strict_loads(raw_bytes)
    request = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(request, Mapping):
        raise ContractError("professional input must be an object")
    _closed_keys(request, _PROFESSIONAL_INPUT_KEYS, "professional input")
    if request["scope_ref"] != approved_scope_ref:
        raise ContractError("professional input scope_ref does not match approved scope")

    runtime_input = request["runtime_input"]
    task_results = request["task_results"]
    task_failures = request["task_failures"]
    if not isinstance(runtime_input, Mapping):
        raise ContractError("professional runtime_input must be an object")
    if not isinstance(task_results, Mapping) or not isinstance(task_failures, Mapping):
        raise ContractError("professional task results and failures must be objects")
    _closed_keys(
        runtime_input,
        _PROFESSIONAL_RUNTIME_KEYS,
        "professional runtime_input",
    )
    if any(not isinstance(key, str) or not key for key in task_results):
        raise ContractError("professional task result keys must be non-empty strings")
    if any(not isinstance(key, str) or not key for key in task_failures):
        raise ContractError("professional task failure keys must be non-empty strings")
    overlap = set(task_results) & set(task_failures)
    if overlap:
        raise ContractError(
            f"professional task cannot both succeed and fail: {sorted(overlap)}"
        )
    work_plans = runtime_input["work_plans"]
    if not isinstance(work_plans, list) or not work_plans:
        raise ContractError("professional runtime requires Work Item plans")
    work_keys = [
        item.get("local_key")
        for item in work_plans
        if isinstance(item, Mapping)
    ]
    if len(work_keys) != len(work_plans) or any(
        not isinstance(key, str) or not key for key in work_keys
    ):
        raise ContractError("professional Work Item plan keys are invalid")
    if len(work_keys) != len(set(work_keys)):
        raise ContractError("professional Work Item plan keys are duplicated")
    declared_keys = set(task_results) | set(task_failures)
    if set(work_keys) != declared_keys:
        raise ContractError(
            "professional task outcomes must cover every Work Item plan; "
            f"missing={sorted(set(work_keys) - declared_keys)}, "
            f"unknown={sorted(declared_keys - set(work_keys))}"
        )

    accounting_binding = (
        bind_accounting_professional_inputs(accounting_bundle, request)
        if accounting_bundle is not None else None
    )

    def execute_task(task_request: dict[str, Any]) -> Mapping[str, Any]:
        work_key = task_request.get("work_plan_key")
        if not isinstance(work_key, str) or work_key not in declared_keys:
            raise ContractError("runtime requested an undeclared Work Item result")
        if work_key in task_failures:
            failure_code = task_failures[work_key]
            if not isinstance(failure_code, str):
                raise ContractError("professional task failure code must be a string")
            raise TaskExecutionFailure(failure_code)
        result = task_results[work_key]
        if not isinstance(result, Mapping):
            raise ContractError("professional task result must be an object")
        return result

    envelope = evidence_core.get("envelope")
    if not isinstance(envelope, Mapping):
        raise ContractError("Evidence Core envelope is missing")
    result = ProfessionalAnalysisRuntime().run(
        run_id=run_id,
        revision=revision,
        evidence_core=evidence_core,
        expected_evidence_core_hash=str(envelope.get("artifact_hash", "")),
        task_executor=execute_task,
        **runtime_input,
    )
    request_bytes = canonical_bytes(request)
    request_hash = hashlib.sha256(request_bytes).hexdigest()
    result_hash = str(result["content_hash"])
    artifact_files: dict[str, bytes] = {
        f"analysis/professional/requests/{request_hash}.json": request_bytes,
        "analysis/professional/runtime-result.json": canonical_bytes(result),
        f"analysis/professional/runs/{result_hash}.json": canonical_bytes(result),
        "analysis/professional/economic-event.json": canonical_bytes(result["event"]),
        "analysis/professional/routing-decisions.json": canonical_bytes(
            result["routing_decisions"]
        ),
        "analysis/professional/domain-routes.json": canonical_bytes(
            result["domain_routes"]
        ),
        "analysis/professional/signal-cases.json": canonical_bytes(
            result["signal_cases"]
        ),
        "analysis/professional/priority-records.json": canonical_bytes(
            result["priority_records"]
        ),
        "analysis/professional/work-graphs.json": canonical_bytes(result["graphs"]),
        "analysis/professional/work-items.json": canonical_bytes(result["work_items"]),
        "analysis/professional/result-cas.json": canonical_bytes(result["result_cas"]),
        "analysis/professional/domain-assessments.json": canonical_bytes(
            result["domain_assessments"]
        ),
        "analysis/professional/findings.json": canonical_bytes(result["findings"]),
        "analysis/professional/relations.json": canonical_bytes(result["relations"]),
        "analysis/professional/issue-clusters.json": canonical_bytes(result["clusters"]),
        "analysis/professional/completion-assessment.json": canonical_bytes(
            result["completion"]
        ),
        "analysis/professional/grading-inputs.json": canonical_bytes(
            result["grading_inputs"]
        ),
        "analysis/professional/grade-records.json": canonical_bytes(
            result["grade_records"]
        ),
        "analysis/professional/execution-authority.json": canonical_bytes(
            result["execution_authority"]
        ),
    }
    if accounting_binding is not None:
        artifact_files["analysis/professional/accounting-binding.json"] = (
            canonical_bytes(accounting_binding)
        )
    if result["finding_join_manifest"] is not None:
        artifact_files["analysis/professional/finding-join-manifest.json"] = (
            canonical_bytes(result["finding_join_manifest"])
        )
    if result["cross_domain_integration"] is not None:
        artifact_files["analysis/professional/cross-domain-integration.json"] = (
            canonical_bytes(result["cross_domain_integration"])
        )
    return (
        artifact_files,
        {
            "professional_request_hash": request_hash,
            "professional_runtime_result_hash": result_hash,
            "professional_completion_status": result["completion"]["status"],
            "professional_finalization_allowed": result["finalization_allowed"],
            "professional_finding_count": len(result["findings"]),
            "professional_product_display": result["execution_authority"]["product_display"],
            "accounting_professional_binding_hash": (
                accounting_binding["content_hash"]
                if accounting_binding is not None else None
            ),
        },
        result,
    )
def _execute(args: SimpleNamespace) -> tuple[int, ApplicationResult]:
    store = ArtifactStore(args.artifact_root)
    store.open_run(args.run_id)
    pointer = store.state()
    current = int(pointer["revision"])
    if current != args.expected_revision:
        raise RevisionConflict(f"expected revision {args.expected_revision}, current is {current}")
    files = _snapshot_payloads(store, current)
    state = _workflow_state(files)
    if state["state"] in TERMINAL:
        raise ContractError(f"terminal state cannot mutate: {state['state']}")
    data: dict[str, Any] = {}
    exit_code = 0
    command_ok = True
    command_message = "mutation committed"
    if args.command == "scan":
        if state["state"] not in {"context_ready", "data_confirmation_required", "mapping_proposal_ready"}:
            raise ContractError(f"scan is not allowed from {state['state']}")
        effective_mission = _effective_mission(files)
        scan_files = dict(files)
        scan_files["mission/effective-mission-contract.json"] = canonical_bytes(effective_mission)
        updates, scan_data = build_scan_artifacts(
            files=scan_files,
            pointer=pointer,
            run_id=args.run_id,
            current_revision=current,
            source_root=store.verify_revision(current),
            mission=effective_mission,
        )
        updates["mission/effective-mission-contract.json"] = canonical_bytes(effective_mission)
        files.update(updates)
        data.update(scan_data)
        if scan_data["mapping_question_count"] and not scan_data["mapping_applied"]:
            state = _advance(state, "scan", {"mapping_ambiguous": True})
            exit_code = 2
        else:
            state = _advance(state, "scan", {"scan_passed": True})
    elif args.command == "run-components":
        if state["state"] != "deep_dive_authorized":
            raise ContractError(f"run-components is not allowed from {state['state']}")
        overlay = strict_loads(files.get("workflow/hitl-overlay.json", b"{}"))
        scope = overlay.get("deep_dive_scope") if isinstance(overlay, dict) else None
        if not isinstance(scope, dict):
            raise ContractError("approved deep-dive scope is missing")
        normalized_scope = normalize_authorized_scope(scope)
        required_inputs = set(normalized_scope["required_inputs"])
        provided_inputs = {
            name
            for name, value in (
                ("accounting", args.accounting_input),
                ("professional", args.professional_input),
            )
            if value is not None
        }
        missing_inputs = sorted(required_inputs - provided_inputs)
        if missing_inputs:
            raise ContractError(
                f"required input is missing from approved scope: {missing_inputs}"
            )
        core = json.loads(files["evidence/core.json"].decode("utf-8"))
        integrated = strict_loads(files.get("reasoning/integrated-assessment.json", b"{}"))
        plan, runs = execute_authorized_scope(
            files, core, integrated, scope, args.scope_ref,
        )
        accounting_bundle: dict[str, Any] | None = None
        if args.accounting_input is not None:
            accounting_files, accounting_data, accounting_bundle = (
                _accounting_component_artifacts(
                args.accounting_input,
                run_id=args.run_id,
                revision=current + 1,
                approved_scope_ref=args.scope_ref,
                )
            )
            files.update(accounting_files)
            data.update(accounting_data)
        files[f"components/plans/deep-dive-{args.scope_ref}.json"] = canonical_bytes(plan.to_dict())
        for run in runs:
            files[f"components/runs/{run['component_run_id']}.json"] = canonical_bytes(run)
        for run_id, document in component_input_documents(plan, runs).items():
            files[f"components/inputs/{run_id}.json"] = canonical_bytes(document)
        updated_core = merge_component_runs(
            core, runs, run_id=args.run_id, revision=current + 1,
            parent_artifact_hash=str(pointer.get("manifest_hash", "")),
        )
        EvidenceCoreValidator().validate(updated_core, source_root=store.verify_revision(current))
        files["evidence/core.json"] = canonical_bytes(updated_core)
        scope_doc = {
            "scope_ref": args.scope_ref,
            "component_ids": normalized_scope["component_ids"],
            "issue_ids": normalized_scope["issue_ids"],
            "required_inputs": normalized_scope["required_inputs"],
            "component_run_ids": [run["component_run_id"] for run in runs],
        }
        files["components/scope.json"] = canonical_bytes(scope_doc)
        files["components/input-requirements.json"] = canonical_bytes({
            "schema_version": "1.0.0",
            "scope_ref": args.scope_ref,
            "required_inputs": normalized_scope["required_inputs"],
            "provided_inputs": sorted(provided_inputs),
        })
        data["component_run_ids"] = scope_doc["component_run_ids"]
        failed_run_ids = [
            str(run["component_run_id"])
            for run in runs
            if run.get("status") == "failed"
        ]
        professional_result: dict[str, Any] | None = None
        if args.professional_input is not None and not failed_run_ids:
            professional_files, professional_data, professional_result = (
                _professional_component_artifacts(
                    args.professional_input,
                    run_id=args.run_id,
                    revision=current + 1,
                    approved_scope_ref=args.scope_ref,
                    evidence_core=updated_core,
                    accounting_bundle=accounting_bundle,
                )
            )
            files.update(professional_files)
            data.update(professional_data)
        state = _advance(
            state,
            "run_deep_components",
            {"authorized_components_only": True},
        )
        if failed_run_ids:
            state = _advance(
                state,
                "deep_failure",
                {"blocker": "component_contract_failure"},
            )
            data["failed_component_run_ids"] = failed_run_ids
            exit_code = EXIT_CONTRACT
            command_ok = False
            command_message = "component execution failed; workflow blocked"
        elif professional_result is not None and not professional_result[
            "finalization_allowed"
        ]:
            state = _advance(
                state,
                "deep_failure",
                {"blocker": "professional_analysis_incomplete"},
            )
            exit_code = EXIT_CONTRACT
            command_ok = False
            command_message = "professional analysis incomplete; workflow blocked"
    elif args.command == "prepare-finalization":
        if state["state"] not in {"deep_dive_ready", "finalization_jobs_ready"}:
            raise ContractError(f"prepare-finalization is not allowed from {state['state']}")
        professional_payload = files.get(
            "analysis/professional/completion-assessment.json"
        )
        if professional_payload is not None:
            strict_loads(professional_payload)
            professional_completion = json.loads(professional_payload.decode("utf-8"))
            verify_completion_assessment(professional_completion)
            if professional_completion["status"] not in {
                "finalization_ready", "limited_completion_ready",
            }:
                raise ContractError("professional completion blocks finalization")
        revalidate_component_artifacts(files)
        updates, finalization_data = prepare_finalization(
            files, run_id=args.run_id, revision=current + 1,
            parent_artifact_hash=str(pointer.get("manifest_hash", "")),
        )
        candidate_core = json.loads(updates["evidence/core.json"].decode("utf-8"))
        EvidenceCoreValidator().validate(candidate_core, source_root=store.verify_revision(current))
        files.update(updates)
        data.update(finalization_data)
        if state["state"] == "deep_dive_ready":
            state = _advance(state, "prepare_finalization", {"deep_result_valid": True})
    elif args.command == "prepare-jobs":
        allowed_states = {
            "schema_mapping": {"schema_mapping_job_ready"},
            "integrated": {"lens_ready"},
            "deep_dive": {"deep_dive_jobs_ready"},
            "writer": {"finalization_jobs_ready"},
        }
        if args.stage != "lens" and state["state"] not in allowed_states[args.stage]:
            raise ContractError(f"prepare-jobs:{args.stage} is not allowed from {state['state']}")
        jobs = _reasoning_jobs(
            args.stage, files=files, pointer=pointer, run_id=args.run_id, revision=current,
        )
        if args.stage == "lens":
            state = _advance(state, "prepare_lens", {"estimated_card_count": len(jobs)})
            if state["state"] == "scope_narrowing_required":
                jobs = []
                exit_code = 2
        for job in jobs:
            SchemaStore().validate("reasoning-job.schema.json", job)
            files[f"tasks/{job['job_id']}/job.json"] = canonical_bytes(job)
        data["job_ids"] = [job["job_id"] for job in jobs]
    elif args.command == "ingest-result":
        job_path = f"tasks/{args.job_id}/job.json"
        if job_path not in files:
            raise ContractError(f"unknown Reasoning Job: {args.job_id}")
        job = strict_loads(files[job_path])
        if not isinstance(job, Mapping):
            raise IntegrityError(f"Reasoning Job is invalid: {args.job_id}")
        stage = job["stage"]
        accepted_source = args.draft_source
        if (
            accepted_source == "deterministic_canonical"
            and stage != "schema_mapping"
        ):
            raise ContractError(
                "deterministic_canonical source is only allowed for schema_mapping"
            )
        expected_states = {
            "schema_mapping": {"schema_mapping_job_ready"},
            "lens": {"lens_jobs_ready"},
            "integrated": {"lens_ready"},
            "deep_dive": {"deep_dive_jobs_ready"},
            "writer": {"finalization_jobs_ready"},
        }
        if state["state"] not in expected_states.get(stage, set()):
            raise ContractError(f"ingest-result:{stage} is not allowed from {state['state']}")
        validation_path = f"tasks/{args.job_id}/validation.json"
        if validation_path in files:
            current_validation = strict_loads(files[validation_path])
            if isinstance(current_validation, Mapping) and current_validation.get("valid") is True:
                raise ContractError(f"Reasoning Job already has an accepted result: {args.job_id}")
        attempts = _reasoning_attempt_records(files, args.job_id, stage)
        if len(attempts) >= 2:
            raise ContractError(f"Reasoning Job exhausted two attempts: {args.job_id}")
        attempt = len(attempts) + 1
        draft = args.draft.read_bytes()
        attempt_root = f"tasks/{args.job_id}/attempts/attempt-{attempt}"
        files[f"{attempt_root}.draft"] = draft

        failure_kind: str | None = None
        validation_error: str | None = None
        materialized_updates: dict[str, bytes] = {}
        materialized_data: dict[str, Any] = {}
        try:
            draft_document = strict_loads(draft)
        except (UnicodeError, ValueError) as error:
            failure_kind = "invalid_json"
            validation_error = str(error)
        else:
            try:
                if not isinstance(draft_document, Mapping):
                    raise ContractError("Reasoning draft must be an object")
                materialized_updates, materialized_data = _materialize_reasoning_draft(
                    job, draft_document, files,
                )
            except ContractError as error:
                failure_kind = "contract"
                validation_error = str(error)

        if failure_kind is None:
            action = "accepted"
            attempt_record = _reasoning_attempt_record(
                job, draft, attempt, valid=True, action=action,
            )
            files.update(materialized_updates)
            data.update(materialized_data)
            files[validation_path] = canonical_bytes(_accepted_validation(
                job, attempt, source=accepted_source, action=action,
            ))
        else:
            action = next_attempt_action(
                stage, attempt, required=True, failure_kind=failure_kind,
            )
            attempt_record = _reasoning_attempt_record(
                job,
                draft,
                attempt,
                valid=False,
                action=action,
                failure_kind=failure_kind,
                validation_errors=(validation_error or "draft validation failed",),
            )
            data["validation_errors"] = attempt_record["validation_errors"]
            files[validation_path] = canonical_bytes(attempt_record)
            if action == "deterministic_mapping":
                fallback = strict_loads(files["intake/canonical-mapping-proposal.json"])
                SchemaStore().validate("schema-mapping-draft.schema.json", fallback)
                files[f"tasks/{args.job_id}/draft.json"] = canonical_bytes(fallback)
                files[validation_path] = canonical_bytes(_accepted_validation(
                    job, attempt, source="deterministic_fallback", action=action,
                ))
            elif action == "fallback":
                fallback = _deterministic_writer_fallback(job)
                files[f"tasks/{args.job_id}/writer.json"] = canonical_bytes(fallback)
                files[validation_path] = canonical_bytes(_accepted_validation(
                    job, attempt, source="deterministic_fallback", action=action,
                ))
                data["writer_result_id"] = fallback["writer_result_id"]
            elif action == "blocked":
                state = _block_reasoning_failure(state, stage)
                exit_code = EXIT_CONTRACT
                command_ok = False
                command_message = "reasoning draft failed twice; workflow blocked"
            elif action == "retry":
                exit_code = EXIT_CONTRACT
                command_ok = False
                command_message = "reasoning draft validation failed; one retry remains"
            else:
                raise ContractError(f"unsupported Reasoning attempt action: {action}")
        files[f"{attempt_root}.json"] = canonical_bytes(attempt_record)
        data.update({
            "job_id": args.job_id,
            "attempt": attempt,
            "attempt_action": action,
        })
    elif args.command == "reduce-stage" and args.stage == "lens":
        jobs = []
        for path, payload in files.items():
            if path.startswith("tasks/") and path.endswith("/job.json"):
                job = strict_loads(payload)
                if job.get("stage") == "lens":
                    jobs.append(job)
        if not jobs:
            raise ContractError("no lens Jobs are prepared")
        tasks = [
            {
                "job_id": job["job_id"],
                "required": True,
                "required_signal_ids": job.get("required_signal_ids", []),
            }
            for job in jobs
        ]
        first = sorted(jobs, key=lambda item: item["job_id"])[0]
        manifest = freeze_join_manifest(
            first["artifact_ref"], first["mission_contract_hash"], first["pack_manifest_hash"],
            tasks, "1970-01-01T00:00:00Z",
        )
        results = []
        for job in jobs:
            card_path = f"tasks/{job['job_id']}/card.json"
            validation_path = f"tasks/{job['job_id']}/validation.json"
            validation = strict_loads(files.get(validation_path, b"{}"))
            if (
                card_path not in files
                or not isinstance(validation, Mapping)
                or validation.get("valid") is not True
                or validation.get("source") != "model_draft"
            ):
                raise ContractError(f"lens Job lacks a validated card: {job['job_id']}")
            card = strict_loads(files[card_path])
            status = "valid_not_assessable" if card.get("assessment_status") == "not_assessable" else "completed"
            results.append({"job_id": job["job_id"], "status": status, "card": card})
        joined = reduce_join(manifest, results)
        files["reasoning/join-manifest.json"] = canonical_bytes(manifest)
        files["reasoning/join-result.json"] = canonical_bytes(joined)
        data.update({"join_manifest_id": manifest["join_manifest_id"], "join_result_id": joined["join_result_id"]})
        state = _advance(state, "reduce_lens", {"required_tasks_accepted": True})
    elif args.command == "reduce-stage" and args.stage == "schema_mapping":
        candidates: list[tuple[bytes, Mapping[str, Any]]] = []
        for path, payload in files.items():
            if not path.startswith("tasks/") or not path.endswith("/draft.json"):
                continue
            job_path = path.replace("/draft.json", "/job.json")
            validation_path = path.replace("/draft.json", "/validation.json")
            if job_path not in files or validation_path not in files:
                continue
            candidate_job = strict_loads(files[job_path])
            validation = strict_loads(files[validation_path])
            if (
                isinstance(candidate_job, Mapping)
                and candidate_job.get("stage") == "schema_mapping"
                and isinstance(validation, Mapping)
                and validation.get("valid") is True
                and validation.get("source") in {
                    "model_draft",
                    "deterministic_canonical",
                    "deterministic_fallback",
                }
            ):
                candidates.append((payload, validation))
        if len(candidates) != 1:
            raise ContractError("schema_mapping reducer requires exactly one validated draft")
        proposal = strict_loads(candidates[0][0])
        SchemaStore().validate("schema-mapping-draft.schema.json", proposal)
        canonical_proposal = strict_loads(files["intake/canonical-mapping-proposal.json"])
        if canonical_bytes(proposal) != canonical_bytes(canonical_proposal):
            raise ContractError("schema mapping draft differs from the deterministic canonical proposal")
        files["reasoning/schema-mapping-proposal.json"] = canonical_bytes(proposal)
        data["reduction_source"] = candidates[0][1]["source"]
        state = _advance(state, "ingest_schema_mapping", {"draft_or_fallback_valid": True})
    elif args.command == "reduce-stage" and args.stage in {"integrated", "deep_dive", "writer"}:
        artifact_names = {
            "integrated": ("integrated.json", "reasoning/integrated-assessment.json", "integrated_assessment_id"),
            "deep_dive": ("deep-dive.json", "reasoning/deep-dive-result.json", "deep_dive_result_id"),
            "writer": ("writer.json", "reasoning/writer-result.json", "writer_result_id"),
        }
        leaf, destination, identifier_key = artifact_names[args.stage]
        candidates: list[tuple[dict[str, Any], Mapping[str, Any]]] = []
        for path, payload in files.items():
            if path.startswith("tasks/") and path.endswith(f"/{leaf}"):
                task_root = path.rsplit("/", 1)[0]
                job_path = f"{task_root}/job.json"
                validation_path = f"{task_root}/validation.json"
                if job_path not in files or validation_path not in files:
                    continue
                candidate_job = strict_loads(files[job_path])
                validation = strict_loads(files[validation_path])
                materialized = strict_loads(payload)
                allowed_sources = (
                    {"model_draft", "deterministic_fallback"}
                    if args.stage == "writer" else {"model_draft"}
                )
                if (
                    isinstance(candidate_job, Mapping)
                    and candidate_job.get("stage") == args.stage
                    and isinstance(validation, Mapping)
                    and validation.get("valid") is True
                    and validation.get("source") in allowed_sources
                    and isinstance(materialized, dict)
                ):
                    candidates.append((materialized, validation))
        if len(candidates) != 1:
            raise ContractError(f"{args.stage} reducer requires exactly one validated result")
        materialized, validation = candidates[0]
        files[destination] = canonical_bytes(materialized)
        data[identifier_key] = materialized[identifier_key]
        data["reduction_source"] = validation["source"]
        events = {
            "integrated": ("ingest_integrated", {"barrier_and_draft_valid": True}),
            "deep_dive": ("ingest_deep_result", {"required_deep_valid": True}),
            "writer": ("ingest_writer", {"grade_and_writer_valid": True}),
        }
        if args.stage == "writer" and validation["source"] == "deterministic_fallback":
            event, event_context = (
                "writer_fallback", {"fallback_valid_after_two_attempts": True},
            )
        else:
            event, event_context = events[args.stage]
        state = _advance(state, event, event_context)
    elif args.command == "approval-request":
        overlay = strict_loads(args.overlay.read_bytes())
        if not isinstance(overlay, dict) or not isinstance(overlay.get("patch_operations", []), list):
            raise ContractError("HITL overlay must contain patch_operations")
        operations = overlay.get("patch_operations", [])
        base_overlay = strict_loads(files.get("workflow/hitl-overlay.json", b"{}"))
        preview = apply_overlay(
            base_overlay, args.gate, operations,
            runtime_context=overlay.get("runtime_context", {}),
        )
        paths = [item.get("path", "") for item in operations if isinstance(item, dict)]
        invalidated = sorted(invalidated_gates(paths))
        if args.gate == "context":
            if state["state"] != "context_confirmation_required":
                raise ContractError(f"context approval is not allowed from {state['state']}")
        elif args.gate == "data":
            if state["state"] == "mapping_proposal_ready":
                state = _advance(state, "request_data_approval", {"proposal_diff_valid": True})
            elif state["state"] != "data_confirmation_required":
                raise ContractError(f"data approval is not allowed from {state['state']}")
        elif args.gate == "scope_narrowing":
            if state["state"] != "scope_narrowing_required":
                raise ContractError(f"scope approval is not allowed from {state['state']}")
        elif args.gate == "diagnostic":
            if state["state"] == "integrated_draft":
                state = _advance(state, "request_diagnostic_approval", {"issues_valid": True})
            elif state["state"] != "diagnostic_approval_required":
                raise ContractError(f"diagnostic approval is not allowed from {state['state']}")
        elif args.gate == "final":
            if state["state"] == "writer_ready":
                state = _advance(state, "request_final_approval", {"output_valid": True})
            elif state["state"] != "final_approval_required":
                raise ContractError(f"final approval is not allowed from {state['state']}")
        next_state = dict(state)
        next_state["revision"] = current + 1
        additional = {
            "workflow/state.json": canonical_bytes(next_state),
            "workflow/pending-overlay.json": canonical_bytes(preview),
            "workflow/pending-runtime-context.json": canonical_bytes(overlay.get("runtime_context", {})),
            f"audit/events/r{current + 1:04d}-approval-request.json": canonical_bytes({
                "command": "approval-request", "gate": args.gate,
                "from_revision": current, "to_revision": current + 1,
            }),
        }
        service = ApprovalService(RevisionManager(store))
        request_record, nonce, revision = service.request(
            expected_revision=current,
            gate=args.gate,
            base_artifact_ref=f"{args.run_id}@r{current:04d}",
            base_artifact_hash=str(pointer.get("manifest_hash", "")),
            patch_operations=operations,
            invalidated_approval_ids=invalidated,
            result_preview_hash=hashlib.sha256(canonical_bytes(preview)).hexdigest(),
            additional_updates=additional,
        )
        return 2, _application_result(
            command=args.command, ok=True, code=2, message="human action required",
            run_id=args.run_id, revision=revision, state=next_state["state"],
            data={"approval_request_id": request_record["approval_request_id"], "nonce": nonce},
        )
    elif args.command == "approve-web":
        revisions = RevisionManager(store)
        request_path = f"approvals/requests/{args.request_id}.json"
        request_record = strict_loads(revisions.read(request_path, revision=current))
        base_overlay = strict_loads(files.get("workflow/hitl-overlay.json", b"{}"))
        runtime_context = strict_loads(
            files.get("workflow/pending-runtime-context.json", b"{}")
        )
        materialized = apply_overlay(
            base_overlay,
            request_record["gate"],
            request_record.get("patch_operations", []),
            runtime_context=runtime_context,
        )
        gate = request_record["gate"]
        scan_updates: dict[str, bytes] = {}
        if gate == "context":
            base_mission = strict_loads(files["mission/mission-contract.json"])
            if not isinstance(base_mission, Mapping):
                raise ContractError("Mission Contract must be an object")
            materialize_confirmed_mission(
                base_mission,
                materialized,
                actor_id=args.actor_id,
                actor_role=args.actor_role,
                confirmed_at=str(request_record["created_at"]),
            )
            next_state = _advance(state, "approve_context", {"approval_valid": True})
        elif gate == "data":
            effective_mission = _effective_mission(files)
            scan_updates, _ = build_scan_artifacts(
                files=files,
                pointer=pointer,
                run_id=args.run_id,
                current_revision=current,
                source_root=store.verify_revision(current),
                mission=effective_mission,
                mapping_overlay=materialized,
            )
            candidate_core = json.loads(scan_updates["evidence/core.json"].decode("utf-8"))
            EvidenceCoreValidator().validate(
                candidate_core,
                source_root=store.verify_revision(current),
            )
            next_state = _advance(state, "approve_data", {"mapping_patch_valid": True})
        elif gate == "scope_narrowing":
            next_state = _advance(state, "approve_scope", {"scope_valid": True})
        elif gate == "diagnostic":
            integrated = strict_loads(
                files.get("reasoning/integrated-assessment.json", b"{}")
            )
            issues = integrated.get("payload", {}).get("integrated_issues", [])
            issue_dispositions = materialized.get("issue_dispositions", {})
            decision_dispositions = materialized.get("decision_dispositions", {})
            authorizations = materialized.get("verification_authorizations", {})
            for issue in issues:
                local_key = issue.get("local_key")
                issue_status = _overlay_status(issue_dispositions.get(local_key))
                decision_status = _overlay_status(decision_dispositions.get(local_key))
                if issue_status not in {"accepted", "rejected", "disputed"}:
                    raise ContractError(f"Diagnostic disposition is incomplete: {local_key}")
                if (
                    issue_status != "rejected"
                    and decision_status not in {"needed", "not_needed", "disputed"}
                ):
                    raise ContractError(f"Decision disposition is incomplete: {local_key}")
                if issue_status == "disputed" and not bool(authorizations.get(local_key, False)):
                    raise ContractError(
                        f"Disputed issue lacks verification authorization: {local_key}"
                    )
            deep_scope = materialized.get("deep_dive_scope", {})
            next_state = _advance(state, "approve_diagnostic", {
                "approval_valid": True,
                "deep_scope_empty": not bool(
                    deep_scope.get("component_ids") or deep_scope.get("issue_ids")
                ),
            })
        elif gate == "final":
            delivery_scope = materialized.get("delivery_scope")
            if not isinstance(delivery_scope, dict) or not delivery_scope:
                raise ContractError("Final approval requires a non-empty delivery scope")
            next_state = _advance(
                state,
                "approve_final",
                {"all_dispositions_complete": True},
            )
        else:
            raise ContractError(f"unsupported approval gate: {gate}")
        next_state["revision"] = current + 1
        additional = {
            "workflow/state.json": canonical_bytes(next_state),
            "workflow/hitl-overlay.json": canonical_bytes(materialized),
            "workflow/pending-overlay.json": None,
            "workflow/pending-runtime-context.json": None,
            f"audit/events/r{current + 1:04d}-approve-web.json": canonical_bytes({
                "command": "approve-web",
                "gate": gate,
                "from_revision": current,
                "to_revision": current + 1,
            }),
        }
        if gate == "data":
            additional.update(scan_updates)
        approval, revision = ApprovalService(revisions).approve_web(
            args.request_id,
            expected_revision=current,
            actor_id=args.actor_id,
            actor_role=args.actor_role,
            nonce=args.nonce,
            rationale=args.rationale,
            browser_session_fingerprint=args.browser_session_fingerprint,
            response_hash=args.response_hash,
            additional_updates=additional,
        )
        return 0, _application_result(
            command=args.command,
            ok=True,
            code=0,
            message="approval committed",
            run_id=args.run_id,
            revision=revision,
            state=next_state["state"],
            data={"approval_id": approval["approval_id"], "gate": approval["gate"]},
        )
    elif args.command == "decide-web":
        revisions = RevisionManager(store)
        request_path = f"approvals/requests/{args.request_id}.json"
        request_record = strict_loads(revisions.read(request_path, revision=current))
        gate = request_record.get("gate")
        expected_states = {
            "context": "context_confirmation_required",
            "data": "data_confirmation_required",
            "scope_narrowing": "scope_narrowing_required",
            "diagnostic": "diagnostic_approval_required",
            "final": "final_approval_required",
        }
        if gate not in expected_states or state["state"] != expected_states[gate]:
            raise ContractError(
                f"{args.decision} for {gate} is not allowed from {state['state']}"
            )
        if args.decision == "reject":
            if args.change_scope is not None:
                raise ContractError("reject does not accept change_scope")
            next_state = _advance(state, "stop", {})
        elif gate == "data":
            if args.change_scope not in {None, "data"}:
                raise ContractError("Data request_changes only accepts change_scope=data")
            next_state = dict(state)
        elif gate == "diagnostic":
            if args.change_scope not in {"data", "scan", "reasoning"}:
                raise ContractError(
                    "Diagnostic request_changes requires data, scan, or reasoning scope"
                )
            next_state = _advance(
                state,
                "request_diagnostic_changes",
                {"change_scope": args.change_scope},
            )
        elif gate == "final":
            if args.change_scope not in {"deep", "wording", "routing"}:
                raise ContractError(
                    "Final request_changes requires deep, wording, or routing scope"
                )
            next_state = _advance(
                state,
                "request_final_changes",
                {"change_scope": args.change_scope},
            )
        else:
            raise ContractError(f"request_changes is not supported for {gate}")
        next_state["revision"] = current + 1
        additional = {
            "workflow/state.json": canonical_bytes(next_state),
            "workflow/pending-overlay.json": None,
            "workflow/pending-runtime-context.json": None,
            f"audit/events/r{current + 1:04d}-decide-web.json": canonical_bytes({
                "command": "decide-web",
                "decision": args.decision,
                "gate": gate,
                "change_scope": args.change_scope,
                "from_revision": current,
                "to_revision": current + 1,
            }),
        }
        decision_record, revision = ApprovalService(revisions).decide_web(
            args.request_id,
            decision=args.decision,
            expected_revision=current,
            actor_id=args.actor_id,
            actor_role=args.actor_role,
            nonce=args.nonce,
            rationale=args.rationale,
            browser_session_fingerprint=args.browser_session_fingerprint,
            response_hash=args.response_hash,
            additional_updates=additional,
        )
        return 0, _application_result(
            command=args.command,
            ok=True,
            code=0,
            message="human decision committed",
            run_id=args.run_id,
            revision=revision,
            state=next_state["state"],
            data={
                "approval_id": decision_record["approval_id"],
                "gate": gate,
                "decision": args.decision,
            },
        )
    elif args.command == "resume":
        blocker_resolved = _recorded_blocker_is_resolved(files, state)
        if not blocker_resolved:
            raise ContractError("recorded blocker is unresolved")
        state = _advance(
            state,
            "resume",
            {"blocker_resolved": blocker_resolved, "expected_revision": current},
        )
    elif args.command == "stop":
        state = _advance(state, "stop", {})
    elif args.command == "cancel":
        state = _advance(state, "cancel", {})
    elif args.command == "finalize":
        if state["state"] != "delivery_approved":
            raise ContractError("finalize requires delivery_approved state")
        revalidate_component_artifacts(files)
        package = build_delivery_package(files, run_id=args.run_id, revision=current + 1)
        files.update(package)
        data["delivery_files"] = sorted(package)
        state = _advance(state, "finalize", {"final_validator_passed": True})

    new_revision = current + 1
    state["revision"] = new_revision
    files["workflow/state.json"] = canonical_bytes(state)
    files[f"audit/events/r{new_revision:04d}-{args.command}.json"] = canonical_bytes(
        {"command": args.command, "from_revision": current, "to_revision": new_revision}
    )
    store.publish(current, files)
    return exit_code, _application_result(
        command=args.command, ok=command_ok, code=exit_code,
        message="human action required" if exit_code == 2 else command_message,
        run_id=args.run_id, revision=new_revision, state=state["state"], data=data,
    )


SUPPORTED_MUTATIONS = frozenset({
    "scan",
    "run-components",
    "prepare-finalization",
    "prepare-jobs",
    "ingest-result",
    "reduce-stage",
    "approval-request",
    "approve-web",
    "decide-web",
    "resume",
    "stop",
    "cancel",
    "finalize",
})

_PARAMETER_CONTRACTS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "scan": (frozenset(), frozenset()),
    "run-components": (
        frozenset({"scope_ref"}),
        frozenset({"accounting_input", "professional_input"}),
    ),
    "prepare-finalization": (frozenset(), frozenset()),
    "prepare-jobs": (frozenset({"stage"}), frozenset()),
    "ingest-result": (
        frozenset({"job_id", "draft_document"}),
        frozenset({"draft_source"}),
    ),
    "reduce-stage": (frozenset({"stage"}), frozenset()),
    "approval-request": (
        frozenset({"gate", "overlay_document"}),
        frozenset(),
    ),
    "approve-web": (
        frozenset({
            "request_id",
            "actor_id",
            "actor_role",
            "nonce",
            "rationale",
            "browser_session_fingerprint",
            "response_hash",
        }),
        frozenset(),
    ),
    "decide-web": (
        frozenset({
            "request_id",
            "decision",
            "actor_id",
            "actor_role",
            "nonce",
            "rationale",
            "browser_session_fingerprint",
            "response_hash",
            "change_scope",
        }),
        frozenset(),
    ),
    "resume": (frozenset(), frozenset()),
    "stop": (frozenset(), frozenset()),
    "cancel": (frozenset(), frozenset()),
    "finalize": (frozenset(), frozenset()),
}


class _DocumentPayload:
    def __init__(self, value: Any, *, label: str) -> None:
        if isinstance(value, bytes):
            self._payload = value
            return
        if not isinstance(value, Mapping):
            raise ContractError(f"{label} must be an object or JSON bytes")
        try:
            parsed = strict_loads(json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ))
            self._payload = canonical_bytes(parsed)
        except (TypeError, ValueError) as error:
            raise ContractError(f"{label} is not valid JSON") from error

    def read_bytes(self) -> bytes:
        return self._payload


def _validated_parameters(request: MutationRequest) -> dict[str, Any]:
    if request.command not in SUPPORTED_MUTATIONS:
        raise ContractError(f"unsupported mutation command: {request.command}")
    if not isinstance(request.parameters, Mapping):
        raise ContractError("mutation parameters must be an object")
    if any(not isinstance(key, str) for key in request.parameters):
        raise ContractError("mutation parameter names must be strings")
    required, optional = _PARAMETER_CONTRACTS[request.command]
    supplied = frozenset(request.parameters)
    missing = sorted(required - supplied)
    if missing:
        raise ContractError(
            f"missing required parameters for {request.command}: {', '.join(missing)}"
        )
    unexpected = sorted(supplied - required - optional)
    if unexpected:
        raise ContractError(
            f"unexpected parameters for {request.command}: {', '.join(unexpected)}"
        )
    values = dict(request.parameters)
    document_parameters = {"draft_document", "overlay_document"}
    for key in sorted(required - document_parameters - {"change_scope"}):
        value = values[key]
        if not isinstance(value, str) or not value.strip():
            raise ContractError(f"{key} must be a non-empty string")
    change_scope = values.get("change_scope")
    if change_scope is not None and (
        not isinstance(change_scope, str) or not change_scope.strip()
    ):
        raise ContractError("change_scope must be null or a non-empty string")
    for key in ("accounting_input", "professional_input"):
        value = values.get(key)
        if value is not None and not isinstance(value, Path):
            raise ContractError(f"{key} must be a filesystem path or null")
    stage = values.get("stage")
    if "stage" in values and stage not in {
        "schema_mapping", "lens", "integrated", "deep_dive", "writer",
    }:
        raise ContractError(f"unsupported stage: {stage}")
    gate = values.get("gate")
    if "gate" in values and gate not in GATES:
        raise ContractError(f"unsupported approval gate: {gate}")
    decision = values.get("decision")
    if "decision" in values and decision not in {"request_changes", "reject"}:
        raise ContractError(f"unsupported web decision: {decision}")
    draft_source = values.get("draft_source")
    if draft_source is not None and draft_source not in {
        "model_draft",
        "deterministic_canonical",
    }:
        raise ContractError(f"unsupported draft source: {draft_source}")
    return values


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
