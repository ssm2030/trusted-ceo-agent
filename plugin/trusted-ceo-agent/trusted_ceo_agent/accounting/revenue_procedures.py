"""Deterministic Contract & Revenue procedures for RV-01 through RV-16.

The module materializes accounting procedure outcomes only.  It does not create
Facts, Signals, Findings, Grades, or Approvals, and its authority is permanently
bounded until an approved professional pack release raises that ceiling.
"""

from __future__ import annotations

import copy
import hashlib
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any

from trusted_ceo_agent.accounting.seeds import ISSUE_PROCEDURE_MAP
from trusted_ceo_agent.canonical import canonical_bytes, canonical_decimal
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError

_SCHEMA = "accounting-contract-revenue-result.schema.json"
_SCHEMA_STORE = SchemaStore()
_ISSUE_IDS = tuple(f"RV-{number:02d}" for number in range(1, 17))
_PROCEDURE_IDS = tuple(ISSUE_PROCEDURE_MAP[issue_id] for issue_id in _ISSUE_IDS)
_TOP_FIELDS = {
    "run_id",
    "revision",
    "period_start",
    "period_end",
    "contracts",
    "obligations",
    "events",
    "balances",
    "contract_costs",
    "credit_risks",
}
_CONTRACT_FIELDS = {
    "contract_id",
    "customer_id",
    "entity",
    "currency",
    "start_date",
    "end_date",
    "approved",
    "enforceable_rights",
    "collectability_evidence_ref",
    "fixed_consideration",
    "constrained_variable_consideration",
    "credits",
    "refunds",
    "approved_modifications",
    "recorded_transaction_price",
    "payment_due_date",
    "significant_financing_recorded",
    "discount_rate",
    "presentation",
    "controls_before_transfer",
    "inventory_risk",
    "price_discretion",
    "license_type",
    "side_agreement_ref",
    "cancelled_date",
    "tax_judgement_required",
    "legal_judgement_required",
}
_OBLIGATION_FIELDS = {
    "obligation_id",
    "contract_id",
    "promise_ref",
    "distinct",
    "standalone_selling_price",
    "allocated_price",
    "satisfaction_pattern",
    "progress_method",
    "eligible_to_date",
    "expected_total_eligible",
    "control_transfer_date",
    "acceptance_date",
    "recognized_revenue",
}
_EVENT_FIELDS = {
    "event_id",
    "contract_id",
    "obligation_id",
    "event_type",
    "event_date",
    "amount",
    "entity",
    "currency",
    "period",
    "source_ref",
}
_BALANCE_FIELDS = {
    "contract_id",
    "entity",
    "currency",
    "period",
    "accounts_receivable",
    "contract_asset",
    "contract_liability",
    "refund_liability",
}
_COST_FIELDS = {
    "cost_id",
    "contract_id",
    "cost_type",
    "amount",
    "incremental",
    "directly_related",
    "recoverable",
    "capitalized_amount",
    "source_ref",
}
_CREDIT_FIELDS = {
    "contract_id",
    "entity",
    "currency",
    "period",
    "aging_days",
    "outstanding_amount",
    "lifetime_loss_rate",
    "recorded_ecl",
    "credit_evidence_ref",
}
_EVENT_TYPES = {
    "contract",
    "modification",
    "promise",
    "performance",
    "acceptance",
    "revenue",
    "billing",
    "collection",
    "refund",
    "credit",
    "termination",
    "side_agreement",
}
_MONEY_QUANTUM = Decimal("0.01")


def _digest(value: Mapping[str, Any], excluded: str | None = None) -> str:
    body = dict(value)
    if excluded is not None:
        body.pop(excluded, None)
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def _closed(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} must be an object")
    unknown = sorted(set(value) - fields)
    missing = sorted(fields - set(value))
    if unknown or missing:
        raise ContractError(f"{label} field mismatch; missing={missing}; unknown={unknown}")
    return value


