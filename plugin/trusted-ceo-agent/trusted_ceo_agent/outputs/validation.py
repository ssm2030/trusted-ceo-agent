from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads


ABSOLUTE_PATH = re.compile(
    r"(?:(?<![A-Za-z0-9])[A-Za-z]:[\\/]"
    r"|(?:^|[\s\x22='(),])[\\/]{1,2}(?=[^\\/])"
    r"|file:(?:/{1,3}|\\\\))",
    re.IGNORECASE,
)
DEFAULT_FINAL_RESULT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "schemas" / "final-result.schema.json"
)
AUDIT_MANIFEST_PATH = "final/audit-manifest.json"


class FinalValidationError(ValueError):
    """The trusted final result cannot be published."""


def _schema_compatible_numbers(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {key: _schema_compatible_numbers(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_schema_compatible_numbers(child) for child in value]
    return value


def _walk_strings(value: Any, path: tuple[str, ...] = ()):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, Mapping):
        for key, child in value.items():
            yield from _walk_strings(child, (*path, str(key)))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            yield from _walk_strings(child, (*path, str(index)))


def validate_active_issues(
    issues: Sequence[Mapping[str, Any]],
    evidence_links: Mapping[str, Mapping[str, Any]],
) -> None:
    for issue in issues:
        if issue.get("disposition", "accepted") != "accepted":
            continue
        link_ids = issue.get("evidence_link_ids")
        if not isinstance(link_ids, list) or not link_ids:
            raise FinalValidationError(f"active issue lacks material evidence: {issue.get('issue_id')}")
        for link_id in link_ids:
            if link_id not in evidence_links:
                raise FinalValidationError(f"unknown Evidence Link: {link_id}")
            link = evidence_links[link_id]
            if "source_ids" in link and not link["source_ids"]:
                raise FinalValidationError(f"Evidence Link does not resolve to Source: {link_id}")


def validate_final_approval(approvals: Sequence[Mapping[str, Any]]) -> None:
    if not any(item.get("gate") == "final" and item.get("status") == "current" for item in approvals):
        raise FinalValidationError("a current Final approval is required")


def validate_no_absolute_paths(value: Any) -> None:
    for path, text in _walk_strings(value):
        structured_json_pointer = (
            (bool(path) and path[-1] == "json_pointer")
            or (len(path) >= 2 and path[-2:] == ("locator", "pointer"))
        )
        if structured_json_pointer and text.startswith("/") and "\\" not in text:
            continue
        if ABSOLUTE_PATH.search(text):
            location = "/".join(path) or "<root>"
            raise FinalValidationError(
                f"absolute paths are forbidden in customer output at {location}"
            )


def _validate_final_result_schema(
    result: Mapping[str, Any],
    schema_path: str | Path | None,
) -> bool:
    candidate = Path(schema_path) if schema_path is not None else DEFAULT_FINAL_RESULT_SCHEMA_PATH
    if not candidate.is_file():
        return False
    try:
        schema = _schema_compatible_numbers(strict_loads(candidate.read_bytes()))
        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(schema).iter_errors(result),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
    except (OSError, ValueError, SchemaError) as exc:
        raise FinalValidationError(f"final-result schema could not be loaded: {exc}") from exc
    if errors:
        error = errors[0]
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        raise FinalValidationError(f"final-result schema violation at {location}: {error.message}")
    return True


def validate_final_result(
    result: Mapping[str, Any],
    *,
    evidence_links: Mapping[str, Mapping[str, Any]],
    schema_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate a publishable Final Result against its external trust context."""
    checks: list[str] = []
    schema_validated = _validate_final_result_schema(result, schema_path)
    validate_active_issues(result.get("issues", []), evidence_links)
    checks.append("active_evidence_link_reachability")
    validate_final_approval(result.get("approvals", []))
    checks.append("final_approval_current")
    validate_no_absolute_paths(result)
    checks.append("absolute_path_redaction")
    if schema_validated:
        checks.append("final_result_schema")
    return {
        "status": "passed",
        "checks": checks,
        "issue_count": len(result.get("issues", [])),
    }


def _validate_audit_manifest(package: Mapping[str, bytes]) -> None:
    from trusted_ceo_agent.outputs.audit import build_audit_manifest

    for path, payload in package.items():
        if not isinstance(path, str) or not isinstance(payload, bytes):
            raise FinalValidationError("rendered package must map relative paths to bytes")
    manifest_payload = package.get(AUDIT_MANIFEST_PATH)
    if manifest_payload is None:
        raise FinalValidationError("audit manifest is missing")
    covered_files = {
        path: payload for path, payload in package.items() if path != AUDIT_MANIFEST_PATH
    }
    expected_payload = canonical_bytes(build_audit_manifest(covered_files))
    if manifest_payload != expected_payload:
        raise FinalValidationError("audit manifest does not match rendered package bytes")


def revalidate_package(
    result: Mapping[str, Any],
    package: Mapping[str, bytes],
    *,
    evidence_links: Mapping[str, Mapping[str, Any]],
    schema_path: str | Path | None = None,
) -> dict[str, Any]:
    """Revalidate trust context, audit hashes, and deterministic package rendering."""
    summary = validate_final_result(
        result,
        evidence_links=evidence_links,
        schema_path=schema_path,
    )
    _validate_audit_manifest(package)
    summary["checks"].append("audit_manifest")

    from trusted_ceo_agent.outputs.render import render_package

    expected = render_package(result)
    if set(package) != set(expected):
        raise FinalValidationError("rendered package file set is not deterministic")
    comparison_order = sorted(
        expected,
        key=lambda path: (path == AUDIT_MANIFEST_PATH, path),
    )
    for path in comparison_order:
        if package[path] != expected[path]:
            raise FinalValidationError(f"rendered package differs at {path}")
    summary["checks"].append("deterministic_rerender_byte_equivalence")
    return summary


def validation_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    validate_no_absolute_paths(result)
    return {
        "status": "passed",
        "checks": ["absolute_path_redaction"],
        "issue_count": len(result.get("issues", [])),
    }
