"""Deterministic Boundary procedures for project cost issue families CA-01..CA-16."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes, canonical_decimal
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError

_SCHEMA = "accounting-project-cost-procedure-result.schema.json"
_SCHEMA_STORE = SchemaStore()

SUPPORTED_PROJECT_COST_ISSUES = tuple(f"CA-{number:02d}" for number in range(1, 17))

_PROCEDURE_IDS = {
    "CA-01": "P-CA-01",
    "CA-02": "P-CA-02",
    "CA-03": "P-CA-03",
    "CA-04": "P-CA-04",
    "CA-05": "P-CA-05",
    "CA-06": "P-CA-06",
    "CA-07": "P-CA-07",
    "CA-08": "P-CA-08",
    "CA-09": "P-CA-09",
    "CA-10": "P-CA-10",
    "CA-11": "P-CA-11",
    "CA-12": "P-CA-12",
    "CA-13": "P-CA-13",
    "CA-14": "P-CA-14",
    "CA-15": "P-CA-06",
    "CA-16": "P-CA-09",
}

_CODES = {
    "CA-01": "gl_project_population_difference",
    "CA-02": "direct_indirect_classification_difference",
    "CA-03": "non_homogeneous_pool_cost",
    "CA-04": "allocation_driver_sensitivity",
    "CA-05": "allocation_rate_difference",
    "CA-06": "allocation_completeness_difference",
    "CA-07": "idle_or_abnormal_cost_allocated",
    "CA-08": "payroll_timesheet_difference",
    "CA-09": "vendor_usage_attribution_difference",
    "CA-10": "wip_roll_forward_difference",
    "CA-11": "contract_cost_asset_difference",
    "CA-12": "capitalization_scope_difference",
    "CA-13": "onerous_contract_provision_difference",
    "CA-14": "budget_eac_bridge_difference",
    "CA-15": "alternate_allocation_margin_difference",
    "CA-16": "cross_charge_policy_difference",
}

_REQUIRED_METRICS = {
    "CA-01": frozenset(
        {
            "gl_cost",
            "directly_assigned_cost",
            "allocated_cost",
            "unassigned_cost",
            "excluded_cost",
        }
    ),
    "CA-02": frozenset({"classified_direct_cost", "traceable_direct_cost"}),
    "CA-03": frozenset({"pool_cost", "homogeneous_pool_cost"}),
    "CA-04": frozenset({"current_allocated_cost", "causal_driver_allocated_cost"}),
    "CA-05": frozenset(
        {
            "eligible_pool_cost",
            "eligible_driver_quantity",
            "recorded_allocation_rate",
            "project_driver_quantity",
            "recorded_allocated_cost",
        }
    ),
    "CA-06": frozenset(
        {"eligible_pool_cost", "total_allocated_cost", "duplicate_allocated_cost"}
    ),
    "CA-07": frozenset(
        {
            "total_pool_cost",
            "normal_capacity",
            "actual_utilisation",
            "abnormal_waste_cost",
            "project_allocated_idle_cost",
        }
    ),
    "CA-08": frozenset(
        {
            "paid_or_accrued_hours",
            "project_hours",
            "internal_hours",
            "leave_hours",
            "unassigned_hours",
            "payroll_cost",
            "timesheet_allocated_cost",
        }
    ),
    "CA-09": frozenset(
        {"vendor_or_service_cost", "usage_matched_cost", "recorded_project_cost"}
    ),
    "CA-10": frozenset(
        {
            "opening_wip",
            "eligible_current_cost",
            "recognised_cost",
            "write_down",
            "transfer",
            "closing_wip",
        }
    ),
    "CA-11": frozenset(
        {
            "opening_contract_cost_asset",
            "eligible_contract_cost_additions",
            "recorded_contract_cost_additions",
            "amortisation",
            "impairment",
            "closing_contract_cost_asset",
        }
    ),
    "CA-12": frozenset(
        {
            "development_cost",
            "training_cost",
            "maintenance_cost",
            "approved_capitalisable_development_cost",
            "recorded_capitalised_cost",
        }
    ),
    "CA-13": frozenset(
        {"expected_economic_benefits", "unavoidable_costs", "recognised_provision"}
    ),
    "CA-14": frozenset(
        {
            "baseline_budget",
            "approved_change_orders",
            "unapproved_scope_candidate",
            "price_and_rate_changes",
            "productivity_variance",
            "expected_total_cost",
            "eac",
        }
    ),
    "CA-15": frozenset(
        {"project_revenue", "recorded_project_cost", "alternate_driver_project_cost"}
    ),
    "CA-16": frozenset(
        {"cross_charge_cost", "policy_supported_charge", "recorded_project_cost"}
    ),
}

_REVIEW_SCOPE = {
    "CA-01": "accounting",
    "CA-02": "accounting_and_management",
    "CA-03": "management_accounting",
    "CA-04": "management_accounting",
    "CA-05": "accounting_and_management",
    "CA-06": "accounting_and_management",
    "CA-07": "accounting_and_management",
    "CA-08": "labor_privacy_and_accounting",
    "CA-09": "accounting_and_management",
    "CA-10": "accounting",
    "CA-11": "accounting",
    "CA-12": "accounting",
    "CA-13": "accounting",
    "CA-14": "accounting_and_management",
    "CA-15": "management_accounting",
    "CA-16": "accounting_tax_and_legal",
}

_TOP_FIELDS = frozenset({"run_id", "revision", "rows"})
_ROW_FIELDS = frozenset(
    {
        "row_id",
        "entity",
        "currency",
        "period",
        "project_id",
        "metrics",
        "source_refs",
        "counter_evidence_refs",
    }
)


class _NotAssessable(Exception):
    def __init__(self, metric: str):
        super().__init__(metric)
        self.metric = metric


def _digest(value: Mapping[str, Any], excluded: str | None = None) -> str:
    body = dict(value)
    if excluded is not None:
        body.pop(excluded, None)
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def _object(value: Any, fields: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} must be an object")
    missing = sorted(fields - set(value))
    unknown = sorted(set(value) - fields)
    if missing or unknown:
        raise ContractError(f"{label} field mismatch; missing={missing}; unknown={unknown}")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must be a non-empty string")
    return value


def _refs(value: Any, label: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ContractError(f"{label} must be an array")
    refs = [_text(item, f"{label}[{index}]") for index, item in enumerate(value)]
    if len(refs) != len(set(refs)):
        raise ContractError(f"{label} must not contain duplicates")
    return sorted(refs)


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


def _normalize(issue_id: str, value: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    root = _object(value, _TOP_FIELDS, "project cost input")
    revision = root["revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ContractError("revision must be a non-negative integer")
    raw_rows = root["rows"]
    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes)):
        raise ContractError("rows must be an array")

    rows: list[dict[str, Any]] = []
    missing_inputs: list[str] = []
    row_ids: set[str] = set()
    required = _REQUIRED_METRICS[issue_id]
    for index, raw in enumerate(raw_rows):
        row = _object(raw, _ROW_FIELDS, f"rows[{index}]")
        row_id = _text(row["row_id"], f"rows[{index}].row_id")
        if row_id in row_ids:
            raise ContractError(f"duplicate row_id: {row_id}")
        row_ids.add(row_id)
        raw_metrics = row["metrics"]
        if not isinstance(raw_metrics, Mapping):
            raise ContractError(f"rows[{index}].metrics must be an object")
        unknown = sorted(set(raw_metrics) - required)
        if unknown:
            raise ContractError(f"rows[{index}].metrics has unknown fields: {unknown}")
        metrics = {
            name: _decimal(raw_metrics[name], f"rows[{index}].metrics.{name}")
            for name in sorted(set(raw_metrics) & required)
        }
        for name in sorted(required - set(raw_metrics)):
            missing_inputs.append(f"{row_id}:metrics.{name}")
        source_refs = _refs(row["source_refs"], f"rows[{index}].source_refs")
        counter_refs = _refs(
            row["counter_evidence_refs"], f"rows[{index}].counter_evidence_refs"
        )
        if not source_refs:
            missing_inputs.append(f"{row_id}:source_refs")
        if not counter_refs:
            missing_inputs.append(f"{row_id}:counter_evidence_refs")
        rows.append(
            {
                "row_id": row_id,
                "entity": _text(row["entity"], f"rows[{index}].entity"),
                "currency": _text(row["currency"], f"rows[{index}].currency"),
                "period": _text(row["period"], f"rows[{index}].period"),
                "project_id": _text(row["project_id"], f"rows[{index}].project_id"),
                "metrics": metrics,
                "source_refs": source_refs,
                "counter_evidence_refs": counter_refs,
            }
        )
    if not rows:
        missing_inputs.append("rows")
    rows.sort(
        key=lambda row: (
            row["entity"],
            row["currency"],
            row["period"],
            row["project_id"],
            row["row_id"],
        )
    )
    return (
        {
            "run_id": _text(root["run_id"], "run_id"),
            "revision": revision,
            "rows": rows,
        },
        sorted(missing_inputs),
    )


def _m(row: Mapping[str, Any], name: str) -> Decimal:
    return Decimal(row["metrics"][name])


Calculation = Callable[[Mapping[str, Any]], tuple[Decimal, Decimal, Decimal]]


def _ca01(row):
    observed = _m(row, "gl_cost")
    expected = sum(
        (
            _m(row, "directly_assigned_cost"),
            _m(row, "allocated_cost"),
            _m(row, "unassigned_cost"),
            _m(row, "excluded_cost"),
        ),
        Decimal(0),
    )
    return observed, expected, observed - expected


def _ca02(row):
    observed = _m(row, "classified_direct_cost")
    expected = _m(row, "traceable_direct_cost")
    return observed, expected, observed - expected


def _ca03(row):
    observed = _m(row, "pool_cost")
    expected = _m(row, "homogeneous_pool_cost")
    return observed, expected, observed - expected


def _ca04(row):
    observed = _m(row, "current_allocated_cost")
    expected = _m(row, "causal_driver_allocated_cost")
    return observed, expected, observed - expected


def _ca05(row):
    denominator = _m(row, "eligible_driver_quantity")
    if denominator == 0:
        raise _NotAssessable("metrics.eligible_driver_quantity:non_zero")
    expected = _m(row, "eligible_pool_cost") / denominator
    observed = _m(row, "recorded_allocation_rate")
    project_quantity = _m(row, "project_driver_quantity")
    recorded_amount = _m(row, "recorded_allocated_cost")
    expected_amount = expected * project_quantity
    if observed == expected and recorded_amount != expected_amount:
        return recorded_amount, expected_amount, recorded_amount - expected_amount
    return observed, expected, observed - expected


def _ca06(row):
    observed = _m(row, "total_allocated_cost") - _m(row, "duplicate_allocated_cost")
    expected = _m(row, "eligible_pool_cost")
    return observed, expected, observed - expected


def _ca07(row):
    normal = _m(row, "normal_capacity")
    if normal <= 0:
        raise _NotAssessable("metrics.normal_capacity:positive")
    actual = _m(row, "actual_utilisation")
    idle_quantity = max(normal - actual, Decimal(0))
    idle_cost = _m(row, "total_pool_cost") / normal * idle_quantity
    observed = _m(row, "project_allocated_idle_cost") + _m(row, "abnormal_waste_cost")
    expected = Decimal(0)
    if idle_cost == 0 and observed == 0:
        return observed, expected, Decimal(0)
    return observed, expected, observed


def _ca08(row):
    hours = sum(
        (
            _m(row, "project_hours"),
            _m(row, "internal_hours"),
            _m(row, "leave_hours"),
            _m(row, "unassigned_hours"),
        ),
        Decimal(0),
    )
    paid = _m(row, "paid_or_accrued_hours")
    payroll = _m(row, "payroll_cost")
    allocated = _m(row, "timesheet_allocated_cost")
    if paid != hours:
        return hours, paid, hours - paid
    return allocated, payroll, allocated - payroll


def _ca09(row):
    usage = _m(row, "usage_matched_cost")
    recorded = _m(row, "recorded_project_cost")
    vendor = _m(row, "vendor_or_service_cost")
    if recorded != usage:
        return recorded, usage, recorded - usage
    return usage, vendor, usage - vendor


def _ca10(row):
    expected = (
        _m(row, "opening_wip")
        + _m(row, "eligible_current_cost")
        - _m(row, "recognised_cost")
        - _m(row, "write_down")
        + _m(row, "transfer")
    )
    observed = _m(row, "closing_wip")
    return observed, expected, observed - expected


def _ca11(row):
    expected = (
        _m(row, "opening_contract_cost_asset")
        + _m(row, "eligible_contract_cost_additions")
        - _m(row, "amortisation")
        - _m(row, "impairment")
    )
    observed = _m(row, "closing_contract_cost_asset")
    recorded_additions = _m(row, "recorded_contract_cost_additions")
    if observed == expected and recorded_additions != _m(row, "eligible_contract_cost_additions"):
        return (
            recorded_additions,
            _m(row, "eligible_contract_cost_additions"),
            recorded_additions - _m(row, "eligible_contract_cost_additions"),
        )
    return observed, expected, observed - expected


def _ca12(row):
    approved = min(
        _m(row, "approved_capitalisable_development_cost"),
        _m(row, "development_cost"),
    )
    observed = _m(row, "recorded_capitalised_cost")
    return observed, approved, observed - approved


def _ca13(row):
    expected = max(
        _m(row, "unavoidable_costs") - _m(row, "expected_economic_benefits"),
        Decimal(0),
    )
    observed = _m(row, "recognised_provision")
    return observed, expected, observed - expected


def _ca14(row):
    expected = sum(
        (
            _m(row, "baseline_budget"),
            _m(row, "approved_change_orders"),
            _m(row, "unapproved_scope_candidate"),
            _m(row, "price_and_rate_changes"),
            _m(row, "productivity_variance"),
        ),
        Decimal(0),
    )
    stated_total = _m(row, "expected_total_cost")
    observed = _m(row, "eac")
    if stated_total != expected:
        return stated_total, expected, stated_total - expected
    return observed, expected, observed - expected


def _ca15(row):
    revenue = _m(row, "project_revenue")
    observed = revenue - _m(row, "recorded_project_cost")
    expected = revenue - _m(row, "alternate_driver_project_cost")
    return observed, expected, observed - expected


def _ca16(row):
    policy = min(_m(row, "policy_supported_charge"), _m(row, "cross_charge_cost"))
    observed = _m(row, "recorded_project_cost")
    return observed, policy, observed - policy


_CALCULATIONS: dict[str, Calculation] = {
    "CA-01": _ca01,
    "CA-02": _ca02,
    "CA-03": _ca03,
    "CA-04": _ca04,
    "CA-05": _ca05,
    "CA-06": _ca06,
    "CA-07": _ca07,
    "CA-08": _ca08,
    "CA-09": _ca09,
    "CA-10": _ca10,
    "CA-11": _ca11,
    "CA-12": _ca12,
    "CA-13": _ca13,
    "CA-14": _ca14,
    "CA-15": _ca15,
    "CA-16": _ca16,
}


def _outcome(
    issue_id: str,
    row: Mapping[str, Any],
    values: tuple[Decimal, Decimal, Decimal],
) -> dict[str, Any]:
    observed, expected, difference = values
    return {
        "code": _CODES[issue_id],
        "row_id": row["row_id"],
        "entity": row["entity"],
        "currency": row["currency"],
        "period": row["period"],
        "project_id": row["project_id"],
        "observed": canonical_decimal(observed),
        "expected": canonical_decimal(expected),
        "amount": canonical_decimal(difference),
        "review_scope": _REVIEW_SCOPE[issue_id],
        "boundary_reason": "professional_judgment_and_approved_pack_review_required",
        "source_refs": copy.deepcopy(row["source_refs"]),
        "counter_evidence_refs": copy.deepcopy(row["counter_evidence_refs"]),
    }


def run_project_cost_procedure(issue_id: str, value: Mapping[str, Any]) -> dict[str, Any]:
    """Run one closed, deterministic project-cost procedure without making findings."""
    if issue_id not in SUPPORTED_PROJECT_COST_ISSUES:
        raise ContractError(f"unsupported project cost issue family: {issue_id}")
    if not isinstance(value, Mapping):
        raise ContractError("project cost input must be an object")
    data, missing_inputs = _normalize(issue_id, value)
    outcomes: list[dict[str, Any]] = []
    if not missing_inputs:
        for row in data["rows"]:
            try:
                values = _CALCULATIONS[issue_id](row)
            except _NotAssessable as error:
                missing_inputs.append(f"{row['row_id']}:{error.metric}")
                continue
            if values[2] != 0:
                outcomes.append(_outcome(issue_id, row, values))
    if missing_inputs:
        outcomes = []
        status = "not_assessable"
    else:
        status = "exceptions_found" if outcomes else "passed"
    outcomes.sort(key=canonical_bytes)
    result = {
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
    result["content_hash"] = _digest(result)
    _SCHEMA_STORE.validate(_SCHEMA, result)
    return result


def verify_project_cost_procedure_result(value: Mapping[str, Any]) -> None:
    """Fail closed on schema or immutable content-hash drift."""
    if not isinstance(value, Mapping):
        raise ContractError("project cost procedure result must be an object")
    _SCHEMA_STORE.validate(_SCHEMA, value)
    if value["content_hash"] != _digest(value, "content_hash"):
        raise ContractError("project cost procedure result content hash mismatch")
