from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from trusted_ceo_agent.contracts.ids import make_id


def build_capability_map(
    requirements: Mapping[str, Sequence[str]],
    available_source_roles: Iterable[str],
    *,
    blocking_quality_by_role: Mapping[str, Sequence[str]] | None = None,
) -> dict:
    available = set(available_source_roles)
    blocking = blocking_quality_by_role or {}
    capabilities: list[dict] = []
    for capability_code, required_roles in sorted(requirements.items()):
        required = set(required_roles)
        present = sorted(required & available)
        missing = sorted(required - available)
        quality_ids = sorted({issue for role in required for issue in blocking.get(role, ())})
        if not present:
            status = "unsupported"
            reasons = ["required_source_roles_missing"]
        elif missing or quality_ids:
            status = "partial"
            reasons = (["required_source_roles_missing"] if missing else []) + (["blocking_quality"] if quality_ids else [])
        else:
            status = "available"
            reasons = []
        identity = {"capability_code": capability_code, "required_roles": sorted(required)}
        capabilities.append({
            "capability_id": make_id("capability", identity),
            "capability_code": capability_code,
            "status": status,
            "available_source_roles": present,
            "missing_source_roles": missing,
            "quality_issue_ids": quality_ids,
            "reason_codes": reasons,
        })
    return {
        "capability_map_id": make_id("capability_map", capabilities),
        "capabilities": capabilities,
    }

