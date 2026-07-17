from __future__ import annotations

import copy
from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.evaluation.metrics import (
    COUNT_METRICS,
    QUALITY_SCORE_METRICS,
    digest,
    mean_score,
    require_hash,
    require_integer,
    require_text,
    score_text,
    signed_score_text,
)
from trusted_ceo_agent.evaluation.runner import (
    CONCURRENCY_PROFILE_IDS,
    verify_evaluation_result,
)


_SCHEMAS = SchemaStore()


QUALITY_POLICY_FIELDS = frozenset({
    "schema_version",
    "policy_id",
    "baseline_profile_id",
    "metric_margins",
    "require_byte_equivalence",
    "min_workload_classes",
    "min_runs_per_condition",
    "require_external_model_evaluation",
    "require_blinded_expert_evaluation",
    "policy_hash",
})
PROFILE_FIELDS = frozenset({
    "schema_version",
    "profile_id",
    "max_workers",
    "execution_mode",
    "baseline_profile_id",
    "quality_policy_id",
    "quality_policy_hash",
    "lifecycle_status",
    "rollback_profile_id",
    "profile_hash",
})
REPORT_FIELDS = frozenset({
    "schema_version",
    "report_id",
    "quality_policy_id",
    "quality_policy_hash",
    "baseline_profile_id",
    "candidate_profile_id",
    "paired_result_count",
    "workload_classes",
    "conditions",
    "runs_per_workload_condition",
    "pair_coverage_complete",
    "semantic_equivalent",
    "byte_equivalent",
    "metric_deltas",
    "count_deltas",
    "external_model_status",
    "blinded_expert_status",
    "gate_status",
    "eligible_for_activation",
    "failure_codes",
    "report_hash",
})
PROFILE_WORKERS = {
    "sequential": 1,
    "parallel_2": 2,
    "parallel_3": 3,
    "parallel_4": 4,
}


def _quality_policy_body(
    *,
    policy_id: Any,
    metric_margins: Mapping[str, Any],
    require_byte_equivalence: Any,
    min_workload_classes: Any,
    min_runs_per_condition: Any,
    require_external_model_evaluation: Any,
    require_blinded_expert_evaluation: Any,
) -> dict[str, Any]:
    if not isinstance(metric_margins, Mapping) or set(metric_margins) != set(
        QUALITY_SCORE_METRICS
    ):
        raise ContractError("metric_margins fields do not match the contract")
    if require_byte_equivalence is not True:
        raise ContractError("byte equivalence cannot be disabled")
    if require_external_model_evaluation is not True:
        raise ContractError("external model evaluation cannot be disabled")
    if require_blinded_expert_evaluation is not True:
        raise ContractError("blinded expert evaluation cannot be disabled")
    return {
        "schema_version": "1.0.0",
        "policy_id": require_text(policy_id, "policy_id"),
        "baseline_profile_id": "sequential",
        "metric_margins": {
            metric: score_text(metric_margins[metric], f"metric_margins.{metric}")
            for metric in QUALITY_SCORE_METRICS
        },
        "require_byte_equivalence": True,
        "min_workload_classes": require_integer(
            min_workload_classes, "min_workload_classes", minimum=4
        ),
        "min_runs_per_condition": require_integer(
            min_runs_per_condition, "min_runs_per_condition", minimum=10
        ),
        "require_external_model_evaluation": True,
        "require_blinded_expert_evaluation": True,
    }


def build_quality_policy(
    *,
    policy_id: str,
    metric_margins: Mapping[str, Any],
    require_byte_equivalence: bool = True,
    min_workload_classes: int = 4,
    min_runs_per_condition: int = 10,
    require_external_model_evaluation: bool = True,
    require_blinded_expert_evaluation: bool = True,
) -> dict[str, Any]:
    body = _quality_policy_body(
        policy_id=policy_id,
        metric_margins=metric_margins,
        require_byte_equivalence=require_byte_equivalence,
        min_workload_classes=min_workload_classes,
        min_runs_per_condition=min_runs_per_condition,
        require_external_model_evaluation=require_external_model_evaluation,
        require_blinded_expert_evaluation=require_blinded_expert_evaluation,
    )
    policy = dict(body)
    policy["policy_hash"] = digest(body)
    verify_quality_policy(policy)
    return policy


