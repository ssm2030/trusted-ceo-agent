from __future__ import annotations

from trusted_ceo_agent.errors import ContractError


RETRYABLE = {"contract", "invalid_json", "host_failure"}


def next_attempt_action(stage: str, attempt: int, *, required: bool, failure_kind: str) -> str:
    if attempt < 1 or attempt > 2:
        raise ContractError("attempt must be one or two")
    if failure_kind == "data_insufficient":
        return "not_assessable"
    if failure_kind not in RETRYABLE:
        raise ContractError(f"unknown failure kind: {failure_kind}")
    if attempt == 1:
        return "retry"
    if stage == "writer":
        return "fallback"
    if stage == "schema_mapping":
        return "deterministic_mapping"
    if stage == "lens" and not required:
        return "coverage_gap"
    return "blocked"
