from __future__ import annotations


PARALLEL_LIMITS = {
    "file_schema_quality": 4,
    "deterministic_components": 4,
    "lens_jobs": 3,
    "join": 1,
    "integrated_reasoning": 1,
    "deep_components": 4,
    "deep_integrator": 1,
    "output_writer": 1,
}


TIME_BUDGET_SECONDS = {
    "context_contract": 5,
    "intake_snapshot_quality": 20,
    "capability_pack": 5,
    "deterministic_scan": 20,
    "lens_host_reasoning": 45,
    "join": 5,
    "integrated_reasoning": 45,
    "pre_approval_target": 140,
    "deep_components": 20,
    "deep_reasoning": 35,
    "writer_expert_render": 25,
    "final_validation": 5,
    "post_approval_target": 85,
    "full_target": 225,
    "full_hard_limit": 300,
    "live_demo_target": 50,
    "live_demo_hard_limit": 75,
}


MODEL_PROFILES = {
    "schema_mapper": {"profile": "balanced_structured", "logical_concurrency": 1},
    "lens_analyst": {"profile": "balanced_structured", "logical_concurrency": 3},
    "integrator": {"profile": "strong_structured", "logical_concurrency": 1},
    "deep_dive_integrator": {"profile": "strong_structured", "logical_concurrency": 1},
    "output_writer": {"profile": "strong_structured", "logical_concurrency": 1},
}


def validate_policy() -> None:
    if TIME_BUDGET_SECONDS["full_target"] >= TIME_BUDGET_SECONDS["full_hard_limit"]:
        raise ValueError("full runtime target must be below its hard limit")
    if TIME_BUDGET_SECONDS["live_demo_target"] >= TIME_BUDGET_SECONDS["live_demo_hard_limit"]:
        raise ValueError("live demo target must be below its hard limit")
    for stage in ("join", "integrated_reasoning", "deep_integrator", "output_writer"):
        if PARALLEL_LIMITS[stage] != 1:
            raise ValueError(f"post-Join stage must be single-worker: {stage}")
    if PARALLEL_LIMITS["lens_jobs"] > 3:
        raise ValueError("lens logical concurrency cannot exceed three")


validate_policy()
