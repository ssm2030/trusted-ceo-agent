from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.components.plans import (
    ComponentPlanResult,
    execute_materialized_plan,
    materialize_component_plan,
)
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.evidence.core import assemble_evidence_core


_SPECIALIST_INPUTS = frozenset({"accounting", "professional"})


def normalize_authorized_scope(scope: Mapping[str, Any]) -> dict[str, list[str]]:
    component_ids = scope.get("component_ids", [])
    issue_ids = scope.get("issue_ids", [])
    required_inputs = scope.get("required_inputs", [])
    for label, values in (
        ("component_ids", component_ids),
        ("issue_ids", issue_ids),
        ("required_inputs", required_inputs),
    ):
        if not isinstance(values, list) or not all(
            isinstance(item, str) and item for item in values
        ):
            raise ContractError(
                f"approved {label} must be an array of non-empty strings"
            )
    unknown_inputs = set(required_inputs) - _SPECIALIST_INPUTS
    if unknown_inputs:
        raise ContractError(
            f"approved required_inputs are unsupported: {sorted(unknown_inputs)}"
        )
    return {
        "component_ids": sorted(set(component_ids)),
        "issue_ids": sorted(set(issue_ids)),
        "required_inputs": sorted(set(required_inputs)),
    }


def bind_accounting_professional_inputs(
    accounting_bundle: Mapping[str, Any],
    professional_request: Mapping[str, Any],
) -> dict[str, Any]:
    from trusted_ceo_agent.accounting.dispatcher import (
        verify_accounting_execution_bundle,
    )

    verified = verify_accounting_execution_bundle(accounting_bundle)
    manifest = verified["execution_manifest"]
    family_by_id = {
        str(item["issue_family_id"]): str(item["parent_result_hash"])
        for item in manifest["family_records"]
    }
    if len(family_by_id) != 64:
        raise ContractError("accounting execution bundle must cover all 64 families")

    runtime_input = professional_request.get("runtime_input")
    task_results = professional_request.get("task_results")
    task_failures = professional_request.get("task_failures")
    if not isinstance(runtime_input, Mapping):
        raise ContractError("professional runtime_input is missing for accounting binding")
    if not isinstance(task_results, Mapping) or not isinstance(task_failures, Mapping):
        raise ContractError("professional task outcomes are missing for accounting binding")
    work_plans = runtime_input.get("work_plans")
    if not isinstance(work_plans, list):
        raise ContractError("professional work_plans are missing for accounting binding")

    bindings: list[dict[str, Any]] = []
    seen_work_keys: set[str] = set()
    for work in work_plans:
        if not isinstance(work, Mapping) or work.get("domain") != "accounting":
            continue
        work_key = work.get("local_key")
        family_id = work.get("issue_family")
        packet_hash = work.get("packet_hash")
        if not isinstance(work_key, str) or not work_key:
            raise ContractError("accounting Work Item local_key is invalid")
        if work_key in seen_work_keys:
            raise ContractError(f"duplicate accounting Work Item key: {work_key}")
        seen_work_keys.add(work_key)
        if not isinstance(family_id, str) or family_id not in family_by_id:
            raise ContractError(
                f"accounting Work Item uses an unknown issue_family: {family_id}"
            )
        expected_hash = family_by_id[family_id]
        if packet_hash != expected_hash:
            raise ContractError(
                f"accounting Work Item packet_hash does not bind {family_id}"
            )

        finding_bindings: list[dict[str, Any]] = []
        if work_key in task_results:
            outcome = task_results[work_key]
            if not isinstance(outcome, Mapping):
                raise ContractError("professional task result must be an object")
            findings = outcome.get("findings")
            if not isinstance(findings, list):
                raise ContractError("professional task findings must be an array")
            for finding in findings:
                if not isinstance(finding, Mapping):
                    raise ContractError("professional Finding entry must be an object")
                spec = finding.get("spec")
                if not isinstance(spec, Mapping):
                    raise ContractError("professional Finding spec must be an object")
                family_refs = spec.get("issue_family_refs")
                procedure_refs = spec.get("procedure_result_refs")
                if not isinstance(family_refs, list) or not all(
                    isinstance(item, str) and item for item in family_refs
                ):
                    raise ContractError(
                        "accounting Finding issue_family_refs must be strings"
                    )
                if family_id not in family_refs:
                    raise ContractError(
                        "accounting Finding must include its Work Item issue_family"
                    )
                unknown_families = set(family_refs) - set(family_by_id)
                if unknown_families:
                    raise ContractError(
                        "accounting Finding uses unknown issue_family_refs: "
                        f"{sorted(unknown_families)}"
                    )
                expected_refs = sorted(
                    {family_by_id[item] for item in family_refs}
                )
                if not isinstance(procedure_refs, list) or sorted(
                    set(procedure_refs)
                ) != expected_refs:
                    raise ContractError(
                        "accounting Finding procedure_result_refs do not bind "
                        "the verified Suite results"
                    )
                finding_bindings.append({
                    "finding_key": finding.get("finding_key"),
                    "issue_family_refs": sorted(set(family_refs)),
                    "procedure_result_refs": expected_refs,
                })
        elif work_key not in task_failures:
            raise ContractError(
                f"accounting Work Item lacks a declared task outcome: {work_key}"
            )

        bindings.append({
            "work_plan_key": work_key,
            "issue_family_id": family_id,
            "parent_result_hash": expected_hash,
            "finding_bindings": sorted(
                finding_bindings,
                key=lambda item: str(item["finding_key"]),
            ),
        })

    body = {
        "schema_version": "1.0.0",
        "accounting_execution_bundle_hash": verified["content_hash"],
        "run_id": verified["run_id"],
        "revision": verified["revision"],
        "available_family_count": len(family_by_id),
        "bound_work_item_count": len(bindings),
        "bindings": sorted(bindings, key=lambda item: item["work_plan_key"]),
    }
    return {
        **body,
        "content_hash": hashlib.sha256(canonical_bytes(body)).hexdigest(),
    }


