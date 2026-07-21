"""Build snapshot-bound accounting requests from multitable JSON inputs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from typing import Any, cast

from trusted_ceo_agent.accounting.input_contracts import (
    CASHFLOW_POPULATIONS as _CASHFLOW_POPULATIONS,
    MAX_CALCULATION_EXPONENT as _MAX_CALCULATION_EXPONENT,
    SUITE_RELEASE_ID as _SUITE_RELEASE_ID,
    TABLE_FIELDS as _TABLE_FIELDS,
)
from trusted_ceo_agent.accounting.input_validation import (
    calculation_precision as _calculation_precision,
    decimal_value as _decimal,
    integer_value as _integer,
    source_ref as _source_ref,
    validate_rows as _validate_rows,
    validate_runtime_binding as _validate_runtime_binding,
)
from trusted_ceo_agent.accounting.suite import build_machine_draft_suite
from trusted_ceo_agent.canonical import canonical_decimal
from trusted_ceo_agent.errors import ContractError

def _tier_zero_input(
    document: Mapping[str, Any],
    tables: Mapping[str, list[dict[str, Any]]],
    *,
    run_id: str,
    revision: int,
    source_id: str,
    snapshot_sha256: str,
) -> dict[str, Any]:
    period = cast(Mapping[str, str], document["reporting_period"])
    headers = [
        {
            "journal_id": row["journal_id"],
            "source_id": source_id,
            "sequence": _integer(row["sequence"], "journal sequence"),
            "status": row["status"],
            "entity": row["entity"],
            "currency": row["currency"],
            "period": row["period"],
        }
        for row in tables["journal_headers"]
    ]
    lines = [
        {
            "line_id": row["line_id"],
            "journal_id": row["journal_id"],
            "account_id": row["account_id"],
            "debit": row["debit"],
            "credit": row["credit"],
            "entity": row["entity"],
            "currency": row["currency"],
            "period": row["period"],
        }
        for row in tables["journal_lines"]
    ]
    debit_total = sum(
        (_decimal(row["debit"], "journal debit") for row in tables["journal_lines"]),
        Decimal(0),
    )
    credit_total = sum(
        (_decimal(row["credit"], "journal credit") for row in tables["journal_lines"]),
        Decimal(0),
    )
    trial_balance = [
        {
            "account_id": row["account_id"],
            "entity": row["entity"],
            "currency": row["currency"],
            "period": row["period"],
            "prior_closing": row["prior_closing"],
            "opening": row["opening"],
            "debit_turnover": row["debit_turnover"],
            "credit_turnover": row["credit_turnover"],
            "closing": row["closing"],
            "control_subledger": (
                None
                if row["control_subledger"] == "not_applicable"
                else row["control_subledger"]
            ),
        }
        for row in tables["trial_balance"]
    ]
    subledgers = _subledger_balances(tables)
    return {
        "run_id": run_id,
        "revision": revision,
        "source_manifests": [
            {
                "source_id": source_id,
                "source_sha256": snapshot_sha256,
                "period_start": period["start"],
                "period_end": period["end"],
                "header_count": len(headers),
                "line_count": len(lines),
                "debit_total": canonical_decimal(debit_total),
                "credit_total": canonical_decimal(credit_total),
            }
        ],
        "journal_headers": sorted(headers, key=lambda item: item["journal_id"]),
        "journal_lines": sorted(
            lines,
            key=lambda item: (item["journal_id"], item["line_id"]),
        ),
        "trial_balance": sorted(
            trial_balance,
            key=lambda item: (
                item["entity"],
                item["currency"],
                item["period"],
                item["account_id"],
            ),
        ),
        "subledger_balances": subledgers,
    }


def _subledger_balances(
    tables: Mapping[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    accounts = {
        row["account_id"]: row for row in tables["chart_of_accounts"]
    }
    trial_balance = tables["trial_balance"]
    result: list[dict[str, Any]] = []
    specifications = (
        (
            "receivable_aging",
            "ar_item_id",
            "receivable_aging",
        ),
        (
            "payable_aging",
            "ap_item_id",
            "payable_aging",
        ),
    )
    for table_name, object_field, control_name in specifications:
        for row in tables[table_name]:
            period = cast(str, row["as_of_date"])[:7]
            matches = [
                item
                for item in trial_balance
                if item["control_subledger"] == control_name
                and item["entity"] == row["entity"]
                and item["currency"] == row["currency"]
                and item["period"] == period
            ]
            if len(matches) != 1:
                raise ContractError(
                    f"{table_name} row requires exactly one "
                    "trial balance control account"
                )
            account_id = cast(str, matches[0]["account_id"])
            amount = _decimal(
                row["outstanding_amount"],
                f"{table_name}.outstanding_amount",
            )
            normal_balance = accounts[account_id]["normal_balance"]
            if normal_balance == "credit":
                amount = -amount
            elif normal_balance != "debit":
                raise ContractError(
                    f"unsupported normal_balance for {account_id}"
                )
            result.append(
                {
                    "subledger": control_name,
                    "account_id": account_id,
                    "object_id": row[object_field],
                    "entity": row["entity"],
                    "currency": row["currency"],
                    "period": period,
                    "amount": canonical_decimal(amount),
                }
            )
    return sorted(
        result,
        key=lambda item: (
            item["entity"],
            item["currency"],
            item["period"],
            item["subledger"],
            item["account_id"],
            item["object_id"],
        ),
    )


def _empty_raw_core(
    *,
    run_id: str,
    revision: int,
    period_end: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "revision": revision,
        "close_timestamp": period_end,
        "journals": [],
        "allowed_account_pairs": [],
        "subsequent_disbursements": [],
        "policy_changes": [],
        "capitalization_items": [],
        "counterparties": [],
    }


def _empty_revenue(
    *,
    run_id: str,
    revision: int,
    period_start: str,
    period_end: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "revision": revision,
        "period_start": period_start,
        "period_end": period_end,
        "contracts": [],
        "obligations": [],
        "events": [],
        "balances": [],
        "contract_costs": [],
        "credit_risks": [],
    }


def _empty_cashflow(
    *,
    run_id: str,
    revision: int,
    period_end: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "revision": revision,
        "as_of_date": period_end,
        **{name: [] for name in _CASHFLOW_POPULATIONS},
    }


def _ca02_rows(
    tables: Mapping[str, list[dict[str, Any]]],
    *,
    source_id: str,
    snapshot_sha256: str,
) -> list[dict[str, Any]]:
    vendor_by_id = {
        row["vendor_cost_id"]: (index, row)
        for index, row in enumerate(tables["vendor_costs"])
    }
    groups: dict[
        tuple[str, str, str, str],
        dict[str, list[tuple[int, dict[str, Any]]]],
    ] = {}
    for vendor_index, vendor in enumerate(tables["vendor_costs"]):
        period = cast(str, vendor["cost_date"])[:7]
        key = (
            cast(str, vendor["entity"]),
            cast(str, vendor["currency"]),
            period,
            cast(str, vendor["project_id"]),
        )
        group = groups.setdefault(key, {"vendors": [], "directs": []})
        group["vendors"].append((vendor_index, vendor))

    for direct_index, direct in enumerate(tables["direct_costs"]):
        if direct["source_table"] != "vendor_costs":
            continue
        _vendor_index, vendor = vendor_by_id[direct["source_row_id"]]
        if any(
            direct[field] != vendor[field]
            for field in ("entity", "currency", "project_id")
        ):
            raise ContractError(
                "linked direct_costs and vendor_costs dimensions differ"
            )
        vendor_period = cast(str, vendor["cost_date"])[:7]
        direct_period = cast(str, direct["cost_date"])[:7]
        if direct_period != vendor_period:
            raise ContractError(
                "linked direct_costs and vendor_costs periods differ"
            )
        key = (
            cast(str, vendor["entity"]),
            cast(str, vendor["currency"]),
            vendor_period,
            cast(str, vendor["project_id"]),
        )
        groups[key]["directs"].append((direct_index, direct))

    result = []
    for (entity, currency, period, project_id), group in sorted(groups.items()):
        vendors = group["vendors"]
        directs = group["directs"]
        if not directs:
            continue
        classified = sum(
            (
                _decimal(row["amount"], "vendor cost amount")
                for _index, row in vendors
                if row["direct_flag"] is True
            ),
            Decimal(0),
        )
        traceable = sum(
            (
                _decimal(row["amount"], "direct cost amount")
                for _index, row in directs
            ),
            Decimal(0),
        )
        result.append(
            {
                "row_id": (
                    f"CA-02:{entity}:{currency}:{period}:{project_id}"
                ),
                "entity": entity,
                "currency": currency,
                "period": period,
                "project_id": project_id,
                "metrics": {
                    "classified_direct_cost": canonical_decimal(classified),
                    "traceable_direct_cost": canonical_decimal(traceable),
                },
                "source_refs": sorted(
                    _source_ref(
                        source_id,
                        snapshot_sha256,
                        "vendor_costs",
                        index,
                    )
                    for index, _row in vendors
                ),
                "counter_evidence_refs": sorted(
                    _source_ref(
                        source_id,
                        snapshot_sha256,
                        "direct_costs",
                        index,
                    )
                    for index, _row in directs
                ),
            }
        )
    return result


def _ca04_rows(
    tables: Mapping[str, list[dict[str, Any]]],
    *,
    source_id: str,
    snapshot_sha256: str,
) -> list[dict[str, Any]]:
    pools = {
        row["pool_id"]: (index, row)
        for index, row in enumerate(tables["allocation_pools"])
    }
    drivers_by_pool: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, row in enumerate(tables["allocation_drivers"]):
        drivers_by_pool[cast(str, row["pool_id"])].append((index, row))
    results_by_scope: dict[
        tuple[str, str],
        list[tuple[int, dict[str, Any]]],
    ] = defaultdict(list)
    driver_by_id = {
        row["driver_id"]: row for row in tables["allocation_drivers"]
    }
    for index, row in enumerate(tables["allocation_results"]):
        driver = driver_by_id[row["driver_id"]]
        if (
            driver["pool_id"] != row["pool_id"]
            or driver["project_id"] != row["project_id"]
        ):
            raise ContractError(
                "allocation result driver differs from its pool/project"
            )
        results_by_scope[
            (cast(str, row["pool_id"]), cast(str, row["project_id"]))
        ].append((index, row))

    result = []
    for (pool_id, project_id), allocation_rows in sorted(
        results_by_scope.items()
    ):
        pool_index, pool = pools[pool_id]
        pool_drivers = drivers_by_pool[pool_id]
        project_drivers = [
            item for item in pool_drivers if item[1]["project_id"] == project_id
        ]
        if not project_drivers:
            continue
        dimensions = ("entity", "period")
        if any(
            row[field] != pool[field]
            for _index, row in (*allocation_rows, *pool_drivers)
            for field in dimensions
        ):
            raise ContractError("allocation pool, driver, and result dimensions differ")
        if any(
            row["currency"] != pool["currency"]
            for _index, row in allocation_rows
        ):
            raise ContractError("allocation pool and result currency differ")
        total_quantity = sum(
            (
                _decimal(row["driver_quantity"], "driver quantity")
                for _index, row in pool_drivers
            ),
            Decimal(0),
        )
        project_quantity = sum(
            (
                _decimal(row["driver_quantity"], "driver quantity")
                for _index, row in project_drivers
            ),
            Decimal(0),
        )
        if total_quantity <= 0 or project_quantity < 0:
            continue
        current = sum(
            (
                _decimal(row["allocated_amount"], "allocated amount")
                for _index, row in allocation_rows
            ),
            Decimal(0),
        )
        causal = (
            _decimal(pool["source_amount"], "pool source amount")
            * project_quantity
            / total_quantity
        )
        entity = cast(str, pool["entity"])
        currency = cast(str, pool["currency"])
        period = cast(str, pool["period"])
        result.append(
            {
                "row_id": (
                    f"CA-04:{entity}:{currency}:{period}:{project_id}:{pool_id}"
                ),
                "entity": entity,
                "currency": currency,
                "period": period,
                "project_id": project_id,
                "metrics": {
                    "current_allocated_cost": canonical_decimal(current),
                    "causal_driver_allocated_cost": canonical_decimal(causal),
                },
                "source_refs": sorted(
                    _source_ref(
                        source_id,
                        snapshot_sha256,
                        "allocation_results",
                        index,
                    )
                    for index, _row in allocation_rows
                ),
                "counter_evidence_refs": sorted(
                    {
                        _source_ref(
                            source_id,
                            snapshot_sha256,
                            "allocation_pools",
                            pool_index,
                        ),
                        *(
                            _source_ref(
                                source_id,
                                snapshot_sha256,
                                "allocation_drivers",
                                index,
                            )
                            for index, _row in pool_drivers
                        ),
                    }
                ),
            }
        )
    return result


def _project_cost_inputs(
    tables: Mapping[str, list[dict[str, Any]]],
    *,
    run_id: str,
    revision: int,
    source_id: str,
    snapshot_sha256: str,
) -> dict[str, dict[str, Any]]:
    result = {
        f"CA-{number:02d}": {
            "run_id": run_id,
            "revision": revision,
            "rows": [],
        }
        for number in range(1, 17)
    }
    result["CA-02"]["rows"] = _ca02_rows(
        tables,
        source_id=source_id,
        snapshot_sha256=snapshot_sha256,
    )
    result["CA-04"]["rows"] = _ca04_rows(
        tables,
        source_id=source_id,
        snapshot_sha256=snapshot_sha256,
    )
    return result


def _build_accounting_request_in_context(
    document: Mapping[str, Any],
    *,
    run_id: str,
    revision: int,
    scope_ref: str,
    source_id: str,
    snapshot_sha256: str,
) -> dict[str, Any]:
    """Validate one immutable source and build the closed seven-field request."""
    (
        normalized_run_id,
        normalized_revision,
        normalized_scope_ref,
        normalized_source_id,
        normalized_hash,
    ) = _validate_runtime_binding(
        run_id=run_id,
        revision=revision,
        scope_ref=scope_ref,
        source_id=source_id,
        snapshot_sha256=snapshot_sha256,
    )
    tables = _validate_rows(document)
    period = cast(Mapping[str, str], document["reporting_period"])
    tier_zero = _tier_zero_input(
        document,
        tables,
        run_id=normalized_run_id,
        revision=normalized_revision,
        source_id=normalized_source_id,
        snapshot_sha256=normalized_hash,
    )
    return {
        "scope_ref": normalized_scope_ref,
        "suite": build_machine_draft_suite(
            release_id=_SUITE_RELEASE_ID,
            effective_from=period["start"],
            effective_to=period["end"],
        ),
        "tier_zero_input": tier_zero,
        "raw_core_population": _empty_raw_core(
            run_id=normalized_run_id,
            revision=normalized_revision,
            period_end=period["end"],
        ),
        "revenue_input": _empty_revenue(
            run_id=normalized_run_id,
            revision=normalized_revision,
            period_start=period["start"],
            period_end=period["end"],
        ),
        "cashflow_input": _empty_cashflow(
            run_id=normalized_run_id,
            revision=normalized_revision,
            period_end=period["end"],
        ),
        "project_cost_inputs": _project_cost_inputs(
            tables,
            run_id=normalized_run_id,
            revision=normalized_revision,
            source_id=normalized_source_id,
            snapshot_sha256=normalized_hash,
        ),
    }


def build_accounting_request(
    document: Mapping[str, Any],
    *,
    run_id: str,
    revision: int,
    scope_ref: str,
    source_id: str,
    snapshot_sha256: str,
) -> dict[str, Any]:
    """Build deterministically without inheriting process Decimal context."""
    context = Context(
        prec=_calculation_precision(document),
        rounding=ROUND_HALF_EVEN,
        Emin=-_MAX_CALCULATION_EXPONENT,
        Emax=_MAX_CALCULATION_EXPONENT,
    )
    with localcontext(context):
        return _build_accounting_request_in_context(
            document,
            run_id=run_id,
            revision=revision,
            scope_ref=scope_ref,
            source_id=source_id,
            snapshot_sha256=snapshot_sha256,
        )


__all__ = ["build_accounting_request"]
