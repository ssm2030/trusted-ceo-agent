from __future__ import annotations

import hashlib
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.ids import make_id


def quality_issue(
    *,
    issue_code: str,
    severity: str,
    reason_code: str,
    source_ref: dict[str, Any] | None = None,
    affected_field: str | None = None,
    raw_value: Any = None,
    normalized_role: str | None = None,
    suggested_resolution: str = "",
) -> dict[str, Any]:
    raw_hash = None if raw_value is None else hashlib.sha256(canonical_bytes(raw_value)).hexdigest()
    identity = {
        "issue_code": issue_code,
        "source_ref": source_ref,
        "affected_field": affected_field,
        "raw_value_hash": raw_hash,
        "reason_code": reason_code,
    }
    return {
        "quality_issue_id": make_id("quality", identity),
        "source_ref": source_ref,
        "issue_code": issue_code,
        "severity": severity,
        "affected_field": affected_field,
        "raw_value_hash": raw_hash,
        "normalized_role": normalized_role,
        "reason_code": reason_code,
        "suggested_resolution": suggested_resolution,
        "resolution_status": "open",
    }