def execute_authorized_scope(
    files: Mapping[str, bytes],
    core: Mapping[str, Any],
    integrated_assessment: Mapping[str, Any],
    scope: Mapping[str, Any],
    supplied_scope_ref: str,
) -> tuple[ComponentPlanResult, tuple[dict[str, Any], ...]]:
    normalized_scope = normalize_authorized_scope(scope)
    expected_scope_ref = make_id("scope", normalized_scope)
    if supplied_scope_ref != expected_scope_ref:
        raise ContractError("scope ref does not match the approved diagnostic scope")
    plan = materialize_component_plan(
        files=files,
        core=core,
        stage="deep_dive",
        integrated_assessment=integrated_assessment,
        approved_scope=normalized_scope,
    )
    results = execute_materialized_plan(
        plan,
        core.get("fact_register", []),
        input_artifact_hash=str(core.get("envelope", {}).get("artifact_hash", "")),
        max_workers=max(1, min(4, len(plan.entries))),
    ) if plan.entries else ()
    schemas = SchemaStore()
    documents = tuple(result.to_dict() for result in results)
    for document in documents:
        schemas.validate("component-run.schema.json", document)
    return plan, documents


def execute_analysis_scope(
    files: Mapping[str, bytes],
    core: Mapping[str, Any],
    problem_family_refs: tuple[str, ...],
) -> tuple[ComponentPlanResult, tuple[dict[str, Any], ...]]:
    plan = materialize_component_plan(
        files=files,
        core=core,
        stage="analysis",
        problem_family_refs=problem_family_refs,
    )
    results = execute_materialized_plan(
        plan,
        core.get("fact_register", []),
        input_artifact_hash=str(core.get("envelope", {}).get("artifact_hash", "")),
        max_workers=max(1, min(4, len(plan.entries))),
    ) if plan.entries else ()
    schemas = SchemaStore()
    documents = tuple(result.to_dict() for result in results)
    for document in documents:
        schemas.validate("component-run.schema.json", document)
    return plan, documents


