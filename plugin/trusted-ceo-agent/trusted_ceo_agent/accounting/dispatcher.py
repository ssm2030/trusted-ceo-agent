"""Deterministic dispatcher for the complete 64-family accounting Suite."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from trusted_ceo_agent.accounting.execution import (
    AccountingExecutionRegistry,
    verify_accounting_execution_manifest,
)
from trusted_ceo_agent.accounting.seeds import ISSUE_ROWS
from trusted_ceo_agent.accounting.suite import validate_accounting_suite
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError

_SCHEMA = "accounting-execution-bundle.schema.json"
_SCHEMA_STORE = SchemaStore()
_PROJECT_IDS = tuple(f"CA-{number:02d}" for number in range(1, 17))
_EXPECTED_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tier_zero", tuple(f"AC-{number:02d}" for number in range(1, 6))),
    *(
        ("core_extended", (f"AC-{number:02d}",))
        for number in range(6, 17)
    ),
    ("revenue", tuple(f"RV-{number:02d}" for number in range(1, 17))),
    ("cashflow", tuple(f"CF-{number:02d}" for number in range(1, 17))),
    *(("project_cost", (issue_id,)) for issue_id in _PROJECT_IDS),
)
_ISSUE_IDS = tuple(row[0] for row in ISSUE_ROWS)


def _digest(value: Mapping[str, Any], excluded: str | None = None) -> str:
    body = dict(value)
    if excluded is not None:
        body.pop(excluded, None)
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def _binding(value: Mapping[str, Any], label: str) -> tuple[str, int]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} must be an object")
    run_id = value.get("run_id")
    revision = value.get("revision")
    if not isinstance(run_id, str) or not run_id:
        raise ContractError(f"{label} requires run_id")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ContractError(f"{label} requires non-negative revision")
    return run_id, revision


def _preflight(
    tier_zero_input: Mapping[str, Any],
    raw_core_population: Mapping[str, Any],
    revenue_input: Mapping[str, Any],
    cashflow_input: Mapping[str, Any],
    project_cost_inputs: Mapping[str, Mapping[str, Any]],
) -> tuple[str, int]:
    if not isinstance(project_cost_inputs, Mapping):
        raise ContractError("project_cost_inputs must be an object")
    if set(project_cost_inputs) != set(_PROJECT_IDS):
        missing = sorted(set(_PROJECT_IDS) - set(project_cost_inputs))
        unknown = sorted(set(project_cost_inputs) - set(_PROJECT_IDS))
        raise ContractError(
            "project_cost_inputs must contain CA-01..CA-16; "
            f"missing={missing}, unknown={unknown}"
        )
    expected = _binding(tier_zero_input, "tier_zero_input")
    candidates: list[tuple[str, Mapping[str, Any]]] = [
        ("raw_core_population", raw_core_population),
        ("revenue_input", revenue_input),
        ("cashflow_input", cashflow_input),
        *(
            (f"project_cost_inputs[{issue_id}]", project_cost_inputs[issue_id])
            for issue_id in _PROJECT_IDS
        ),
    ]
    for label, value in candidates:
        if _binding(value, label) != expected:
            raise ContractError(f"{label} crosses accounting run or revision")
    return expected


def _artifact(
    result_type: str,
    family_ids: Sequence[str],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "result_type": result_type,
        "family_ids": list(family_ids),
        "content_hash": payload["content_hash"],
        "payload": copy.deepcopy(dict(payload)),
    }


def dispatch_accounting_suite(
    *,
    suite: Mapping[str, Any],
    tier_zero_input: Mapping[str, Any],
    raw_core_population: Mapping[str, Any],
    revenue_input: Mapping[str, Any],
    cashflow_input: Mapping[str, Any],
    project_cost_inputs: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Run every deterministic accounting Pack entry point exactly once."""
    from trusted_ceo_agent.accounting.cashflow_procedures import (
        run_cashflow_procedures,
    )
    from trusted_ceo_agent.accounting.core_extended_procedures import (
        run_core_extended_procedure,
    )
    from trusted_ceo_agent.accounting.core_procedures import run_tier_zero_procedures
    from trusted_ceo_agent.accounting.project_cost_procedures import (
        run_project_cost_procedure,
    )
    from trusted_ceo_agent.accounting.raw_journal_adapter import (
        materialize_core_extended_inputs,
    )
    from trusted_ceo_agent.accounting.revenue_procedures import run_revenue_procedures

    verified_suite = validate_accounting_suite(suite)
    run_id, revision = _preflight(
        tier_zero_input,
        raw_core_population,
        revenue_input,
        cashflow_input,
        project_cost_inputs,
    )
    registry = AccountingExecutionRegistry(verified_suite)
    artifacts: list[dict[str, Any]] = []

    tier_zero = run_tier_zero_procedures(tier_zero_input)
    registry.record_tier_zero(tier_zero)
    artifacts.append(_artifact("tier_zero", _EXPECTED_GROUPS[0][1], tier_zero))

    core_inputs = materialize_core_extended_inputs(raw_core_population)
    core_ids = tuple(f"AC-{number:02d}" for number in range(6, 17))
    if tuple(core_inputs) != core_ids:
        raise ContractError("raw core population did not produce AC-06..AC-16")
    for issue_id in core_ids:
        result = run_core_extended_procedure(issue_id, core_inputs[issue_id])
        registry.record_core_extended(result)
        artifacts.append(_artifact("core_extended", (issue_id,), result))

    revenue = run_revenue_procedures(revenue_input)
    registry.record_revenue(revenue)
    artifacts.append(
        _artifact(
            "revenue",
            tuple(f"RV-{number:02d}" for number in range(1, 17)),
            revenue,
        )
    )

    cashflow = run_cashflow_procedures(cashflow_input)
    registry.record_cashflow(cashflow)
    artifacts.append(
        _artifact(
            "cashflow",
            tuple(f"CF-{number:02d}" for number in range(1, 17)),
            cashflow,
        )
    )

    for issue_id in _PROJECT_IDS:
        result = run_project_cost_procedure(issue_id, project_cost_inputs[issue_id])
        registry.record_project_cost(result)
        artifacts.append(_artifact("project_cost", (issue_id,), result))

    manifest = registry.finalize()
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "suite_id": verified_suite["suite_id"],
        "release_id": verified_suite["release_id"],
        "suite_hash": verified_suite["content_hash"],
        "run_id": run_id,
        "revision": revision,
        "execution_manifest": manifest,
        "result_artifacts": artifacts,
        "authority_ceiling": "Boundary",
    }
    bundle = {**body, "content_hash": _digest(body)}
    return verify_accounting_execution_bundle(bundle)


