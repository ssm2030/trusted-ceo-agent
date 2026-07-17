"""Deterministic Cash Flow and Working Capital procedures (CF-01 through CF-16).

The pack only transforms supplied accounting evidence into typed procedure
outcomes.  It never creates Facts, Signals, Findings, Grades, or Approvals.
Professional judgements remain Boundary outputs with explicit expert triggers.
"""

from __future__ import annotations

import copy
import hashlib
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from trusted_ceo_agent.accounting.seeds import ISSUE_PROCEDURE_MAP
from trusted_ceo_agent.canonical import canonical_bytes, canonical_decimal
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError

_SCHEMA_STORE = SchemaStore()
_ISSUE_IDS = tuple(f"CF-{number:02d}" for number in range(1, 17))
_DIMENSIONS = ("entity", "currency", "period")
_TOP_FIELDS = {
    "run_id",
    "revision",
    "as_of_date",
    "bank_reconciliations",
    "cash_items",
    "cash_transactions",
    "financing_bridges",
    "supplier_finance_programs",
    "receivables",
    "payables",
    "profit_cash_bridges",
    "counterparty_exposures",
    "receivable_transfers",
    "covenants",
    "mandatory_payments",
    "period_end_events",
    "forecasts",
    "liquidity_positions",
}


def _spec(
    identifier: str,
    fields: tuple[str, ...],
    *,
    decimals: tuple[str, ...] = (),
    integers: tuple[str, ...] = (),
    booleans: tuple[str, ...] = (),
    nullable: tuple[str, ...] = (),
    enums: Mapping[str, tuple[str, ...]] | None = None,
) -> dict[str, Any]:
    return {
        "identifier": identifier,
        "fields": (
            set(fields)
            | set(_DIMENSIONS)
            | {identifier}
            | set(decimals)
            | set(integers)
            | set(booleans)
            | set(nullable)
            | set(enums or {})
        ),
        "decimals": set(decimals),
        "integers": set(integers),
        "booleans": set(booleans),
        "nullable": set(nullable),
        "enums": dict(enums or {}),
    }


