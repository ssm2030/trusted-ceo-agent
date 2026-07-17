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


def execute_authorized_scope(
    files: Mapping[str, bytes],
    core: Mapping[str, Any],
    integrated_assessment: Mapping[str, Any],
    scope: Mapping[str, Any],
    supplied_scope_ref: str,
) -> tuple[ComponentPlanResult, tuple[dict[str, Any], ...]]:
    component_ids = scope.get("component_ids", [])
    issue_ids = scope.get("issue_ids", [])
    if not isinstance(component_ids, list) or not all(isinstance(item, str) for item in component_ids):
        raise ContractError("approved component_ids must be an array of strings")
    if not isinstance(issue_ids, list) or not all(isinstance(item, str) for item in issue_ids):
        raise ContractError("approved issue_ids must be an array of strings")
    normalized_scope = {
        "component_ids": sorted(set(component_ids)),
        "issue_ids": sorted(set(issue_ids)),
    }
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
        evidence_links=core["evidence_links"],
        capability_map=core["capability_map"],
    )
