from __future__ import annotations

import json
import unicodedata
from decimal import Decimal
from typing import Any, Collection


DEFAULT_MAX_DEPTH = 32
DEFAULT_MAX_ITEMS = 100_000
DEFAULT_MAX_STRING = 1_000_000


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    seen_raw: set[str] = set()
    for raw_key, value in pairs:
        if raw_key in seen_raw:
            raise ValueError(f"duplicate JSON key: {raw_key}")
        seen_raw.add(raw_key)
        key = unicodedata.normalize("NFC", raw_key)
        if key in result:
            raise ValueError(f"JSON keys collide after NFC normalization: {raw_key}")
        result[key] = value
    return result


def _check_limits(value: Any, depth: int, item_count: list[int]) -> None:
    if depth > DEFAULT_MAX_DEPTH:
        raise ValueError("JSON maximum depth exceeded")
    if isinstance(value, str):
        if len(value) > DEFAULT_MAX_STRING:
            raise ValueError("JSON string limit exceeded")
        return
    if isinstance(value, dict):
        item_count[0] += len(value)
        if item_count[0] > DEFAULT_MAX_ITEMS:
            raise ValueError("JSON item limit exceeded")
        for key, child in value.items():
            _check_limits(key, depth + 1, item_count)
            _check_limits(child, depth + 1, item_count)
    elif isinstance(value, list):
        item_count[0] += len(value)
        if item_count[0] > DEFAULT_MAX_ITEMS:
            raise ValueError("JSON item limit exceeded")
        for child in value:
            _check_limits(child, depth + 1, item_count)


def strict_loads(payload: str | bytes) -> Any:
    text = payload.decode("utf-8", errors="strict") if isinstance(payload, bytes) else payload
    value = json.loads(
        text,
        object_pairs_hook=_object_pairs,
        parse_int=Decimal,
        parse_float=Decimal,
        parse_constant=_reject_constant,
    )
    _check_limits(value, 0, [0])
    return value


def canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("non-finite decimal is forbidden")
    if value == 0:
        return "0"
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _pointer_escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _canonical_value(value: Any, path: str, set_paths: Collection[str]) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise ValueError("binary floating point is forbidden")
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for raw_key, child in value.items():
            if not isinstance(raw_key, str):
                raise ValueError("JSON object keys must be strings")
            key = unicodedata.normalize("NFC", raw_key)
            if key in normalized:
                raise ValueError("object keys collide after NFC normalization")
            child_path = f"{path}/{_pointer_escape(key)}"
            normalized[key] = _canonical_value(child, child_path, set_paths)
        return {key: normalized[key] for key in sorted(normalized)}
    if isinstance(value, (list, tuple)):
        items = [_canonical_value(child, f"{path}/{index}", set_paths) for index, child in enumerate(value)]
        if path in set_paths:
            encoded = [
                json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                for item in items
            ]
            if len(encoded) != len(set(encoded)):
                raise ValueError(f"duplicate member in canonical set array: {path}")
            items = [item for _, item in sorted(zip(encoded, items), key=lambda pair: pair[0])]
        return items
    raise ValueError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_bytes(value: Any, set_paths: Collection[str] | None = None) -> bytes:
    normalized = _canonical_value(value, "", set_paths or frozenset())
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

