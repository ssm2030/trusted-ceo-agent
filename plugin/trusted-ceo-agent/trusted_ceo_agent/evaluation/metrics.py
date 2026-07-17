from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes, canonical_decimal
from trusted_ceo_agent.errors import ContractError


QUALITY_SCORE_METRICS = (
    "critical_recall",
    "mandatory_recall",
    "cross_domain_trigger_recall",
    "evidence_role_coverage",
    "counter_evidence_coverage",
    "authority_state_accuracy",
    "expert_practice_quality",
)
COUNT_METRICS = (
    "unsupported_claim_count",
    "prohibited_conclusion_count",
)
QUALITY_METRIC_FIELDS = frozenset(QUALITY_SCORE_METRICS + COUNT_METRICS)
RESERVED_TIMING_KEYS = frozenset({
    "stage_timing",
    "stage_timings",
    "timing_telemetry",
    "runtime_timing",
    "_timing",
})


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def require_hash(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ContractError(f"{field} must be a lowercase SHA-256")
    return value


def require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{field} must be a non-empty string")
    return value


def require_integer(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise ContractError(f"{field} must be an integer >= {minimum}")
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContractError(f"{field} must be an integer >= {minimum}")
    return value


def decimal_value(
    value: Any,
    field: str,
    *,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ContractError(f"{field} must be a finite decimal")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ContractError(f"{field} must be a finite decimal") from error
    if not parsed.is_finite():
        raise ContractError(f"{field} must be a finite decimal")
    if minimum is not None and parsed < minimum:
        raise ContractError(f"{field} must be >= {canonical_decimal(minimum)}")
    if maximum is not None and parsed > maximum:
        raise ContractError(f"{field} must be <= {canonical_decimal(maximum)}")
    return parsed


def score_text(value: Any, field: str) -> str:
    return canonical_decimal(
        decimal_value(value, field, minimum=Decimal("0"), maximum=Decimal("1"))
    )


def signed_score_text(value: Decimal) -> str:
    if value < Decimal("-1") or value > Decimal("1"):
        raise ContractError("quality delta must be between -1 and 1")
    return canonical_decimal(value)


def build_quality_metrics(
    *,
    critical_recall: Any,
    mandatory_recall: Any,
    cross_domain_trigger_recall: Any,
    evidence_role_coverage: Any,
    counter_evidence_coverage: Any,
    authority_state_accuracy: Any,
    expert_practice_quality: Any | None,
    unsupported_claim_count: Any,
    prohibited_conclusion_count: Any,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "critical_recall": score_text(critical_recall, "critical_recall"),
        "mandatory_recall": score_text(mandatory_recall, "mandatory_recall"),
        "cross_domain_trigger_recall": score_text(
            cross_domain_trigger_recall, "cross_domain_trigger_recall"
        ),
        "evidence_role_coverage": score_text(
            evidence_role_coverage, "evidence_role_coverage"
        ),
        "counter_evidence_coverage": score_text(
            counter_evidence_coverage, "counter_evidence_coverage"
        ),
        "authority_state_accuracy": score_text(
            authority_state_accuracy, "authority_state_accuracy"
        ),
        "expert_practice_quality": (
            None
            if expert_practice_quality is None
            else score_text(expert_practice_quality, "expert_practice_quality")
        ),
        "unsupported_claim_count": require_integer(
            unsupported_claim_count, "unsupported_claim_count"
        ),
        "prohibited_conclusion_count": require_integer(
            prohibited_conclusion_count, "prohibited_conclusion_count"
        ),
    }
    return metrics


def validate_quality_metrics(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != QUALITY_METRIC_FIELDS:
        raise ContractError("quality_metrics fields do not match the contract")
    return build_quality_metrics(
        critical_recall=value["critical_recall"],
        mandatory_recall=value["mandatory_recall"],
        cross_domain_trigger_recall=value["cross_domain_trigger_recall"],
        evidence_role_coverage=value["evidence_role_coverage"],
        counter_evidence_coverage=value["counter_evidence_coverage"],
        authority_state_accuracy=value["authority_state_accuracy"],
        expert_practice_quality=value["expert_practice_quality"],
        unsupported_claim_count=value["unsupported_claim_count"],
        prohibited_conclusion_count=value["prohibited_conclusion_count"],
    )


def _reject_timing_telemetry(value: Any, path: str = "") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ContractError("semantic output keys must be strings")
            child_path = f"{path}/{key}"
            if key in RESERVED_TIMING_KEYS:
                raise ContractError(
                    f"timing telemetry is forbidden in semantic output: {child_path}"
                )
            _reject_timing_telemetry(child, child_path)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_timing_telemetry(child, f"{path}/{index}")


def semantic_output_hash(value: Any) -> str:
    _reject_timing_telemetry(value)
    try:
        payload = canonical_bytes(value)
    except (TypeError, ValueError) as error:
        raise ContractError(f"semantic output is not canonical JSON: {error}") from error
    return hashlib.sha256(payload).hexdigest()


def byte_output_hash(payload: Any) -> str:
    if not isinstance(payload, bytes):
        raise ContractError("output_bytes must be bytes")
    return hashlib.sha256(payload).hexdigest()


def mean_score(values: Sequence[Any], field: str) -> Decimal:
    if not values:
        raise ContractError(f"{field} requires at least one score")
    parsed = [decimal_value(value, field) for value in values]
    return sum(parsed, Decimal("0")) / Decimal(len(parsed))


def nearest_rank_percentile(values: Sequence[Any], percentile: int) -> int:
    if not values:
        raise ContractError("percentile requires at least one observation")
    if percentile < 1 or percentile > 100:
        raise ContractError("percentile must be between 1 and 100")
    normalized = sorted(require_integer(value, "timing", minimum=0) for value in values)
    index = max(0, math.ceil((percentile / 100) * len(normalized)) - 1)
    return normalized[index]
