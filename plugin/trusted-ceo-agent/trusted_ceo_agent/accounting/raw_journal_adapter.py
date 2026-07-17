"""Deterministically materialize AC-06..AC-16 inputs from raw populations."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from trusted_ceo_agent.canonical import canonical_decimal
from trusted_ceo_agent.errors import ContractError

_TOP_FIELDS = {
    "run_id", "revision", "close_timestamp", "journals", "allowed_account_pairs",
    "subsequent_disbursements", "policy_changes", "capitalization_items",
    "counterparties",
}
_JOURNAL_FIELDS = {
    "journal_id", "entity", "currency", "period", "source_id", "document_id",
    "posting_date", "economic_event_date", "entered_at", "approved_at",
    "creator_id", "approver_id", "creator_role", "source_type",
    "changed_from_automatic", "debit_account", "credit_account", "amount",
    "description", "counterparty_id", "reversal_of", "expected_reversal",
    "period_reopened", "suspense", "days_outstanding", "clear_repost",
    "recurring_expected", "authorized_exception", "timing_documented",
    "kpi_direction", "source_refs", "counter_evidence_refs",
}
_PAIR_FIELDS = {"entity", "debit_account", "credit_account"}
_SIDE_COMMON = {
    "row_id", "entity", "currency", "period", "source_refs",
    "counter_evidence_refs",
}
_SIDE_SPECS = {
    "subsequent_disbursements": {
        "prior_service_amount", "recurring_expected", "recorded_accrual",
        "new_period_service_amount",
    },
    "policy_changes": {
        "policy_change_amount", "estimate_change_amount", "prior_error_amount",
        "comparative_restated_amount",
    },
    "capitalization_items": {
        "recorded_capitalized_amount", "supported_capitalizable_amount",
        "impairment_indicator_amount", "recorded_impairment_amount",
    },
    "counterparties": {
        "counterparty_id", "candidate_amount", "confirmed_amount", "disclosed_amount",
    },
}


def _object(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} must be an object")
    missing = sorted(fields - set(value))
    unknown = sorted(set(value) - fields)
    if missing or unknown:
        raise ContractError(f"{label} field mismatch; missing={missing}; unknown={unknown}")
    return value


def _array(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ContractError(f"{label} must be an array")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must be a non-empty string")
    return value


def _nullable_text(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError(f"{label} must be boolean")
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
        raise ContractError(f"{label} must be a decimal string") from error
    if not number.is_finite() or number < 0:
        raise ContractError(f"{label} must be finite and non-negative")
    return canonical_decimal(number)


def _date(value: Any, label: str) -> str:
    text = _text(value, label)
    try:
        date.fromisoformat(text)
    except ValueError as error:
        raise ContractError(f"{label} must be ISO date") from error
    return text


def _datetime(value: Any, label: str) -> str:
    text = _text(value, label)
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(f"{label} must be ISO datetime") from error
    return text


def _refs(value: Any, label: str) -> list[str]:
    refs = [_text(item, f"{label}[]") for item in _array(value, label)]
    if len(refs) != len(set(refs)):
        raise ContractError(f"{label} contains duplicates")
    return sorted(refs)


def _normalize_journals(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(_array(value, "journals")):
        row = _object(raw, _JOURNAL_FIELDS, f"journals[{index}]")
        source_type = _text(row["source_type"], f"journals[{index}].source_type")
        if source_type not in {"manual", "automatic"}:
            raise ContractError("journal source_type must be manual or automatic")
        direction = _text(row["kpi_direction"], f"journals[{index}].kpi_direction")
        if direction not in {"improves", "neutral", "worsens"}:
            raise ContractError("journal kpi_direction is invalid")
        rows.append({
            "journal_id": _text(row["journal_id"], f"journals[{index}].journal_id"),
            "entity": _text(row["entity"], f"journals[{index}].entity"),
            "currency": _text(row["currency"], f"journals[{index}].currency"),
            "period": _text(row["period"], f"journals[{index}].period"),
            "source_id": _text(row["source_id"], f"journals[{index}].source_id"),
            "document_id": _text(row["document_id"], f"journals[{index}].document_id"),
            "posting_date": _date(row["posting_date"], f"journals[{index}].posting_date"),
            "economic_event_date": _date(row["economic_event_date"], f"journals[{index}].economic_event_date"),
            "entered_at": _datetime(row["entered_at"], f"journals[{index}].entered_at"),
            "approved_at": _datetime(row["approved_at"], f"journals[{index}].approved_at"),
            "creator_id": _text(row["creator_id"], f"journals[{index}].creator_id"),
            "approver_id": _text(row["approver_id"], f"journals[{index}].approver_id"),
            "creator_role": _text(row["creator_role"], f"journals[{index}].creator_role"),
            "source_type": source_type,
            "changed_from_automatic": _boolean(row["changed_from_automatic"], f"journals[{index}].changed_from_automatic"),
            "debit_account": _text(row["debit_account"], f"journals[{index}].debit_account"),
            "credit_account": _text(row["credit_account"], f"journals[{index}].credit_account"),
            "amount": _decimal(row["amount"], f"journals[{index}].amount"),
            "description": _text(row["description"], f"journals[{index}].description"),
            "counterparty_id": _text(row["counterparty_id"], f"journals[{index}].counterparty_id"),
            "reversal_of": _nullable_text(row["reversal_of"], f"journals[{index}].reversal_of"),
            "expected_reversal": _boolean(row["expected_reversal"], f"journals[{index}].expected_reversal"),
            "period_reopened": _boolean(row["period_reopened"], f"journals[{index}].period_reopened"),
            "suspense": _boolean(row["suspense"], f"journals[{index}].suspense"),
            "days_outstanding": _integer(row["days_outstanding"], f"journals[{index}].days_outstanding"),
            "clear_repost": _boolean(row["clear_repost"], f"journals[{index}].clear_repost"),
            "recurring_expected": _boolean(row["recurring_expected"], f"journals[{index}].recurring_expected"),
            "authorized_exception": _boolean(row["authorized_exception"], f"journals[{index}].authorized_exception"),
            "timing_documented": _boolean(row["timing_documented"], f"journals[{index}].timing_documented"),
            "kpi_direction": direction,
            "source_refs": _refs(row["source_refs"], f"journals[{index}].source_refs"),
            "counter_evidence_refs": _refs(row["counter_evidence_refs"], f"journals[{index}].counter_evidence_refs"),
        })
    rows.sort(key=lambda item: item["journal_id"])
    ids = [item["journal_id"] for item in rows]
    if len(ids) != len(set(ids)):
        raise ContractError("journals contains duplicate journal_id")
    return rows


def _normalize_pairs(value: Any) -> list[dict[str, str]]:
    result = []
    for index, raw in enumerate(_array(value, "allowed_account_pairs")):
        row = _object(raw, _PAIR_FIELDS, f"allowed_account_pairs[{index}]")
        result.append({field: _text(row[field], f"allowed_account_pairs[{index}].{field}") for field in sorted(_PAIR_FIELDS)})
    return sorted(result, key=lambda item: (item["entity"], item["debit_account"], item["credit_account"]))


def _normalize_side(name: str, value: Any) -> list[dict[str, Any]]:
    metric_fields = _SIDE_SPECS[name]
    fields = _SIDE_COMMON | metric_fields
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(_array(value, name)):
        row = _object(raw, fields, f"{name}[{index}]")
        normalized: dict[str, Any] = {
            "row_id": _text(row["row_id"], f"{name}[{index}].row_id"),
            "entity": _text(row["entity"], f"{name}[{index}].entity"),
            "currency": _text(row["currency"], f"{name}[{index}].currency"),
            "period": _text(row["period"], f"{name}[{index}].period"),
            "source_refs": _refs(row["source_refs"], f"{name}[{index}].source_refs"),
            "counter_evidence_refs": _refs(row["counter_evidence_refs"], f"{name}[{index}].counter_evidence_refs"),
        }
        for field in sorted(metric_fields):
            if field == "counterparty_id":
                normalized[field] = _text(row[field], f"{name}[{index}].{field}")
            else:
                normalized[field] = _decimal(row[field], f"{name}[{index}].{field}")
        result.append(normalized)
    result.sort(key=lambda item: item["row_id"])
    ids = [item["row_id"] for item in result]
    if len(ids) != len(set(ids)):
        raise ContractError(f"{name} contains duplicate row_id")
    return result


def _scope(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return row["entity"], row["currency"], row["period"]


def _amount(row: Mapping[str, Any]) -> Decimal:
    return Decimal(row["amount"])


def _sums(rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> dict[str, Decimal]:
    return {field: sum((Decimal(row[field]) for row in rows), Decimal(0)) for field in fields}


def _refs_for(rows: Sequence[Mapping[str, Any]], field: str) -> list[str]:
    return sorted({ref for row in rows for ref in row[field]})


def _row(issue_id: str, scope: tuple[str, str, str], metrics: Mapping[str, Decimal], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    entity, currency, period = scope
    return {
        "row_id": f"raw:{issue_id}:{entity}:{currency}:{period}",
        "entity": entity,
        "currency": currency,
        "period": period,
        "metrics": {key: canonical_decimal(value) for key, value in sorted(metrics.items())},
        "source_refs": _refs_for(rows, "source_refs"),
        "counter_evidence_refs": _refs_for(rows, "counter_evidence_refs"),
    }


def _journal_metrics(rows: list[dict[str, Any]], close_at: datetime, allowed: set[tuple[str, str, str]]) -> dict[str, dict[str, Decimal]]:
    exact_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        exact_groups[(row["source_id"], row["document_id"], row["debit_account"], row["credit_account"], row["amount"], row["posting_date"])].append(row)
    exact = sum((_amount(group[0]) * (len(group) - 1) for group in exact_groups.values() if len(group) > 1), Decimal(0))
    near_ids: set[str] = set()
    split_ids: set[str] = set()
    reversal_pairs: set[tuple[str, str]] = set()
    for index, left in enumerate(rows):
        for right in rows[index + 1:]:
            same_base = (
                left["debit_account"] == right["debit_account"]
                and left["credit_account"] == right["credit_account"]
                and left["amount"] == right["amount"]
                and left["counterparty_id"] == right["counterparty_id"]
            )
            exact_key = (
                left["source_id"] == right["source_id"]
                and left["document_id"] == right["document_id"]
                and left["posting_date"] == right["posting_date"]
            )
            if same_base and not exact_key and abs((date.fromisoformat(left["posting_date"]) - date.fromisoformat(right["posting_date"])).days) <= 3:
                near_ids.add(right["journal_id"])
            if (
                left["debit_account"] == right["credit_account"]
                and left["credit_account"] == right["debit_account"]
                and left["amount"] == right["amount"]
            ):
                reversal_pairs.add((left["journal_id"], right["journal_id"]))
    for target in rows:
        candidates = [item for item in rows if item["journal_id"] != target["journal_id"] and item["debit_account"] == target["debit_account"] and item["credit_account"] == target["credit_account"] and item["counterparty_id"] == target["counterparty_id"]]
        found = False
        for index, left in enumerate(candidates):
            for right in candidates[index + 1:]:
                if _amount(left) + _amount(right) == _amount(target):
                    split_ids.add(target["journal_id"])
                    found = True
                    break
            if found:
                break
    post_close = sum((_amount(row) for row in rows if datetime.fromisoformat(row["entered_at"].replace("Z", "+00:00")) > close_at and date.fromisoformat(row["posting_date"]) <= close_at.date()), Decimal(0))
    direct_allowed = {(entity, debit, credit) for entity, debit, credit in allowed}
    reverse_allowed = {(entity, credit, debit) for entity, debit, credit in allowed}
    originals = {row["journal_id"]: row for row in rows if row["expected_reversal"]}
    reversals: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["reversal_of"] is not None:
            reversals[row["reversal_of"]].append(row)
    original_amount = matched = duplicate = partial = wrong = Decimal(0)
    for journal_id, original in originals.items():
        original_amount += _amount(original)
        candidates = reversals.get(journal_id, [])
        exact_matches = [row for row in candidates if row["debit_account"] == original["credit_account"] and row["credit_account"] == original["debit_account"] and row["amount"] == original["amount"]]
        if exact_matches:
            matched += _amount(exact_matches[0])
            duplicate += sum((_amount(row) for row in exact_matches[1:]), Decimal(0))
        partial += sum((_amount(row) for row in candidates if row not in exact_matches and row["debit_account"] == original["credit_account"] and row["credit_account"] == original["debit_account"]), Decimal(0))
        wrong += sum((_amount(row) for row in candidates if row["debit_account"] != original["credit_account"] or row["credit_account"] != original["debit_account"]), Decimal(0))
    creator_totals: dict[str, Decimal] = defaultdict(Decimal)
    manual_total = Decimal(0)
    for row in rows:
        if row["source_type"] == "manual":
            creator_totals[row["creator_id"]] += _amount(row)
            manual_total += _amount(row)
    concentrated = max(creator_totals.values(), default=Decimal(0)) if manual_total else Decimal(0)
    return {
        "AC-06": {
            "exact_duplicate_amount": exact,
            "near_duplicate_amount": sum((_amount(row) for row in rows if row["journal_id"] in near_ids), Decimal(0)),
            "split_duplicate_amount": sum((_amount(row) for row in rows if row["journal_id"] in split_ids), Decimal(0)),
            "reversal_like_amount": sum((_amount(next(item for item in rows if item["journal_id"] == pair[1])) for pair in sorted(reversal_pairs)), Decimal(0)),
            "legitimate_recurring_amount": sum((_amount(row) for row in rows if row["recurring_expected"]), Decimal(0)),
        },
        "AC-07": {
            "post_close_backdated_amount": post_close,
            "reopened_period_amount": sum((_amount(row) for row in rows if row["period_reopened"]), Decimal(0)),
            "immediate_reversal_amount": sum((_amount(row) for row in rows if row["reversal_of"] is not None), Decimal(0)),
            "documented_timing_difference_amount": sum((_amount(row) for row in rows if row["timing_documented"]), Decimal(0)),
        },
        "AC-08": {
            "same_creator_approver_amount": sum((_amount(row) for row in rows if row["creator_id"] == row["approver_id"]), Decimal(0)),
            "admin_posting_amount": sum((_amount(row) for row in rows if row["creator_role"] == "admin"), Decimal(0)),
            "manual_override_amount": sum((_amount(row) for row in rows if row["changed_from_automatic"]), Decimal(0)),
            "after_hours_amount": sum((_amount(row) for row in rows if datetime.fromisoformat(row["entered_at"].replace("Z", "+00:00")).hour < 6 or datetime.fromisoformat(row["entered_at"].replace("Z", "+00:00")).hour >= 22), Decimal(0)),
            "authorized_exception_amount": sum((_amount(row) for row in rows if row["authorized_exception"]), Decimal(0)),
        },
        "AC-09": {
            "rare_pair_amount": sum((_amount(row) for row in rows if (row["entity"], row["debit_account"], row["credit_account"]) not in direct_allowed and (row["entity"], row["debit_account"], row["credit_account"]) not in reverse_allowed), Decimal(0)),
            "reverse_normal_balance_amount": sum((_amount(row) for row in rows if (row["entity"], row["debit_account"], row["credit_account"]) in reverse_allowed), Decimal(0)),
            "approved_pair_exception_amount": sum((_amount(row) for row in rows if row["authorized_exception"]), Decimal(0)),
        },
        "AC-10": {
            "original_amount": original_amount,
            "matched_reversal_amount": matched,
            "duplicate_reversal_amount": duplicate,
            "partial_reversal_amount": partial,
            "wrong_account_reversal_amount": wrong,
        },
        "AC-11": {
            "closing_suspense_balance": sum((_amount(row) for row in rows if row["suspense"]), Decimal(0)),
            "aged_balance": sum((_amount(row) for row in rows if row["suspense"] and row["days_outstanding"] >= 90), Decimal(0)),
            "clear_repost_amount": sum((_amount(row) for row in rows if row["clear_repost"]), Decimal(0)),
            "supported_balance": sum((_amount(row) for row in rows if row["suspense"] and row["authorized_exception"]), Decimal(0)),
        },
        "AC-16": {
            "manual_kpi_improving_amount": sum((_amount(row) for row in rows if row["source_type"] == "manual" and row["kpi_direction"] == "improves"), Decimal(0)),
            "next_period_reversal_amount": sum((_amount(row) for row in rows if row["reversal_of"] is not None), Decimal(0)),
            "concentrated_user_amount": concentrated,
            "supported_business_amount": sum((_amount(row) for row in rows if row["authorized_exception"]), Decimal(0)),
        },
    }


def materialize_core_extended_inputs(value: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Create closed AC-06..AC-16 inputs from one immutable raw snapshot."""
    root = _object(value, _TOP_FIELDS, "raw accounting population")
    run_id = _text(root["run_id"], "run_id")
    revision = _integer(root["revision"], "revision")
    close_text = _datetime(root["close_timestamp"], "close_timestamp")
    close_at = datetime.fromisoformat(close_text.replace("Z", "+00:00"))
    journals = _normalize_journals(root["journals"])
    pairs = _normalize_pairs(root["allowed_account_pairs"])
    side = {name: _normalize_side(name, root[name]) for name in _SIDE_SPECS}
    allowed = {(item["entity"], item["debit_account"], item["credit_account"]) for item in pairs}
    journal_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in journals:
        journal_groups[_scope(row)].append(row)
    result: dict[str, dict[str, Any]] = {f"AC-{number:02d}": {"run_id": run_id, "revision": revision, "rows": []} for number in range(6, 17)}
    for scope in sorted(journal_groups):
        rows = journal_groups[scope]
        metrics = _journal_metrics(rows, close_at, allowed)
        for issue_id, values in metrics.items():
            result[issue_id]["rows"].append(_row(issue_id, scope, values, rows))
    side_map = {
        "AC-12": ("subsequent_disbursements", {
            "subsequent_payment_prior_service_amount": "prior_service_amount",
            "recurring_cost_expected": "recurring_expected",
            "recorded_accrual_amount": "recorded_accrual",
            "new_period_service_amount": "new_period_service_amount",
        }),
        "AC-13": ("policy_changes", {
            "policy_change_amount": "policy_change_amount",
            "estimate_change_amount": "estimate_change_amount",
            "prior_error_amount": "prior_error_amount",
            "comparative_restated_amount": "comparative_restated_amount",
        }),
        "AC-14": ("capitalization_items", {
            "recorded_capitalized_amount": "recorded_capitalized_amount",
            "supported_capitalizable_amount": "supported_capitalizable_amount",
            "impairment_indicator_amount": "impairment_indicator_amount",
            "recorded_impairment_amount": "recorded_impairment_amount",
        }),
        "AC-15": ("counterparties", {
            "related_party_candidate_amount": "candidate_amount",
            "confirmed_related_party_amount": "confirmed_amount",
            "disclosed_related_party_amount": "disclosed_amount",
        }),
    }
    for issue_id, (name, mapping) in side_map.items():
        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in side[name]:
            groups[_scope(row)].append(row)
        for scope in sorted(groups):
            rows = groups[scope]
            sums = _sums(rows, list(mapping.values()))
            result[issue_id]["rows"].append(_row(issue_id, scope, {target: sums[source] for target, source in mapping.items()}, rows))
    return result


__all__ = ["materialize_core_extended_inputs"]
