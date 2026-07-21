from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from trusted_ceo_agent.canonical import strict_loads
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.web_report.contract_semantics import (
    MAX_BUNDLE_BYTES,
    MAX_CHARTS,
    MAX_CHART_POINTS,
    MAX_ISSUES,
    MAX_PREVIEW_BYTES,
    WebReportContractError,
    validate_bundle_document,
)


CONTRACT_ROOT = (
    Path(__file__).resolve().parents[4] / "contracts" / "web-report" / "v1"
)
def _schema_compatible_numbers(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {key: _schema_compatible_numbers(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_schema_compatible_numbers(child) for child in value]
    return value


def load_bundle_bytes(payload: bytes) -> dict[str, Any]:
    if len(payload) > MAX_BUNDLE_BYTES:
        raise WebReportContractError(
            f"web report bundle exceeds 52_428_800 bytes: {len(payload)}"
        )
    try:
        value = strict_loads(payload)
    except (UnicodeError, ValueError) as error:
        raise WebReportContractError(f"invalid web report JSON: {error}") from error
    if not isinstance(value, dict):
        raise WebReportContractError("web report bundle must be an object")
    value = _schema_compatible_numbers(value)
    try:
        SchemaStore(CONTRACT_ROOT).validate("web-report-bundle.schema.json", value)
    except ContractError as error:
        raise WebReportContractError(f"web report schema invalid: {error}") from error
    validate_bundle_document(value)
    return value




def validate_eligibility_decision(decision: Mapping[str, Any]) -> None:
    try:
        SchemaStore(CONTRACT_ROOT).validate(
            "viewer-eligibility-decision.schema.json",
            _schema_compatible_numbers(decision),
        )
    except ContractError as error:
        raise WebReportContractError(
            f"viewer eligibility decision schema invalid: {error}"
        ) from error

    badges = {
        "trusted_final": "승인·검증된 실행본",
        "poc_fixture": "검증된 POC 시연 실행본",
        "unverified_import": "출처 미확인 묶음",
        "rejected": "열 수 없는 묶음",
    }
    mode = decision["viewer_mode"]
    if decision["badge_label_ko"] != badges[mode]:
        raise WebReportContractError("viewer eligibility badge label mismatch")
    failure_code = decision["failure_code"]
    failure_message = decision["failure_message"]
    if mode == "rejected":
        if decision["eligible"]:
            raise WebReportContractError("rejected viewer mode cannot be eligible")
        if failure_code is None or failure_message is None:
            raise WebReportContractError(
                "rejected viewer mode requires failure code and message"
            )
    else:
        if not decision["eligible"]:
            raise WebReportContractError("eligible viewer mode must be eligible")
        if failure_code is not None or failure_message is not None:
            raise WebReportContractError(
                "eligible viewer mode must not include failure code and message"
            )
