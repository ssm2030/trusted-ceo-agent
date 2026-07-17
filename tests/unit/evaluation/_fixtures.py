from __future__ import annotations

import hashlib
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.evaluation.metrics import build_quality_metrics
from trusted_ceo_agent.evaluation.runner import (
    CONCURRENCY_PROFILE_IDS,
    build_evaluation_case,
    run_paired_evaluation,
)


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def evaluation_cases() -> list[dict[str, Any]]:
    return [
        build_evaluation_case(
            case_key=f"scenario-{workload}-{condition}",
            workload_class=f"workload_{workload}",
            condition=condition,
            scenario_ref=f"fixtures/scenario-{workload}.json",
            input_hash=digest(f"input-{workload}-{condition}"),
            release_id="knowledge_release_fixture",
            release_hash=digest("release"),
            model_profile_id="model_fixture",
            oracle_ref=f"oracles/scenario-{workload}.json",
            oracle_hash=digest(f"oracle-{workload}"),
        )
        for workload in range(4)
        for condition in ("cold", "warm")
    ]


def quality_metrics(
    *,
    critical: str = "1",
    expert: str | None = "1",
) -> dict[str, Any]:
    return build_quality_metrics(
        critical_recall=critical,
        mandatory_recall="1",
        cross_domain_trigger_recall="1",
        evidence_role_coverage="1",
        counter_evidence_coverage="1",
        authority_state_accuracy="1",
        expert_practice_quality=expert,
        unsupported_claim_count=0,
        prohibited_conclusion_count=0,
    )


def execution(
    case: dict[str, Any],
    profile_id: str,
    repetition: int,
    paired_seed: str,
) -> dict[str, Any]:
    semantic_output = {
        "case_id": case["case_id"],
        "finding_ids": ["finding_a", "finding_b"],
        "paired_seed": paired_seed,
    }
    total_by_profile = {
        "sequential": 100,
        "parallel_2": 80,
        "parallel_3": 60,
        "parallel_4": 40,
    }
    total = total_by_profile[profile_id]
    return {
        "semantic_output": semantic_output,
        "output_bytes": canonical_bytes(semantic_output),
        "quality_metrics": quality_metrics(),
        "model_evaluation_status": "evaluated",
        "expert_evaluation_status": "evaluated",
        "stage_durations_ms": {
            "intake": 10,
            "deterministic": 10,
            "domain_reasoning": total - 40,
            "integration": 10,
            "render": 10,
        },
    }


def run_complete(
    *,
    execute=execution,
    repetitions: int = 10,
) -> dict[str, list[dict[str, Any]]]:
    return run_paired_evaluation(
        evaluation_cases(),
        repetitions=repetitions,
        execute=execute,
        profiles=CONCURRENCY_PROFILE_IDS,
        timeout_ms=1_000,
    )

