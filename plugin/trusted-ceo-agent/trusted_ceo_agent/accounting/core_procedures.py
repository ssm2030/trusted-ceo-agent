"""Deterministic Tier 0 accounting integrity procedures (AC-01 through AC-05)."""

from __future__ import annotations

import copy
import hashlib
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes, canonical_decimal
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError

_SCHEMA_STORE = SchemaStore()
_ISSUE_IDS = ("AC-01", "AC-02", "AC-03", "AC-04", "AC-05")
_TOP_FIELDS = {
    "run_id",
    "revision",
    "source_manifests",
    "journal_headers",
    "journal_lines",
    "trial_balance",
    "subledger_balances",
}
_MANIFEST_FIELDS = {
    "source_id",
    "source_sha256",
    "period_start",
    "period_end",
    "header_count",
    "line_count",
    "debit_total",
    "credit_total",
}
_HEADER_FIELDS = {
    "journal_id",
    "source_id",
    "sequence",
    "status",
    "entity",
    "currency",
    "period",
}
_LINE_FIELDS = {
    "line_id",
    "journal_id",
    "account_id",
    "debit",
    "credit",
    "entity",
    "currency",
    "period",
}
_TB_FIELDS = {
    "account_id",
    "entity",
    "currency",
    "period",
    "prior_closing",
    "opening",
    "debit_turnover",
    "credit_turnover",
    "closing",
    "control_subledger",
}
_SUBLEDGER_FIELDS = {
    "subledger",
    "account_id",
    "object_id",
    "entity",
    "currency",
    "period",
    "amount",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


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


def _records(value: Any, fields: set[str], label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ContractError(f"{label} must be an array")
    return [_object(item, fields, f"{label}[{index}]") for index, item in enumerate(value)]


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
    if not number.is_finite():
        raise ContractError(f"{label} must be finite")
    return canonical_decimal(number)


def _unique(records: Sequence[Mapping[str, Any]], key, label: str) -> None:
    keys = [key(item) for item in records]
    if len(keys) != len(set(keys)):
        raise ContractError(f"{label} contains duplicate records")


def _normalize_input(value: Mapping[str, Any]) -> dict[str, Any]:
    root = _object(value, _TOP_FIELDS, "Tier 0 input")
    run_id = _text(root["run_id"], "run_id")
    revision = _integer(root["revision"], "revision")

    manifests: list[dict[str, Any]] = []
    for index, raw in enumerate(_records(root["source_manifests"], _MANIFEST_FIELDS, "source_manifests")):
        source_hash = _text(raw["source_sha256"], f"source_manifests[{index}].source_sha256")
        if not _SHA256.fullmatch(source_hash):
            raise ContractError(f"source_manifests[{index}].source_sha256 must be lowercase SHA-256")
        manifests.append(
            {
                "source_id": _text(raw["source_id"], f"source_manifests[{index}].source_id"),
                "source_sha256": source_hash,
                "period_start": _text(raw["period_start"], f"source_manifests[{index}].period_start"),
                "period_end": _text(raw["period_end"], f"source_manifests[{index}].period_end"),
                "header_count": _integer(raw["header_count"], f"source_manifests[{index}].header_count"),
                "line_count": _integer(raw["line_count"], f"source_manifests[{index}].line_count"),
                "debit_total": _decimal(raw["debit_total"], f"source_manifests[{index}].debit_total"),
                "credit_total": _decimal(raw["credit_total"], f"source_manifests[{index}].credit_total"),
            }
        )
    _unique(manifests, lambda item: item["source_id"], "source_manifests")

    headers: list[dict[str, Any]] = []
    for index, raw in enumerate(_records(root["journal_headers"], _HEADER_FIELDS, "journal_headers")):
        headers.append(
            {
                name: _text(raw[name], f"journal_headers[{index}].{name}")
                for name in ("journal_id", "source_id", "status", "entity", "currency", "period")
            }
            | {"sequence": _integer(raw["sequence"], f"journal_headers[{index}].sequence")}
        )
    _unique(headers, lambda item: item["journal_id"], "journal_headers")

    lines: list[dict[str, Any]] = []
    for index, raw in enumerate(_records(root["journal_lines"], _LINE_FIELDS, "journal_lines")):
        lines.append(
            {
                name: _text(raw[name], f"journal_lines[{index}].{name}")
                for name in ("line_id", "journal_id", "account_id", "entity", "currency", "period")
            }
            | {
                "debit": _decimal(raw["debit"], f"journal_lines[{index}].debit"),
                "credit": _decimal(raw["credit"], f"journal_lines[{index}].credit"),
            }
        )
    _unique(lines, lambda item: item["line_id"], "journal_lines")

    trial_balance: list[dict[str, Any]] = []
    for index, raw in enumerate(_records(root["trial_balance"], _TB_FIELDS, "trial_balance")):
        control = raw["control_subledger"]
        if control is not None:
            control = _text(control, f"trial_balance[{index}].control_subledger")
        trial_balance.append(
            {
                name: _text(raw[name], f"trial_balance[{index}].{name}")
                for name in ("account_id", "entity", "currency", "period")
            }
            | {
                name: _decimal(raw[name], f"trial_balance[{index}].{name}")
                for name in ("prior_closing", "opening", "debit_turnover", "credit_turnover", "closing")
            }
            | {"control_subledger": control}
        )
    dimension_key = lambda item: (
        item["account_id"],
        item["entity"],
        item["currency"],
        item["period"],
    )
    _unique(trial_balance, dimension_key, "trial_balance")

    subledgers: list[dict[str, Any]] = []
    for index, raw in enumerate(
        _records(root["subledger_balances"], _SUBLEDGER_FIELDS, "subledger_balances")
    ):
        subledgers.append(
            {
                name: _text(raw[name], f"subledger_balances[{index}].{name}")
                for name in (
                    "subledger",
                    "account_id",
                    "object_id",
                    "entity",
                    "currency",
                    "period",
                )
            }
            | {"amount": _decimal(raw["amount"], f"subledger_balances[{index}].amount")}
        )
    _unique(
        subledgers,
        lambda item: (
            item["subledger"],
            item["account_id"],
            item["object_id"],
            item["entity"],
            item["currency"],
            item["period"],
        ),
        "subledger_balances",
    )

    return {
        "run_id": run_id,
        "revision": revision,
        "source_manifests": sorted(manifests, key=lambda item: item["source_id"]),
        "journal_headers": sorted(
            headers,
            key=lambda item: (
                item["source_id"],
                item["entity"],
                item["currency"],
                item["period"],
                item["sequence"],
                item["journal_id"],
            ),
        ),
        "journal_lines": sorted(lines, key=lambda item: (item["journal_id"], item["line_id"])),
        "trial_balance": sorted(
            trial_balance,
            key=lambda item: (
                item["entity"],
                item["currency"],
                item["period"],
                item["account_id"],
            ),
        ),
        "subledger_balances": sorted(
            subledgers,
            key=lambda item: (
                item["entity"],
                item["currency"],
                item["period"],
                item["subledger"],
                item["account_id"],
                item["object_id"],
            ),
        ),
    }


def _exception(
    code: str,
    scope_ref: str,
    *,
    entity: str | None = None,
    currency: str | None = None,
    period: str | None = None,
    observed: str | None = None,
    expected: str | None = None,
    difference: Decimal | str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "scope_ref": scope_ref,
        "entity": entity,
        "currency": currency,
        "period": period,
        "observed": observed,
        "expected": expected,
        "difference": (
            canonical_decimal(difference)
            if isinstance(difference, Decimal)
            else difference
        ),
    }


def _procedure(issue_id: str, exceptions: list[dict[str, Any]], assessable: bool) -> dict[str, Any]:
    ordered = sorted(
        exceptions,
        key=lambda item: canonical_bytes(item),
    )
    status = "not_assessable" if not assessable else ("exceptions_found" if ordered else "passed")
    return {
        "issue_family_id": issue_id,
        "procedure_id": f"P-{issue_id}",
        "status": status,
        "exception_count": len(ordered),
        "exceptions": ordered,
    }


def _population(
    data: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Mapping[str, Any]], dict[str, list[Mapping[str, Any]]]]:
    manifests = data["source_manifests"]
    headers = data["journal_headers"]
    lines = data["journal_lines"]
    exceptions: list[dict[str, Any]] = []
    header_by_id = {item["journal_id"]: item for item in headers}
    lines_by_journal: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for line in lines:
        lines_by_journal[line["journal_id"]].append(line)

    manifest_ids = {item["source_id"] for item in manifests}
    for header in headers:
        if header["source_id"] not in manifest_ids:
            exceptions.append(_exception("orphan_header_source", header["journal_id"], observed=header["source_id"]))
        if header["journal_id"] not in lines_by_journal:
            exceptions.append(_exception("orphan_header", header["journal_id"]))
    for line in lines:
        header = header_by_id.get(line["journal_id"])
        if header is None:
            exceptions.append(_exception("orphan_line", line["journal_id"], observed=line["line_id"]))
        elif any(line[name] != header[name] for name in ("entity", "currency", "period")):
            exceptions.append(
                _exception(
                    "line_header_dimension_mismatch",
                    line["line_id"],
                    entity=line["entity"],
                    currency=line["currency"],
                    period=line["period"],
                    observed="/".join(line[name] for name in ("entity", "currency", "period")),
                    expected="/".join(header[name] for name in ("entity", "currency", "period")),
                )
            )

    if sum(item["header_count"] for item in manifests) != len(headers):
        exceptions.append(
            _exception(
                "source_header_count_mismatch",
                "population",
                observed=str(len(headers)),
                expected=str(sum(item["header_count"] for item in manifests)),
            )
        )
    if sum(item["line_count"] for item in manifests) != len(lines):
        exceptions.append(
            _exception(
                "source_line_count_mismatch",
                "population",
                observed=str(len(lines)),
                expected=str(sum(item["line_count"] for item in manifests)),
            )
        )

    headers_by_source: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    lines_by_source: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for header in headers:
        headers_by_source[header["source_id"]].append(header)
        for line in lines_by_journal.get(header["journal_id"], []):
            lines_by_source[header["source_id"]].append(line)
    for manifest in manifests:
        source_id = manifest["source_id"]
        source_headers = headers_by_source.get(source_id, [])
        source_lines = lines_by_source.get(source_id, [])
        if len(source_headers) != manifest["header_count"]:
            exceptions.append(
                _exception(
                    "source_header_count_mismatch",
                    source_id,
                    observed=str(len(source_headers)),
                    expected=str(manifest["header_count"]),
                )
            )
        if len(source_lines) != manifest["line_count"]:
            exceptions.append(
                _exception(
                    "source_line_count_mismatch",
                    source_id,
                    observed=str(len(source_lines)),
                    expected=str(manifest["line_count"]),
                )
            )
        debit = sum((Decimal(item["debit"]) for item in source_lines), Decimal(0))
        credit = sum((Decimal(item["credit"]) for item in source_lines), Decimal(0))
        for side, actual in (("debit", debit), ("credit", credit)):
            expected = Decimal(manifest[f"{side}_total"])
            if actual != expected:
                exceptions.append(
                    _exception(
                        f"source_{side}_total_mismatch",
                        source_id,
                        observed=canonical_decimal(actual),
                        expected=canonical_decimal(expected),
                        difference=actual - expected,
                    )
                )

    sequence_groups: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for header in headers:
        sequence_groups[
            (header["source_id"], header["entity"], header["currency"], header["period"])
        ].append(header)
    for (source_id, entity, currency, period), group in sequence_groups.items():
        sequences = [item["sequence"] for item in group]
        counts = Counter(sequences)
        for sequence, count in counts.items():
            if count > 1:
                exceptions.append(
                    _exception(
                        "sequence_duplicate",
                        source_id,
                        entity=entity,
                        currency=currency,
                        period=period,
                        observed=str(sequence),
                    )
                )
        if sequences:
            missing = sorted(set(range(min(sequences), max(sequences) + 1)) - set(sequences))
            for sequence in missing:
                exceptions.append(
                    _exception(
                        "sequence_gap",
                        source_id,
                        entity=entity,
                        currency=currency,
                        period=period,
                        observed=str(sequence),
                    )
                )
    return (
        _procedure("AC-01", exceptions, bool(manifests and headers and lines)),
        header_by_id,
        lines_by_journal,
    )


def _debit_credit(
    headers: Sequence[Mapping[str, Any]],
    lines_by_journal: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    exceptions: list[dict[str, Any]] = []
    for header in headers:
        journal_lines = lines_by_journal.get(header["journal_id"], [])
        if not journal_lines:
            continue
        imbalance = sum(
            (Decimal(item["debit"]) - Decimal(item["credit"]) for item in journal_lines),
            Decimal(0),
        )
        if imbalance:
            exceptions.append(
                _exception(
                    "journal_debit_credit_imbalance",
                    header["journal_id"],
                    entity=header["entity"],
                    currency=header["currency"],
                    period=header["period"],
                    difference=imbalance,
                )
            )
    return _procedure("AC-02", exceptions, bool(headers and any(lines_by_journal.values())))


def _gl_tb(
    lines: Sequence[Mapping[str, Any]],
    trial_balance: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    exceptions: list[dict[str, Any]] = []
    gl: dict[tuple[str, str, str, str], Decimal] = defaultdict(Decimal)
    tb: dict[tuple[str, str, str, str], Decimal] = {}
    for line in lines:
        key = (line["account_id"], line["entity"], line["currency"], line["period"])
        gl[key] += Decimal(line["debit"]) - Decimal(line["credit"])
    for row in trial_balance:
        key = (row["account_id"], row["entity"], row["currency"], row["period"])
        tb[key] = Decimal(row["debit_turnover"]) - Decimal(row["credit_turnover"])
    for key in sorted(set(gl) | set(tb)):
        account, entity, currency, period = key
        actual = gl.get(key, Decimal(0))
        expected = tb.get(key, Decimal(0))
        if actual != expected:
            exceptions.append(
                _exception(
                    "gl_tb_movement_difference",
                    account,
                    entity=entity,
                    currency=currency,
                    period=period,
                    observed=canonical_decimal(actual),
                    expected=canonical_decimal(expected),
                    difference=actual - expected,
                )
            )
    return _procedure("AC-03", exceptions, bool(lines and trial_balance))


def _opening_roll_forward(trial_balance: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    exceptions: list[dict[str, Any]] = []
    for row in trial_balance:
        identity = {
            "entity": row["entity"],
            "currency": row["currency"],
            "period": row["period"],
        }
        prior = Decimal(row["prior_closing"])
        opening = Decimal(row["opening"])
        movement = Decimal(row["debit_turnover"]) - Decimal(row["credit_turnover"])
        closing = Decimal(row["closing"])
        if prior != opening:
            exceptions.append(
                _exception(
                    "prior_closing_opening_difference",
                    row["account_id"],
                    **identity,
                    observed=canonical_decimal(opening),
                    expected=canonical_decimal(prior),
                    difference=opening - prior,
                )
            )
        expected_closing = opening + movement
        if expected_closing != closing:
            exceptions.append(
                _exception(
                    "opening_roll_forward_residual",
                    row["account_id"],
                    **identity,
                    observed=canonical_decimal(closing),
                    expected=canonical_decimal(expected_closing),
                    difference=closing - expected_closing,
                )
            )
    return _procedure("AC-04", exceptions, bool(trial_balance))


def _subledger_gl(
    trial_balance: Sequence[Mapping[str, Any]],
    subledgers: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    exceptions: list[dict[str, Any]] = []
    gl: dict[tuple[str, str, str, str, str], Decimal] = {}
    sub: dict[tuple[str, str, str, str, str], Decimal] = defaultdict(Decimal)
    for row in trial_balance:
        if row["control_subledger"] is not None:
            key = (
                row["control_subledger"],
                row["account_id"],
                row["entity"],
                row["currency"],
                row["period"],
            )
            gl[key] = Decimal(row["closing"])
    for row in subledgers:
        key = (
            row["subledger"],
            row["account_id"],
            row["entity"],
            row["currency"],
            row["period"],
        )
        sub[key] += Decimal(row["amount"])
    for key in sorted(set(gl) | set(sub)):
        subledger, account, entity, currency, period = key
        if key not in gl:
            code = "gl_control_missing_for_subledger"
        elif key not in sub:
            code = "subledger_population_missing"
        elif gl[key] != sub[key]:
            code = "subledger_gl_difference"
        else:
            continue
        observed = sub.get(key, Decimal(0))
        expected = gl.get(key, Decimal(0))
        exceptions.append(
            _exception(
                code,
                f"{subledger}:{account}",
                entity=entity,
                currency=currency,
                period=period,
                observed=canonical_decimal(observed),
                expected=canonical_decimal(expected),
                difference=observed - expected,
            )
        )
    return _procedure("AC-05", exceptions, bool(trial_balance and subledgers))


def run_tier_zero_procedures(value: Mapping[str, Any]) -> dict[str, Any]:
    """Run the five mandatory, deterministic accounting integrity procedures."""
    if not isinstance(value, Mapping):
        raise ContractError("Tier 0 input must be an object")
    data = _normalize_input(value)
    ac01, _header_by_id, lines_by_journal = _population(data)
    procedures = [
        ac01,
        _debit_credit(data["journal_headers"], lines_by_journal),
        _gl_tb(data["journal_lines"], data["trial_balance"]),
        _opening_roll_forward(data["trial_balance"]),
        _subledger_gl(data["trial_balance"], data["subledger_balances"]),
    ]
    status_counts = Counter(item["status"] for item in procedures)
    population_status_counts = dict(
        sorted(Counter(item["status"] for item in data["journal_headers"]).items())
    )
    status_populations = [
        {
            "status": status,
            "journal_ids": sorted(
                item["journal_id"] for item in data["journal_headers"] if item["status"] == status
            ),
        }
        for status in sorted(population_status_counts)
    ]
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": data["run_id"],
        "revision": data["revision"],
        "input_hash": _digest(data),
        "source_manifests": copy.deepcopy(data["source_manifests"]),
        "population_status_counts": population_status_counts,
        "status_populations": status_populations,
        "procedure_results": procedures,
        "procedure_status_counts": dict(sorted(status_counts.items())),
        "coverage_complete": all(item["status"] != "not_assessable" for item in procedures),
        "authority_ceiling": "Boundary",
    }
    result = {**body, "content_hash": _digest(body)}
    _SCHEMA_STORE.validate("accounting-tier-zero-result.schema.json", result)
    return result


def verify_tier_zero_result(value: Mapping[str, Any]) -> dict[str, Any]:
    """Verify a closed Tier 0 result and its deterministic execution evidence hash."""
    if not isinstance(value, Mapping):
        raise ContractError("Tier 0 result must be an object")
    _SCHEMA_STORE.validate("accounting-tier-zero-result.schema.json", value)
    if value["content_hash"] != _digest(value, "content_hash"):
        raise ContractError("Tier 0 result content hash mismatch")
    results = value["procedure_results"]
    if [item["issue_family_id"] for item in results] != list(_ISSUE_IDS):
        raise ContractError("Tier 0 result must contain AC-01 through AC-05 in order")
    for item in results:
        if item["procedure_id"] != f"P-{item['issue_family_id']}":
            raise ContractError("Tier 0 procedure reference mismatch")
        if item["exception_count"] != len(item["exceptions"]):
            raise ContractError("Tier 0 exception count mismatch")
        if item["status"] == "passed" and item["exceptions"]:
            raise ContractError("passed Tier 0 procedure cannot contain exceptions")
        if item["status"] == "exceptions_found" and not item["exceptions"]:
            raise ContractError("exceptions_found Tier 0 procedure requires exceptions")
    expected_coverage = all(item["status"] != "not_assessable" for item in results)
    if value["coverage_complete"] is not expected_coverage:
        raise ContractError("Tier 0 coverage flag mismatch")
    expected_status_counts = dict(sorted(Counter(item["status"] for item in results).items()))
    if value["procedure_status_counts"] != expected_status_counts:
        raise ContractError("Tier 0 procedure status counts mismatch")
    return copy.deepcopy(dict(value))


def assert_accounting_core_screened(value: Mapping[str, Any]) -> str:
    """Return the sole Tier 0 display claim only for verified, complete execution."""
    trusted = verify_tier_zero_result(value)
    if not trusted["coverage_complete"]:
        raise ContractError("accounting_core_screened requires all five Tier 0 procedures")
    return "accounting_core_screened"