def verify_quality_policy(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or set(value) != QUALITY_POLICY_FIELDS:
        raise ContractError("QualityPolicy fields do not match the contract")
    policy = dict(value)
    body = _quality_policy_body(
        policy_id=policy.get("policy_id"),
        metric_margins=policy.get("metric_margins"),
        require_byte_equivalence=policy.get("require_byte_equivalence"),
        min_workload_classes=policy.get("min_workload_classes"),
        min_runs_per_condition=policy.get("min_runs_per_condition"),
        require_external_model_evaluation=policy.get(
            "require_external_model_evaluation"
        ),
        require_blinded_expert_evaluation=policy.get(
            "require_blinded_expert_evaluation"
        ),
    )
    if policy.get("schema_version") != "1.0.0":
        raise ContractError("unsupported QualityPolicy schema version")
    if policy.get("baseline_profile_id") != "sequential":
        raise ContractError("QualityPolicy baseline must be sequential")
    if policy.get("policy_hash") != digest(body):
        raise ContractError("QualityPolicy hash mismatch")
    _SCHEMAS.validate("quality-policy.schema.json", policy)


def build_concurrency_profile(
    profile_id: str,
    quality_policy: Mapping[str, Any],
) -> dict[str, Any]:
    verify_quality_policy(quality_policy)
    if profile_id not in CONCURRENCY_PROFILE_IDS:
        raise ContractError("unsupported concurrency profile")
    body = {
        "schema_version": "1.0.0",
        "profile_id": profile_id,
        "max_workers": PROFILE_WORKERS[profile_id],
        "execution_mode": (
            "sequential" if profile_id == "sequential" else "bounded_parallel"
        ),
        "baseline_profile_id": "sequential",
        "quality_policy_id": quality_policy["policy_id"],
        "quality_policy_hash": quality_policy["policy_hash"],
        "lifecycle_status": (
            "baseline" if profile_id == "sequential" else "experimental"
        ),
        "rollback_profile_id": "sequential",
    }
    profile = dict(body)
    profile["profile_hash"] = digest(body)
    verify_concurrency_profile(profile)
    return profile


def verify_concurrency_profile(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or set(value) != PROFILE_FIELDS:
        raise ContractError("ConcurrencyProfile fields do not match the contract")
    profile = dict(value)
    profile_id = profile.get("profile_id")
    if profile_id not in CONCURRENCY_PROFILE_IDS:
        raise ContractError("unsupported concurrency profile")
    expected_mode = "sequential" if profile_id == "sequential" else "bounded_parallel"
    expected_lifecycle = "baseline" if profile_id == "sequential" else "experimental"
    if profile.get("max_workers") != PROFILE_WORKERS[profile_id]:
        raise ContractError("ConcurrencyProfile worker count mismatch")
    if profile.get("execution_mode") != expected_mode:
        raise ContractError("ConcurrencyProfile execution mode mismatch")
    if profile.get("lifecycle_status") != expected_lifecycle:
        raise ContractError("ConcurrencyProfile lifecycle mismatch")
    if (
        profile.get("baseline_profile_id") != "sequential"
        or profile.get("rollback_profile_id") != "sequential"
    ):
        raise ContractError("ConcurrencyProfile must preserve sequential rollback")
    require_text(profile.get("quality_policy_id"), "quality_policy_id")
    require_hash(profile.get("quality_policy_hash"), "quality_policy_hash")
    body = {key: profile[key] for key in profile if key != "profile_hash"}
    if profile.get("profile_hash") != digest(body):
        raise ContractError("ConcurrencyProfile hash mismatch")
    _SCHEMAS.validate("concurrency-profile.schema.json", profile)


def _pair_key(result: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        result["case_id"],
        result["workload_class"],
        result["condition"],
        result["repetition"],
        result["paired_seed"],
        result["input_hash"],
        result["release_hash"],
        result["model_profile_id"],
    )


def _result_map(
    results: Sequence[Mapping[str, Any]],
    profile_id: str,
) -> dict[tuple[Any, ...], dict[str, Any]]:
    mapped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for raw in results:
        result = dict(raw)
        verify_evaluation_result(result)
        if result["profile_id"] != profile_id:
            continue
        key = _pair_key(result)
        if key in mapped:
            raise ContractError(f"duplicate paired result for {profile_id}")
        mapped[key] = result
    return mapped


def _metric_delta(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    metric: str,
) -> Decimal | None:
    baseline_values: list[Any] = []
    candidate_values: list[Any] = []
    for baseline, candidate in pairs:
        baseline_metrics = baseline.get("quality_metrics")
        candidate_metrics = candidate.get("quality_metrics")
        if baseline_metrics is None or candidate_metrics is None:
            return None
        baseline_value = baseline_metrics.get(metric)
        candidate_value = candidate_metrics.get(metric)
        if baseline_value is None or candidate_value is None:
            return None
        baseline_values.append(baseline_value)
        candidate_values.append(candidate_value)
    if not baseline_values:
        return None
    return mean_score(candidate_values, metric) - mean_score(
        baseline_values, metric
    )


def build_non_inferiority_report(
    results: Sequence[Mapping[str, Any]],
    quality_policy: Mapping[str, Any],
    *,
    candidate_profile_id: str,
) -> dict[str, Any]:
    verify_quality_policy(quality_policy)
    if candidate_profile_id not in {"parallel_2", "parallel_3", "parallel_4"}:
        raise ContractError("candidate profile must be bounded parallel")
    baseline_map = _result_map(results, "sequential")
    candidate_map = _result_map(results, candidate_profile_id)
    baseline_keys = set(baseline_map)
    candidate_keys = set(candidate_map)
    common_keys = sorted(baseline_keys & candidate_keys)
    pairs = [(baseline_map[key], candidate_map[key]) for key in common_keys]
    pair_coverage_complete = bool(common_keys) and baseline_keys == candidate_keys
    workloads = sorted({
        result["workload_class"]
        for mapping in (baseline_map, candidate_map)
        for result in mapping.values()
    })
    conditions = sorted({
        result["condition"]
        for mapping in (baseline_map, candidate_map)
        for result in mapping.values()
    })
    run_counts: dict[str, int] = defaultdict(int)
    for baseline, _candidate in pairs:
        run_counts[f"{baseline['workload_class']}|{baseline['condition']}"] += 1

    complete_pairs = [
        (baseline, candidate)
        for baseline, candidate in pairs
        if baseline["status"] == "completed" and candidate["status"] == "completed"
    ]
    execution_complete = len(complete_pairs) == len(pairs) and bool(pairs)
    execution_failed = any(
        result["status"] in {"timeout", "cancelled", "failed"}
        for pair in pairs
        for result in pair
    )
    semantic_equivalent = execution_complete and all(
        baseline["semantic_output_hash"] == candidate["semantic_output_hash"]
        for baseline, candidate in complete_pairs
    )
    byte_equivalent = execution_complete and all(
        baseline["byte_output_hash"] == candidate["byte_output_hash"]
        for baseline, candidate in complete_pairs
    )
    external_model_evaluated = execution_complete and all(
        baseline["model_evaluation_status"] == "evaluated"
        and candidate["model_evaluation_status"] == "evaluated"
        for baseline, candidate in complete_pairs
    )
    blinded_expert_evaluated = execution_complete and all(
        baseline["expert_evaluation_status"] == "evaluated"
        and candidate["expert_evaluation_status"] == "evaluated"
        and baseline["quality_metrics"]["expert_practice_quality"] is not None
        and candidate["quality_metrics"]["expert_practice_quality"] is not None
        for baseline, candidate in complete_pairs
    )

    raw_deltas = {
        metric: _metric_delta(complete_pairs, metric)
        for metric in QUALITY_SCORE_METRICS
    }
    metric_deltas = {
        metric: None if delta is None else signed_score_text(delta)
        for metric, delta in raw_deltas.items()
    }
    count_deltas = {
        metric: sum(
            candidate["quality_metrics"][metric]
            - baseline["quality_metrics"][metric]
            for baseline, candidate in complete_pairs
        )
        for metric in COUNT_METRICS
    }

    failures: set[str] = set()
    if len(workloads) < quality_policy["min_workload_classes"]:
        failures.add("insufficient_workload_coverage")
    expected_count_keys = {
        f"{workload}|{condition}"
        for workload in workloads
        for condition in ("cold", "warm")
    }
    if any(
        run_counts.get(key, 0) < quality_policy["min_runs_per_condition"]
        for key in expected_count_keys
    ):
        failures.add("insufficient_condition_runs")
    if not pair_coverage_complete:
        failures.add("pair_coverage_mismatch")
    if execution_failed:
        failures.add("execution_incomplete")
    if execution_failed or (execution_complete and not semantic_equivalent):
        failures.add("semantic_output_mismatch")
    if (
        quality_policy["require_byte_equivalence"]
        and (execution_failed or (execution_complete and not byte_equivalent))
    ):
        failures.add("byte_output_mismatch")
    for metric, delta in raw_deltas.items():
        if metric == "expert_practice_quality" and delta is None:
            continue
        if delta is None:
            failures.add(f"{metric}_not_evaluated")
            continue
        margin = Decimal(quality_policy["metric_margins"][metric])
        if delta < -margin:
            failures.add(f"{metric}_non_inferiority_failed")
    for metric, delta in count_deltas.items():
        if delta > 0:
            failures.add(f"{metric}_increased")
    if not external_model_evaluated:
        failures.add("external_model_not_evaluated")
    if not blinded_expert_evaluated:
        failures.add("blinded_expert_not_evaluated")

    external_failures = {
        "external_model_not_evaluated",
        "blinded_expert_not_evaluated",
    } | {f"{metric}_not_evaluated" for metric in QUALITY_SCORE_METRICS}
    hard_failures = failures - external_failures
    if hard_failures:
        gate_status = "fail"
    elif failures:
        gate_status = "not_evaluated"
    else:
        gate_status = "pass"
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "quality_policy_id": quality_policy["policy_id"],
        "quality_policy_hash": quality_policy["policy_hash"],
        "baseline_profile_id": "sequential",
        "candidate_profile_id": candidate_profile_id,
        "paired_result_count": len(pairs),
        "workload_classes": workloads,
        "conditions": conditions,
        "runs_per_workload_condition": {
            key: run_counts.get(key, 0) for key in sorted(expected_count_keys)
        },
        "pair_coverage_complete": pair_coverage_complete,
        "semantic_equivalent": semantic_equivalent,
        "byte_equivalent": byte_equivalent,
        "metric_deltas": metric_deltas,
        "count_deltas": count_deltas,
        "external_model_status": (
            "evaluated" if external_model_evaluated else "not_evaluated"
        ),
        "blinded_expert_status": (
            "evaluated" if blinded_expert_evaluated else "not_evaluated"
        ),
        "gate_status": gate_status,
        "eligible_for_activation": gate_status == "pass",
        "failure_codes": sorted(failures),
    }
    report = dict(body)
    report["report_id"] = "noninferiorityreport_" + digest(body)[:24]
    report["report_hash"] = digest(report)
    verify_non_inferiority_report(report)
    return report


def verify_non_inferiority_report(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or set(value) != REPORT_FIELDS:
        raise ContractError("NonInferiorityReport fields do not match the contract")
    report = dict(value)
    require_hash(report.get("quality_policy_hash"), "quality_policy_hash")
    require_hash(report.get("report_hash"), "report_hash")
    if report.get("baseline_profile_id") != "sequential":
        raise ContractError("non-inferiority baseline must be sequential")
    if report.get("candidate_profile_id") not in {
        "parallel_2", "parallel_3", "parallel_4"
    }:
        raise ContractError("invalid non-inferiority candidate")
    require_integer(report.get("paired_result_count"), "paired_result_count")
    if report.get("gate_status") not in {"pass", "fail", "not_evaluated"}:
        raise ContractError("invalid non-inferiority gate status")
    if report.get("eligible_for_activation") is not (
        report.get("gate_status") == "pass"
    ):
        raise ContractError("non-inferiority activation eligibility mismatch")
    body = {
        key: report[key]
        for key in report
        if key not in {"report_id", "report_hash"}
    }
    expected_id = "noninferiorityreport_" + digest(body)[:24]
    if report.get("report_id") != expected_id:
        raise ContractError("NonInferiorityReport ID mismatch")
    unhashed = {key: report[key] for key in report if key != "report_hash"}
    if report["report_hash"] != digest(unhashed):
        raise ContractError("NonInferiorityReport hash mismatch")
    _SCHEMAS.validate("non-inferiority-report.schema.json", report)


class ConcurrencyProfileRegistry:
    """Revision-bound activation registry with sequential rollback."""

    def __init__(self, profiles: Sequence[Mapping[str, Any]]) -> None:
        self._profiles: dict[str, dict[str, Any]] = {}
        for raw in profiles:
            profile = dict(raw)
            verify_concurrency_profile(profile)
            profile_id = profile["profile_id"]
            if profile_id in self._profiles:
                raise ContractError(f"duplicate ConcurrencyProfile: {profile_id}")
            self._profiles[profile_id] = copy.deepcopy(profile)
        if set(self._profiles) != set(CONCURRENCY_PROFILE_IDS):
            raise ContractError("registry requires sequential and parallel_2/3/4")
        quality_hashes = {
            profile["quality_policy_hash"] for profile in self._profiles.values()
        }
        if len(quality_hashes) != 1:
            raise ContractError("ConcurrencyProfiles use different QualityPolicies")
        self._events: list[dict[str, Any]] = []

    def bind_profile(self, *, run_revision: int) -> str:
        revision = require_integer(run_revision, "run_revision")
        profile_id = "sequential"
        for event in sorted(
            self._events,
            key=lambda item: (
                item["effective_for_runs_after_revision"],
                item["event_id"],
            ),
        ):
            if event["effective_for_runs_after_revision"] <= revision:
                profile_id = event["to_profile_id"]
        return profile_id

    def _append_event(self, body: Mapping[str, Any]) -> dict[str, Any]:
        event = dict(body)
        event["event_id"] = "profileevent_" + digest(event)[:24]
        event["event_hash"] = digest(event)
        self._events.append(copy.deepcopy(event))
        return event

    def activate(
        self,
        *,
        profile_id: str,
        non_inferiority_report: Mapping[str, Any],
        performance_policy: Mapping[str, Any],
        approval_ref: str,
        current_revision: int,
    ) -> dict[str, Any]:
        from trusted_ceo_agent.evaluation.performance import (
            verify_performance_policy,
        )

        if profile_id not in {"parallel_2", "parallel_3", "parallel_4"}:
            raise ContractError("only bounded parallel profiles require activation")
        report = dict(non_inferiority_report)
        policy = dict(performance_policy)
        verify_non_inferiority_report(report)
        verify_performance_policy(policy)
        revision = require_integer(current_revision, "current_revision")
        approval_ref = require_text(approval_ref, "approval_ref")
        if self.bind_profile(run_revision=revision) != "sequential":
            raise ContractError("active parallel profile must be rolled back first")
        profile = self._profiles[profile_id]
        if (
            report["candidate_profile_id"] != profile_id
            or report["gate_status"] != "pass"
            or report["eligible_for_activation"] is not True
        ):
            raise ContractError("profile did not pass non-inferiority")
        if report["quality_policy_hash"] != profile["quality_policy_hash"]:
            raise ContractError("report uses another QualityPolicy")
        if (
            policy["status"] != "approved"
            or policy["activation_eligible"] is not True
            or policy["selected_profile_id"] != profile_id
            or policy["rollback_profile_id"] != "sequential"
        ):
            raise ContractError("PerformancePolicy does not approve this profile")
        report_refs = {
            (item["report_id"], item["report_hash"])
            for item in policy["quality_report_refs"]
        }
        if (report["report_id"], report["report_hash"]) not in report_refs:
            raise ContractError("PerformancePolicy is not bound to the quality report")
        return self._append_event({
            "event_type": "activation",
            "from_profile_id": "sequential",
            "to_profile_id": profile_id,
            "profile_hash": profile["profile_hash"],
            "non_inferiority_report_id": report["report_id"],
            "non_inferiority_report_hash": report["report_hash"],
            "performance_policy_id": policy["policy_id"],
            "performance_policy_hash": policy["policy_hash"],
            "approval_ref": approval_ref,
            "reason": "approved_quality_and_performance_gates",
            "effective_for_runs_after_revision": revision + 1,
        })

    def rollback(
        self,
        *,
        approval_ref: str,
        reason: str,
        current_revision: int,
    ) -> dict[str, Any]:
        revision = require_integer(current_revision, "current_revision")
        approval_ref = require_text(approval_ref, "approval_ref")
        reason = require_text(reason, "reason")
        active = self.bind_profile(run_revision=revision)
        if active == "sequential":
            raise ContractError("no active parallel profile to roll back")
        return self._append_event({
            "event_type": "rollback",
            "from_profile_id": active,
            "to_profile_id": "sequential",
            "profile_hash": self._profiles[active]["profile_hash"],
            "non_inferiority_report_id": None,
            "non_inferiority_report_hash": None,
            "performance_policy_id": None,
            "performance_policy_hash": None,
            "approval_ref": approval_ref,
            "reason": reason,
            "effective_for_runs_after_revision": revision + 1,
        })

    def events(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._events)