def _records(value: Any, fields: set[str], label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ContractError(f"{label} must be an array")
    return [_closed(item, fields, f"{label}[{index}]") for index, item in enumerate(value)]


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


def _decimal(value: Any, label: str, *, non_negative: bool = True) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{label} must be an exact decimal string")
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ContractError(f"{label} must be an exact decimal string") from error
    if not number.is_finite() or (non_negative and number < 0):
        raise ContractError(f"{label} must be finite and non-negative")
    return canonical_decimal(number)


def _date(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    text = _text(value, label)
    try:
        date.fromisoformat(text)
    except ValueError as error:
        raise ContractError(f"{label} must be an ISO date") from error
    return text


def _choice(value: Any, choices: set[str], label: str) -> str:
    text = _text(value, label)
    if text not in choices:
        raise ContractError(f"{label} must be one of {sorted(choices)}")
    return text


def _unique(records: Sequence[Mapping[str, Any]], key, label: str) -> None:
    seen: set[Any] = set()
    for record in records:
        identity = key(record)
        if identity in seen:
            raise ContractError(f"duplicate {label}: {identity}")
        seen.add(identity)


def _normalize_input(value: Mapping[str, Any]) -> dict[str, Any]:
    source = _closed(value, _TOP_FIELDS, "revenue input")
    run_id = _text(source["run_id"], "run_id")
    revision = _integer(source["revision"], "revision")
    period_start = _date(source["period_start"], "period_start")
    period_end = _date(source["period_end"], "period_end")
    assert period_start is not None and period_end is not None
    if period_start > period_end:
        raise ContractError("period_start must not be after period_end")

    contracts = []
    for index, raw in enumerate(_records(source["contracts"], _CONTRACT_FIELDS, "contracts")):
        label = f"contracts[{index}]"
        contract = {
            "contract_id": _text(raw["contract_id"], f"{label}.contract_id"),
            "customer_id": _text(raw["customer_id"], f"{label}.customer_id"),
            "entity": _text(raw["entity"], f"{label}.entity"),
            "currency": _text(raw["currency"], f"{label}.currency"),
            "start_date": _date(raw["start_date"], f"{label}.start_date"),
            "end_date": _date(raw["end_date"], f"{label}.end_date"),
            "approved": _boolean(raw["approved"], f"{label}.approved"),
            "enforceable_rights": _boolean(
                raw["enforceable_rights"], f"{label}.enforceable_rights"
            ),
            "collectability_evidence_ref": _nullable_text(
                raw["collectability_evidence_ref"],
                f"{label}.collectability_evidence_ref",
            ),
            "fixed_consideration": _decimal(
                raw["fixed_consideration"], f"{label}.fixed_consideration"
            ),
            "constrained_variable_consideration": _decimal(
                raw["constrained_variable_consideration"],
                f"{label}.constrained_variable_consideration",
            ),
            "credits": _decimal(raw["credits"], f"{label}.credits"),
            "refunds": _decimal(raw["refunds"], f"{label}.refunds"),
            "approved_modifications": _decimal(
                raw["approved_modifications"], f"{label}.approved_modifications"
            ),
            "recorded_transaction_price": _decimal(
                raw["recorded_transaction_price"],
                f"{label}.recorded_transaction_price",
            ),
            "payment_due_date": _date(
                raw["payment_due_date"], f"{label}.payment_due_date"
            ),
            "significant_financing_recorded": _decimal(
                raw["significant_financing_recorded"],
                f"{label}.significant_financing_recorded",
            ),
            "discount_rate": _decimal(raw["discount_rate"], f"{label}.discount_rate"),
            "presentation": _choice(
                raw["presentation"], {"gross", "net"}, f"{label}.presentation"
            ),
            "controls_before_transfer": _boolean(
                raw["controls_before_transfer"],
                f"{label}.controls_before_transfer",
            ),
            "inventory_risk": _boolean(raw["inventory_risk"], f"{label}.inventory_risk"),
            "price_discretion": _boolean(
                raw["price_discretion"], f"{label}.price_discretion"
            ),
            "license_type": _choice(
                raw["license_type"], {"none", "access", "use"}, f"{label}.license_type"
            ),
            "side_agreement_ref": _nullable_text(
                raw["side_agreement_ref"], f"{label}.side_agreement_ref"
            ),
            "cancelled_date": _date(
                raw["cancelled_date"], f"{label}.cancelled_date", nullable=True
            ),
            "tax_judgement_required": _boolean(
                raw["tax_judgement_required"], f"{label}.tax_judgement_required"
            ),
            "legal_judgement_required": _boolean(
                raw["legal_judgement_required"], f"{label}.legal_judgement_required"
            ),
        }
        assert contract["start_date"] is not None and contract["end_date"] is not None
        if contract["start_date"] > contract["end_date"]:
            raise ContractError(f"{label} start_date must not be after end_date")
        contracts.append(contract)
    contracts.sort(key=lambda item: item["contract_id"])
    _unique(contracts, lambda item: item["contract_id"], "contract_id")
    contract_by_id = {item["contract_id"]: item for item in contracts}

    obligations = []
    for index, raw in enumerate(
        _records(source["obligations"], _OBLIGATION_FIELDS, "obligations")
    ):
        label = f"obligations[{index}]"
        obligation = {
            "obligation_id": _text(raw["obligation_id"], f"{label}.obligation_id"),
            "contract_id": _text(raw["contract_id"], f"{label}.contract_id"),
            "promise_ref": _text(raw["promise_ref"], f"{label}.promise_ref"),
            "distinct": _boolean(raw["distinct"], f"{label}.distinct"),
            "standalone_selling_price": _decimal(
                raw["standalone_selling_price"],
                f"{label}.standalone_selling_price",
            ),
            "allocated_price": _decimal(
                raw["allocated_price"], f"{label}.allocated_price"
            ),
            "satisfaction_pattern": _choice(
                raw["satisfaction_pattern"],
                {"over_time", "point_in_time"},
                f"{label}.satisfaction_pattern",
            ),
            "progress_method": _choice(
                raw["progress_method"],
                {"none", "input", "output", "elapsed_time"},
                f"{label}.progress_method",
            ),
            "eligible_to_date": _decimal(
                raw["eligible_to_date"], f"{label}.eligible_to_date"
            ),
            "expected_total_eligible": _decimal(
                raw["expected_total_eligible"],
                f"{label}.expected_total_eligible",
            ),
            "control_transfer_date": _date(
                raw["control_transfer_date"],
                f"{label}.control_transfer_date",
                nullable=True,
            ),
            "acceptance_date": _date(
                raw["acceptance_date"], f"{label}.acceptance_date", nullable=True
            ),
            "recognized_revenue": _decimal(
                raw["recognized_revenue"], f"{label}.recognized_revenue"
            ),
        }
        if obligation["contract_id"] not in contract_by_id:
            raise ContractError(f"{label} references unknown contract")
        obligations.append(obligation)
    obligations.sort(key=lambda item: item["obligation_id"])
    _unique(obligations, lambda item: item["obligation_id"], "obligation_id")
    obligation_by_id = {item["obligation_id"]: item for item in obligations}

    events = []
    for index, raw in enumerate(_records(source["events"], _EVENT_FIELDS, "events")):
        label = f"events[{index}]"
        event = {
            "event_id": _text(raw["event_id"], f"{label}.event_id"),
            "contract_id": _text(raw["contract_id"], f"{label}.contract_id"),
            "obligation_id": _nullable_text(
                raw["obligation_id"], f"{label}.obligation_id"
            ),
            "event_type": _choice(raw["event_type"], _EVENT_TYPES, f"{label}.event_type"),
            "event_date": _date(raw["event_date"], f"{label}.event_date"),
            "amount": _decimal(raw["amount"], f"{label}.amount"),
            "entity": _text(raw["entity"], f"{label}.entity"),
            "currency": _text(raw["currency"], f"{label}.currency"),
            "period": _text(raw["period"], f"{label}.period"),
            "source_ref": _text(raw["source_ref"], f"{label}.source_ref"),
        }
        contract = contract_by_id.get(event["contract_id"])
        if contract is None:
            raise ContractError(f"{label} references unknown contract")
        if event["entity"] != contract["entity"]:
            raise ContractError(f"{label} entity does not match contract lineage")
        if (
            event["currency"] != contract["currency"]
            and event["event_type"] not in {"billing", "collection", "refund", "credit"}
        ):
            raise ContractError(f"{label} currency does not match contract lineage")
        obligation_id = event["obligation_id"]
        if obligation_id is not None:
            obligation = obligation_by_id.get(obligation_id)
            if obligation is None and obligation_by_id:
                raise ContractError(f"{label} obligation lineage mismatch")
            if obligation is not None and obligation["contract_id"] != event["contract_id"]:
                raise ContractError(f"{label} obligation lineage mismatch")
        events.append(event)
    events.sort(key=lambda item: (item["event_date"], item["event_id"]))
    _unique(events, lambda item: item["event_id"], "event_id")

    balances = []
    for index, raw in enumerate(_records(source["balances"], _BALANCE_FIELDS, "balances")):
        label = f"balances[{index}]"
        balance = {
            "contract_id": _text(raw["contract_id"], f"{label}.contract_id"),
            "entity": _text(raw["entity"], f"{label}.entity"),
            "currency": _text(raw["currency"], f"{label}.currency"),
            "period": _text(raw["period"], f"{label}.period"),
            "accounts_receivable": _decimal(
                raw["accounts_receivable"], f"{label}.accounts_receivable"
            ),
            "contract_asset": _decimal(
                raw["contract_asset"], f"{label}.contract_asset"
            ),
            "contract_liability": _decimal(
                raw["contract_liability"], f"{label}.contract_liability"
            ),
            "refund_liability": _decimal(
                raw["refund_liability"], f"{label}.refund_liability"
            ),
        }
        contract = contract_by_id.get(balance["contract_id"])
        if contract is None:
            raise ContractError(f"{label} references unknown contract")
        if (balance["entity"], balance["currency"]) != (
            contract["entity"],
            contract["currency"],
        ):
            raise ContractError(f"{label} entity/currency lineage mismatch")
        balances.append(balance)
    balances.sort(key=lambda item: (item["contract_id"], item["period"]))
    _unique(
        balances,
        lambda item: (item["contract_id"], item["entity"], item["currency"], item["period"]),
        "contract balance key",
    )

    costs = []
    for index, raw in enumerate(
        _records(source["contract_costs"], _COST_FIELDS, "contract_costs")
    ):
        label = f"contract_costs[{index}]"
        cost = {
            "cost_id": _text(raw["cost_id"], f"{label}.cost_id"),
            "contract_id": _text(raw["contract_id"], f"{label}.contract_id"),
            "cost_type": _choice(
                raw["cost_type"],
                {"acquisition", "fulfilment", "general", "training"},
                f"{label}.cost_type",
            ),
            "amount": _decimal(raw["amount"], f"{label}.amount"),
            "incremental": _boolean(raw["incremental"], f"{label}.incremental"),
            "directly_related": _boolean(
                raw["directly_related"], f"{label}.directly_related"
            ),
            "recoverable": _boolean(raw["recoverable"], f"{label}.recoverable"),
            "capitalized_amount": _decimal(
                raw["capitalized_amount"], f"{label}.capitalized_amount"
            ),
            "source_ref": _text(raw["source_ref"], f"{label}.source_ref"),
        }
        if cost["contract_id"] not in contract_by_id:
            raise ContractError(f"{label} references unknown contract")
        costs.append(cost)
    costs.sort(key=lambda item: item["cost_id"])
    _unique(costs, lambda item: item["cost_id"], "cost_id")

    credit_risks = []
    for index, raw in enumerate(
        _records(source["credit_risks"], _CREDIT_FIELDS, "credit_risks")
    ):
        label = f"credit_risks[{index}]"
        risk = {
            "contract_id": _text(raw["contract_id"], f"{label}.contract_id"),
            "entity": _text(raw["entity"], f"{label}.entity"),
            "currency": _text(raw["currency"], f"{label}.currency"),
            "period": _text(raw["period"], f"{label}.period"),
            "aging_days": _integer(raw["aging_days"], f"{label}.aging_days"),
            "outstanding_amount": _decimal(
                raw["outstanding_amount"], f"{label}.outstanding_amount"
            ),
            "lifetime_loss_rate": _decimal(
                raw["lifetime_loss_rate"], f"{label}.lifetime_loss_rate"
            ),
            "recorded_ecl": _decimal(raw["recorded_ecl"], f"{label}.recorded_ecl"),
            "credit_evidence_ref": _text(
                raw["credit_evidence_ref"], f"{label}.credit_evidence_ref"
            ),
        }
        contract = contract_by_id.get(risk["contract_id"])
        if contract is None:
            raise ContractError(f"{label} references unknown contract")
        if (risk["entity"], risk["currency"]) != (
            contract["entity"],
            contract["currency"],
        ):
            raise ContractError(f"{label} entity/currency lineage mismatch")
        if Decimal(risk["lifetime_loss_rate"]) > 1:
            raise ContractError(f"{label}.lifetime_loss_rate must not exceed 1")
        credit_risks.append(risk)
    credit_risks.sort(
        key=lambda item: (item["contract_id"], item["period"], item["aging_days"])
    )
    _unique(
        credit_risks,
        lambda item: (item["contract_id"], item["entity"], item["currency"], item["period"]),
        "credit risk key",
    )
    return {
        "run_id": run_id,
        "revision": revision,
        "period_start": period_start,
        "period_end": period_end,
        "contracts": contracts,
        "obligations": obligations,
        "events": events,
        "balances": balances,
        "contract_costs": costs,
        "credit_risks": credit_risks,
    }


def _money(value: str) -> Decimal:
    return Decimal(value)


def _rounded(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)


def _contract_period(contract: Mapping[str, Any]) -> str:
    return str(contract["end_date"])[:7]


def _transaction_price(contract: Mapping[str, Any]) -> Decimal:
    return (
        _money(contract["fixed_consideration"])
        + _money(contract["constrained_variable_consideration"])
        - _money(contract["credits"])
        - _money(contract["refunds"])
        + _money(contract["approved_modifications"])
    )


def _outcome(
    code: str,
    severity: str,
    scope_ref: str,
    *,
    entity: str | None = None,
    currency: str | None = None,
    period: str | None = None,
    observed: str | None = None,
    expected: str | None = None,
    difference: Decimal | str | None = None,
    source_refs: Sequence[str] = (),
    event_ids: Sequence[str] = (),
    expert_review_required: bool = False,
) -> dict[str, Any]:
    if isinstance(difference, Decimal):
        difference = canonical_decimal(difference)
    return {
        "code": code,
        "severity": severity,
        "scope_ref": scope_ref,
        "entity": entity,
        "currency": currency,
        "period": period,
        "observed": observed,
        "expected": expected,
        "difference": difference,
        "source_refs": sorted(set(source_refs)),
        "event_ids": sorted(set(event_ids)),
        "expert_review_required": expert_review_required,
    }


def _missing(code: str, population: str) -> dict[str, Any]:
    return _outcome(
        code,
        "missing_input",
        population,
        observed="missing",
        expected="closed typed population",
    )


def _status(outcomes: Sequence[Mapping[str, Any]]) -> str:
    severities = {item["severity"] for item in outcomes}
    if "missing_input" in severities:
        return "not_assessable"
    if severities & {"exception", "boundary"}:
        return "exceptions_found"
    return "passed"


def _procedure(
    issue_id: str,
    population_ids: Sequence[str],
    outcomes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    ordered = sorted(
        (copy.deepcopy(dict(item)) for item in outcomes),
        key=lambda item: (
            item["code"],
            item["scope_ref"],
            item["observed"] or "",
            item["expected"] or "",
            tuple(item["event_ids"]),
        ),
    )
    return {
        "issue_family_id": issue_id,
        "procedure_id": ISSUE_PROCEDURE_MAP[issue_id],
        "implementation_status": "implemented_deterministic",
        "status": _status(ordered),
        "population_ids": sorted(set(population_ids)),
        "outcomes": ordered,
    }


def _context(data: Mapping[str, Any]) -> dict[str, Any]:
    contracts = {item["contract_id"]: item for item in data["contracts"]}
    obligations = {item["obligation_id"]: item for item in data["obligations"]}
    obligations_by_contract: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    events_by_contract: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    events_by_obligation: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for obligation in data["obligations"]:
        obligations_by_contract[obligation["contract_id"]].append(obligation)
    for event in data["events"]:
        events_by_contract[event["contract_id"]].append(event)
        if event["obligation_id"] is not None:
            events_by_obligation[event["obligation_id"]].append(event)
    return {
        "data": data,
        "contracts": contracts,
        "obligations": obligations,
        "obligations_by_contract": obligations_by_contract,
        "events_by_contract": events_by_contract,
        "events_by_obligation": events_by_obligation,
    }


def _event_sum(
    context: Mapping[str, Any], contract_id: str, event_types: set[str]
) -> Decimal:
    return sum(
        (
            _money(event["amount"])
            for event in context["events_by_contract"].get(contract_id, ())
            if event["event_type"] in event_types
        ),
        Decimal(0),
    )


def _rv01(context: Mapping[str, Any]) -> dict[str, Any]:
    data = context["data"]
    contracts = data["contracts"]
    if not contracts or not data["events"]:
        return _procedure("RV-01", [], [_missing("contract_population_missing", "contracts")])
    outcomes: list[dict[str, Any]] = []
    for contract in contracts:
        events = context["events_by_contract"][contract["contract_id"]]
        contract_events = [item for item in events if item["event_type"] == "contract"]
        common = {
            "entity": contract["entity"],
            "currency": contract["currency"],
            "period": _contract_period(contract),
            "event_ids": [item["event_id"] for item in contract_events],
            "source_refs": [item["source_ref"] for item in contract_events],
        }
        if not contract_events:
            outcomes.append(
                _outcome(
                    "contract_event_missing",
                    "exception",
                    contract["contract_id"],
                    observed="0",
                    expected="1 or more",
                    **common,
                )
            )
        if not contract["approved"] or not contract["enforceable_rights"]:
            outcomes.append(
                _outcome(
                    "contract_approval_or_rights_missing",
                    "exception",
                    contract["contract_id"],
                    observed=f"approved={contract['approved']};rights={contract['enforceable_rights']}",
                    expected="approved=True;rights=True",
                    **common,
                )
            )
        if contract["collectability_evidence_ref"] is None:
            outcomes.append(
                _outcome(
                    "collectability_evidence_missing",
                    "exception",
                    contract["contract_id"],
                    observed="missing",
                    expected="evidence reference",
                    **common,
                )
            )
    if not outcomes:
        outcomes.append(
            _outcome(
                "contract_population_reconciled",
                "info",
                "contract_population",
                observed=str(len(contracts)),
                expected=str(len(contracts)),
                event_ids=[item["event_id"] for item in data["events"]],
                source_refs=[item["source_ref"] for item in data["events"]],
            )
        )
    return _procedure("RV-01", [item["contract_id"] for item in contracts], outcomes)


def _rv02(context: Mapping[str, Any]) -> dict[str, Any]:
    data = context["data"]
    if not data["contracts"] or not data["events"]:
        return _procedure(
            "RV-02", [], [_missing("contract_change_population_missing", "contracts/events")]
        )
    outcomes: list[dict[str, Any]] = []
    grouping: dict[tuple[str, str], list[str]] = defaultdict(list)
    for contract in data["contracts"]:
        grouping[(contract["customer_id"], contract["start_date"])].append(
            contract["contract_id"]
        )
        modifications = [
            event
            for event in context["events_by_contract"][contract["contract_id"]]
            if event["event_type"] == "modification"
        ]
        observed = sum((_money(item["amount"]) for item in modifications), Decimal(0))
        expected = _money(contract["approved_modifications"])
        if observed != expected:
            outcomes.append(
                _outcome(
                    "unapproved_modification",
                    "exception",
                    contract["contract_id"],
                    entity=contract["entity"],
                    currency=contract["currency"],
                    period=_contract_period(contract),
                    observed=canonical_decimal(observed),
                    expected=canonical_decimal(expected),
                    difference=observed - expected,
                    source_refs=[item["source_ref"] for item in modifications],
                    event_ids=[item["event_id"] for item in modifications],
                )
            )
    for (customer_id, start_date), contract_ids in sorted(grouping.items()):
        if len(contract_ids) > 1:
            outcomes.append(
                _outcome(
                    "contract_combination_candidate",
                    "exception",
                    customer_id,
                    period=start_date[:7],
                    observed=",".join(sorted(contract_ids)),
                    expected="documented combination assessment",
                )
            )
    if not outcomes:
        outcomes.append(
            _outcome(
                "contract_changes_reconciled",
                "info",
                "contract_change_population",
                observed=str(
                    sum(
                        1
                        for item in data["events"]
                        if item["event_type"] == "modification"
                    )
                ),
                expected="approved modification amount",
            )
        )
    return _procedure(
        "RV-02", [item["contract_id"] for item in data["contracts"]], outcomes
    )


def _rv03(context: Mapping[str, Any]) -> dict[str, Any]:
    data = context["data"]
    if not data["contracts"] or not data["obligations"] or not data["events"]:
        return _procedure(
            "RV-03", [], [_missing("promise_population_missing", "obligations/events")]
        )
    outcomes: list[dict[str, Any]] = []
    event_ids = {item["event_id"] for item in data["events"] if item["event_type"] == "promise"}
    for contract in data["contracts"]:
        if not context["obligations_by_contract"].get(contract["contract_id"]):
            outcomes.append(
                _outcome(
                    "contract_without_obligation",
                    "exception",
                    contract["contract_id"],
                    entity=contract["entity"],
                    currency=contract["currency"],
                    period=_contract_period(contract),
                    observed="0",
                    expected="1 or more",
                )
            )
    for obligation in data["obligations"]:
        contract = context["contracts"][obligation["contract_id"]]
        if obligation["promise_ref"] not in event_ids:
            outcomes.append(
                _outcome(
                    "promise_event_missing",
                    "exception",
                    obligation["obligation_id"],
                    entity=contract["entity"],
                    currency=contract["currency"],
                    period=_contract_period(contract),
                    observed=obligation["promise_ref"],
                    expected="promise event id",
                )
            )
        if not obligation["distinct"]:
            outcomes.append(
                _outcome(
                    "distinct_obligation_review",
                    "exception",
                    obligation["obligation_id"],
                    entity=contract["entity"],
                    currency=contract["currency"],
                    period=_contract_period(contract),
                    observed="distinct=False",
                    expected="documented distinct-benefit assessment",
                    event_ids=[obligation["promise_ref"]],
                )
            )
    if not outcomes:
        outcomes.append(
            _outcome(
                "promise_graph_reconciled",
                "info",
                "obligation_population",
                observed=str(len(data["obligations"])),
                expected=str(len(data["obligations"])),
                event_ids=sorted(event_ids),
            )
        )
    return _procedure(
        "RV-03", [item["obligation_id"] for item in data["obligations"]], outcomes
    )


def _rv04(context: Mapping[str, Any]) -> dict[str, Any]:
    contracts = context["data"]["contracts"]
    if not contracts:
        return _procedure(
            "RV-04", [], [_missing("pricing_population_missing", "contracts")]
        )
    outcomes: list[dict[str, Any]] = []
    for contract in contracts:
        expected = _transaction_price(contract)
        observed = _money(contract["recorded_transaction_price"])
        if observed != expected:
            outcomes.append(
                _outcome(
                    "transaction_price_difference",
                    "exception",
                    contract["contract_id"],
                    entity=contract["entity"],
                    currency=contract["currency"],
                    period=_contract_period(contract),
                    observed=canonical_decimal(observed),
                    expected=canonical_decimal(expected),
                    difference=observed - expected,
                    source_refs=(
                        [contract["collectability_evidence_ref"]]
                        if contract["collectability_evidence_ref"]
                        else []
                    ),
                )
            )
    if not outcomes:
        outcomes.append(
            _outcome(
                "price_waterfall_reperformed",
                "info",
                "pricing_population",
                observed=canonical_decimal(sum((_transaction_price(item) for item in contracts), Decimal(0))),
                expected="fixed+constrained_variable-credits-refunds+approved_modifications",
            )
        )
    return _procedure("RV-04", [item["contract_id"] for item in contracts], outcomes)


def _rv05(context: Mapping[str, Any]) -> dict[str, Any]:
    obligations = context["data"]["obligations"]
    if not obligations:
        return _procedure(
            "RV-05", [], [_missing("ssp_population_missing", "obligations")]
        )
    outcomes: list[dict[str, Any]] = []
    for contract_id, population in sorted(context["obligations_by_contract"].items()):
        contract = context["contracts"][contract_id]
        total_ssp = sum(
            (_money(item["standalone_selling_price"]) for item in population), Decimal(0)
        )
        if total_ssp <= 0:
            outcomes.append(
                _outcome(
                    "ssp_basis_missing",
                    "exception",
                    contract_id,
                    entity=contract["entity"],
                    currency=contract["currency"],
                    period=_contract_period(contract),
                    observed=canonical_decimal(total_ssp),
                    expected="positive total SSP",
                )
            )
            continue
        transaction_price = _transaction_price(contract)
        for obligation in population:
            expected = _rounded(
                transaction_price
                * _money(obligation["standalone_selling_price"])
                / total_ssp
            )
            observed = _money(obligation["allocated_price"])
            if observed != expected:
                outcomes.append(
                    _outcome(
                        "ssp_allocation_difference",
                        "exception",
                        obligation["obligation_id"],
                        entity=contract["entity"],
                        currency=contract["currency"],
                        period=_contract_period(contract),
                        observed=canonical_decimal(observed),
                        expected=canonical_decimal(expected),
                        difference=observed - expected,
                        event_ids=[obligation["promise_ref"]],
                    )
                )
    if not outcomes:
        outcomes.append(
            _outcome(
                "ssp_allocation_reperformed",
                "info",
                "obligation_population",
                observed=str(len(obligations)),
                expected="relative SSP allocation",
                event_ids=[item["promise_ref"] for item in obligations],
            )
        )
    return _procedure(
        "RV-05", [item["obligation_id"] for item in obligations], outcomes
    )


def _rv06(context: Mapping[str, Any]) -> dict[str, Any]:
    obligations = context["data"]["obligations"]
    events = context["data"]["events"]
    if not obligations or not events:
        return _procedure(
            "RV-06", [], [_missing("satisfaction_population_missing", "obligations/events")]
        )
    outcomes: list[dict[str, Any]] = []
    for obligation in obligations:
        contract = context["contracts"][obligation["contract_id"]]
        obligation_events = context["events_by_obligation"].get(obligation["obligation_id"], [])
        if obligation["satisfaction_pattern"] == "over_time":
            performance = [
                item for item in obligation_events if item["event_type"] == "performance"
            ]
            if obligation["progress_method"] == "none" or not performance:
                outcomes.append(
                    _outcome(
                        "over_time_satisfaction_evidence_missing",
                        "exception",
                        obligation["obligation_id"],
                        entity=contract["entity"],
                        currency=contract["currency"],
                        period=_contract_period(contract),
                        observed=obligation["progress_method"],
                        expected="progress method and performance event",
                        event_ids=[item["event_id"] for item in performance],
                        source_refs=[item["source_ref"] for item in performance],
                    )
                )
        elif (
            obligation["control_transfer_date"] is None
            or obligation["acceptance_date"] is None
        ):
            outcomes.append(
                _outcome(
                    "point_in_time_satisfaction_evidence_missing",
                    "exception",
                    obligation["obligation_id"],
                    entity=contract["entity"],
                    currency=contract["currency"],
                    period=_contract_period(contract),
                    observed="missing control transfer or acceptance date",
                    expected="both dated evidence fields",
                )
            )
    if not outcomes:
        outcomes.append(
            _outcome(
                "satisfaction_patterns_tested",
                "info",
                "obligation_population",
                observed=str(len(obligations)),
                expected="pattern-specific satisfaction evidence",
            )
        )
    return _procedure(
        "RV-06", [item["obligation_id"] for item in obligations], outcomes
    )


def _rv07(context: Mapping[str, Any]) -> dict[str, Any]:
    obligations = context["data"]["obligations"]
    if not obligations:
        return _procedure(
            "RV-07", [], [_missing("progress_population_missing", "obligations")]
        )
    over_time = [item for item in obligations if item["satisfaction_pattern"] == "over_time"]
    outcomes: list[dict[str, Any]] = []
    for obligation in over_time:
        contract = context["contracts"][obligation["contract_id"]]
        total = _money(obligation["expected_total_eligible"])
        to_date = _money(obligation["eligible_to_date"])
        if total <= 0 or to_date > total:
            outcomes.append(
                _outcome(
                    "progress_denominator_invalid",
                    "exception",
                    obligation["obligation_id"],
                    entity=contract["entity"],
                    currency=contract["currency"],
                    period=_contract_period(contract),
                    observed=f"{canonical_decimal(to_date)}/{canonical_decimal(total)}",
                    expected="0 <= eligible_to_date <= positive expected_total",
                    event_ids=[obligation["promise_ref"]],
                )
            )
            continue
        expected = _rounded(_money(obligation["allocated_price"]) * to_date / total)
        observed = _money(obligation["recognized_revenue"])
        if observed != expected:
            outcomes.append(
                _outcome(
                    "progress_reperformance_difference",
                    "exception",
                    obligation["obligation_id"],
                    entity=contract["entity"],
                    currency=contract["currency"],
                    period=_contract_period(contract),
                    observed=canonical_decimal(observed),
                    expected=canonical_decimal(expected),
                    difference=observed - expected,
                    event_ids=[obligation["promise_ref"]],
                )
            )
    if not outcomes:
        outcomes.append(
            _outcome(
                "progress_reperformed",
                "info",
                "over_time_obligation_population",
                observed=str(len(over_time)),
                expected="eligible_to_date/expected_total_eligible",
            )
        )
    return _procedure(
        "RV-07", [item["obligation_id"] for item in over_time], outcomes
    )


def _rv08(context: Mapping[str, Any]) -> dict[str, Any]:
    data = context["data"]
    if not data["events"] or not data["obligations"]:
        return _procedure(
            "RV-08", [], [_missing("cutoff_population_missing", "events/obligations")]
        )
    outcomes: list[dict[str, Any]] = []
    for event in data["events"]:
        if event["period"] != event["event_date"][:7]:
            outcomes.append(
                _outcome(
                    "event_period_mismatch",
                    "exception",
                    event["event_id"],
                    entity=event["entity"],
                    currency=event["currency"],
                    period=event["period"],
                    observed=event["event_date"][:7],
                    expected=event["period"],
                    source_refs=[event["source_ref"]],
                    event_ids=[event["event_id"]],
                )
            )
        if event["event_type"] != "revenue":
            continue
        obligation_id = event["obligation_id"]
        if obligation_id is None:
            outcomes.append(
                _outcome(
                    "revenue_obligation_lineage_missing",
                    "exception",
                    event["event_id"],
                    entity=event["entity"],
                    currency=event["currency"],
                    period=event["period"],
                    observed="missing",
                    expected="obligation_id",
                    source_refs=[event["source_ref"]],
                    event_ids=[event["event_id"]],
                )
            )
            continue
        obligation = context["obligations"][obligation_id]
        satisfaction_date: str | None
        if obligation["satisfaction_pattern"] == "point_in_time":
            dates = [
                item
                for item in (
                    obligation["control_transfer_date"],
                    obligation["acceptance_date"],
                )
                if item is not None
            ]
            satisfaction_date = max(dates) if len(dates) == 2 else None
        else:
            performance_dates = [
                item["event_date"]
                for item in context["events_by_obligation"].get(obligation_id, [])
                if item["event_type"] == "performance"
            ]
            satisfaction_date = min(performance_dates) if performance_dates else None
        if satisfaction_date is None or event["event_date"] < satisfaction_date:
            outcomes.append(
                _outcome(
                    "revenue_before_satisfaction",
                    "exception",
                    event["event_id"],
                    entity=event["entity"],
                    currency=event["currency"],
                    period=event["period"],
                    observed=event["event_date"],
                    expected=satisfaction_date or "dated satisfaction evidence",
                    source_refs=[event["source_ref"]],
                    event_ids=[event["event_id"]],
                )
            )
    if not outcomes:
        outcomes.append(
            _outcome(
                "population_cutoff_aligned",
                "info",
                "revenue_event_population",
                observed=str(sum(1 for item in data["events"] if item["event_type"] == "revenue")),
                expected="event date, period, and satisfaction alignment",
                event_ids=[item["event_id"] for item in data["events"]],
                source_refs=[item["source_ref"] for item in data["events"]],
            )
        )
    return _procedure(
        "RV-08", [item["event_id"] for item in data["events"]], outcomes
    )


def _rv09(context: Mapping[str, Any]) -> dict[str, Any]:
    contracts = context["data"]["contracts"]
    if not contracts:
        return _procedure(
            "RV-09", [], [_missing("principal_agent_population_missing", "contracts")]
        )
    outcomes: list[dict[str, Any]] = []
    for contract in contracts:
        indicator_count = sum(
            1
            for value in (
                contract["controls_before_transfer"],
                contract["inventory_risk"],
                contract["price_discretion"],
            )
            if value
        )
        expected = "gross" if indicator_count >= 2 else "net"
        if contract["presentation"] != expected:
            outcomes.append(
                _outcome(
                    "principal_agent_presentation_difference",
                    "exception",
                    contract["contract_id"],
                    entity=contract["entity"],
                    currency=contract["currency"],
                    period=_contract_period(contract),
                    observed=contract["presentation"],
                    expected=expected,
                    difference=str(indicator_count),
                )
            )
    if not outcomes:
        outcomes.append(
            _outcome(
                "principal_agent_indicators_tested",
                "info",
                "contract_population",
                observed=str(len(contracts)),
                expected="control, inventory risk, and price discretion indicators",
            )
        )
    return _procedure("RV-09", [item["contract_id"] for item in contracts], outcomes)


def _rv10(context: Mapping[str, Any]) -> dict[str, Any]:
    contracts = context["data"]["contracts"]
    obligations = context["data"]["obligations"]
    if not contracts or not obligations:
        return _procedure(
            "RV-10", [], [_missing("license_population_missing", "contracts/obligations")]
        )
    outcomes: list[dict[str, Any]] = []
    license_count = 0
    for contract in contracts:
        license_type = contract["license_type"]
        if license_type == "none":
            continue
        license_count += 1
        expected = "over_time" if license_type == "access" else "point_in_time"
        for obligation in context["obligations_by_contract"].get(contract["contract_id"], []):
            if obligation["satisfaction_pattern"] != expected:
                outcomes.append(
                    _outcome(
                        "license_pattern_difference",
                        "exception",
                        obligation["obligation_id"],
                        entity=contract["entity"],
                        currency=contract["currency"],
                        period=_contract_period(contract),
                        observed=obligation["satisfaction_pattern"],
                        expected=expected,
                        event_ids=[obligation["promise_ref"]],
                    )
                )
    if not outcomes:
        outcomes.append(
            _outcome(
                "license_right_pattern_tested",
                "info",
                "license_contract_population",
                observed=str(license_count),
                expected="access=over_time;use=point_in_time",
            )
        )
    return _procedure("RV-10", [item["contract_id"] for item in contracts], outcomes)


def _rv11(context: Mapping[str, Any]) -> dict[str, Any]:
    data = context["data"]
    if not data["events"] or not data["balances"]:
        return _procedure(
            "RV-11", [], [_missing("contract_balance_population_missing", "events/balances")]
        )
    outcomes: list[dict[str, Any]] = []
    for balance in data["balances"]:
        contract_id = balance["contract_id"]
        revenue = _event_sum(context, contract_id, {"revenue"})
        billing = _event_sum(context, contract_id, {"billing"})
        collections = _event_sum(context, contract_id, {"collection"})
        credits = _event_sum(context, contract_id, {"credit", "refund"})
        expected = {
            "accounts_receivable": max(billing - collections - credits, Decimal(0)),
            "contract_asset": max(revenue - billing, Decimal(0)),
            "contract_liability": max(billing - revenue, Decimal(0)),
        }
        event_population = context["events_by_contract"][contract_id]
        for field, amount in expected.items():
            observed = _money(balance[field])
            if observed != amount:
                outcomes.append(
                    _outcome(
                        "contract_balance_difference",
                        "exception",
                        f"{contract_id}:{field}",
                        entity=balance["entity"],
                        currency=balance["currency"],
                        period=balance["period"],
                        observed=canonical_decimal(observed),
                        expected=canonical_decimal(amount),
                        difference=observed - amount,
                        event_ids=[item["event_id"] for item in event_population],
                        source_refs=[item["source_ref"] for item in event_population],
                    )
                )
    if not outcomes:
        outcomes.append(
            _outcome(
                "contract_balance_rollforward_reperformed",
                "info",
                "contract_balance_population",
                observed=str(len(data["balances"])),
                expected="revenue, billing, collection, credit roll-forward",
            )
        )
    return _procedure(
        "RV-11",
        [f"{item['contract_id']}:{item['period']}" for item in data["balances"]],
        outcomes,
    )


def _rv12(context: Mapping[str, Any]) -> dict[str, Any]:
    contracts = context["data"]["contracts"]
    if not contracts:
        return _procedure(
            "RV-12", [], [_missing("financing_population_missing", "contracts")]
        )
    outcomes: list[dict[str, Any]] = []
    for contract in contracts:
        days = abs(
            (
                date.fromisoformat(contract["payment_due_date"])
                - date.fromisoformat(contract["end_date"])
            ).days
        )
        expected = Decimal(0)
        if days > 365:
            rate = _money(contract["discount_rate"])
            if rate == 0:
                outcomes.append(
                    _outcome(
                        "financing_discount_rate_missing",
                        "exception",
                        contract["contract_id"],
                        entity=contract["entity"],
                        currency=contract["currency"],
                        period=_contract_period(contract),
                        observed="0",
                        expected="positive discount rate for >365 day timing gap",
                    )
                )
                continue
            expected = _rounded(
                _transaction_price(contract) * rate * Decimal(days) / Decimal(365)
            )
        observed = _money(contract["significant_financing_recorded"])
        if observed != expected:
            outcomes.append(
                _outcome(
                    "financing_component_difference",
                    "exception",
                    contract["contract_id"],
                    entity=contract["entity"],
                    currency=contract["currency"],
                    period=_contract_period(contract),
                    observed=canonical_decimal(observed),
                    expected=canonical_decimal(expected),
                    difference=observed - expected,
                )
            )
    if not outcomes:
        outcomes.append(
            _outcome(
                "financing_timing_reperformed",
                "info",
                "contract_population",
                observed=str(len(contracts)),
                expected="payment-performance timing and discount reperformance",
            )
        )
    return _procedure("RV-12", [item["contract_id"] for item in contracts], outcomes)


def _rv13(context: Mapping[str, Any]) -> dict[str, Any]:
    data = context["data"]
    if not data["events"] or not data["balances"]:
        return _procedure(
            "RV-13", [], [_missing("refund_population_missing", "events/balances")]
        )
    outcomes: list[dict[str, Any]] = []
    for balance in data["balances"]:
        refund_events = [
            item
            for item in context["events_by_contract"][balance["contract_id"]]
            if item["event_type"] in {"refund", "credit"}
        ]
        expected = sum((_money(item["amount"]) for item in refund_events), Decimal(0))
        observed = _money(balance["refund_liability"])
        if observed != expected:
            outcomes.append(
                _outcome(
                    "refund_liability_difference",
                    "exception",
                    balance["contract_id"],
                    entity=balance["entity"],
                    currency=balance["currency"],
                    period=balance["period"],
                    observed=canonical_decimal(observed),
                    expected=canonical_decimal(expected),
                    difference=observed - expected,
                    event_ids=[item["event_id"] for item in refund_events],
                    source_refs=[item["source_ref"] for item in refund_events],
                )
            )
    if not outcomes:
        outcomes.append(
            _outcome(
                "refund_credit_population_reconciled",
                "info",
                "refund_population",
                observed=str(
                    sum(
                        1
                        for item in data["events"]
                        if item["event_type"] in {"refund", "credit"}
                    )
                ),
                expected="refund liability roll-forward",
            )
        )
    return _procedure(
        "RV-13",
        [f"{item['contract_id']}:{item['period']}" for item in data["balances"]],
        outcomes,
    )


def _rv14(context: Mapping[str, Any]) -> dict[str, Any]:
    costs = context["data"]["contract_costs"]
    if not costs:
        return _procedure(
            "RV-14", [], [_missing("contract_cost_population_missing", "contract_costs")]
        )
    outcomes: list[dict[str, Any]] = []
    for cost in costs:
        eligible = cost["recoverable"] and (
            (cost["cost_type"] == "acquisition" and cost["incremental"])
            or (cost["cost_type"] == "fulfilment" and cost["directly_related"])
        )
        expected = _money(cost["amount"]) if eligible else Decimal(0)
        observed = _money(cost["capitalized_amount"])
        if observed != expected:
            contract = context["contracts"][cost["contract_id"]]
            outcomes.append(
                _outcome(
                    "contract_cost_capitalization_difference",
                    "exception",
                    cost["cost_id"],
                    entity=contract["entity"],
                    currency=contract["currency"],
                    period=_contract_period(contract),
                    observed=canonical_decimal(observed),
                    expected=canonical_decimal(expected),
                    difference=observed - expected,
                    source_refs=[cost["source_ref"]],
                )
            )
    if not outcomes:
        outcomes.append(
            _outcome(
                "contract_cost_eligibility_reperformed",
                "info",
                "contract_cost_population",
                observed=str(len(costs)),
                expected="incremental/direct/recoverable eligibility",
                source_refs=[item["source_ref"] for item in costs],
            )
        )
    return _procedure("RV-14", [item["cost_id"] for item in costs], outcomes)


def _rv15(context: Mapping[str, Any]) -> dict[str, Any]:
    data = context["data"]
    if not data["contracts"] or not data["events"]:
        return _procedure(
            "RV-15", [], [_missing("side_agreement_population_missing", "contracts/events")]
        )
    outcomes: list[dict[str, Any]] = []
    for contract in data["contracts"]:
        events = context["events_by_contract"][contract["contract_id"]]
        terminations = [item for item in events if item["event_type"] == "termination"]
        side_events = [item for item in events if item["event_type"] == "side_agreement"]
        for event in terminations:
            if (
                contract["cancelled_date"] is None
                or contract["cancelled_date"] != event["event_date"]
            ):
                outcomes.append(
                    _outcome(
                        "termination_not_reflected",
                        "exception",
                        contract["contract_id"],
                        entity=contract["entity"],
                        currency=contract["currency"],
                        period=event["period"],
                        observed=contract["cancelled_date"] or "missing",
                        expected=event["event_date"],
                        source_refs=[event["source_ref"]],
                        event_ids=[event["event_id"]],
                    )
                )
        if contract["side_agreement_ref"] is not None or side_events:
            outcomes.append(
                _outcome(
                    "side_agreement_requires_contract_update",
                    "boundary",
                    contract["contract_id"],
                    entity=contract["entity"],
                    currency=contract["currency"],
                    period=_contract_period(contract),
                    observed=contract["side_agreement_ref"] or "side agreement event",
                    expected="approved contract terms and professional review",
                    source_refs=(
                        [contract["side_agreement_ref"]]
                        if contract["side_agreement_ref"]
                        else [item["source_ref"] for item in side_events]
                    ),
                    event_ids=[item["event_id"] for item in side_events],
                    expert_review_required=True,
                )
            )
        if contract["legal_judgement_required"]:
            outcomes.append(
                _outcome(
                    "legal_judgement_boundary",
                    "boundary",
                    contract["contract_id"],
                    entity=contract["entity"],
                    currency=contract["currency"],
                    period=_contract_period(contract),
                    observed="legal_judgement_required=True",
                    expected="legal expert review packet",
                    event_ids=[item["event_id"] for item in events],
                    source_refs=[item["source_ref"] for item in events],
                    expert_review_required=True,
                )
            )
    if not outcomes:
        outcomes.append(
            _outcome(
                "side_agreement_and_termination_search_completed",
                "info",
                "contract_event_population",
                observed=str(len(data["events"])),
                expected="modification, termination, and side evidence linkage",
                event_ids=[item["event_id"] for item in data["events"]],
                source_refs=[item["source_ref"] for item in data["events"]],
            )
        )
    return _procedure(
        "RV-15", [item["contract_id"] for item in data["contracts"]], outcomes
    )


def _rv16(context: Mapping[str, Any]) -> dict[str, Any]:
    risks = context["data"]["credit_risks"]
    if not risks:
        return _procedure(
            "RV-16", [], [_missing("credit_risk_population_missing", "credit_risks")]
        )
    outcomes: list[dict[str, Any]] = []
    for risk in risks:
        expected = _rounded(
            _money(risk["outstanding_amount"]) * _money(risk["lifetime_loss_rate"])
        )
        observed = _money(risk["recorded_ecl"])
        if observed != expected:
            outcomes.append(
                _outcome(
                    "ecl_reperformance_difference",
                    "exception",
                    f"{risk['contract_id']}:{risk['period']}",
                    entity=risk["entity"],
                    currency=risk["currency"],
                    period=risk["period"],
                    observed=canonical_decimal(observed),
                    expected=canonical_decimal(expected),
                    difference=observed - expected,
                    source_refs=[risk["credit_evidence_ref"]],
                )
            )
    if not outcomes:
        outcomes.append(
            _outcome(
                "ecl_reperformed",
                "info",
                "credit_risk_population",
                observed=str(len(risks)),
                expected="outstanding_amount*lifetime_loss_rate",
                source_refs=[item["credit_evidence_ref"] for item in risks],
            )
        )
    return _procedure(
        "RV-16",
        [f"{item['contract_id']}:{item['period']}" for item in risks],
        outcomes,
    )


def _cross_domain_triggers(context: Mapping[str, Any]) -> list[dict[str, Any]]:
    triggers: list[dict[str, Any]] = []
    for contract in context["data"]["contracts"]:
        events = context["events_by_contract"].get(contract["contract_id"], [])
        sources = sorted({item["source_ref"] for item in events})
        event_ids = sorted({item["event_id"] for item in events})
        if contract["legal_judgement_required"]:
            triggers.append(
                {
                    "trigger_id": f"TRG-RV-LEGAL-{contract['contract_id']}",
                    "scope_ref": contract["contract_id"],
                    "target_domain": "legal",
                    "disposition": "expert_review_required",
                    "source_refs": sources,
                    "event_ids": event_ids,
                }
            )
        if contract["tax_judgement_required"]:
            triggers.append(
                {
                    "trigger_id": f"TRG-RV-TAX-{contract['contract_id']}",
                    "scope_ref": contract["contract_id"],
                    "target_domain": "tax",
                    "disposition": "expert_review_required",
                    "source_refs": sources,
                    "event_ids": event_ids,
                }
            )
        for event in events:
            if event["currency"] != contract["currency"]:
                triggers.append(
                    {
                        "trigger_id": f"TRG-RV-FX-{event['event_id']}",
                        "scope_ref": contract["contract_id"],
                        "target_domain": "foreign_exchange",
                        "disposition": "further_procedure_required",
                        "source_refs": [event["source_ref"]],
                        "event_ids": [event["event_id"]],
                    }
                )
    return sorted(
        triggers,
        key=lambda item: (
            item["target_domain"],
            item["scope_ref"],
            item["trigger_id"],
        ),
    )


_PROCEDURES = (
    _rv01,
    _rv02,
    _rv03,
    _rv04,
    _rv05,
    _rv06,
    _rv07,
    _rv08,
    _rv09,
    _rv10,
    _rv11,
    _rv12,
    _rv13,
    _rv14,
    _rv15,
    _rv16,
)


def run_revenue_procedures(value: Mapping[str, Any]) -> dict[str, Any]:
    """Execute all 16 revenue Issue Families against one closed input snapshot."""
    if not isinstance(value, Mapping):
        raise ContractError("revenue input must be an object")
    data = _normalize_input(value)
    context = _context(data)
    procedure_results = [procedure(context) for procedure in _PROCEDURES]
    counts = Counter(item["status"] for item in procedure_results)
    status_counts = {
        status: counts.get(status, 0)
        for status in ("passed", "exceptions_found", "not_assessable")
    }
    triggers = _cross_domain_triggers(context)
    expert_review_required = any(
        item["disposition"] == "expert_review_required" for item in triggers
    ) or any(
        outcome["expert_review_required"]
        for result in procedure_results
        for outcome in result["outcomes"]
    )
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": data["run_id"],
        "revision": data["revision"],
        "input_hash": _digest(data),
        "procedure_results": procedure_results,
        "procedure_status_counts": status_counts,
        "cross_domain_triggers": triggers,
        "coverage_complete": all(
            item["status"] != "not_assessable" for item in procedure_results
        ),
        "implementation_complete": all(
            item["implementation_status"] == "implemented_deterministic"
            for item in procedure_results
        ),
        "authority_ceiling": "Boundary",
        "expert_review_required": expert_review_required,
    }
    result = {**body, "content_hash": _digest(body)}
    _SCHEMA_STORE.validate(_SCHEMA, result)
    return result


def verify_revenue_procedure_result(value: Mapping[str, Any]) -> dict[str, Any]:
    """Verify schema, seed dispatch, derived state, order, and immutable hash."""
    if not isinstance(value, Mapping):
        raise ContractError("revenue result must be an object")
    _SCHEMA_STORE.validate(_SCHEMA, value)
    if value["content_hash"] != _digest(value, "content_hash"):
        raise ContractError("revenue result content hash mismatch")
    results = value["procedure_results"]
    if [item["issue_family_id"] for item in results] != list(_ISSUE_IDS):
        raise ContractError("revenue result must contain RV-01 through RV-16 in order")
    if [item["procedure_id"] for item in results] != list(_PROCEDURE_IDS):
        raise ContractError("revenue procedure dispatch does not match approved seeds")
    for result in results:
        if result["population_ids"] != sorted(set(result["population_ids"])):
            raise ContractError("revenue procedure population must be sorted and unique")
        expected_outcomes = sorted(
            result["outcomes"],
            key=lambda item: (
                item["code"],
                item["scope_ref"],
                item["observed"] or "",
                item["expected"] or "",
                tuple(item["event_ids"]),
            ),
        )
        if result["outcomes"] != expected_outcomes:
            raise ContractError("revenue outcomes must use deterministic order")
        for outcome in result["outcomes"]:
            if outcome["source_refs"] != sorted(set(outcome["source_refs"])):
                raise ContractError("outcome source refs must be sorted and unique")
            if outcome["event_ids"] != sorted(set(outcome["event_ids"])):
                raise ContractError("outcome event ids must be sorted and unique")
        if result["status"] != _status(result["outcomes"]):
            raise ContractError("revenue procedure status is inconsistent with outcomes")
    counts = Counter(item["status"] for item in results)
    expected_counts = {
        status: counts.get(status, 0)
        for status in ("passed", "exceptions_found", "not_assessable")
    }
    if value["procedure_status_counts"] != expected_counts:
        raise ContractError("revenue procedure status counts mismatch")
    expected_coverage = all(item["status"] != "not_assessable" for item in results)
    if value["coverage_complete"] is not expected_coverage:
        raise ContractError("revenue coverage flag mismatch")
    expected_implementation = all(
        item["implementation_status"] == "implemented_deterministic" for item in results
    )
    if value["implementation_complete"] is not expected_implementation:
        raise ContractError("revenue implementation flag mismatch")
    expected_triggers = sorted(
        value["cross_domain_triggers"],
        key=lambda item: (item["target_domain"], item["scope_ref"], item["trigger_id"]),
    )
    if value["cross_domain_triggers"] != expected_triggers:
        raise ContractError("cross-domain triggers must use deterministic order")
    expected_expert_review = any(
        item["disposition"] == "expert_review_required"
        for item in value["cross_domain_triggers"]
    ) or any(
        outcome["expert_review_required"]
        for result in results
        for outcome in result["outcomes"]
    )
    if value["expert_review_required"] is not expected_expert_review:
        raise ContractError("expert review flag mismatch")
    return copy.deepcopy(dict(value))
