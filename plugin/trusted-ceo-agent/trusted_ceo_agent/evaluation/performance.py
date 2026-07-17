from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping, Sequence, Set
from datetime import datetime
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.evaluation.metrics import (
    digest,
    nearest_rank_percentile,
    require_hash,
    require_integer,
    require_text,
)


_SCHEMAS = SchemaStore()


STAGE_NAMES = (
    "intake",
    "deterministic",
    "domain_reasoning",
    "integration",
    "render",
)
SUMMARY_STAGE_NAMES = STAGE_NAMES + ("total",)
PROFILE_IDS = ("sequential", "parallel_2", "parallel_3", "parallel_4")
TIMING_FIELDS = frozenset({
    "schema_version",
    "stage_timing_id",
    "case_id",
    "workload_class",
    "condition",
    "profile_id",
    "repetition",
    "paired_seed",
    "stages_ms",
    "total_ms",
    "outcome",
    "telemetry_hash",
})
PERFORMANCE_POLICY_FIELDS = frozenset({
    "schema_version",
    "policy_id",
    "target_environment",
    "quality_report_refs",
    "workload_classes",
    "min_runs_per_condition",
    "measured_profile_statistics",
    "target_slo_ms",
    "selected_profile_id",
    "rollback_profile_id",
    "status",
    "approval_ref",
    "approved_by",
    "approved_at",
    "rollback_drill_passed",
    "activation_eligible",
    "policy_hash",
})


def _timing_body(
    *,
    case_id: str,
    workload_class: str,
    condition: str,
    profile_id: str,
    repetition: int,
    paired_seed: str,
    stages_ms: Mapping[str, Any],
    outcome: str,
) -> dict[str, Any]:
    if profile_id not in PROFILE_IDS:
        raise ContractError("unsupported concurrency profile")
    if condition not in {"cold", "warm"}:
        raise ContractError("condition must be cold or warm")
    if outcome not in {"completed", "timeout", "cancelled", "failed"}:
        raise ContractError("invalid stage timing outcome")
    if not isinstance(stages_ms, Mapping) or set(stages_ms) != set(STAGE_NAMES):
        raise ContractError("stage_durations_ms fields do not match the contract")
    normalized_stages = {
        stage: require_integer(stages_ms[stage], f"stages_ms.{stage}")
        for stage in STAGE_NAMES
    }
    return {
        "schema_version": "1.0.0",
        "case_id": require_text(case_id, "case_id"),
        "workload_class": require_text(workload_class, "workload_class"),
        "condition": condition,
        "profile_id": profile_id,
        "repetition": require_integer(repetition, "repetition"),
        "paired_seed": require_hash(paired_seed, "paired_seed"),
        "stages_ms": normalized_stages,
        "total_ms": sum(normalized_stages.values()),
        "outcome": outcome,
    }


def build_stage_timing(
    *,
    case_id: str,
    workload_class: str,
    condition: str,
    profile_id: str,
    repetition: int,
    paired_seed: str,
    stages_ms: Mapping[str, Any],
    outcome: str,
) -> dict[str, Any]:
    body = _timing_body(
        case_id=case_id,
        workload_class=workload_class,
        condition=condition,
        profile_id=profile_id,
        repetition=repetition,
        paired_seed=paired_seed,
        stages_ms=stages_ms,
        outcome=outcome,
    )
    timing = dict(body)
    timing["stage_timing_id"] = "stagetiming_" + digest(body)[:24]
    timing["telemetry_hash"] = digest(timing)
    _SCHEMAS.validate("stage-timing.schema.json", timing)
    return timing