_RECORD_SPECS = {
    "bank_reconciliations": _spec(
        "reconciliation_id",
        ("bank_account_id", "bank_source_ref", "gl_source_ref"),
        decimals=(
            "bank_balance",
            "deposits_in_transit",
            "outstanding_payments",
            "verified_reconciling_items",
            "cash_gl_balance",
        ),
    ),
    "cash_items": _spec(
        "cash_item_id",
        (),
        decimals=("amount",),
        integers=("maturity_days",),
        booleans=("readily_convertible", "restricted"),
        nullable=("restriction_evidence_ref",),
        enums={
            "instrument_type": ("demand_deposit", "term_deposit", "escrow", "other"),
            "value_change_risk": ("insignificant", "significant"),
            "recorded_classification": (
                "cash",
                "cash_equivalent",
                "restricted_cash",
                "other",
            ),
        },
    ),
    "cash_transactions": _spec(
        "transaction_id",
        ("source_ref",),
        decimals=("amount",),
        booleans=("is_cash", "reported_in_cashflow"),
        nullable=("original_event_ref", "counterparty_id", "invoice_id"),
        enums={
            "economic_event": (
                "customer_collection",
                "supplier_payment",
                "payroll",
                "tax",
                "interest",
                "debt_proceeds",
                "debt_repayment",
                "asset_purchase",
                "asset_sale",
                "other",
            ),
            "reported_classification": ("operating", "investing", "financing", "excluded"),
            "expected_classification": ("operating", "investing", "financing", "excluded"),
        },
    ),
    "financing_bridges": _spec(
        "bridge_id",
        ("source_ref",),
        decimals=(
            "opening_liability",
            "cash_proceeds",
            "cash_repayments",
            "noncash_changes",
            "fx_changes",
            "other_changes",
            "closing_liability",
        ),
    ),
    "supplier_finance_programs": _spec(
        "program_id",
        ("counterparty_id",),
        decimals=("amount",),
        integers=("standard_term_days", "actual_term_days"),
        booleans=("financial_institution_pays_supplier",),
        nullable=("contract_ref", "disclosure_ref"),
        enums={"recorded_classification": ("ap", "borrowing", "unknown")},
    ),
    "receivables": _spec(
        "invoice_id",
        ("customer_id", "source_ref"),
        decimals=(
            "outstanding_amount",
            "subsequent_collections",
            "credit_notes",
            "disputes",
            "write_offs",
            "expected_credit_loss",
        ),
        integers=("aging_days",),
    ),
    "payables": _spec(
        "payable_id",
        ("supplier_id", "source_ref"),
        decimals=("amount", "outstanding_amount", "paid_after_period"),
        integers=("days_overdue", "standard_term_days", "actual_term_days"),
        booleans=("disputed",),
        nullable=("supplier_finance_program_id",),
    ),
    "profit_cash_bridges": _spec(
        "bridge_id",
        ("source_ref",),
        decimals=(
            "operating_result",
            "noncash_expense",
            "noncash_income",
            "ar_change",
            "contract_balance_change",
            "ap_change",
            "payroll_tax_change",
            "provision_change",
            "deferred_change",
            "other_working_capital_change",
            "operating_adjustments",
            "reported_operating_cash_flow",
        ),
    ),
    "counterparty_exposures": _spec(
        "exposure_id",
        ("counterparty_id", "source_ref"),
        decimals=("exposure_amount", "total_population_amount", "stress_loss_rate"),
        enums={"counterparty_type": ("customer", "supplier")},
    ),
    "receivable_transfers": _spec(
        "transfer_id",
        (),
        decimals=("amount", "cash_received", "recourse_amount"),
        booleans=("retained_risk", "servicing_retained", "repurchase_obligation"),
        nullable=("contract_evidence_ref",),
        enums={"recorded_treatment": ("sale", "borrowing")},
    ),
    "covenants": _spec(
        "covenant_id",
        ("metric_name",),
        decimals=("actual_value", "threshold_value", "headroom"),
        nullable=("contract_ref",),
        enums={"direction": ("min", "max")},
    ),
    "mandatory_payments": _spec(
        "payment_id",
        (),
        decimals=("amount_due", "amount_paid"),
        integers=("days_overdue",),
        nullable=("due_evidence_ref",),
        enums={"payment_type": ("tax", "payroll", "essential")},
    ),
    "period_end_events": _spec(
        "event_id",
        ("source_ref",),
        decimals=("inflow_amount", "outflow_amount"),
        integers=("days_from_period_end",),
        nullable=("related_event_ref",),
        enums={
            "event_type": (
                "ordinary",
                "temporary_deposit",
                "deposit_reversal",
                "supplier_payment_delay",
                "factoring",
                "one_off_collection",
                "tax_payroll_accrual",
            )
        },
    ),
    "forecasts": _spec(
        "forecast_id",
        ("source_ref",),
        decimals=(
            "forecast_amount",
            "actual_amount",
            "opening_available_cash",
            "mandatory_outflows",
            "scenario_inflows",
            "minimum_cash_required",
        ),
        integers=("horizon_days",),
    ),
    "liquidity_positions": _spec(
        "position_id",
        (),
        decimals=(
            "unrestricted_cash",
            "committed_undrawn_facilities",
            "mandatory_outflows",
            "scenario_inflows",
            "covenant_headroom",
            "stress_shortfall",
        ),
        integers=("runway_days", "minimum_runway_days"),
        nullable=("management_plan_evidence_ref", "going_concern_assessment_ref"),
    ),
}


def _digest(value: Mapping[str, Any], excluded: str | None = None) -> str:
    body = dict(value)
    if excluded is not None:
        body.pop(excluded, None)
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must be a non-empty string")
    return value


