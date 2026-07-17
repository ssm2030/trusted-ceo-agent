"""Immutable execution evidence for the 64 accounting Issue Families."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping, Sequence
from typing import Any, Callable

from trusted_ceo_agent.accounting.seeds import (
    COMMON_PROCEDURE_IDS,
    ISSUE_PROCEDURE_MAP,
    ISSUE_ROWS,
    PROCEDURE_SEED_TITLES,
)
from trusted_ceo_agent.accounting.suite import validate_accounting_suite
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError

_SCHEMA = "accounting-procedure-execution-manifest.schema.json"
_SCHEMA_STORE = SchemaStore()
_ISSUE_IDS = tuple(row[0] for row in ISSUE_ROWS)
_PROCEDURE_IDS = tuple(PROCEDURE_SEED_TITLES)


def _digest(value: Mapping[str, Any], excluded: str | None = None) -> str:
    body = dict(value)
    if excluded is not None:
        body.pop(excluded, None)
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


class AccountingExecutionRegistry:
    """Collect verified Pack results without mutating immutable Suite seeds."""

    def __init__(self, suite: Mapping[str, Any]) -> None:
        self._suite = validate_accounting_suite(suite)
        self._records: dict[str, dict[str, Any]] = {}
        self._parents: dict[str, dict[str, Any]] = {}
        self._run_id: str | None = None
        self._revision: int | None = None

    def _bind_run(self, result: Mapping[str, Any]) -> None:
        run_id = result.get("run_id")
        revision = result.get("revision")
        if not isinstance(run_id, str) or not run_id:
            raise ContractError("accounting execution result requires run_id")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ContractError("accounting execution result requires non-negative revision")
        if self._run_id is None:
            self._run_id, self._revision = run_id, revision
        elif (run_id, revision) != (self._run_id, self._revision):
            raise ContractError("accounting execution results cross run or revision")

    def _record_verified(
        self,
        result: Mapping[str, Any],
        items: Sequence[Mapping[str, Any]],
    ) -> None:
        self._bind_run(result)
        parent_hash = result.get("content_hash")
        input_hash = result.get("input_hash")
        if not isinstance(parent_hash, str) or not isinstance(input_hash, str):
            raise ContractError("verified accounting result requires immutable hashes")
        for item in items:
            issue_id = item.get("issue_family_id")
            procedure_id = item.get("procedure_id")
            if issue_id not in _ISSUE_IDS:
                raise ContractError(f"unknown accounting Issue Family: {issue_id}")
            if procedure_id != ISSUE_PROCEDURE_MAP[issue_id]:
                raise ContractError(f"{issue_id} procedure dispatch mismatch")
            if issue_id in self._records:
                raise ContractError(f"duplicate accounting execution evidence: {issue_id}")
            status = item.get("status")
            if status not in {"passed", "exceptions_found", "not_assessable"}:
                raise ContractError(f"{issue_id} has invalid execution status")
            expert_required = bool(result.get("expert_review_required", False))
            if isinstance(item.get("expert_review_required"), bool):
                expert_required = item["expert_review_required"]
            record = {
                "issue_family_id": issue_id,
                "procedure_id": procedure_id,
                "status": status,
                "parent_result_hash": parent_hash,
                "selector_hash": hashlib.sha256(canonical_bytes(item)).hexdigest(),
                "input_hash": input_hash,
                "authority_ceiling": result.get("authority_ceiling", "Boundary"),
                "expert_review_required": expert_required,
            }
            self._records[issue_id] = record
            self._parents[issue_id] = copy.deepcopy(dict(result))

    def record_tier_zero(self, result: Mapping[str, Any]) -> None:
        from trusted_ceo_agent.accounting.core_procedures import verify_tier_zero_result

        verified = verify_tier_zero_result(result)
        self._record_verified(verified, verified["procedure_results"])

    def record_core_extended(self, result: Mapping[str, Any]) -> None:
        from trusted_ceo_agent.accounting.core_extended_procedures import (
            verify_core_extended_procedure_result,
        )

        verified = verify_core_extended_procedure_result(result)
        self._record_verified(verified, [verified])

    def record_revenue(self, result: Mapping[str, Any]) -> None:
        from trusted_ceo_agent.accounting.revenue_procedures import (
            verify_revenue_procedure_result,
        )

        verified = verify_revenue_procedure_result(result)
        self._record_verified(verified, verified["procedure_results"])

    def record_cashflow(self, result: Mapping[str, Any]) -> None:
        from trusted_ceo_agent.accounting.cashflow_procedures import (
            verify_cashflow_procedure_result,
        )

        verified = verify_cashflow_procedure_result(result)
        self._record_verified(verified, verified["procedure_results"])

    def record_project_cost(self, result: Mapping[str, Any]) -> None:
        from trusted_ceo_agent.accounting.project_cost_procedures import (
            verify_project_cost_procedure_result,
        )

        verify_project_cost_procedure_result(result)
        self._record_verified(result, [result])

    def family_result(self, issue_id: str) -> dict[str, Any]:
        if issue_id not in self._parents:
            raise ContractError(f"accounting result is not registered: {issue_id}")
        return copy.deepcopy(self._parents[issue_id])

    def finalize(self) -> dict[str, Any]:
        missing = [issue_id for issue_id in _ISSUE_IDS if issue_id not in self._records]
        if missing:
            raise ContractError(f"accounting execution manifest missing families: {missing}")
        family_records = [copy.deepcopy(self._records[issue_id]) for issue_id in _ISSUE_IDS]
        procedure_records: list[dict[str, Any]] = []
        for procedure_id in _PROCEDURE_IDS:
            if procedure_id in COMMON_PROCEDURE_IDS:
                selected = family_records
            else:
                selected = [
                    item for item in family_records if item["procedure_id"] == procedure_id
                ]
            if not selected:
                raise ContractError(f"Procedure has no verified execution: {procedure_id}")
            evidence = {
                "procedure_id": procedure_id,
                "family_ids": [item["issue_family_id"] for item in selected],
                "result_hashes": sorted(
                    {item["parent_result_hash"] for item in selected}
                ),
                "execution_status": "verified",
            }
            procedure_records.append({**evidence, "evidence_hash": _digest(evidence)})
        body: dict[str, Any] = {
            "schema_version": "1.0.0",
            "suite_id": self._suite["suite_id"],
            "release_id": self._suite["release_id"],
            "suite_hash": self._suite["content_hash"],
            "run_id": self._run_id,
            "revision": self._revision,
            "family_records": family_records,
            "procedure_records": procedure_records,
            "coverage_complete": True,
            "authority_ceiling": "Boundary",
        }
        manifest = {**body, "content_hash": _digest(body)}
        verify_accounting_execution_manifest(manifest)
        return manifest


def verify_accounting_execution_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError("accounting execution manifest must be an object")
    _SCHEMA_STORE.validate(_SCHEMA, value)
    if value["content_hash"] != _digest(value, "content_hash"):
        raise ContractError("accounting execution manifest content hash mismatch")
    family_records = value["family_records"]
    if [item["issue_family_id"] for item in family_records] != list(_ISSUE_IDS):
        raise ContractError("accounting execution manifest must contain 64 ordered families")
    if any(
        item["procedure_id"] != ISSUE_PROCEDURE_MAP[item["issue_family_id"]]
        for item in family_records
    ):
        raise ContractError("accounting execution manifest procedure mapping mismatch")
    procedures = value["procedure_records"]
    if [item["procedure_id"] for item in procedures] != list(_PROCEDURE_IDS):
        raise ContractError("accounting execution manifest procedure set mismatch")
    for item in procedures:
        evidence = dict(item)
        claimed = evidence.pop("evidence_hash")
        if claimed != _digest(evidence):
            raise ContractError("accounting Procedure evidence hash mismatch")
    if value["coverage_complete"] is not True:
        raise ContractError("complete 64-family execution coverage is required")
    return copy.deepcopy(dict(value))


__all__ = ["AccountingExecutionRegistry", "verify_accounting_execution_manifest"]
