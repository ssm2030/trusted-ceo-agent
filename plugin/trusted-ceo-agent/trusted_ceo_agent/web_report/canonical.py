from __future__ import annotations

import hashlib
from copy import deepcopy
from decimal import Decimal
from typing import Any, Mapping

import rfc8785


def _compatible(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite JSON number is forbidden")
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {str(key): _compatible(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_compatible(child) for child in value]
    return value


def jcs_bytes(value: Any) -> bytes:
    """Return RFC 8785 JSON Canonicalization Scheme bytes."""

    return rfc8785.dumps(_compatible(value))


def jcs_sha256(
    value: Mapping[str, Any],
    *,
    omit_root_field: str | None = None,
) -> str:
    """Hash JCS bytes, optionally omitting one top-level field."""

    body = deepcopy(dict(value))
    if omit_root_field is not None:
        body.pop(omit_root_field, None)
    return hashlib.sha256(jcs_bytes(body)).hexdigest()