def _nullable_text(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


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
    if not number.is_finite():
        raise ContractError(f"{label} must be finite")
    return canonical_decimal(number)


def _records(value: Any, spec: Mapping[str, Any], label: str) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ContractError(f"{label} must be an array")
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise ContractError(f"{label}[{index}] must be an object")
        missing = sorted(spec["fields"] - set(raw))
        unknown = sorted(set(raw) - spec["fields"])
        if missing or unknown:
            raise ContractError(
                f"{label}[{index}] field mismatch; missing={missing}; unknown={unknown}"
            )
        item: dict[str, Any] = {}
        for field in sorted(spec["fields"]):
            field_label = f"{label}[{index}].{field}"
            if field in spec["decimals"]:
                item[field] = _decimal(raw[field], field_label)
            elif field in spec["integers"]:
                item[field] = _integer(raw[field], field_label)
            elif field in spec["booleans"]:
                if not isinstance(raw[field], bool):
                    raise ContractError(f"{field_label} must be a boolean")
                item[field] = raw[field]
            elif field in spec["nullable"]:
                item[field] = _nullable_text(raw[field], field_label)
            else:
                item[field] = _text(raw[field], field_label)
            if field in spec["enums"] and item[field] not in spec["enums"][field]:
                raise ContractError(f"{field_label} has an unsupported value")
        normalized.append(item)
    identifier = spec["identifier"]
    ids = [item[identifier] for item in normalized]
    if len(ids) != len(set(ids)):
        raise ContractError(f"{label} contains duplicate {identifier}")
    return sorted(
        normalized,
        key=lambda item: tuple(item[field] for field in _DIMENSIONS) + (item[identifier],),
    )


def _normalize_input(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError("Cash Flow procedure input must be an object")
    missing = sorted(_TOP_FIELDS - set(value))
    unknown = sorted(set(value) - _TOP_FIELDS)
    if missing or unknown:
        raise ContractError(
            f"Cash Flow input field mismatch; missing={missing}; unknown={unknown}"
        )
    result: dict[str, Any] = {
        "run_id": _text(value["run_id"], "run_id"),
        "revision": _integer(value["revision"], "revision"),
        "as_of_date": _text(value["as_of_date"], "as_of_date"),
    }
    for name, spec in _RECORD_SPECS.items():
        result[name] = _records(value[name], spec, name)

    programs = {item["program_id"]: item for item in result["supplier_finance_programs"]}
    for payable in result["payables"]:
        program_id = payable["supplier_finance_program_id"]
        if program_id is None:
            continue
        program = programs.get(program_id)
        if program is None:
            raise ContractError("payable references unknown supplier finance program")
        if any(payable[field] != program[field] for field in _DIMENSIONS):
            raise ContractError("payable and supplier finance program dimensions differ")

    events = {item["event_id"]: item for item in result["period_end_events"]}
    for event in result["period_end_events"]:
        related = event["related_event_ref"]
        if related is not None and related in events:
            if any(event[field] != events[related][field] for field in _DIMENSIONS):
                raise ContractError("related period-end event dimensions differ")
    return result


def _d(item: Mapping[str, Any], field: str) -> Decimal:
    return Decimal(item[field])


def _evidence(*refs: str | None) -> list[str]:
    return sorted({ref for ref in refs if ref is not None})


def _outcome(
    code: str,
    scope_ref: str,
    *,
    record: Mapping[str, Any] | None = None,
    observed: str | Decimal | None = None,
    expected: str | Decimal | None = None,
    difference: str | Decimal | None = None,
    disposition: str = "exception",
    evidence_refs: Sequence[str] = (),
) -> dict[str, Any]:
    def render(value: str | Decimal | None) -> str | None:
        return canonical_decimal(value) if isinstance(value, Decimal) else value

    return {
        "code": code,
        "scope_ref": scope_ref,
        "entity": record["entity"] if record is not None else None,
        "currency": record["currency"] if record is not None else None,
        "period": record["period"] if record is not None else None,
        "observed": render(observed),
        "expected": render(expected),
        "difference": render(difference),
        "disposition": disposition,
        "evidence_refs": sorted(set(evidence_refs)),
    }


def _trigger(
    issue_id: str,
    target_domain: str,
    scope_ref: str,
    reason_code: str,
    evidence_refs: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "trigger_id": f"{issue_id}:{target_domain}:{scope_ref}:{reason_code}",
        "issue_family_id": issue_id,
        "target_domain": target_domain,
        "scope_ref": scope_ref,
        "reason_code": reason_code,
        "disposition": "expert_review_required",
        "evidence_refs": sorted(set(evidence_refs)),
    }


def _scope_id(item: Mapping[str, Any], identifier: str) -> str:
    return "/".join(str(item[field]) for field in (*_DIMENSIONS, identifier))


def _missing() -> list[dict[str, Any]]:
    return [
        _outcome(
            "required_population_missing",
            "population",
            disposition="not_assessable",
        )
    ]


def _cf01(data: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = data["bank_reconciliations"]
    if not records:
        return _missing(), []
    outcomes = []
    for item in records:
        adjusted = (
            _d(item, "bank_balance")
            + _d(item, "deposits_in_transit")
            - _d(item, "outstanding_payments")
            + _d(item, "verified_reconciling_items")
        )
        difference = adjusted - _d(item, "cash_gl_balance")
        if difference:
            outcomes.append(_outcome(
                "bank_gl_unexplained_difference",
                _scope_id(item, "reconciliation_id"),
                record=item,
                observed=_d(item, "cash_gl_balance"),
                expected=adjusted,
                difference=difference,
                evidence_refs=_evidence(item["bank_source_ref"], item["gl_source_ref"]),
            ))
    return outcomes, []


def _cf02(data: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = data["cash_items"]
    if not records:
        return _missing(), []
    outcomes, triggers = [], []
    for item in records:
        scope = _scope_id(item, "cash_item_id")
        if item["restricted"]:
            expected = "restricted_cash"
            if item["restriction_evidence_ref"] is None:
                outcomes.append(_outcome(
                    "restriction_evidence_missing",
                    scope,
                    record=item,
                    disposition="not_assessable",
                ))
                triggers.append(_trigger("CF-02", "accounting", scope, "restriction_terms_require_review"))
        elif item["instrument_type"] == "demand_deposit":
            expected = "cash"
        elif (
            item["instrument_type"] == "term_deposit"
            and item["maturity_days"] <= 90
            and item["readily_convertible"]
            and item["value_change_risk"] == "insignificant"
        ):
            expected = "cash_equivalent"
        else:
            expected = "other"
        if item["recorded_classification"] != expected:
            outcomes.append(_outcome(
                "cash_classification_difference",
                scope,
                record=item,
                observed=item["recorded_classification"],
                expected=expected,
                evidence_refs=_evidence(item["restriction_evidence_ref"]),
            ))
    return outcomes, triggers


def _cf03(data: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = data["cash_transactions"]
    if not records:
        return _missing(), []
    outcomes = []
    for item in records:
        scope = _scope_id(item, "transaction_id")
        if item["original_event_ref"] is None:
            outcomes.append(_outcome(
                "original_economic_event_missing",
                scope,
                record=item,
                disposition="not_assessable",
                evidence_refs=_evidence(item["source_ref"]),
            ))
        elif item["reported_classification"] != item["expected_classification"]:
            outcomes.append(_outcome(
                "cashflow_classification_difference",
                scope,
                record=item,
                observed=item["reported_classification"],
                expected=item["expected_classification"],
                evidence_refs=_evidence(item["source_ref"], item["original_event_ref"]),
            ))
    return outcomes, []


def _cf04(data: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = data["cash_transactions"]
    if not records:
        return _missing(), []
    outcomes = []
    for item in records:
        scope = _scope_id(item, "transaction_id")
        evidence = _evidence(item["source_ref"], item["original_event_ref"])
        if not item["is_cash"] and item["reported_in_cashflow"]:
            outcomes.append(_outcome(
                "noncash_transaction_included",
                scope,
                record=item,
                observed="included",
                expected="excluded",
                evidence_refs=evidence,
            ))
        elif item["is_cash"] and not item["reported_in_cashflow"]:
            outcomes.append(_outcome(
                "cash_transaction_omitted",
                scope,
                record=item,
                observed="excluded",
                expected="included",
                evidence_refs=evidence,
            ))
    return outcomes, []


def _cf05(data: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = data["financing_bridges"]
    if not records:
        return _missing(), []
    outcomes = []
    for item in records:
        expected = (
            _d(item, "opening_liability")
            + _d(item, "cash_proceeds")
            - _d(item, "cash_repayments")
            + _d(item, "noncash_changes")
            + _d(item, "fx_changes")
            + _d(item, "other_changes")
        )
        difference = _d(item, "closing_liability") - expected
        if difference:
            outcomes.append(_outcome(
                "financing_bridge_difference",
                _scope_id(item, "bridge_id"),
                record=item,
                observed=_d(item, "closing_liability"),
                expected=expected,
                difference=difference,
                evidence_refs=_evidence(item["source_ref"]),
            ))
    return outcomes, []


def _cf06(data: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = data["supplier_finance_programs"]
    if not records:
        return _missing(), []
    outcomes, triggers = [], []
    for item in records:
        scope = _scope_id(item, "program_id")
        is_program = (
            _d(item, "amount") > 0
            or item["financial_institution_pays_supplier"]
            or item["actual_term_days"] > item["standard_term_days"]
        )
        if not is_program:
            continue
        if item["contract_ref"] is None:
            outcomes.append(_outcome(
                "supplier_finance_contract_missing",
                scope,
                record=item,
                disposition="not_assessable",
            ))
            triggers.append(_trigger("CF-06", "legal", scope, "supplier_finance_terms_require_review"))
        if item["disclosure_ref"] is None:
            outcomes.append(_outcome(
                "supplier_finance_disclosure_missing",
                scope,
                record=item,
                evidence_refs=_evidence(item["contract_ref"]),
            ))
            triggers.append(_trigger("CF-06", "accounting", scope, "supplier_finance_disclosure_review"))
        if item["recorded_classification"] == "ap" and (
            item["financial_institution_pays_supplier"]
            or item["actual_term_days"] > item["standard_term_days"]
        ):
            evidence = _evidence(item["contract_ref"], item["disclosure_ref"])
            outcomes.append(_outcome(
                "supplier_finance_classification_candidate",
                scope,
                record=item,
                observed="ap",
                expected="expert_review_required",
                disposition="expert_review_required",
                evidence_refs=evidence,
            ))
            triggers.append(_trigger(
                "CF-06",
                "accounting",
                scope,
                "supplier_finance_classification_review",
                evidence,
            ))
    return outcomes, triggers


def _cf07(data: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = data["receivables"]
    if not records:
        return _missing(), []
    outcomes = []
    for item in records:
        unresolved = (
            _d(item, "outstanding_amount")
            - _d(item, "subsequent_collections")
            - _d(item, "credit_notes")
            - _d(item, "disputes")
            - _d(item, "write_offs")
        )
        if item["aging_days"] >= 90 and unresolved > _d(item, "expected_credit_loss"):
            outcomes.append(_outcome(
                "collection_deterioration",
                _scope_id(item, "invoice_id"),
                record=item,
                observed=unresolved,
                expected=_d(item, "expected_credit_loss"),
                difference=unresolved - _d(item, "expected_credit_loss"),
                evidence_refs=_evidence(item["source_ref"]),
            ))
    return outcomes, []


def _cf08(data: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = data["payables"]
    if not records:
        return _missing(), []
    outcomes = []
    for item in records:
        scope = _scope_id(item, "payable_id")
        if item["days_overdue"] > 0 and _d(item, "outstanding_amount") > 0:
            outcomes.append(_outcome(
                "overdue_payable",
                scope,
                record=item,
                observed=_d(item, "outstanding_amount"),
                expected=Decimal(0),
                difference=_d(item, "outstanding_amount"),
                evidence_refs=_evidence(item["source_ref"]),
            ))
        if item["actual_term_days"] > item["standard_term_days"] and not item["disputed"]:
            outcomes.append(_outcome(
                "payment_term_stretch",
                scope,
                record=item,
                observed=str(item["actual_term_days"]),
                expected=str(item["standard_term_days"]),
                difference=str(item["actual_term_days"] - item["standard_term_days"]),
                evidence_refs=_evidence(item["source_ref"]),
            ))
    return outcomes, []


def _cf09(data: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = data["profit_cash_bridges"]
    if not records:
        return _missing(), []
    outcomes = []
    components = (
        "operating_result",
        "noncash_expense",
        "ar_change",
        "contract_balance_change",
        "ap_change",
        "payroll_tax_change",
        "provision_change",
        "deferred_change",
        "other_working_capital_change",
        "operating_adjustments",
    )
    for item in records:
        expected = sum((_d(item, name) for name in components), Decimal(0)) - _d(
            item, "noncash_income"
        )
        difference = _d(item, "reported_operating_cash_flow") - expected
        if difference:
            outcomes.append(_outcome(
                "profit_to_cash_bridge_difference",
                _scope_id(item, "bridge_id"),
                record=item,
                observed=_d(item, "reported_operating_cash_flow"),
                expected=expected,
                difference=difference,
                evidence_refs=_evidence(item["source_ref"]),
            ))
    return outcomes, []


def _cf10(data: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = data["counterparty_exposures"]
    if not records:
        return _missing(), []
    outcomes = []
    for item in records:
        total = _d(item, "total_population_amount")
        scope = _scope_id(item, "exposure_id")
        if total <= 0:
            outcomes.append(_outcome(
                "concentration_population_invalid",
                scope,
                record=item,
                observed=total,
                disposition="not_assessable",
                evidence_refs=_evidence(item["source_ref"]),
            ))
            continue
        ratio = _d(item, "exposure_amount") / total
        if ratio >= Decimal("0.20"):
            outcomes.append(_outcome(
                "counterparty_concentration",
                scope,
                record=item,
                observed=ratio,
                expected=Decimal("0.20"),
                difference=ratio - Decimal("0.20"),
                evidence_refs=_evidence(item["source_ref"]),
            ))
    return outcomes, []


def _cf11(data: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = data["receivable_transfers"]
    if not records:
        return _missing(), []
    outcomes, triggers = [], []
    for item in records:
        scope = _scope_id(item, "transfer_id")
        if item["contract_evidence_ref"] is None:
            outcomes.append(_outcome(
                "transfer_contract_missing",
                scope,
                record=item,
                disposition="not_assessable",
            ))
            triggers.append(_trigger("CF-11", "legal", scope, "derecognition_terms_require_review"))
        risk_retained = (
            _d(item, "recourse_amount") > 0
            or item["retained_risk"]
            or item["repurchase_obligation"]
        )
        if item["recorded_treatment"] == "sale" and risk_retained:
            outcomes.append(_outcome(
                "receivable_transfer_treatment_candidate",
                scope,
                record=item,
                observed="sale",
                expected="expert_review_required",
                disposition="expert_review_required",
                evidence_refs=_evidence(item["contract_evidence_ref"]),
            ))
            triggers.append(_trigger(
                "CF-11",
                "accounting",
                scope,
                "derecognition_and_recourse_review",
                _evidence(item["contract_evidence_ref"]),
            ))
    return outcomes, triggers


def _cf12(data: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = data["covenants"]
    if not records:
        return _missing(), []
    outcomes, triggers = [], []
    for item in records:
        scope = _scope_id(item, "covenant_id")
        if item["contract_ref"] is None:
            outcomes.append(_outcome(
                "covenant_contract_missing",
                scope,
                record=item,
                disposition="not_assessable",
            ))
            triggers.append(_trigger("CF-12", "legal", scope, "covenant_terms_require_review"))
        actual, threshold = _d(item, "actual_value"), _d(item, "threshold_value")
        breached = (
            item["direction"] == "min" and actual < threshold
        ) or (
            item["direction"] == "max" and actual > threshold
        )
        if breached:
            outcomes.append(_outcome(
                "covenant_breach_trigger",
                scope,
                record=item,
                observed=actual,
                expected=threshold,
                difference=_d(item, "headroom"),
                disposition="expert_review_required",
                evidence_refs=_evidence(item["contract_ref"]),
            ))
            triggers.append(_trigger(
                "CF-12",
                "accounting",
                scope,
                "covenant_classification_review",
                _evidence(item["contract_ref"]),
            ))
    return outcomes, triggers


def _cf13(data: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = data["mandatory_payments"]
    if not records:
        return _missing(), []
    outcomes, triggers = [], []
    domain = {"tax": "tax", "payroll": "labor", "essential": "legal"}
    for item in records:
        scope = _scope_id(item, "payment_id")
        unpaid = _d(item, "amount_due") - _d(item, "amount_paid")
        if item["due_evidence_ref"] is None:
            outcomes.append(_outcome(
                "mandatory_payment_evidence_missing",
                scope,
                record=item,
                disposition="not_assessable",
            ))
            triggers.append(_trigger(
                "CF-13",
                domain[item["payment_type"]],
                scope,
                "payment_obligation_requires_review",
            ))
        if item["days_overdue"] > 0 and unpaid > 0:
            outcomes.append(_outcome(
                "mandatory_payment_overdue",
                scope,
                record=item,
                observed=unpaid,
                expected=Decimal(0),
                difference=unpaid,
                disposition="expert_review_required",
                evidence_refs=_evidence(item["due_evidence_ref"]),
            ))
            triggers.append(_trigger(
                "CF-13",
                domain[item["payment_type"]],
                scope,
                "overdue_mandatory_payment",
                _evidence(item["due_evidence_ref"]),
            ))
    return outcomes, triggers


def _cf14(data: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = data["period_end_events"]
    if not records:
        return _missing(), []
    outcomes = []
    for item in records:
        if item["event_type"] == "ordinary":
            continue
        scope = _scope_id(item, "event_id")
        if (
            item["event_type"] in {"temporary_deposit", "deposit_reversal"}
            and item["related_event_ref"] is None
        ):
            outcomes.append(_outcome(
                "period_end_reversal_link_missing",
                scope,
                record=item,
                disposition="not_assessable",
                evidence_refs=_evidence(item["source_ref"]),
            ))
        else:
            outcomes.append(_outcome(
                "period_end_window_pattern",
                scope,
                record=item,
                observed=item["event_type"],
                expected="ordinary",
                evidence_refs=_evidence(item["source_ref"], item["related_event_ref"]),
            ))
    return outcomes, []


def _cf15(data: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = data["forecasts"]
    if not records:
        return _missing(), []
    outcomes = []
    for item in records:
        scope = _scope_id(item, "forecast_id")
        forecast_error = _d(item, "forecast_amount") - _d(item, "actual_amount")
        if forecast_error > 0:
            outcomes.append(_outcome(
                "forecast_optimism_bias",
                scope,
                record=item,
                observed=_d(item, "forecast_amount"),
                expected=_d(item, "actual_amount"),
                difference=forecast_error,
                evidence_refs=_evidence(item["source_ref"]),
            ))
        available = (
            _d(item, "opening_available_cash")
            + _d(item, "scenario_inflows")
            - _d(item, "mandatory_outflows")
        )
        if available < _d(item, "minimum_cash_required"):
            outcomes.append(_outcome(
                "forecast_runway_shortfall",
                scope,
                record=item,
                observed=available,
                expected=_d(item, "minimum_cash_required"),
                difference=available - _d(item, "minimum_cash_required"),
                evidence_refs=_evidence(item["source_ref"]),
            ))
    return outcomes, []


def _cf16(data: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = data["liquidity_positions"]
    if not records:
        return _missing(), []
    outcomes, triggers = [], []
    for item in records:
        stressed = (
            item["runway_days"] < item["minimum_runway_days"]
            or _d(item, "stress_shortfall") > 0
            or _d(item, "covenant_headroom") < 0
        )
        if not stressed:
            continue
        scope = _scope_id(item, "position_id")
        evidence = _evidence(
            item["management_plan_evidence_ref"],
            item["going_concern_assessment_ref"],
        )
        outcomes.append(_outcome(
            "going_concern_trigger",
            scope,
            record=item,
            observed=str(item["runway_days"]),
            expected=str(item["minimum_runway_days"]),
            difference=_d(item, "stress_shortfall"),
            disposition="expert_review_required",
            evidence_refs=evidence,
        ))
        if (
            item["management_plan_evidence_ref"] is None
            or item["going_concern_assessment_ref"] is None
        ):
            outcomes.append(_outcome(
                "going_concern_evidence_missing",
                scope,
                record=item,
                disposition="not_assessable",
                evidence_refs=evidence,
            ))
        triggers.append(_trigger(
            "CF-16",
            "going_concern",
            scope,
            "liquidity_stress_requires_expert_assessment",
            evidence,
        ))
    return outcomes, triggers


_HANDLERS: Mapping[
    str,
    Callable[[Mapping[str, Any]], tuple[list[dict[str, Any]], list[dict[str, Any]]]],
] = {
    "CF-01": _cf01,
    "CF-02": _cf02,
    "CF-03": _cf03,
    "CF-04": _cf04,
    "CF-05": _cf05,
    "CF-06": _cf06,
    "CF-07": _cf07,
    "CF-08": _cf08,
    "CF-09": _cf09,
    "CF-10": _cf10,
    "CF-11": _cf11,
    "CF-12": _cf12,
    "CF-13": _cf13,
    "CF-14": _cf14,
    "CF-15": _cf15,
    "CF-16": _cf16,
}


def _procedure(
    issue_id: str,
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    if not outcomes:
        outcomes = [
            _outcome(
                "no_exception",
                "population",
                disposition="no_exception",
            )
        ]
    ordered = sorted(outcomes, key=canonical_bytes)
    dispositions = {item["disposition"] for item in ordered}
    if "not_assessable" in dispositions:
        status = "not_assessable"
    elif "expert_review_required" in dispositions:
        status = "expert_review_required"
    elif "exception" in dispositions:
        status = "exceptions_found"
    else:
        status = "passed"
    return {
        "issue_family_id": issue_id,
        "procedure_id": ISSUE_PROCEDURE_MAP[issue_id],
        "implementation_status": "implemented_deterministic",
        "status": status,
        "outcome_count": len(ordered),
        "outcomes": ordered,
    }


def run_cashflow_procedures(value: Mapping[str, Any]) -> dict[str, Any]:
    """Execute the closed CF-01..CF-16 pack on supplied evidence."""
    data = _normalize_input(value)
    procedure_results: list[dict[str, Any]] = []
    triggers: list[dict[str, Any]] = []
    for issue_id in _ISSUE_IDS:
        outcomes, issue_triggers = _HANDLERS[issue_id](data)
        procedure_results.append(_procedure(issue_id, outcomes))
        triggers.extend(issue_triggers)
    ordered_triggers = sorted(
        {canonical_bytes(item): item for item in triggers}.values(),
        key=canonical_bytes,
    )
    status_counts = dict(
        sorted(Counter(item["status"] for item in procedure_results).items())
    )
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": data["run_id"],
        "revision": data["revision"],
        "as_of_date": data["as_of_date"],
        "input_hash": _digest(data),
        "procedure_results": procedure_results,
        "procedure_status_counts": status_counts,
        "coverage_complete": all(
            item["status"] != "not_assessable" for item in procedure_results
        ),
        "cross_domain_triggers": ordered_triggers,
        "expert_review_required": bool(ordered_triggers),
        "authority_ceiling": "Boundary",
    }
    result = {**body, "content_hash": _digest(body)}
    _SCHEMA_STORE.validate("accounting-cashflow-procedure-result.schema.json", result)
    return result


def verify_cashflow_procedure_result(value: Mapping[str, Any]) -> dict[str, Any]:
    """Verify result shape, hashes, complete dispatch, and derived flags."""
    if not isinstance(value, Mapping):
        raise ContractError("Cash Flow procedure result must be an object")
    _SCHEMA_STORE.validate("accounting-cashflow-procedure-result.schema.json", value)
    if value["content_hash"] != _digest(value, "content_hash"):
        raise ContractError("Cash Flow result content hash mismatch")
    results = value["procedure_results"]
    if [item["issue_family_id"] for item in results] != list(_ISSUE_IDS):
        raise ContractError("Cash Flow result must contain CF-01 through CF-16 in order")
    for item in results:
        issue_id = item["issue_family_id"]
        if item["procedure_id"] != ISSUE_PROCEDURE_MAP[issue_id]:
            raise ContractError("Cash Flow procedure dispatch mismatch")
        if item["implementation_status"] != "implemented_deterministic":
            raise ContractError("Cash Flow procedure implementation status mismatch")
        if item["outcome_count"] != len(item["outcomes"]):
            raise ContractError("Cash Flow outcome count mismatch")
        dispositions = {outcome["disposition"] for outcome in item["outcomes"]}
        expected_status = (
            "not_assessable"
            if "not_assessable" in dispositions
            else "expert_review_required"
            if "expert_review_required" in dispositions
            else "exceptions_found"
            if "exception" in dispositions
            else "passed"
        )
        if item["status"] != expected_status:
            raise ContractError("Cash Flow procedure status mismatch")
    expected_counts = dict(sorted(Counter(item["status"] for item in results).items()))
    if value["procedure_status_counts"] != expected_counts:
        raise ContractError("Cash Flow procedure status counts mismatch")
    expected_coverage = all(item["status"] != "not_assessable" for item in results)
    if value["coverage_complete"] is not expected_coverage:
        raise ContractError("Cash Flow coverage flag mismatch")
    if value["expert_review_required"] is not bool(value["cross_domain_triggers"]):
        raise ContractError("Cash Flow expert review flag mismatch")
    if value["cross_domain_triggers"] != sorted(
        value["cross_domain_triggers"], key=canonical_bytes
    ):
        raise ContractError("Cash Flow cross-domain trigger order mismatch")
    return copy.deepcopy(dict(value))
