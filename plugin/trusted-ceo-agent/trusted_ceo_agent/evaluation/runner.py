from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.evaluation.metrics import (
    QUALITY_SCORE_METRICS,
    byte_output_hash,
    digest,
    require_hash,
    require_integer,
    require_text,
    semantic_output_hash,
    validate_quality_metrics,
)
from trusted_ceo_agent.evaluation.performance import (
    STAGE_NAMES,
    build_stage_timing,
)


_SCHEMAS = SchemaStore()


CONCURRENCY_PROFILE_IDS = (
    "sequential",
    "parallel_2",
    "parallel_3",
    "parallel_4",
)
CASE_FIELDS = frozenset({
    "schema_version",
    "case_id",
    "workload_class",
    "condition",
    "scenario_ref",
    "input_hash",
    "release_id",
    "release_hash",
    "model_profile_id",
    "oracle_ref",
    "oracle_hash",
    "required_metric_names",
    "case_hash",
})
RESULT_FIELDS = frozenset({
    "schema_version",
    "result_id",
    "case_id",
    "workload_class",
    "condition",
    "profile_id",
    "repetition",
    "paired_seed",
    "input_hash",
    "release_hash",
    "model_profile_id",
    "status",
    "failure_code",
    "semantic_output_hash",
    "byte_output_hash",
    "quality_metrics",
    "model_evaluation_status",
    "expert_evaluation_status",
    "stage_timing_ref",
    "stage_timing_hash",
    "semantic_result_hash",
    "result_hash",
})
EXECUTION_FIELDS = frozenset({
    "semantic_output",
    "output_bytes",
    "quality_metrics",
    "model_evaluation_status",
    "expert_evaluation_status",
    "stage_durations_ms",
})
FAILURE_CODES = frozenset({
    "contract_invalid",
    "packet_hash_mismatch",
    "source_unavailable",
    "model_timeout",
    "model_contract_failure",
    "procedure_failed",
    "required_evidence_missing",
    "stale_revision",
    "cancelled_by_human",
    "resource_exhausted",
    "unsupported_pack",
    "external_evaluation_unavailable",
})


class EvaluationCancelled(Exception):
    """The evaluation was cancelled before it could produce a trusted result."""


def _case_body(
    *,
    workload_class: Any,
    condition: Any,
    scenario_ref: Any,
    input_hash: Any,
    release_id: Any,
    release_hash: Any,
    model_profile_id: Any,
    oracle_ref: Any,
    oracle_hash: Any,
    required_metric_names: Sequence[str],
) -> dict[str, Any]:
    if condition not in {"cold", "warm"}:
        raise ContractError("condition must be cold or warm")
    if not isinstance(required_metric_names, (list, tuple)):
        raise ContractError("required_metric_names must be an array")
    metric_names = sorted(
        require_text(metric, "required_metric_names")
        for metric in required_metric_names
    )
    if metric_names != sorted(QUALITY_SCORE_METRICS):
        raise ContractError("EvaluationCase must require every quality score metric")
    return {
        "schema_version": "1.0.0",
        "workload_class": require_text(workload_class, "workload_class"),
        "condition": condition,
        "scenario_ref": require_text(scenario_ref, "scenario_ref"),
        "input_hash": require_hash(input_hash, "input_hash"),
        "release_id": require_text(release_id, "release_id"),
        "release_hash": require_hash(release_hash, "release_hash"),
        "model_profile_id": require_text(model_profile_id, "model_profile_id"),
        "oracle_ref": require_text(oracle_ref, "oracle_ref"),
        "oracle_hash": require_hash(oracle_hash, "oracle_hash"),
        "required_metric_names": metric_names,
    }


def build_evaluation_case(
    *,
    case_key: str,
    workload_class: str,
    condition: str,
    scenario_ref: str,
    input_hash: str,
    release_id: str,
    release_hash: str,
    model_profile_id: str,
    oracle_ref: str,
    oracle_hash: str,
    required_metric_names: Sequence[str] = QUALITY_SCORE_METRICS,
) -> dict[str, Any]:
    body = _case_body(
        workload_class=workload_class,
        condition=condition,
        scenario_ref=scenario_ref,
        input_hash=input_hash,
        release_id=release_id,
        release_hash=release_hash,
        model_profile_id=model_profile_id,
        oracle_ref=oracle_ref,
        oracle_hash=oracle_hash,
        required_metric_names=required_metric_names,
    )
    identity = {
        "case_key": require_text(case_key, "case_key"),
        **body,
    }
    case = dict(body)
    case["case_id"] = "evaluationcase_" + digest(identity)[:24]
    case["case_hash"] = digest(case)
    verify_evaluation_case(case)
    return case


