from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from trusted_ceo_agent.accounting.dispatcher import dispatch_accounting_suite
from trusted_ceo_agent.analysis.runtime import ProfessionalAnalysisRuntime, TaskExecutionFailure
from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.evidence.revalidation import revalidate_component_artifacts
from trusted_ceo_agent.runtime_components import bind_accounting_professional_inputs

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
accounting_component_artifacts = _accounting_component_artifacts
professional_component_artifacts = _professional_component_artifacts
