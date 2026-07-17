"""Account Universe completeness and product-claim gate for accounting runs."""

from __future__ import annotations

import copy
import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from trusted_ceo_agent.accounting.suite import assess_suite_readiness, validate_accounting_suite
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, IntegrityError

ACCOUNT_STATES = {
    "deep_reviewed",
    "core_screened",
    "pack_required",
    "not_assessable",
    "not_applicable",
    "excluded_by_approved_scope",
}
GAP_STATES = {"core_screened", "pack_required", "not_assessable"}
_SCHEMA_STORE = SchemaStore()


def _non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must be a non-empty string")
    return value


def _string_list(value: Any, label: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ContractError(f"{label} must be a list of strings")
    result = [_non_empty_string(item, label) for item in value]
    if len(result) != len(set(result)):
        raise ContractError(f"{label} contains duplicates")
    if not allow_empty and not result:
        raise ContractError(f"{label} must not be empty")
    return result


def _validate_period(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} exclusion effective period is required")
    try:
        start_raw = _non_empty_string(value.get("from"), label)
        end_raw = _non_empty_string(value.get("to"), label)
        start = date.fromisoformat(start_raw)
        end = date.fromisoformat(end_raw)
    except ValueError as error:
        raise ContractError(f"{label} exclusion effective period is invalid") from error
    if start > end:
        raise ContractError(f"{label} exclusion effective period is reversed")
    return {"from": start_raw, "to": end_raw}


def _normalize_record(value: Mapping[str, Any], known_packs: set[str]) -> dict[str, Any]:
    account_id = _non_empty_string(value.get("account_family_id"), "account_family_id")
    state = value.get("state")
    if state not in ACCOUNT_STATES:
        raise ContractError(f"{account_id} state is blank or unknown: {state!r}")
    material = value.get("material")
    if not isinstance(material, bool):
        raise ContractError(f"{account_id} material must be boolean")
    pack_id = value.get("pack_id")
    if pack_id is not None:
        pack_id = _non_empty_string(pack_id, f"{account_id} pack_id")
        if pack_id not in known_packs:
            raise ContractError(f"{account_id} references an unknown accounting pack")
    missing = _string_list(value.get("missing_capabilities", []), f"{account_id} missing capabilities")
    actions = _string_list(value.get("next_actions", []), f"{account_id} next actions")
    evidence = _string_list(value.get("evidence_refs", []), f"{account_id} evidence refs")

    approval_ref = value.get("approval_ref")
    exclusion_reason = value.get("exclusion_reason")
    exclusion_period = value.get("exclusion_effective_period")
    if state == "excluded_by_approved_scope":
        approval_ref = _non_empty_string(approval_ref, f"{account_id} exclusion approval")
        exclusion_reason = _non_empty_string(exclusion_reason, f"{account_id} exclusion reason")
        exclusion_period = _validate_period(exclusion_period, account_id)
    else:
        if approval_ref is not None:
            approval_ref = _non_empty_string(approval_ref, f"{account_id} approval_ref")
        if exclusion_reason is not None:
            exclusion_reason = _non_empty_string(exclusion_reason, f"{account_id} exclusion_reason")
        if exclusion_period is not None:
            exclusion_period = _validate_period(exclusion_period, account_id)

    if state in {"not_assessable", "pack_required"} and (not missing or not actions):
        raise ContractError(f"{account_id} {state} requires missing capability and next action")
    if state == "deep_reviewed" and pack_id is None:
        raise ContractError(f"{account_id} deep_reviewed requires a known pack")
    if state == "not_applicable" and not evidence:
        raise ContractError(f"{account_id} not_applicable requires evidence")

    return {
        "account_family_id": account_id,
        "amount_fact_ref": _non_empty_string(value.get("amount_fact_ref"), f"{account_id} amount Fact ref"),
        "risk": _non_empty_string(value.get("risk"), f"{account_id} risk"),
        "material": material,
        "state": state,
        "pack_id": pack_id,
        "missing_capabilities": missing,
        "next_actions": actions,
        "evidence_refs": evidence,
        "approval_ref": approval_ref,
        "exclusion_reason": exclusion_reason,
        "exclusion_effective_period": exclusion_period,
    }


def assess_account_universe(
    *,
    source_account_family_ids: Sequence[str],
    records: Sequence[Mapping[str, Any]],
    suite: Mapping[str, Any],
    requested_product_claim: str | None = None,
) -> dict[str, Any]:
    """Require one explicit state for every family declared by deterministic mapping."""
    trusted_suite = validate_accounting_suite(suite)
    source_ids = _string_list(
        source_account_family_ids,
        "source_account_family_ids",
        allow_empty=False,
    )
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise ContractError("account universe records must be a list")
    known_packs = {pack["pack_id"] for pack in trusted_suite["packs"]}
    normalized = [
        _normalize_record(record, known_packs)
        if isinstance(record, Mapping)
        else (_ for _ in ()).throw(ContractError("account universe record must be an object"))
        for record in records
    ]
    record_ids = [record["account_family_id"] for record in normalized]
    if len(record_ids) != len(set(record_ids)):
        raise ContractError("account universe contains duplicate account family records")
    missing = sorted(set(source_ids) - set(record_ids))
    extra = sorted(set(record_ids) - set(source_ids))
    if missing or extra:
        raise ContractError(f"account universe mapping mismatch; missing={missing}; extra={extra}")

    pack_authority = {pack["pack_id"]: pack["authority"] for pack in trusted_suite["packs"]}
    blockers: set[str] = set()
    material_gaps: list[str] = []
    for record in normalized:
        if record["material"] and record["state"] in GAP_STATES:
            material_gaps.append(record["account_family_id"])
            blockers.add(f"material_{record['state']}")
        if record["state"] == "deep_reviewed" and pack_authority[record["pack_id"]] == "machine_draft":
            blockers.add("deep_review_pack_not_activated")

    readiness = assess_suite_readiness(trusted_suite)
    if readiness["blocker_codes"]:
        blockers.add("suite_not_expert_released")
    ordered_records = sorted(normalized, key=lambda item: item["account_family_id"])
    ordered_gaps = sorted(material_gaps)
    ordered_blockers = sorted(blockers)
    full_allowed = (
        trusted_suite["authority"] == "Full"
        and not ordered_gaps
        and not ordered_blockers
        and all(
            not record["material"]
            or record["state"] in {
                "deep_reviewed", "not_applicable", "excluded_by_approved_scope"
            }
            for record in ordered_records
        )
    )
    senior_allowed = (
        readiness["senior_accountant_claim_allowed"]
        and not ordered_gaps
        and "deep_review_pack_not_activated" not in blockers
    )
    product_display = {
        "machine_draft": "machine_draft",
        "Boundary": "three_cycles_boundary",
        "Provisional": "senior_accountant_draft_scope",
        "Full": "company_wide_accounting_full",
    }[trusted_suite["authority"]]

    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "suite_ref": {
            "suite_id": trusted_suite["suite_id"],
            "release_id": trusted_suite["release_id"],
            "content_hash": trusted_suite["content_hash"],
        },
        "source_account_family_ids": sorted(source_ids),
        "records": ordered_records,
        "state_counts": dict(sorted(Counter(record["state"] for record in ordered_records).items())),
        "coverage_gap_count": len(ordered_gaps),
        "material_gap_account_family_ids": ordered_gaps,
        "blocker_codes": ordered_blockers,
        "claim_authority": trusted_suite["authority"],
        "product_display": product_display,
        "senior_accountant_claim_allowed": senior_allowed,
        "company_wide_full_allowed": full_allowed,
        "requested_product_claim": requested_product_claim,
    }
    result = {**body, "assessment_hash": hashlib.sha256(canonical_bytes(body)).hexdigest()}
    _SCHEMA_STORE.validate("account-universe-assessment.schema.json", result)
    if requested_product_claim == "company_wide_accounting_full" and not full_allowed:
        raise ContractError("company-wide Full accounting claim is blocked by Account Universe coverage")
    if requested_product_claim == "senior_accountant_draft_scope" and not senior_allowed:
        raise ContractError("senior accountant claim is blocked by coverage or expert release")
    if requested_product_claim not in {
        None,
        "machine_draft",
        "accounting_core_screened",
        "three_cycles_boundary",
        "senior_accountant_draft_scope",
        "company_wide_accounting_full",
    }:
        raise ContractError(f"unknown accounting product claim: {requested_product_claim}")
    return result


def validate_account_universe_assessment(value: Mapping[str, Any]) -> dict[str, Any]:
    _SCHEMA_STORE.validate("account-universe-assessment.schema.json", value)
    expected = hashlib.sha256(
        canonical_bytes({key: child for key, child in value.items() if key != "assessment_hash"})
    ).hexdigest()
    if value["assessment_hash"] != expected:
        raise IntegrityError("account universe assessment hash mismatch")
    return copy.deepcopy(dict(value))