def verify_evaluation_case(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or set(value) != CASE_FIELDS:
        raise ContractError("EvaluationCase fields do not match the contract")
    case = dict(value)
    body = _case_body(
        workload_class=case.get("workload_class"),
        condition=case.get("condition"),
        scenario_ref=case.get("scenario_ref"),
        input_hash=case.get("input_hash"),
        release_id=case.get("release_id"),
        release_hash=case.get("release_hash"),
        model_profile_id=case.get("model_profile_id"),
        oracle_ref=case.get("oracle_ref"),
        oracle_hash=case.get("oracle_hash"),
        required_metric_names=case.get("required_metric_names"),
    )
    if case.get("schema_version") != "1.0.0":
        raise ContractError("unsupported EvaluationCase schema version")
    if not isinstance(case.get("case_id"), str) or not case["case_id"].startswith(
        "evaluationcase_"
    ):
        raise ContractError("invalid EvaluationCase ID")
    expected_hash = digest(
        {
            **body,
            "case_id": case["case_id"],
        }
    )
    if case.get("case_hash") != expected_hash:
        raise ContractError("EvaluationCase hash mismatch")
    _SCHEMAS.validate("evaluation-case.schema.json", case)


def _semantic_result_body(
    *,
    case: Mapping[str, Any],
    profile_id: str,
    repetition: int,
    paired_seed: str,
    status: str,
    failure_code: str | None,
    output_semantic_hash: str | None,
    output_byte_hash: str | None,
    quality_metrics: Mapping[str, Any] | None,
    model_evaluation_status: str,
    expert_evaluation_status: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "case_id": case["case_id"],
        "workload_class": case["workload_class"],
        "condition": case["condition"],
        "profile_id": profile_id,
        "repetition": repetition,
        "paired_seed": paired_seed,
        "input_hash": case["input_hash"],
        "release_hash": case["release_hash"],
        "model_profile_id": case["model_profile_id"],
        "status": status,
        "failure_code": failure_code,
        "semantic_output_hash": output_semantic_hash,
        "byte_output_hash": output_byte_hash,
        "quality_metrics": (
            None if quality_metrics is None else dict(quality_metrics)
        ),
        "model_evaluation_status": model_evaluation_status,
        "expert_evaluation_status": expert_evaluation_status,
    }


def _finalize_result(
    semantic_body: Mapping[str, Any],
    *,
    stage_timing_ref: str | None,
    stage_timing_hash: str | None,
) -> dict[str, Any]:
    semantic_hash = digest(dict(semantic_body))
    core = {
        **dict(semantic_body),
        "stage_timing_ref": stage_timing_ref,
        "stage_timing_hash": stage_timing_hash,
        "semantic_result_hash": semantic_hash,
    }
    result = dict(core)
    result["result_id"] = "evaluationresult_" + digest(core)[:24]
    result["result_hash"] = digest(result)
    verify_evaluation_result(result)
    return result


def _terminal_result(
    case: Mapping[str, Any],
    profile_id: str,
    repetition: int,
    paired_seed: str,
    *,
    status: str,
    failure_code: str | None,
    timing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    semantic_body = _semantic_result_body(
        case=case,
        profile_id=profile_id,
        repetition=repetition,
        paired_seed=paired_seed,
        status=status,
        failure_code=failure_code,
        output_semantic_hash=None,
        output_byte_hash=None,
        quality_metrics=None,
        model_evaluation_status="not_evaluated",
        expert_evaluation_status="not_evaluated",
    )
    return _finalize_result(
        semantic_body,
        stage_timing_ref=None if timing is None else timing["stage_timing_id"],
        stage_timing_hash=None if timing is None else timing["telemetry_hash"],
    )


def build_evaluation_result(
    case: Mapping[str, Any],
    profile_id: str,
    repetition: int,
    paired_seed: str,
    execution: Mapping[str, Any],
    *,
    timeout_ms: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    verify_evaluation_case(case)
    if profile_id not in CONCURRENCY_PROFILE_IDS:
        raise ContractError("unsupported concurrency profile")
    repetition = require_integer(repetition, "repetition")
    paired_seed = require_hash(paired_seed, "paired_seed")
    if not isinstance(execution, Mapping) or set(execution) != EXECUTION_FIELDS:
        raise ContractError("evaluation execution fields do not match the contract")
    if not isinstance(execution["stage_durations_ms"], Mapping):
        raise ContractError("stage_durations_ms must be an object")
    stages = {
        stage: require_integer(
            execution["stage_durations_ms"].get(stage),
            f"stage_durations_ms.{stage}",
        )
        for stage in STAGE_NAMES
    }
    if set(execution["stage_durations_ms"]) != set(STAGE_NAMES):
        raise ContractError("stage_durations_ms fields do not match the contract")
    total_ms = sum(stages.values())
    timeout = None if timeout_ms is None else require_integer(
        timeout_ms, "timeout_ms", minimum=1
    )
    if timeout is not None and total_ms > timeout:
        timing = build_stage_timing(
            case_id=case["case_id"],
            workload_class=case["workload_class"],
            condition=case["condition"],
            profile_id=profile_id,
            repetition=repetition,
            paired_seed=paired_seed,
            stages_ms=stages,
            outcome="timeout",
        )
        return (
            _terminal_result(
                case,
                profile_id,
                repetition,
                paired_seed,
                status="timeout",
                failure_code="model_timeout",
                timing=timing,
            ),
            timing,
        )

    model_status = execution["model_evaluation_status"]
    expert_status = execution["expert_evaluation_status"]
    if model_status not in {"evaluated", "not_evaluated"}:
        raise ContractError("invalid model_evaluation_status")
    if expert_status not in {"evaluated", "not_evaluated"}:
        raise ContractError("invalid expert_evaluation_status")
    metrics = validate_quality_metrics(execution["quality_metrics"])
    if (
        expert_status == "evaluated"
        and metrics["expert_practice_quality"] is None
    ) or (
        expert_status == "not_evaluated"
        and metrics["expert_practice_quality"] is not None
    ):
        raise ContractError("expert evaluation status and score disagree")

    semantic_hash = semantic_output_hash(execution["semantic_output"])
    expected_bytes = canonical_bytes(execution["semantic_output"])
    output_bytes = execution["output_bytes"]
    if not isinstance(output_bytes, bytes) or output_bytes != expected_bytes:
        raise ContractError(
            "output_bytes must be the canonical bytes of semantic_output"
        )
    timing = build_stage_timing(
        case_id=case["case_id"],
        workload_class=case["workload_class"],
        condition=case["condition"],
        profile_id=profile_id,
        repetition=repetition,
        paired_seed=paired_seed,
        stages_ms=stages,
        outcome="completed",
    )
    semantic_body = _semantic_result_body(
        case=case,
        profile_id=profile_id,
        repetition=repetition,
        paired_seed=paired_seed,
        status="completed",
        failure_code=None,
        output_semantic_hash=semantic_hash,
        output_byte_hash=byte_output_hash(output_bytes),
        quality_metrics=metrics,
        model_evaluation_status=model_status,
        expert_evaluation_status=expert_status,
    )
    return (
        _finalize_result(
            semantic_body,
            stage_timing_ref=timing["stage_timing_id"],
            stage_timing_hash=timing["telemetry_hash"],
        ),
        timing,
    )


def verify_evaluation_result(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or set(value) != RESULT_FIELDS:
        raise ContractError("EvaluationResult fields do not match the contract")
    result = dict(value)
    if result.get("schema_version") != "1.0.0":
        raise ContractError("unsupported EvaluationResult schema version")
    if result.get("profile_id") not in CONCURRENCY_PROFILE_IDS:
        raise ContractError("unsupported EvaluationResult profile")
    require_integer(result.get("repetition"), "repetition")
    for field in ("paired_seed", "input_hash", "release_hash", "semantic_result_hash", "result_hash"):
        require_hash(result.get(field), field)
    for field in ("case_id", "workload_class", "model_profile_id"):
        require_text(result.get(field), field)
    if result.get("condition") not in {"cold", "warm"}:
        raise ContractError("invalid EvaluationResult condition")
    if result.get("status") not in {
        "completed", "timeout", "cancelled", "failed", "not_evaluated"
    }:
        raise ContractError("invalid EvaluationResult status")
    if result.get("failure_code") not in FAILURE_CODES | {None}:
        raise ContractError("invalid EvaluationResult failure code")
    if result.get("model_evaluation_status") not in {"evaluated", "not_evaluated"}:
        raise ContractError("invalid model evaluation status")
    if result.get("expert_evaluation_status") not in {"evaluated", "not_evaluated"}:
        raise ContractError("invalid expert evaluation status")

    completed = result["status"] == "completed"
    if completed:
        for field in (
            "semantic_output_hash",
            "byte_output_hash",
            "stage_timing_hash",
        ):
            require_hash(result.get(field), field)
        require_text(result.get("stage_timing_ref"), "stage_timing_ref")
        metrics = validate_quality_metrics(result.get("quality_metrics"))
        if result.get("failure_code") is not None:
            raise ContractError("completed EvaluationResult cannot have a failure")
        if (
            result["expert_evaluation_status"] == "evaluated"
            and metrics["expert_practice_quality"] is None
        ) or (
            result["expert_evaluation_status"] == "not_evaluated"
            and metrics["expert_practice_quality"] is not None
        ):
            raise ContractError("expert evaluation status and score disagree")
    else:
        if any(
            result.get(field) is not None
            for field in ("semantic_output_hash", "byte_output_hash", "quality_metrics")
        ):
            raise ContractError("non-completed EvaluationResult contains weak output")
        if result["status"] == "not_evaluated" and result["failure_code"] is not None:
            raise ContractError("not_evaluated is not an execution failure")
        if result["status"] in {"timeout", "cancelled", "failed"} and result["failure_code"] is None:
            raise ContractError("failed EvaluationResult lacks a failure code")

    semantic_body = {
        key: result[key]
        for key in _semantic_result_body(
            case={
                "case_id": result["case_id"],
                "workload_class": result["workload_class"],
                "condition": result["condition"],
                "input_hash": result["input_hash"],
                "release_hash": result["release_hash"],
                "model_profile_id": result["model_profile_id"],
            },
            profile_id=result["profile_id"],
            repetition=result["repetition"],
            paired_seed=result["paired_seed"],
            status=result["status"],
            failure_code=result["failure_code"],
            output_semantic_hash=result["semantic_output_hash"],
            output_byte_hash=result["byte_output_hash"],
            quality_metrics=result["quality_metrics"],
            model_evaluation_status=result["model_evaluation_status"],
            expert_evaluation_status=result["expert_evaluation_status"],
        )
    }
    if result["semantic_result_hash"] != digest(semantic_body):
        raise ContractError("EvaluationResult semantic hash mismatch")
    core = {
        **semantic_body,
        "stage_timing_ref": result["stage_timing_ref"],
        "stage_timing_hash": result["stage_timing_hash"],
        "semantic_result_hash": result["semantic_result_hash"],
    }
    expected_id = "evaluationresult_" + digest(core)[:24]
    if result.get("result_id") != expected_id:
        raise ContractError("EvaluationResult ID mismatch")
    unhashed = {key: result[key] for key in result if key != "result_hash"}
    if result["result_hash"] != digest(unhashed):
        raise ContractError("EvaluationResult hash mismatch")
    _SCHEMAS.validate("evaluation-result.schema.json", result)


def _paired_seed(case: Mapping[str, Any], repetition: int, namespace: str) -> str:
    return hashlib.sha256(
        canonical_bytes(
            {
                "namespace": namespace,
                "case_id": case["case_id"],
                "repetition": repetition,
                "input_hash": case["input_hash"],
                "release_hash": case["release_hash"],
                "model_profile_id": case["model_profile_id"],
            }
        )
    ).hexdigest()


def run_paired_evaluation(
    cases: Sequence[Mapping[str, Any]],
    *,
    repetitions: int,
    execute: Callable[
        [dict[str, Any], str, int, str], Mapping[str, Any]
    ] | None,
    profiles: Sequence[str] = CONCURRENCY_PROFILE_IDS,
    timeout_ms: int | None = None,
    cancel_requested: Callable[[dict[str, Any], str, int], bool] | None = None,
    seed_namespace: str = "trusted-ceo-evaluation-v1",
) -> dict[str, list[dict[str, Any]]]:
    repetitions = require_integer(repetitions, "repetitions", minimum=1)
    require_text(seed_namespace, "seed_namespace")
    if not isinstance(cases, (list, tuple)) or not cases:
        raise ContractError("paired evaluation requires EvaluationCases")
    normalized_cases = [dict(case) for case in cases]
    for case in normalized_cases:
        verify_evaluation_case(case)
    case_ids = [case["case_id"] for case in normalized_cases]
    if len(case_ids) != len(set(case_ids)):
        raise ContractError("paired evaluation contains duplicate cases")
    normalized_cases.sort(key=lambda item: item["case_id"])

    if (
        not isinstance(profiles, (list, tuple))
        or set(profiles) != set(CONCURRENCY_PROFILE_IDS)
        or len(profiles) != len(CONCURRENCY_PROFILE_IDS)
    ):
        raise ContractError(
            "paired evaluation must include sequential and parallel_2/3/4 exactly once"
        )
    ordered_profiles = list(CONCURRENCY_PROFILE_IDS)
    results: list[dict[str, Any]] = []
    timings: list[dict[str, Any]] = []
    for case in normalized_cases:
        for repetition in range(repetitions):
            seed = _paired_seed(case, repetition, seed_namespace)
            for profile_id in ordered_profiles:
                if cancel_requested is not None and cancel_requested(
                    case, profile_id, repetition
                ):
                    results.append(
                        _terminal_result(
                            case,
                            profile_id,
                            repetition,
                            seed,
                            status="cancelled",
                            failure_code="cancelled_by_human",
                        )
                    )
                    continue
                if execute is None:
                    results.append(
                        _terminal_result(
                            case,
                            profile_id,
                            repetition,
                            seed,
                            status="not_evaluated",
                            failure_code=None,
                        )
                    )
                    continue
                try:
                    execution = execute(case, profile_id, repetition, seed)
                except EvaluationCancelled:
                    results.append(
                        _terminal_result(
                            case,
                            profile_id,
                            repetition,
                            seed,
                            status="cancelled",
                            failure_code="cancelled_by_human",
                        )
                    )
                    continue
                except TimeoutError:
                    timing = build_stage_timing(
                        case_id=case["case_id"],
                        workload_class=case["workload_class"],
                        condition=case["condition"],
                        profile_id=profile_id,
                        repetition=repetition,
                        paired_seed=seed,
                        stages_ms={stage: 0 for stage in STAGE_NAMES},
                        outcome="timeout",
                    )
                    timings.append(timing)
                    results.append(
                        _terminal_result(
                            case,
                            profile_id,
                            repetition,
                            seed,
                            status="timeout",
                            failure_code="model_timeout",
                            timing=timing,
                        )
                    )
                    continue
                if cancel_requested is not None and cancel_requested(
                    case, profile_id, repetition
                ):
                    results.append(
                        _terminal_result(
                            case,
                            profile_id,
                            repetition,
                            seed,
                            status="cancelled",
                            failure_code="cancelled_by_human",
                        )
                    )
                    continue
                result, timing = build_evaluation_result(
                    case,
                    profile_id,
                    repetition,
                    seed,
                    execution,
                    timeout_ms=timeout_ms,
                )
                results.append(result)
                timings.append(timing)
    results.sort(
        key=lambda item: (
            item["case_id"],
            item["repetition"],
            CONCURRENCY_PROFILE_IDS.index(item["profile_id"]),
        )
    )
    timings.sort(
        key=lambda item: (
            item["case_id"],
            item["repetition"],
            CONCURRENCY_PROFILE_IDS.index(item["profile_id"]),
        )
    )
    return {"results": results, "timings": timings}