def component_input_documents(
    plan: ComponentPlanResult,
    runs: tuple[dict[str, Any], ...],
) -> dict[str, dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    for run in runs:
        run_id = str(run["component_run_id"])
        candidates = [
            entry for entry in plan.entries
            if entry["component_id"] == run["component_id"]
            and sorted(entry.get("input_fact_ids", [])) == sorted(run.get("sorted_input_fact_ids", []))
            and sorted(entry.get("pack_refs", [])) == sorted(run.get("pack_refs", []))
            and entry.get("parameter_hash", entry.get("parameter_template_hash")) == run.get("parameter_hash")
        ]
        if len(candidates) != 1:
            raise ContractError(f"Component run cannot be traced to one plan entry: {run_id}")
        documents[run_id] = {
            "component_run_id": run_id,
            "plan_entry_id": candidates[0]["plan_entry_id"],
            "input_fact_ids": sorted(run.get("sorted_input_fact_ids", [])),
            "input_artifact_hash": run["input_artifact_hash"],
        }
    return documents


def merge_component_runs(
    core: Mapping[str, Any],
    runs: tuple[dict[str, Any], ...],
    *,
    run_id: str,
    revision: int,
    parent_artifact_hash: str,
    stage: str = "deep_dive_jobs_ready",
) -> dict[str, Any]:
    facts = {str(item["fact_id"]): dict(item) for item in core.get("fact_register", [])}
    signals = {str(item["signal_id"]): dict(item) for item in core.get("signal_register", [])}
    for run in runs:
        for item in run.get("output_facts", []):
            identifier = str(item["fact_id"])
            if identifier in facts and canonical_bytes(facts[identifier]) != canonical_bytes(item):
                raise ContractError(f"Component produced conflicting Fact: {identifier}")
            facts[identifier] = dict(item)
        for item in run.get("output_signals", []):
            identifier = str(item["signal_id"])
            if identifier in signals and canonical_bytes(signals[identifier]) != canonical_bytes(item):
                raise ContractError(f"Component produced conflicting Signal: {identifier}")
            signals[identifier] = dict(item)
    component_refs = sorted(set(core.get("component_manifest", {}).get("component_refs", [])) | {
        str(run["component_run_id"]) for run in runs
    })
    semantic_seed = {
        "previous": core["envelope"]["semantic_fingerprint"],
        "component_runs": runs,
    }
    semantic_fingerprint = hashlib.sha256(canonical_bytes(semantic_seed)).hexdigest()
    envelope_seed = {
        "run_id": run_id,
        "revision": revision,
        "parent_artifact_hash": parent_artifact_hash,
        "semantic_fingerprint": semantic_fingerprint,
    }
    envelope = {
        "schema_version": "1.0.0",
        "artifact_id": make_id("artifact", envelope_seed),
        "run_id": run_id,
        "revision": revision,
        "parent_artifact_hash": parent_artifact_hash,
        "stage": stage,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "semantic_fingerprint": semantic_fingerprint,
        "artifact_hash": hashlib.sha256(canonical_bytes(envelope_seed)).hexdigest(),
    }
    return assemble_evidence_core(
        envelope=envelope,
        mission_contract_ref=str(core["mission_contract_ref"]),
        pack_manifest=core["pack_manifest"],
        component_manifest={"component_refs": component_refs},
        source_registry=core["source_registry"],
        data_quality_register=core["data_quality_register"],
        fact_register=list(facts.values()),
        signal_register=list(signals.values()),
        document_evidence_register=core.get('document_evidence_register', []),
        evidence_links=core["evidence_links"],
        capability_map=core["capability_map"],
    )
