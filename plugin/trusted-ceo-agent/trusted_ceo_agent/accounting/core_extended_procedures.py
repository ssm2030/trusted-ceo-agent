"""Deterministic Boundary procedures for Accounting Core AC-06 through AC-16."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes, canonical_decimal
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError

_SCHEMA = "accounting-core-extended-procedure-result.schema.json"
_SCHEMA_STORE = SchemaStore()

SUPPORTED_CORE_EXTENDED_ISSUES = tuple(f"AC-{number:02d}" for number in range(6, 17))

_PROCEDURE_IDS = {
    **{f"AC-{number:02d}": f"P-AC-{number:02d}" for number in range(6, 17)},
}
_CODES = {
    "AC-06": "duplicate_journal_candidate",
    "AC-07": "cutoff_journal_candidate",
    "AC-08": "approval_override_candidate",
    "AC-09": "abnormal_account_pair_candidate",
    "AC-10": "reversal_pairing_difference",
    "AC-11": "aged_suspense_balance",
    "AC-12": "unrecorded_liability_candidate",
    "AC-13": "policy_estimate_error_classification_boundary",
    "AC-14": "capitalization_or_impairment_difference",
    "AC-15": "related_party_trace_boundary",
    "AC-16": "management_bias_concentration_candidate",
}
_REQUIRED_METRICS = {
    "AC-06": frozenset(
        {
            "exact_duplicate_amount",
            "near_duplicate_amount",
            "split_duplicate_amount",
            "reversal_like_amount",
            "legitimate_recurring_amount",
        }
    ),
    "AC-07": frozenset(
        {
            "post_close_backdated_amount",
            "reopened_period_amount",
            "immediate_reversal_amount",
            "documented_timing_difference_amount",
        }
    ),
    "AC-08": frozenset(
        {
            "same_creator_approver_amount",
            "admin_posting_amount",
            "manual_override_amount",
            "after_hours_amount",
            "authorized_exception_amount",
        }
    ),
    "AC-09": frozenset(
        {
            "rare_pair_amount",
            "reverse_normal_balance_amount",
            "approved_pair_exception_amount",
        }
    ),
    "AC-10": frozenset(
        {
            "original_amount",
            "matched_reversal_amount",
            "duplicate_reversal_amount",
            "partial_reversal_amount",
            "wrong_account_reversal_amount",
        }
    ),
    "AC-11": frozenset(
        {
            "closing_suspense_balance",
            "aged_balance",
            "clear_repost_amount",
            "supported_balance",
        }
    ),
    "AC-12": frozenset(
        {
            "subsequent_payment_prior_service_amount",
            "recurring_cost_expected",
            "recorded_accrual_amount",
            "new_period_service_amount",
        }
    ),
    "AC-13": frozenset(
        {
            "policy_change_amount",
            "estimate_change_amount",
            "prior_error_amount",
            "comparative_restated_amount",
        }
    ),
    "AC-14": frozenset(
        {
            "recorded_capitalized_amount",
            "supported_capitalizable_amount",
            "impairment_indicator_amount",
            "recorded_impairment_amount",
        }
    ),
    "AC-15": frozenset(
        {
            "related_party_candidate_amount",
            "confirmed_related_party_amount",
            "disclosed_related_party_amount",
        }
    ),
    "AC-16": frozenset(
        {
            "manual_kpi_improving_amount",
            "next_period_reversal_amount",
            "concentrated_user_amount",
            "supported_business_amount",
        }
    ),
}
_REVIEW_SCOPE = {
    "AC-06": "accounting",
    "AC-07": "accounting",
    "AC-08": "accounting_and_governance",
    "AC-09": "accounting",
    "AC-10": "accounting",
    "AC-11": "accounting",
    "AC-12": "accounting_and_valuation",
    "AC-13": "accounting_and_legal_tax",
    "AC-14": "accounting_and_valuation",
    "AC-15": "accounting_and_legal_tax",
    "AC-16": "accounting_and_fraud_risk",
}
_BOUNDARY_REASON = {
    "AC-06": "recurrence and automatic-reversal counter-evidence must be reviewed",
    "AC-07": "date alignment alone cannot determine an accounting error",
    "AC-08": "role, shift, and authorized control exceptions require review",
    "AC-09": "pair rarity is priority evidence, not an error determination",
    "AC-10": "pairing differences require source-document review",
    "AC-11": "aging requires owner, movement, and support review",
    "AC-12": "service period and new-period counter-evidence require review",
    "AC-13": "approved IAS 8 or K-IFRS 1008 Norm and expert review are required",
    "AC-14": "an account name alone cannot support capitalization",
    "AC-15": "related-party status and disclosure require expert review",
    "AC-16": "independent indicators cannot be collapsed into an opaque score",
}

_TOP_FIELDS = {"run_id", "revision", "rows"}
_ROW_FIELDS = {
    "row_id",
    "entity",
    "currency",
    "period",
    "metrics",
    "source_refs",
    "counter_evidence_refs",
}


def _digest(value: Mapping[str, Any], excluded: str | None = None) -> str:
    body = dict(value)
    if excluded is not None:
        body.pop(excluded, None)
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def _object(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} must be an object")
    unknown = sorted(set(value) - fields)
    missing = sorted(fields - set(value))
    if unknown or missing:
        raise ContractError(f"{label} field mismatch; missing={missing}; unknown={unknown}")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must be a non-empty string")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractError(f"{label} must be a non-negative integer")
    return value


def _decimal(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{label} must be an exact decimal string")
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ContractError(f"{label} must be a valid decimal string") from error
    if not number.is_finite() or number < 0:
        raise ContractError(f"{label} must be a finite non-negative decimal")
    return canonical_decimal(number)


def _refs(value: Any, label: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ContractError(f"{label} must be an array")
    refs = [_text(item, f"{label}[]") for item in value]
    if len(refs) != len(set(refs)):
        raise ContractError(f"{label} must not contain duplicates")
    return sorted(refs)


def _normalize_input(issue_id: str, value: Mapping[str, Any]) -> dict[str, Any]:
    root = _object(value, _TOP_FIELDS, "core extended input")
    rows_value = root["rows"]
    if not isinstance(rows_value, Sequence) or isinstance(rows_value, (str, bytes)):
        raise ContractError("rows must be an array")

    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(rows_value):
        row = _object(raw, _ROW_FIELDS, f"rows[{index}]")
        metrics = row["metrics"]
        if not isinstance(metrics, Mapping):
            raise ContractError(f"rows[{index}].metrics must be an object")
        unknown_metrics = sorted(set(metrics) - _REQUIRED_METRICS[issue_id])
        if unknown_metrics:
            raise ContractError(
                f"rows[{index}].metrics contains unsupported fields: {unknown_metrics}"
            )
        normalized_metrics = {
            name: _decimal(metrics[name], f"rows[{index}].metrics.{name}")
            for name in sorted(metrics)
        }
        rows.append(
            {
                "row_id": _text(row["row_id"], f"rows[{index}].row_id"),
                "entity": _text(row["entity"], f"rows[{index}].entity"),
                "currency": _text(row["currency"], f"rows[{index}].currency"),
                "period": _text(row["period"], f"rows[{index}].period"),
                "metrics": normalized_metrics,
                "source_refs": _refs(row["source_refs"], f"rows[{index}].source_refs"),
                "counter_evidence_refs": _refs(
                    row["counter_evidence_refs"],
                    f"rows[{index}].counter_evidence_refs",
                ),
            }
        )
    rows.sort(key=lambda item: item["row_id"])
    row_ids = [item["row_id"] for item in rows]
    if len(row_ids) != len(set(row_ids)):
        raise ContractError("rows contains duplicate row_id values")
    return {
        "run_id": _text(root["run_id"], "run_id"),
        "revision": _integer(root["revision"], "revision"),
        "rows": rows,
    }


def _d(row: Mapping[str, Any], name: str) -> Decimal:
    return Decimal(row["metrics"][name])


def _quantify(issue_id: str, row: Mapping[str, Any]) -> tuple[Decimal, Decimal, Decimal]:
    d = lambda name: _d(row, name)
    if issue_id == "AC-06":
        observed = (
            d("exact_duplicate_amount")
            + d("near_duplicate_amount")
            + d("split_duplicate_amount")
            + d("reversal_like_amount")
        )
        expected = d("legitimate_recurring_amount")
        amount = max(observed - expected, Decimal(0))
    elif issue_id == "AC-07":
        observed = (
            d("post_close_backdated_amount")
            + d("reopened_period_amount")
            + d("immediate_reversal_amount")
        )
        expected = d("documented_timing_difference_amount")
        amount = max(observed - expected, Decimal(0))
    elif issue_id == "AC-08":
        observed = (
            d("same_creator_approver_amount")
            + d("admin_posting_amount")
            + d("manual_override_amount")
            + d("after_hours_amount")
        )
        expected = d("authorized_exception_amount")
        amount = max(observed - expected, Decimal(0))
    elif issue_id == "AC-09":
        observed = d("rare_pair_amount") + d("reverse_normal_balance_amount")
        expected = d("approved_pair_exception_amount")
        amount = max(observed - expected, Decimal(0))
    elif issue_id == "AC-10":
        observed = d("matched_reversal_amount")
        expected = d("original_amount")
        amount = (
            abs(expected - observed)
            + d("duplicate_reversal_amount")
            + d("partial_reversal_amount")
            + d("wrong_account_reversal_amount")
        )
    elif issue_id == "AC-11":
        observed = max(d("closing_suspense_balance"), d("aged_balance")) + d(
            "clear_repost_amount"
        )
        expected = d("supported_balance")
        amount = max(observed - expected, Decimal(0))
    elif issue_id == "AC-12":
        expected = max(
            d("subsequent_payment_prior_service_amount")
            + d("recurring_cost_expected")
            - d("new_period_service_amount"),
            Decimal(0),
        )
        observed = d("recorded_accrual_amount")
        amount = max(expected - observed, Decimal(0))
    elif issue_id == "AC-13":
        observed = (
            d("policy_change_amount")
            + d("estimate_change_amount")
            + d("prior_error_amount")
        )
        expected = d("comparative_restated_amount")
        amount = abs(observed - expected)
    elif issue_id == "AC-14":
        observed = d("recorded_capitalized_amount") + d("impairment_indicator_amount")
        expected = d("supported_capitalizable_amount") + d("recorded_impairment_amount")
        amount = abs(observed - expected)
    elif issue_id == "AC-15":
        observed = max(
            d("related_party_candidate_amount"),
            d("confirmed_related_party_amount"),
        )
        expected = d("disclosed_related_party_amount")
        amount = max(observed - expected, Decimal(0))
    else:
        observed = (
            d("manual_kpi_improving_amount")
            + d("next_period_reversal_amount")
            + d("concentrated_user_amount")
        )
        expected = d("supported_business_amount")
        amount = max(observed - expected, Decimal(0))
    return observed, expected, amount


def _outcome(
    issue_id: str,
    row: Mapping[str, Any],
    observed: Decimal,
    expected: Decimal,
    amount: Decimal,
) -> dict[str, Any]:
    return {
        "code": _CODES[issue_id],
        "row_id": row["row_id"],
        "entity": row["entity"],
        "currency": row["currency"],
        "period": row["period"],
        "observed": canonical_decimal(observed),
        "expected": canonical_decimal(expected),
        "amount": canonical_decimal(amount),
        "review_scope": _REVIEW_SCOPE[issue_id],
        "boundary_reason": _BOUNDARY_REASON[issue_id],
        "source_refs": list(row["source_refs"]),
        "counter_evidence_refs": list(row["counter_evidence_refs"]),
    }


def run_core_extended_procedure(
    issue_id: str,
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Run one AC-06..AC-16 procedure without making a Finding or approval."""
    if issue_id not in SUPPORTED_CORE_EXTENDED_ISSUES:
        raise ContractError(f"unsupported core extended issue family: {issue_id}")
    if not isinstance(value, Mapping):
        raise ContractError("core extended input must be an object")
    data = _normalize_input(issue_id, value)

    missing_inputs: list[str] = []
    if not data["rows"]:
        missing_inputs.append("rows")
    for row in data["rows"]:
        for name in sorted(_REQUIRED_METRICS[issue_id] - set(row["metrics"])):
            missing_inputs.append(f"{row['row_id']}:metrics.{name}")
        if not row["source_refs"]:
            missing_inputs.append(f"{row['row_id']}:source_refs")
        if not row["counter_evidence_refs"]:
            missing_inputs.append(f"{row['row_id']}:counter_evidence_refs")

    outcomes: list[dict[str, Any]] = []
    if not missing_inputs:
        for row in data["rows"]:
            observed, expected, amount = _quantify(issue_id, row)
            if amount != 0:
                outcomes.append(_outcome(issue_id, row, observed, expected, amount))
        outcomes.sort(key=canonical_bytes)

    if missing_inputs:
        status = "not_assessable"
    elif outcomes:
        status = "exceptions_found"
    else:
        status = "passed"
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": data["run_id"],
        "revision": data["revision"],
        "issue_family_id": issue_id,
        "procedure_id": _PROCEDURE_IDS[issue_id],
        "input_hash": _digest(data),
        "status": status,
        "missing_inputs": sorted(set(missing_inputs)),
        "outcomes": outcomes,
        "authority_ceiling": "Boundary",
        "expert_review_required": True,
    }
    result = {**body, "content_hash": _digest(body)}
    _SCHEMA_STORE.validate(_SCHEMA, result)
    return result


def verify_core_extended_procedure_result(value: Mapping[str, Any]) -> dict[str, Any]:
    """Verify schema, dispatch, status invariants, and immutable content hash."""
    if not isinstance(value, Mapping):
        raise ContractError("core extended procedure result must be an object")
    _SCHEMA_STORE.validate(_SCHEMA, value)
    if value["content_hash"] != _digest(value, "content_hash"):
        raise ContractError("core extended procedure result content hash mismatch")
    issue_id = value["issue_family_id"]
    if value["procedure_id"] != _PROCEDURE_IDS[issue_id]:
        raise ContractError("core extended procedure reference mismatch")
    status = value["status"]
    if status == "not_assessable":
        if not value["missing_inputs"] or value["outcomes"]:
            raise ContractError("not_assessable must have missing inputs and no outcomes")
    elif value["missing_inputs"]:
        raise ContractError("assessed result cannot retain missing inputs")
    elif status == "passed" and value["outcomes"]:
        raise ContractError("passed result cannot contain outcomes")
    elif status == "exceptions_found" and not value["outcomes"]:
        raise ContractError("exceptions_found result requires outcomes")
    return copy.deepcopy(dict(value))
