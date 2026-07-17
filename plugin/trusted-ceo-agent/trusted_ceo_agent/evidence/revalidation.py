from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.components.plans import (
    ComponentPlanResult,
    execute_materialized_plan,
    materialize_component_plan,
)
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, IntegrityError


def _first_difference(left: Any, right: Any, path: str = "$") -> str:
    if type(left) is not type(right):
        return f"{path} type {type(left).__name__}!={type(right).__name__}"
    if isinstance(left, Mapping):
        if set(left) != set(right):
            return f"{path} keys {sorted(set(left) ^ set(right))}"
        for key in sorted(left):
            difference = _first_difference(left[key], right[key], f"{path}.{key}")
            if difference:
                return difference
        return ""
    if isinstance(left, (list, tuple)):
        if len(left) != len(right):
            return f"{path} length {len(left)}!={len(right)}"
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            difference = _first_difference(left_item, right_item, f"{path}[{index}]")
            if difference:
                return difference
        return ""
    return "" if left == right else f"{path} value differs"


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else value
    if isinstance(value, Mapping):
        return {str(key): _plain(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_plain(child) for child in value]
    return value


def _document(files: Mapping[str, bytes], path: str) -> Mapping[str, Any]:
    payload = files.get(path)
    if payload is None:
        raise IntegrityError(f"required Component artifact is missing: {path}")
    value = strict_loads(payload)
    if not isinstance(value, Mapping):
        raise IntegrityError(f"Component artifact must be an object: {path}")
    return value


def _stored_plan(document: Mapping[str, Any]) -> ComponentPlanResult:
    if set(document) != {"entries", "thresholds", "pack_manifest_hash"}:
        raise IntegrityError("stored Component plan has unknown or missing fields")
    entries = document["entries"]
    thresholds = document["thresholds"]
    manifest_hash = document["pack_manifest_hash"]
    if not isinstance(entries, list) or not isinstance(thresholds, Mapping):
        raise IntegrityError("stored Component plan shape is invalid")
    if not isinstance(manifest_hash, str) or len(manifest_hash) != 64:
        raise IntegrityError("stored Component plan manifest hash is invalid")
    return ComponentPlanResult(
        tuple(_plain(dict(entry)) for entry in entries if isinstance(entry, Mapping)),
        {str(key): _plain(dict(value)) for key, value in thresholds.items() if isinstance(value, Mapping)},
        manifest_hash,
    )


def _rematerialize(
    files: Mapping[str, bytes],
    core: Mapping[str, Any],
    path: str,
    stored: ComponentPlanResult,
) -> ComponentPlanResult:
    if path.endswith("/analysis.json"):
        problem_refs = tuple(sorted({
            str(entry["problem_pack_ref"]) for entry in stored.entries
        }))
        return materialize_component_plan(
            files=files,
            core=core,
            stage="analysis",
            problem_family_refs=problem_refs,
        )
    integrated = _document(files, "reasoning/integrated-assessment.json")
    scope = _document(files, "components/scope.json")
    return materialize_component_plan(
        files=files,
        core=core,
        stage="deep_dive",
        integrated_assessment=integrated,
        approved_scope={
            "component_ids": scope.get("component_ids", []),
            "issue_ids": scope.get("issue_ids", []),
        },
    )


def revalidate_component_artifacts(files: Mapping[str, bytes]) -> dict[str, Any]:
    plan_paths = sorted(
        path for path in files
        if path.startswith("components/plans/") and path.endswith(".json")
    )
    run_paths = sorted(
        path for path in files
        if path.startswith("components/runs/") and path.endswith(".json")
    )
    if not plan_paths and not run_paths:
        return {"plan_paths": [], "component_run_ids": []}
    if not plan_paths:
        raise IntegrityError("Component runs exist without an immutable plan")
    core = _plain(dict(_document(files, "evidence/core.json")))
    facts = core.get("fact_register", [])
    if not isinstance(facts, list):
        raise IntegrityError("Evidence Core fact register is invalid")
    schemas = SchemaStore()
    stored_runs: dict[str, Mapping[str, Any]] = {}
    for path in run_paths:
        document = _plain(dict(_document(files, path)))
        schemas.validate("component-run.schema.json", document)
        run_id = str(document.get("component_run_id", ""))
        if path != f"components/runs/{run_id}.json" or run_id in stored_runs:
            raise IntegrityError(f"Component run path or identity is invalid: {path}")
        stored_runs[run_id] = document

    claimed: set[str] = set()
    for path in plan_paths:
        stored_plan = _stored_plan(_document(files, path))
        entry_ids = {str(entry["plan_entry_id"]) for entry in stored_plan.entries}
        input_documents = [
            _document(files, input_path)
            for input_path in sorted(files)
            if input_path.startswith("components/inputs/") and input_path.endswith(".json")
            and _document(files, input_path).get("plan_entry_id") in entry_ids
        ]
        if len(input_documents) != len(stored_plan.entries):
            raise IntegrityError(f"Component plan input audit is incomplete: {path}")
        plan_run_ids = {
            str(document.get("component_run_id", ""))
            for document in input_documents
        }
        resolution_core = dict(core)
        resolution_core["fact_register"] = [
            fact for fact in facts
            if not (
                isinstance(fact.get("derivation"), Mapping)
                and fact["derivation"].get("component_run_id") in plan_run_ids
            )
        ]
        rematerialized = _rematerialize(files, resolution_core, path, stored_plan)
        if canonical_bytes(stored_plan.to_dict()) != canonical_bytes(rematerialized.to_dict()):
            difference = _first_difference(stored_plan.to_dict(), rematerialized.to_dict())
            raise IntegrityError(
                f"Component plan differs from immutable Pack resolution: {path}: {difference}"
            )
        input_hashes = {
            str(document.get("input_artifact_hash", ""))
            for document in input_documents
        }
        if len(input_hashes) != 1 or len(next(iter(input_hashes))) != 64:
            raise IntegrityError(f"Component plan input artifact hash is inconsistent: {path}")
        recomputed = execute_materialized_plan(
            rematerialized,
            resolution_core["fact_register"],
            input_artifact_hash=next(iter(input_hashes)),
            max_workers=1,
        )
        expected_runs = {item.component_run_id: item.to_dict() for item in recomputed}
        audited_ids = {str(document.get("component_run_id", "")) for document in input_documents}
        if audited_ids != set(expected_runs):
            raise IntegrityError(f"Component input audit does not match recomputed runs: {path}")
        for run_id, expected in expected_runs.items():
            stored = stored_runs.get(run_id)
            if stored is None or canonical_bytes(stored) != canonical_bytes(expected):
                difference = "stored run missing" if stored is None else _first_difference(stored, expected)
                raise IntegrityError(
                    f"Component run recomputation mismatch: {run_id}: {difference}"
                )
            input_document = next(
                document for document in input_documents
                if document.get("component_run_id") == run_id
            )
            if sorted(input_document.get("input_fact_ids", [])) != sorted(expected["sorted_input_fact_ids"]):
                raise IntegrityError(f"Component input Fact audit mismatch: {run_id}")
            claimed.add(run_id)
    if claimed != set(stored_runs):
        raise IntegrityError(
            f"Component runs are not covered by plans: {sorted(set(stored_runs) - claimed)}"
        )
    core_facts = {
        str(item["fact_id"]): item
        for item in core.get("fact_register", [])
        if isinstance(item, Mapping) and isinstance(item.get("fact_id"), str)
    }
    core_signals = {
        str(item["signal_id"]): item
        for item in core.get("signal_register", [])
        if isinstance(item, Mapping) and isinstance(item.get("signal_id"), str)
    }
    expected_output_facts: dict[str, Mapping[str, Any]] = {}
    expected_output_signals: dict[str, Mapping[str, Any]] = {}
    for run in stored_runs.values():
        for fact in run.get("output_facts", []):
            expected_output_facts[str(fact["fact_id"])] = fact
        for signal in run.get("output_signals", []):
            expected_output_signals[str(signal["signal_id"])] = signal
    for fact_id, expected in expected_output_facts.items():
        if fact_id not in core_facts or canonical_bytes(core_facts[fact_id]) != canonical_bytes(expected):
            raise IntegrityError(f"Evidence Core Component Fact mismatch: {fact_id}")
    for signal_id, expected in expected_output_signals.items():
        if signal_id not in core_signals or canonical_bytes(core_signals[signal_id]) != canonical_bytes(expected):
            raise IntegrityError(f"Evidence Core Component Signal mismatch: {signal_id}")
    claimed_fact_ids = {
        fact_id for fact_id, fact in core_facts.items()
        if isinstance(fact.get("derivation"), Mapping)
        and fact["derivation"].get("component_run_id") in claimed
    }
    claimed_signal_ids = {
        signal_id for signal_id, signal in core_signals.items()
        if isinstance(signal.get("component_ref"), Mapping)
        and signal["component_ref"].get("component_run_id") in claimed
    }
    if claimed_fact_ids != set(expected_output_facts) or claimed_signal_ids != set(expected_output_signals):
        raise IntegrityError("Evidence Core contains missing or extra Component outputs")
    manifest_refs = set(core.get("component_manifest", {}).get("component_refs", []))
    if not claimed.issubset(manifest_refs):
        raise IntegrityError("Evidence Core Component manifest omits executed runs")
    return {
        "plan_paths": plan_paths,
        "component_run_ids": sorted(claimed),
    }


__all__ = ["revalidate_component_artifacts"]
