from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError


class InvalidGradingInput(ContractError):
    pass


class GradeRuleUncovered(ContractError):
    pass


ENUMS = {
    "assessability": {"assessable", "partial", "not_assessable"},
    "evidence_state": {"sufficient", "limited", "conflicting", "none"},
    "impact_band": {"critical", "high", "medium", "low", "unknown"},
    "urgency_band": {"immediate", "near_term", "routine", "unknown"},
    "executive_materiality": {True, False, "unknown"},
    "decision_needed": {True, False, "unknown"},
    "expert_trigger_state": {"required", "possible", "none"},
    "pack_authority": {"full", "provisional", "boundary"},
    "diagnostic_disposition": {"accepted", "rejected", "disputed", "pending"},
    "issue_disposition": {"standalone", "absorbed", "duplicate", "isolated_low"},
    "response_eligibility": {"eligible", "needs_verification", "prohibited"},
}
REQUIRED = {
    "issue_id", "assessability", "not_assessable_reason_codes", "evidence_state", "impact_band",
    "urgency_band", "mission_priority_match", "executive_materiality", "decision_needed",
    "expert_trigger_state", "pack_authority", "diagnostic_disposition", "verification_authorized",
    "issue_disposition", "trackable", "response_eligibility", "provenance_refs",
}


def _validate(value: Mapping[str, Any]) -> None:
    missing = REQUIRED - set(value)
    extras = set(value) - REQUIRED
    if missing or extras:
        raise InvalidGradingInput(f"grading input keys mismatch: missing={sorted(missing)}, extras={sorted(extras)}")
    for field, allowed in ENUMS.items():
        if value[field] not in allowed:
            raise InvalidGradingInput(f"invalid {field}: {value[field]}")
    for field in ("mission_priority_match", "verification_authorized", "trackable"):
        if not isinstance(value[field], bool):
            raise InvalidGradingInput(f"{field} must be boolean")
    if not isinstance(value["not_assessable_reason_codes"], list) or not isinstance(value["provenance_refs"], list):
        raise InvalidGradingInput("reason and provenance refs must be arrays")
    if value["diagnostic_disposition"] == "accepted" and value["decision_needed"] == "unknown":
        raise InvalidGradingInput("accepted diagnostic requires a boolean decision_needed")
    if value["diagnostic_disposition"] == "disputed" and value["decision_needed"] != "unknown":
        raise InvalidGradingInput("disputed diagnostic requires unknown decision_needed")
    needs_reason = (
        value["assessability"] in {"partial", "not_assessable"}
        or "unknown" in {value["impact_band"], value["urgency_band"], value["executive_materiality"]}
    )
    if needs_reason and not value["not_assessable_reason_codes"] and value["pack_authority"] != "boundary":
        raise InvalidGradingInput("Not Assessable inputs require an explicit reason")


def _record_id(body: Mapping[str, Any]) -> str:
    return "grade_" + hashlib.sha256(canonical_bytes(dict(body))).hexdigest()[:24]


def _withheld(value: Mapping[str, Any], reason: str, rule_version: str, computed_at: str) -> dict[str, Any]:
    body = {
        "issue_id": value["issue_id"], "publication_status": "withheld", "rule_version": rule_version,
        "grading_input_hash": hashlib.sha256(canonical_bytes(dict(value))).hexdigest(),
        "input_snapshot_hash": hashlib.sha256(canonical_bytes(dict(value))).hexdigest(),
        "secondary_flags": [], "reason_codes": [reason], "applied_threshold_refs": [],
        "applied_mission_refs": [], "applied_approval_refs": [], "authority_cap_applied": False,
        "computed_at": computed_at,
    }
    body["grade_record_id"] = _record_id(body)
    return body


def grade(
    grading_input: Mapping[str, Any],
    *,
    rule_version: str = "1.0.0",
    computed_at: str = "1970-01-01T00:00:00Z",
) -> dict[str, Any]:
    value = dict(grading_input)
    _validate(value)
    disposition = value["diagnostic_disposition"]
    if disposition == "pending":
        return _withheld(value, "pending", rule_version, computed_at)
    if disposition == "rejected":
        return _withheld(value, "rejected", rule_version, computed_at)
    if disposition == "disputed" and not value["verification_authorized"]:
        return _withheld(value, "unapproved_dispute", rule_version, computed_at)

    reason_codes: list[str] = []
    secondary: list[str] = []
    authority_cap = False
    if value["pack_authority"] == "boundary":
        primary = "Not Assessable"
        reason_codes.append("unsupported_domain")
    elif value["expert_trigger_state"] == "required":
        primary = "Expert Review Required"
        reason_codes.append("expert_trigger_required")
        if value["executive_materiality"] is True and value["decision_needed"] is True:
            secondary.append("executive_decision_after_expert_review")
    elif (
        value["assessability"] in {"partial", "not_assessable"}
        or value["impact_band"] == "unknown"
        or value["urgency_band"] == "unknown"
        or value["executive_materiality"] == "unknown"
    ):
        primary = "Not Assessable"
        reason_codes.extend(value["not_assessable_reason_codes"])
    elif value["issue_disposition"] in {"duplicate", "absorbed", "isolated_low"} and value["executive_materiality"] is False:
        primary = "Appendix Signal"
        reason_codes.append(value["issue_disposition"])
    elif (
        value["evidence_state"] == "sufficient"
        and value["executive_materiality"] is True
        and value["decision_needed"] is True
        and disposition == "accepted"
    ):
        primary = "Decision Required"
        reason_codes.append("decision_evidence_sufficient")
        if value["pack_authority"] == "provisional":
            primary = "Immediate Verification"
            authority_cap = True
            reason_codes.append("provisional_authority_cap")
    elif (
        value["executive_materiality"] is True
        and (
            value["evidence_state"] in {"limited", "conflicting"}
            or value["decision_needed"] == "unknown"
            or disposition == "disputed"
        )
    ):
        primary = "Immediate Verification"
        reason_codes.append("verification_required")
    elif (
        value["executive_materiality"] is True
        and value["evidence_state"] == "sufficient"
        and value["decision_needed"] is False
        and disposition == "accepted"
        and value["trackable"]
    ):
        primary = "Monitor"
        secondary.append("delegated_owner_action")
        reason_codes.append("trackable_owner_action")
    elif value["executive_materiality"] is False and value["evidence_state"] != "none" and value["trackable"]:
        primary = "Monitor"
        reason_codes.append("low_materiality_trackable")
    else:
        raise GradeRuleUncovered("valid Grading Input is not covered by the decision table")

    if value["expert_trigger_state"] == "possible":
        secondary.append("possible_expert_review")
    input_hash = hashlib.sha256(canonical_bytes(value)).hexdigest()
    body = {
        "issue_id": value["issue_id"], "publication_status": "published", "rule_version": rule_version,
        "grading_input_hash": input_hash, "input_snapshot_hash": input_hash, "primary_grade": primary,
        "secondary_flags": sorted(set(secondary)), "reason_codes": sorted(set(reason_codes)),
        "applied_threshold_refs": [], "applied_mission_refs": [], "applied_approval_refs": [],
        "authority_cap_applied": authority_cap, "computed_at": computed_at,
    }
    body["grade_record_id"] = _record_id(body)
    return body