def _verify_payload(result_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if result_type == "tier_zero":
        from trusted_ceo_agent.accounting.core_procedures import verify_tier_zero_result

        return verify_tier_zero_result(payload)
    if result_type == "core_extended":
        from trusted_ceo_agent.accounting.core_extended_procedures import (
            verify_core_extended_procedure_result,
        )

        return verify_core_extended_procedure_result(payload)
    if result_type == "revenue":
        from trusted_ceo_agent.accounting.revenue_procedures import (
            verify_revenue_procedure_result,
        )

        return verify_revenue_procedure_result(payload)
    if result_type == "cashflow":
        from trusted_ceo_agent.accounting.cashflow_procedures import (
            verify_cashflow_procedure_result,
        )

        return verify_cashflow_procedure_result(payload)
    if result_type == "project_cost":
        from trusted_ceo_agent.accounting.project_cost_procedures import (
            verify_project_cost_procedure_result,
        )

        verify_project_cost_procedure_result(payload)
        return copy.deepcopy(dict(payload))
    raise ContractError(f"unknown accounting result type: {result_type}")


def _payload_family_ids(
    result_type: str, payload: Mapping[str, Any]
) -> tuple[str, ...]:
    if result_type in {"tier_zero", "revenue", "cashflow"}:
        return tuple(item["issue_family_id"] for item in payload["procedure_results"])
    return (payload["issue_family_id"],)


def verify_accounting_execution_bundle(value: Mapping[str, Any]) -> dict[str, Any]:
    """Verify every embedded result and all hash/lineage joins."""
    if not isinstance(value, Mapping):
        raise ContractError("accounting execution bundle must be an object")
    _SCHEMA_STORE.validate(_SCHEMA, value)
    if value["content_hash"] != _digest(value, "content_hash"):
        raise ContractError("accounting execution bundle content hash mismatch")
    manifest = verify_accounting_execution_manifest(value["execution_manifest"])
    manifest_binding = (
        manifest["suite_id"],
        manifest["release_id"],
        manifest["suite_hash"],
        manifest["run_id"],
        manifest["revision"],
    )
    bundle_binding = (
        value["suite_id"],
        value["release_id"],
        value["suite_hash"],
        value["run_id"],
        value["revision"],
    )
    if manifest_binding != bundle_binding:
        raise ContractError("execution manifest does not bind to its bundle")

    artifacts = value["result_artifacts"]
    if len(artifacts) != len(_EXPECTED_GROUPS):
        raise ContractError("accounting execution bundle requires 30 result artifacts")
    seen_hashes: set[str] = set()
    parent_by_family: dict[str, str] = {}
    for artifact, (expected_type, expected_ids) in zip(
        artifacts, _EXPECTED_GROUPS, strict=True
    ):
        result_type = artifact["result_type"]
        if result_type != expected_type or tuple(artifact["family_ids"]) != expected_ids:
            raise ContractError(
                "accounting result artifacts are missing, duplicated, or unordered"
            )
        payload = _verify_payload(result_type, artifact["payload"])
        if artifact["content_hash"] != payload.get("content_hash"):
            raise ContractError("accounting result artifact hash mismatch")
        if artifact["content_hash"] in seen_hashes:
            raise ContractError("duplicate accounting result artifact")
        seen_hashes.add(artifact["content_hash"])
        if (payload.get("run_id"), payload.get("revision")) != (
            value["run_id"],
            value["revision"],
        ):
            raise ContractError("accounting result artifact crosses run or revision")
        if _payload_family_ids(result_type, payload) != expected_ids:
            raise ContractError("accounting result artifact family selector mismatch")
        for issue_id in expected_ids:
            if issue_id in parent_by_family:
                raise ContractError(f"duplicate accounting family result: {issue_id}")
            parent_by_family[issue_id] = artifact["content_hash"]

    if tuple(parent_by_family) != _ISSUE_IDS:
        raise ContractError("accounting bundle does not cover all 64 ordered families")
    if any(
        parent_by_family[item["issue_family_id"]] != item["parent_result_hash"]
        for item in manifest["family_records"]
    ):
        raise ContractError("accounting bundle result lineage does not match manifest")
    return copy.deepcopy(dict(value))


__all__ = ["dispatch_accounting_suite", "verify_accounting_execution_bundle"]
