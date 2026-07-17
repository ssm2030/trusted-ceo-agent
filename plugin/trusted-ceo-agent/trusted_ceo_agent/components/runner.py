from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Mapping, Sequence

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.components.builtins import IMPLEMENTATIONS
from trusted_ceo_agent.components.models import ComponentRunResult, NotAssessable
from trusted_ceo_agent.components.registry import (
    CONTRACTS,
    validate_component_parameters,
    validate_component_thresholds,
)
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.contracts.ids import make_id


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def execute_component(
    component_id: str,
    facts: Sequence[Mapping[str, Any]],
    parameters: Mapping[str, Any],
    *,
    thresholds: Mapping[str, Any] | None = None,
    pack_refs: Sequence[str] = (),
    input_artifact_hash: str = "",
) -> ComponentRunResult:
    if component_id not in CONTRACTS:
        raise ValueError(f"unknown component: {component_id}")
    contract = CONTRACTS[component_id]
    if len(facts) > contract.max_input_records:
        raise ValueError(f"component input limit exceeded: {component_id}")
    sorted_fact_ids = tuple(sorted(str(fact.get("fact_id", "")) for fact in facts))
    parameter_hash = _digest(parameters)
    sorted_pack_refs = tuple(sorted(set(str(ref) for ref in pack_refs)))
    run_payload = {
        "component_id": component_id,
        "component_version": contract.version,
        "input_artifact_hash": input_artifact_hash,
        "sorted_input_fact_ids": list(sorted_fact_ids),
        "parameter_hash": parameter_hash,
        "pack_refs": list(sorted_pack_refs),
    }
    component_run_id = make_id("component_run", run_payload)
    try:
        validate_component_parameters(component_id, parameters)
        validate_component_thresholds(parameters, thresholds)
        output_facts, output_signals = IMPLEMENTATIONS[component_id](
            tuple(facts), dict(parameters), dict(thresholds or {}), component_run_id, parameter_hash
        )
        status = "completed"
        reasons: tuple[str, ...] = ()
    except NotAssessable as error:
        output_facts, output_signals = [], []
        status = "not_assessable"
        reasons = error.reason_codes
    except (ContractError, KeyError, TypeError, ValueError, ArithmeticError):
        output_facts, output_signals = [], []
        status = "failed"
        reasons = ("component_contract_failure",)
    return ComponentRunResult(
        component_run_id=component_run_id,
        component_id=component_id,
        component_version=contract.version,
        input_artifact_hash=input_artifact_hash,
        sorted_input_fact_ids=sorted_fact_ids,
        parameter_hash=parameter_hash,
        pack_refs=sorted_pack_refs,
        output_facts=tuple(sorted(output_facts, key=lambda item: item["fact_id"])),
        output_signals=tuple(sorted(output_signals, key=lambda item: item["signal_id"])),
        status=status,
        reason_codes=reasons,
    )


def execute_plan(
    plan: Sequence[Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
    *,
    thresholds: Mapping[str, Any] | None = None,
    pack_refs: Sequence[str] = (),
    input_artifact_hash: str = "",
    max_workers: int = 1,
) -> tuple[ComponentRunResult, ...]:
    if max_workers not in {1, 2, 3, 4}:
        raise ValueError("component workers must be between 1 and 4")
    ordered_plan = sorted(
        (dict(item) for item in plan),
        key=lambda item: (str(item.get("component_id", "")), canonical_bytes(item.get("parameters", {}))),
    )

    def run(item: Mapping[str, Any]) -> ComponentRunResult:
        return execute_component(
            str(item["component_id"]),
            tuple(facts),
            item.get("parameters", {}),
            thresholds=thresholds,
            pack_refs=pack_refs,
            input_artifact_hash=input_artifact_hash,
        )

    if max_workers == 1:
        results = [run(item) for item in ordered_plan]
    else:
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="trusted-ceo-component") as pool:
            results = list(pool.map(run, ordered_plan))
    return tuple(sorted(results, key=lambda item: item.component_run_id))
