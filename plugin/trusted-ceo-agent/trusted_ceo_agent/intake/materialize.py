from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from trusted_ceo_agent.canonical import canonical_bytes, canonical_decimal
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.evidence.facts import build_observed_fact
from trusted_ceo_agent.evidence.lineage import build_lineage_entry_payload
from trusted_ceo_agent.intake.mapping import ResolvedFieldMapping, validate_unit_contract
from trusted_ceo_agent.intake.models import ParsedDataset, ParsedRecord
from trusted_ceo_agent.intake.quality import quality_issue


@dataclass(frozen=True)
class MaterializationResult:
    fact_register: tuple[dict[str, Any], ...]
    data_quality_register: tuple[dict[str, Any], ...]
    lineage_files: Mapping[str, bytes]


def _time_context(record: ParsedRecord, field: str) -> dict[str, str]:
    raw = record.values.get(field)
    if field == "period":
        value = str(raw).strip()
        if re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value) is None:
            raise ContractError("canonical period must use YYYY-MM")
        return {"period": value}
    if field == "as_of":
        value = str(raw).strip()
        try:
            date.fromisoformat(value)
        except ValueError as error:
            raise ContractError("canonical as_of must use ISO date") from error
        return {"as_of": value}
    raise ContractError("canonical mapping requires period or as_of")


def _scope(record: ParsedRecord, mapping: ResolvedFieldMapping) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for field, dimension_code in mapping.scope_fields:
        raw = record.values.get(field)
        value = "" if raw is None else str(raw).strip()
        if not value:
            raise ContractError(f"canonical scope member is missing: {field}")
        result.append({"dimension_code": dimension_code, "member_code": value})
    return result


def _value(record: ParsedRecord, mapping: ResolvedFieldMapping) -> dict[str, Any]:
    raw = record.values.get(mapping.source_field)
    if isinstance(raw, bool) or raw is None or (isinstance(raw, str) and not raw.strip()):
        raise ContractError(f"canonical value is missing: {mapping.source_field}")
    if mapping.data_type == "date":
        try:
            value = date.fromisoformat(str(raw).strip()).isoformat()
        except ValueError as error:
            raise ContractError(f"canonical date is invalid: {mapping.source_field}") from error
        return {
            "value_type": "date",
            "canonical_value": value,
            "unit_code": None,
            "currency_code": None,
            "scale": None,
        }
    try:
        value = Decimal(str(raw).strip())
    except InvalidOperation as error:
        raise ContractError(f"canonical number is invalid: {mapping.source_field}") from error
    if not value.is_finite():
        raise ContractError(f"canonical number is not finite: {mapping.source_field}")
    if mapping.data_type == "integer":
        if value != value.to_integral_value():
            raise ContractError(f"canonical integer is invalid: {mapping.source_field}")
        canonical_value: str | int = int(value)
    elif mapping.data_type == "decimal":
        canonical_value = canonical_decimal(value)
    else:
        raise ContractError(f"canonical materializer does not support data_type: {mapping.data_type}")
    currency_code = mapping.unit_code if (
        isinstance(mapping.unit_code, str) and re.fullmatch(r"[A-Z]{3}", mapping.unit_code)
    ) else None
    return {
        "value_type": mapping.data_type,
        "canonical_value": canonical_value,
        "unit_code": mapping.unit_code,
        "currency_code": currency_code,
        "scale": mapping.scale,
    }

