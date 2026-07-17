from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from typing import Any, Mapping

from trusted_ceo_agent.canonical import strict_loads
from trusted_ceo_agent.errors import ContractError, IntegrityError
from trusted_ceo_agent.trust.artifact_store import ArtifactStore


_HASH = re.compile(r"^[0-9a-f]{64}$")


def _native_numbers(value: Any) -> Any:
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    if isinstance(value, dict):
        return {str(key): _native_numbers(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_native_numbers(child) for child in value]
    return value


def _manifest(store: ArtifactStore, revision: int) -> tuple[Any, Mapping[str, Any]]:
    if revision < 1:
        raise ContractError("revision must be positive")
    snapshot = store.verify_revision(revision)
    try:
        value = _native_numbers(
            strict_loads((snapshot / "snapshot-manifest.json").read_bytes())
        )
    except (OSError, UnicodeError, ValueError) as error:
        raise IntegrityError("snapshot manifest is invalid") from error
    if not isinstance(value, Mapping):
        raise IntegrityError("snapshot manifest must be an object")
    if value.get("revision") != revision:
        raise IntegrityError("snapshot manifest revision mismatch")
    return snapshot, value


def final_result_hash_for_revision(store: ArtifactStore, revision: int) -> str:
    """Return the content-verified Final Result hash bound to one revision."""

    snapshot, manifest = _manifest(store, revision)
    entries = [
        entry
        for entry in manifest.get("files", [])
        if isinstance(entry, Mapping) and entry.get("path") == "final/result.json"
    ]
    if len(entries) != 1:
        raise IntegrityError("Final Result manifest entry is missing or duplicated")
    expected = entries[0].get("sha256")
    if not isinstance(expected, str) or _HASH.fullmatch(expected) is None:
        raise IntegrityError("Final Result manifest hash is invalid")
    try:
        actual = hashlib.sha256((snapshot / "final/result.json").read_bytes()).hexdigest()
    except OSError as error:
        raise IntegrityError("Final Result artifact is unavailable") from error
    if actual != expected:
        raise IntegrityError("Final Result hash does not match its immutable manifest")
    return actual


def convert_final_revision(
    store: ArtifactStore,
    *,
    run_id: str,
    revision: int,
    expected_final_result_hash: str,
) -> bytes:
    """Convert a verified final revision through the canonical web exporter.

    The explicit hash pins the immutable Final Result input. The canonical exporter
    validates eligibility and only projects stored Findings, Grades, relations, and
    evidence; this facade performs no analytical inference.
    """

    if _HASH.fullmatch(expected_final_result_hash) is None:
        raise ContractError("expected Final Result hash must be lowercase SHA-256")
    actual_hash = final_result_hash_for_revision(store, revision)
    if actual_hash != expected_final_result_hash:
        raise IntegrityError("Final Result hash mismatch")

    # Local import keeps the canonical exporter free to verify this module's
    # manifest-bound hash without creating an import cycle.
    from trusted_ceo_agent.web_report.exporter import export_web_report

    try:
        exported = export_web_report(store, run_id=run_id, revision=revision)
    except IntegrityError:
        raise
    except (ContractError, ValueError) as error:
        raise IntegrityError(f"Final Result validation failed: {error}") from error
    receipt = exported.bundle.get("viewer_eligibility_receipt")
    if not isinstance(receipt, Mapping):
        raise IntegrityError("viewer eligibility receipt is missing")
    if (
        receipt.get("run_id") != run_id
        or receipt.get("finalized_revision") != revision
        or receipt.get("final_result_hash") != actual_hash
    ):
        raise IntegrityError("converted bundle input identity mismatch")
    return exported.payload


__all__ = ["convert_final_revision", "final_result_hash_for_revision"]
