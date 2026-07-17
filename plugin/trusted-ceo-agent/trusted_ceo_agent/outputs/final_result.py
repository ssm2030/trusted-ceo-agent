from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.outputs.validation import (
    validate_active_issues,
    validate_final_approval,
    validate_no_absolute_paths,
)


def build_final_result(
    *,
    run_summary: Mapping[str, Any],
    mission_summary: Mapping[str, Any],
    capability_summary: Mapping[str, Any],
    issues: Sequence[Mapping[str, Any]],
    evidence_links: Mapping[str, Mapping[str, Any]],
    approvals: Sequence[Mapping[str, Any]],
    cross_issue_relations: Sequence[Mapping[str, Any]] = (),
    conditional_responses: Sequence[Mapping[str, Any]] = (),
    monitoring: Sequence[Mapping[str, Any]] = (),
    blind_spots: Sequence[Mapping[str, Any]] = (),
    expert_review_packets: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    validate_active_issues(issues, evidence_links)
    validate_final_approval(approvals)
    active = [
        {key: value for key, value in issue.items() if key != "disposition"}
        for issue in issues
        if issue.get("disposition", "accepted") == "accepted"
    ]
    body: dict[str, Any] = {
        "run_summary": dict(run_summary),
        "mission_summary": dict(mission_summary),
        "capability_summary": dict(capability_summary),
        "issues": sorted(active, key=lambda item: item["issue_id"]),
        "cross_issue_relations": list(cross_issue_relations),
        "conditional_responses": list(conditional_responses),
        "monitoring": list(monitoring),
        "blind_spots": list(blind_spots),
        "expert_review_packets": list(expert_review_packets),
        "approvals": list(approvals),
    }
    validate_no_absolute_paths(body)
    fingerprint = hashlib.sha256(canonical_bytes(body)).hexdigest()
    body["integrity"] = {"semantic_fingerprint": fingerprint}
    return body

