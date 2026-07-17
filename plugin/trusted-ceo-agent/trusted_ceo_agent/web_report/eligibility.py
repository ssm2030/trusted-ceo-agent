from __future__ import annotations

from typing import Any

from trusted_ceo_agent.errors import ContractError, IntegrityError
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from trusted_ceo_agent.web_report.contracts import (
    WebReportContractError,
    load_bundle_bytes,
    validate_eligibility_decision,
)
from trusted_ceo_agent.web_report.exporter import export_web_report


_BADGES = {
    "trusted_final": "승인·검증된 실행본",
    "poc_fixture": "검증된 POC 시연 실행본",
    "unverified_import": "출처 미확인 묶음",
    "rejected": "열 수 없는 묶음",
}


def _denied(
    code: str,
    message: str,
    *,
    run_id: str | None,
    revision: int | None,
    bundle_hash: str | None,
) -> dict[str, Any]:
    decision = {
        "decision_version": "1.0.0",
        "eligible": False,
        "viewer_mode": "rejected",
        "badge_label_ko": _BADGES["rejected"],
        "run_id": run_id,
        "revision": revision,
        "bundle_hash": bundle_hash,
        "completed_checks": [],
        "failure_code": code,
        "failure_message": message,
    }
    validate_eligibility_decision(decision)
    return decision


def _eligible(
    mode: str,
    *,
    run_id: str,
    revision: int,
    bundle_hash: str,
    completed_checks: list[str],
) -> dict[str, Any]:
    decision = {
        "decision_version": "1.0.0",
        "eligible": True,
        "viewer_mode": mode,
        "badge_label_ko": _BADGES[mode],
        "run_id": run_id,
        "revision": revision,
        "bundle_hash": bundle_hash,
        "completed_checks": sorted(set(completed_checks)),
        "failure_code": None,
        "failure_message": None,
    }
    validate_eligibility_decision(decision)
    return decision


def _bundle_failure(error: WebReportContractError) -> str:
    message = str(error).casefold()
    if "52_428_800" in message or "exceeds" in message and "bytes" in message:
        return "BUNDLE_SIZE_EXCEEDED"
    if "invalid web report json" in message or "must be an object" in message:
        return "BUNDLE_JSON_INVALID"
    if "schema invalid" in message:
        return "BUNDLE_SCHEMA_INVALID"
    if "absolute paths" in message:
        return "ABSOLUTE_PATH_LEAK"
    if "hash mismatch" in message:
        return "BUNDLE_HASH_MISMATCH"
    return "REFERENCE_CLOSURE_BROKEN"


def _full_run_failure(error: Exception) -> str:
    message = str(error).casefold()
    if "finalized" in message:
        return "WORKFLOW_NOT_FINALIZED"
    if "required web report check" in message:
        return "REQUIRED_CHECK_MISSING"
    if "approval" in message and (
        "ancestry" in message
        or "first snapshot" in message
        or "revision" in message
        or "invalidated" in message
    ):
        return "ANCESTRY_MISMATCH"
    if "approval" in message:
        return "FINAL_APPROVAL_INVALID"
    return "FULL_RUN_MISMATCH"


def decide_unregistered_import(bundle_payload: bytes) -> dict[str, Any]:
    """Parse a standalone JSON bundle without promoting its embedded receipt."""

    try:
        bundle = load_bundle_bytes(bundle_payload)
    except WebReportContractError as error:
        return _denied(
            _bundle_failure(error),
            str(error),
            run_id=None,
            revision=None,
            bundle_hash=None,
        )
    return _eligible(
        "unverified_import",
        run_id=str(bundle["run"]["run_id"]),
        revision=int(bundle["run"]["revision"]),
        bundle_hash=str(bundle["bundle_hash"]),
        completed_checks=[],
    )


def decide_viewer_eligibility(
    store: ArtifactStore,
    *,
    expected_run_id: str,
    expected_revision: int,
    bundle_payload: bytes,
) -> dict[str, Any]:
    try:
        supplied = load_bundle_bytes(bundle_payload)
    except WebReportContractError as error:
        return _denied(
            _bundle_failure(error),
            str(error),
            run_id=None,
            revision=None,
            bundle_hash=None,
        )

    run_id = str(supplied["run"]["run_id"])
    revision = int(supplied["run"]["revision"])
    bundle_hash = str(supplied["bundle_hash"])
    if run_id != expected_run_id:
        return _denied(
            "RUN_ID_MISMATCH",
            "bundle run ID does not match the registered run",
            run_id=run_id,
            revision=revision,
            bundle_hash=bundle_hash,
        )
    if revision != expected_revision:
        return _denied(
            "REVISION_MISMATCH",
            "bundle revision does not match the registered revision",
            run_id=run_id,
            revision=revision,
            bundle_hash=bundle_hash,
        )

    try:
        recomputed = export_web_report(
            store,
            run_id=expected_run_id,
            revision=expected_revision,
        )
    except (IntegrityError, ContractError) as error:
        return _denied(
            _full_run_failure(error),
            str(error),
            run_id=run_id,
            revision=revision,
            bundle_hash=bundle_hash,
        )

    if bundle_payload != recomputed.payload:
        return _denied(
            "BYTE_MISMATCH",
            "bundle bytes differ from the registered full-run export",
            run_id=run_id,
            revision=revision,
            bundle_hash=bundle_hash,
        )

    receipt = supplied["viewer_eligibility_receipt"]
    recomputed_receipt = recomputed.bundle["viewer_eligibility_receipt"]
    cross_fields = (
        "run_id",
        "approved_revision",
        "finalized_revision",
        "workflow_state",
        "snapshot_manifest_hash",
        "final_result_hash",
        "result_artifact_ref",
        "revision_ancestry_hash",
        "validator_version",
        "completed_checks",
        "final_approval_summary",
    )
    if any(receipt[field] != recomputed_receipt[field] for field in cross_fields):
        return _denied(
            "FULL_RUN_MISMATCH",
            "bundle receipt differs from the registered full run",
            run_id=run_id,
            revision=revision,
            bundle_hash=bundle_hash,
        )
    mode = recomputed_receipt["claimed_viewer_mode"]
    if mode not in {"trusted_final", "poc_fixture"}:
        return _denied(
            "FINAL_APPROVAL_INVALID",
            "registered run does not have an eligible approval mode",
            run_id=run_id,
            revision=revision,
            bundle_hash=bundle_hash,
        )
    checks = sorted(recomputed.checks)
    if (
        sorted(receipt["completed_checks"]) != checks
        or sorted(supplied["trust_view"]["completed_checks"]) != checks
    ):
        return _denied(
            "REQUIRED_CHECK_MISSING",
            "bundle completed checks do not match full validation",
            run_id=run_id,
            revision=revision,
            bundle_hash=bundle_hash,
        )
    return _eligible(
        str(mode),
        run_id=run_id,
        revision=revision,
        bundle_hash=bundle_hash,
        completed_checks=checks,
    )
