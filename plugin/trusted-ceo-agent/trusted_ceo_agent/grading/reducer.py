from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from trusted_ceo_agent.errors import ContractError


def determine_evidence_state(
    support_independence_groups: Iterable[str],
    blocking_unresolved_contradiction: bool,
    minimum_independent_chains: int,
    valid_independent_chain_count: int,
    required_roles_met: bool,
    counter_check_met: bool,
    distinguishing_test_met: bool,
) -> str:
    groups = {value for value in support_independence_groups if value}
    if not groups:
        return "none"
    if blocking_unresolved_contradiction:
        return "conflicting"
    if valid_independent_chain_count < minimum_independent_chains:
        return "limited"
    if not (required_roles_met and counter_check_met and distinguishing_test_met):
        return "limited"
    return "sufficient"


def derive_grading_input(
    issue: Mapping[str, Any],
    *,
    capability: Mapping[str, Any],
    evidence: Mapping[str, Any],
    pack_authority: str,
    diagnostic: Mapping[str, Any],
) -> dict[str, Any]:
    """Reduce runtime-owned facts into the only input accepted by the grader."""
    if "primary_grade" in issue or "grade" in issue or "primary_grade" in diagnostic:
        raise ContractError("grade is runtime-owned")
    assessability = capability.get("assessability")
    reasons = sorted(set(capability.get("reason_codes", [])))
    state = determine_evidence_state(
        evidence.get("support_independence_groups", []),
        bool(evidence.get("blocking_unresolved_contradiction", False)),
        int(evidence.get("minimum_independent_chains", 1)),
        int(evidence.get("valid_independent_chain_count", 0)),
        bool(evidence.get("required_roles_met", False)),
        bool(evidence.get("counter_check_met", False)),
        bool(evidence.get("distinguishing_test_met", False)),
    )
    result = {
        "issue_id": issue["issue_id"],
        "assessability": assessability,
        "not_assessable_reason_codes": reasons,
        "evidence_state": state,
        "impact_band": issue.get("impact_band", "unknown"),
        "urgency_band": issue.get("urgency_band", "unknown"),
        "mission_priority_match": bool(issue.get("mission_priority_match", False)),
        "executive_materiality": issue.get("executive_materiality", "unknown"),
        "decision_needed": diagnostic.get("decision_needed", "unknown"),
        "expert_trigger_state": issue.get("expert_trigger_state", "none"),
        "pack_authority": pack_authority,
        "diagnostic_disposition": diagnostic.get("diagnostic_disposition", "pending"),
        "verification_authorized": bool(diagnostic.get("verification_authorized", False)),
        "issue_disposition": diagnostic.get("issue_disposition", "standalone"),
        "trackable": bool(issue.get("trackable", False)),
        "response_eligibility": issue.get("response_eligibility", "prohibited"),
        "provenance_refs": sorted(set(issue.get("provenance_refs", []))),
    }
    return result