def verify_stage_timing(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or set(value) != TIMING_FIELDS:
        raise ContractError("StageTiming fields do not match the contract")
    body = _timing_body(
        case_id=value.get("case_id"),
        workload_class=value.get("workload_class"),
        condition=value.get("condition"),
        profile_id=value.get("profile_id"),
        repetition=value.get("repetition"),
        paired_seed=value.get("paired_seed"),
        stages_ms=value.get("stages_ms"),
        outcome=value.get("outcome"),
    )
    if value.get("schema_version") != "1.0.0":
        raise ContractError("unsupported StageTiming schema version")
    expected_id = "stagetiming_" + digest(body)[:24]
    if value.get("stage_timing_id") != expected_id:
        raise ContractError("StageTiming ID mismatch")
    hashed = dict(body)
    hashed["stage_timing_id"] = expected_id
    if value.get("telemetry_hash") != digest(hashed):
        raise ContractError("StageTiming telemetry hash mismatch")
    if value.get("total_ms") != body["total_ms"]:
        raise ContractError("StageTiming total does not equal stage sum")
    _SCHEMAS.validate("stage-timing.schema.json", dict(value))


def _metric(values: Sequence[int]) -> dict[str, int]:
    return {
        "count": len(values),
        "p50_ms": nearest_rank_percentile(values, 50),
        "p95_ms": nearest_rank_percentile(values, 95),
        "max_ms": max(values),
    }


def summarize_stage_timings(
    results: Sequence[Mapping[str, Any]],
    stage_timings: Sequence[Mapping[str, Any]],
    *,
    eligible_profile_ids: Set[str],
    min_workload_classes: int,
    min_runs_per_condition: int,
) -> dict[str, Any]:
    from trusted_ceo_agent.evaluation.runner import verify_evaluation_result

    profiles = set(eligible_profile_ids)
    if not profiles or profiles - set(PROFILE_IDS):
        raise ContractError("eligible_profile_ids contains an unsupported profile")
    minimum_workloads = require_integer(
        min_workload_classes, "min_workload_classes", minimum=4
    )
    minimum_runs = require_integer(
        min_runs_per_condition, "min_runs_per_condition", minimum=10
    )

    timing_by_id: dict[str, dict[str, Any]] = {}
    for raw in stage_timings:
        timing = dict(raw)
        verify_stage_timing(timing)
        timing_id = timing["stage_timing_id"]
        if timing_id in timing_by_id:
            raise ContractError(f"duplicate StageTiming: {timing_id}")
        timing_by_id[timing_id] = timing

    values: dict[str, dict[str, dict[str, list[int]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    run_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    workload_by_profile: dict[str, set[str]] = defaultdict(set)
    seen_result_ids: set[str] = set()
    for raw in results:
        result = dict(raw)
        verify_evaluation_result(result)
        if result["profile_id"] not in profiles:
            continue
        result_id = result["result_id"]
        if result_id in seen_result_ids:
            raise ContractError(f"duplicate EvaluationResult: {result_id}")
        seen_result_ids.add(result_id)
        if (
            result["status"] != "completed"
            or result["model_evaluation_status"] != "evaluated"
            or result["expert_evaluation_status"] != "evaluated"
        ):
            raise ContractError(
                "performance measurements require quality-evaluated completed runs"
            )
        timing_ref = result["stage_timing_ref"]
        if timing_ref not in timing_by_id:
            raise ContractError("EvaluationResult StageTiming is unavailable")
        timing = timing_by_id[timing_ref]
        if timing["telemetry_hash"] != result["stage_timing_hash"]:
            raise ContractError("EvaluationResult StageTiming hash mismatch")
        for field in (
            "case_id",
            "workload_class",
            "condition",
            "profile_id",
            "repetition",
            "paired_seed",
        ):
            if timing[field] != result[field]:
                raise ContractError(f"StageTiming does not match EvaluationResult: {field}")
        if timing["outcome"] != "completed":
            raise ContractError("quality-passed performance run has non-completed timing")

        profile_id = result["profile_id"]
        condition = result["condition"]
        workload = result["workload_class"]
        workload_by_profile[profile_id].add(workload)
        run_counts[(profile_id, workload, condition)] += 1
        for stage in STAGE_NAMES:
            values[profile_id][condition][stage].append(timing["stages_ms"][stage])
        values[profile_id][condition]["total"].append(timing["total_ms"])

    for profile_id in sorted(profiles):
        workloads = workload_by_profile.get(profile_id, set())
        if len(workloads) < minimum_workloads:
            raise ContractError(
                f"{profile_id} has fewer than {minimum_workloads} workload classes"
            )
        for condition in ("cold", "warm"):
            for workload in sorted(workloads):
                if run_counts[(profile_id, workload, condition)] < minimum_runs:
                    raise ContractError(
                        f"{profile_id}/{workload}/{condition} has fewer than "
                        f"{minimum_runs} runs"
                    )

    profile_summaries: dict[str, Any] = {}
    for profile_id in sorted(profiles):
        profile_summaries[profile_id] = {
            "conditions": {
                condition: {
                    stage: _metric(values[profile_id][condition][stage])
                    for stage in SUMMARY_STAGE_NAMES
                }
                for condition in ("cold", "warm")
            }
        }
    return {
        "workload_classes": sorted(
            set().union(*(workload_by_profile[profile] for profile in profiles))
        ),
        "min_runs_per_condition": minimum_runs,
        "profiles": profile_summaries,
    }


def _approval(value: Mapping[str, Any] | None) -> tuple[str, Any, Any, bool, str]:
    if value is None:
        return "proposed", None, None, False, ""
    fields = {"approval_ref", "approved_by", "approved_at", "rollback_drill_passed"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ContractError("performance approval fields do not match the contract")
    approval_ref = require_text(value["approval_ref"], "approval_ref")
    approved_by = require_text(value["approved_by"], "approved_by")
    approved_at = require_text(value["approved_at"], "approved_at")
    normalized = approved_at[:-1] + "+00:00" if approved_at.endswith("Z") else approved_at
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ContractError("approved_at must be an ISO-8601 datetime") from error
    if parsed.tzinfo is None:
        raise ContractError("approved_at must include a timezone")
    if value["rollback_drill_passed"] is not True:
        raise ContractError("approved PerformancePolicy requires a passed rollback drill")
    return "approved", approval_ref, approved_by, True, approved_at


def _profile_statistics(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "profile_id": profile_id,
            "condition_statistics": [
                {
                    "condition": condition,
                    "stages": summary["profiles"][profile_id]["conditions"][condition],
                }
                for condition in ("cold", "warm")
            ],
        }
        for profile_id in sorted(summary["profiles"])
    ]


def build_performance_policy(
    *,
    results: Sequence[Mapping[str, Any]],
    stage_timings: Sequence[Mapping[str, Any]],
    non_inferiority_reports: Sequence[Mapping[str, Any]],
    target_environment: str,
    approval: Mapping[str, Any] | None,
) -> dict[str, Any]:
    from trusted_ceo_agent.evaluation.non_inferiority import (
        verify_non_inferiority_report,
    )

    passed: list[dict[str, Any]] = []
    policy_hashes: set[str] = set()
    for raw in non_inferiority_reports:
        report = dict(raw)
        verify_non_inferiority_report(report)
        policy_hashes.add(report["quality_policy_hash"])
        if report["gate_status"] == "pass" and report["eligible_for_activation"] is True:
            passed.append(report)
    if not passed:
        raise ContractError("PerformancePolicy requires a passed non-inferiority report")
    if len(policy_hashes) != 1:
        raise ContractError("non-inferiority reports use different QualityPolicy hashes")

    eligible_profiles = {"sequential"} | {
        report["candidate_profile_id"] for report in passed
    }
    minimum_workloads = max(
        4,
        min(len(report["workload_classes"]) for report in passed),
    )
    minimum_runs = min(
        min(report["runs_per_workload_condition"].values())
        for report in passed
    )
    if minimum_runs < 10:
        raise ContractError("PerformancePolicy requires at least ten runs per condition")
    summary = summarize_stage_timings(
        results,
        stage_timings,
        eligible_profile_ids=eligible_profiles,
        min_workload_classes=minimum_workloads,
        min_runs_per_condition=minimum_runs,
    )

    def profile_p95(profile_id: str) -> int:
        return max(
            summary["profiles"][profile_id]["conditions"][condition]["total"]["p95_ms"]
            for condition in ("cold", "warm")
        )

    selected = min(sorted(eligible_profiles), key=lambda item: (profile_p95(item), item))
    status, approval_ref, approved_by, drill_passed, approved_at = _approval(approval)
    selected_stats = summary["profiles"][selected]["conditions"]
    target_slo = {
        stage: max(
            selected_stats[condition][stage]["p95_ms"]
            for condition in ("cold", "warm")
        )
        for stage in SUMMARY_STAGE_NAMES
    }
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "target_environment": require_text(
            target_environment, "target_environment"
        ),
        "quality_report_refs": sorted(
            [
                {
                    "report_id": report["report_id"],
                    "report_hash": report["report_hash"],
                    "candidate_profile_id": report["candidate_profile_id"],
                }
                for report in passed
            ],
            key=lambda item: item["candidate_profile_id"],
        ),
        "workload_classes": list(summary["workload_classes"]),
        "min_runs_per_condition": minimum_runs,
        "measured_profile_statistics": _profile_statistics(summary),
        "target_slo_ms": target_slo,
        "selected_profile_id": selected,
        "rollback_profile_id": "sequential",
        "status": status,
        "approval_ref": approval_ref,
        "approved_by": approved_by,
        "approved_at": approved_at or None,
        "rollback_drill_passed": drill_passed,
        "activation_eligible": status == "approved" and selected != "sequential",
    }
    policy = dict(body)
    policy["policy_id"] = "performancepolicy_" + digest(body)[:24]
    policy["policy_hash"] = digest(policy)
    verify_performance_policy(policy)
    return policy


def verify_performance_policy(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or set(value) != PERFORMANCE_POLICY_FIELDS:
        raise ContractError("PerformancePolicy fields do not match the contract")
    policy = dict(value)
    expected_hash = require_hash(policy["policy_hash"], "policy_hash")
    unhashed = {key: policy[key] for key in policy if key != "policy_hash"}
    if expected_hash != digest(unhashed):
        raise ContractError("PerformancePolicy hash mismatch")
    body = {
        key: policy[key]
        for key in policy
        if key not in {"policy_id", "policy_hash"}
    }
    if policy["policy_id"] != "performancepolicy_" + digest(body)[:24]:
        raise ContractError("PerformancePolicy ID mismatch")
    status = policy["status"]
    if status == "approved":
        if (
            not policy["approval_ref"]
            or not policy["approved_by"]
            or not policy["approved_at"]
            or policy["rollback_drill_passed"] is not True
        ):
            raise ContractError("approved PerformancePolicy lacks approval evidence")
    elif status == "proposed":
        if any(
            policy[field] is not None
            for field in ("approval_ref", "approved_by", "approved_at")
        ) or policy["rollback_drill_passed"] is not False:
            raise ContractError("proposed PerformancePolicy cannot contain approval evidence")
    else:
        raise ContractError("unsupported PerformancePolicy status")
    expected_activation = status == "approved" and policy["selected_profile_id"] != "sequential"
    if policy["activation_eligible"] is not expected_activation:
        raise ContractError("PerformancePolicy activation eligibility mismatch")
    _SCHEMAS.validate("performance-policy.schema.json", policy)