def materialize_observed_facts(
    dataset: ParsedDataset,
    mappings: Sequence[ResolvedFieldMapping],
) -> MaterializationResult:
    facts: list[dict[str, Any]] = []
    quality_issues: list[dict[str, Any]] = []
    lineage_files: dict[str, bytes] = {}
    occurrences: Counter[str] = Counter()
    pending: list[tuple[ResolvedFieldMapping, ParsedRecord, list[str], dict[str, Any], list[dict[str, str]], dict[str, str], bytes]] = []
    for mapping in sorted(mappings, key=lambda item: item.source_field):
        if mapping.source_id != dataset.source_id or not mapping.confirmed:
            raise ContractError("materialization requires a confirmed mapping for the dataset")
        validate_unit_contract(
            mapping.data_type, mapping.unit_policy, mapping.unit_code, mapping.scale
        )
        selected_fields = sorted({
            mapping.source_field,
            mapping.time_field,
            *(field for field, _ in mapping.scope_fields),
        })
        for record in dataset.records:
            try:
                fact_value = _value(record, mapping)
            except ContractError:
                is_date = mapping.data_type == "date"
                quality_issues.append(quality_issue(
                    issue_code="invalid_date" if is_date else "invalid_decimal",
                    severity="blocking",
                    reason_code="canonical_date_invalid" if is_date else "canonical_number_invalid",
                    source_ref={"source_id": dataset.source_id, "locator": record.locator},
                    affected_field=mapping.source_field,
                    raw_value=record.values.get(mapping.source_field),
                    normalized_role=mapping.metric_code,
                    suggested_resolution=(
                        "Provide an ISO date in the confirmed canonical column."
                        if is_date
                        else "Provide a finite numeric value in the confirmed canonical column."
                    ),
                ))
                continue
            try:
                fact_scope = _scope(record, mapping)
            except ContractError:
                affected = next(
                    (field for field, _ in mapping.scope_fields if not str(record.values.get(field) or "").strip()),
                    mapping.scope_fields[0][0] if mapping.scope_fields else mapping.source_field,
                )
                quality_issues.append(quality_issue(
                    issue_code="inconsistent_dimension",
                    severity="blocking",
                    reason_code="canonical_scope_member_missing",
                    source_ref={"source_id": dataset.source_id, "locator": record.locator},
                    affected_field=affected,
                    raw_value=record.values.get(affected),
                    normalized_role=mapping.dimension_code,
                    suggested_resolution="Provide a non-empty member in every confirmed canonical scope column.",
                ))
                continue
            try:
                fact_time = _time_context(record, mapping.time_field)
            except ContractError:
                quality_issues.append(quality_issue(
                    issue_code="ambiguous_period" if mapping.time_field == "period" else "invalid_date",
                    severity="blocking",
                    reason_code="canonical_time_invalid",
                    source_ref={"source_id": dataset.source_id, "locator": record.locator},
                    affected_field=mapping.time_field,
                    raw_value=record.values.get(mapping.time_field),
                    normalized_role=mapping.time_role,
                    suggested_resolution="Provide a valid value in the confirmed canonical time column.",
                ))
                continue
            business_key = canonical_bytes({
                "metric_code": mapping.metric_code,
                "observation_role": mapping.observation_role,
                "scope": fact_scope,
                "time_context": fact_time,
            })
            pending.append((mapping, record, selected_fields, fact_value, fact_scope, fact_time, business_key))

    key_counts: Counter[bytes] = Counter(item[6] for item in pending)
    duplicate_keys: set[bytes] = set()
    for mapping, _, _, _, _, _, business_key in pending:
        if key_counts[business_key] <= 1 or business_key in duplicate_keys:
            continue
        duplicate_keys.add(business_key)
        quality_issues.append(quality_issue(
            issue_code="duplicate_business_key",
            severity="blocking",
            reason_code="duplicate_metric_scope_time_key",
            source_ref={
                "source_id": dataset.source_id,
                "business_key_hash": hashlib.sha256(business_key).hexdigest(),
            },
            affected_field=mapping.source_field,
            raw_value=None,
            normalized_role=mapping.metric_code,
            suggested_resolution="Deduplicate or reconcile records with the same metric, scope, and time key.",
        ))

    for mapping, record, selected_fields, fact_value, fact_scope, fact_time, business_key in pending:
        if business_key in duplicate_keys:
            continue
        selected_row = {field: record.values.get(field) for field in selected_fields}
        row_fingerprint = hashlib.sha256(canonical_bytes(selected_row)).hexdigest()
        occurrences[row_fingerprint] += 1
        lineage_ref, lineage_payload = build_lineage_entry_payload(
            selected_row, occurrences[row_fingerprint]
        )
        existing = lineage_files.get(lineage_ref)
        if existing is not None and existing != lineage_payload:
            raise ContractError("lineage content-address collision")
        lineage_files[lineage_ref] = lineage_payload
        source_ref = dataset.source_reference(
            record,
            selected_fields,
            "observe",
            lineage_ref,
            observation_role=mapping.observation_role,
        )
        facts.append(build_observed_fact(
            fact_code=mapping.metric_code,
            metric_code=mapping.metric_code,
            semantic_role="observation",
            observation_role=mapping.observation_role,
            scope=fact_scope,
            time_context=fact_time,
            value=fact_value,
            source_refs=[source_ref],
        ))
    return MaterializationResult(
        fact_register=tuple(sorted(facts, key=lambda item: item["fact_id"])),
        data_quality_register=tuple(sorted(quality_issues, key=lambda item: item["quality_issue_id"])),
        lineage_files={key: lineage_files[key] for key in sorted(lineage_files)},
    )
