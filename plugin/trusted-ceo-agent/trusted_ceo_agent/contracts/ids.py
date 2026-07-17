from __future__ import annotations

import hashlib
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes


def make_id(kind: str, payload: Any) -> str:
    if not kind or not kind.replace("-", "").replace("_", "").isalnum():
        raise ValueError("invalid ID kind")
    digest = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    return f"{kind}_{digest[:24]}"


def fact_id(
    fact_kind: str,
    fact_code: str,
    semantic_role: str,
    scope: dict[str, Any],
    time: dict[str, Any],
    lineage_fingerprint: str | None = None,
    comparison_context: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "fact_kind": fact_kind,
        "fact_code": fact_code,
        "semantic_role": semantic_role,
        "scope": scope,
        "time": time,
        "comparison_context": comparison_context or {},
    }
    if fact_kind == "observed":
        if not lineage_fingerprint:
            raise ValueError("observed Fact ID requires lineage")
        payload["lineage_fingerprint"] = lineage_fingerprint
    return make_id("fact", payload)


def signal_id(payload: Any) -> str:
    return make_id("signal", payload)


def evidence_link_id(payload: Any) -> str:
    return make_id("evidence", payload)
