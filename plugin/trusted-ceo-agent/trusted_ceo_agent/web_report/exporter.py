from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

from trusted_ceo_agent import __version__
from trusted_ceo_agent.canonical import strict_loads
from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from trusted_ceo_agent.trust.revision_validation import (
    REQUIRED_WEB_REPORT_CHECKS,
    validate_revision,
)
from trusted_ceo_agent.web_report.canonical import jcs_bytes, jcs_sha256
from trusted_ceo_agent.web_report.closure import (
    EvidenceClosure,
    build_evidence_closure,
)
from trusted_ceo_agent.web_report.contracts import load_bundle_bytes
from trusted_ceo_agent.web_report.converter import final_result_hash_for_revision
from trusted_ceo_agent.web_report.expert_packets import build_expert_packet_view
from trusted_ceo_agent.web_report.presentation import build_presentation_manifest
from trusted_ceo_agent.web_report.previews import build_source_views
from trusted_ceo_agent.web_report.revisions import build_revision_artifacts
from trusted_ceo_agent.workflow.approvals import current_approvals


_APPROVED_REVISION = re.compile(
    r"(?:@r(?P<suffix>[0-9]{4,})$|(?:^|/)revisions/(?P<path>[0-9]+)/)"
)
_COLLECTION_IDS = (
    ("issues", "issue_id"),
    ("cross_issue_relations", "relation_id"),
    ("conditional_responses", "response_id"),
    ("monitoring", "monitor_id"),
    ("blind_spots", "blind_spot_id"),
    ("expert_review_packets", "expert_packet_id"),
)


@dataclass(frozen=True)
class ExportedWebReport:
    bundle: dict[str, Any]
    payload: bytes
    checks: tuple[str, ...]


def _document(
    files: Mapping[str, bytes],
    path: str,
) -> dict[str, Any]:
    payload = files.get(path)
    if payload is None:
        raise IntegrityError(f"required web report artifact is missing: {path}")
    try:
        value = strict_loads(payload)
    except (UnicodeError, ValueError) as error:
        raise IntegrityError(f"invalid web report artifact: {path}") from error
    if not isinstance(value, dict):
        raise IntegrityError(f"web report artifact must be an object: {path}")
    return dict(value)


def _native_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise IntegrityError(f"{label} must be an integer")
    result = int(value)
    if value != result:
        raise IntegrityError(f"{label} must be an integer")
    return result


def _assert_grade_alignment(
    final_result: Mapping[str, Any],
    files: Mapping[str, bytes],
) -> None:
    published: dict[str, str] = {}
    for path, payload in files.items():
        if not path.startswith("grading/records/") or not path.endswith(".json"):
            continue
        record = strict_loads(payload)
        if not isinstance(record, Mapping) or record.get("publication_status") != "published":
            continue
        issue_id = record.get("issue_id")
        primary_grade = record.get("primary_grade")
        if not isinstance(issue_id, str) or not isinstance(primary_grade, str):
            raise IntegrityError("published Grade Record is invalid")
        if issue_id in published:
            raise IntegrityError(f"duplicate published Grade Record: {issue_id}")
        published[issue_id] = primary_grade

    issues = final_result.get("issues", [])
    if not isinstance(issues, list):
        raise IntegrityError("Final Result issues must be an array")
    for issue in issues:
        if not isinstance(issue, Mapping):
            raise IntegrityError("Final Result issue is invalid")
        issue_id = issue.get("issue_id")
        primary_grade = issue.get("primary_grade")
        if (
            not isinstance(issue_id, str)
            or not isinstance(primary_grade, str)
            or published.get(issue_id) != primary_grade
        ):
            raise IntegrityError(f"Grade Record mismatch: {issue_id}")


def _approval_summary(record: Mapping[str, Any]) -> dict[str, Any]:
    fixture_only = record.get("fixture_only", False)
    if fixture_only is not None and not isinstance(fixture_only, bool):
        raise IntegrityError("Final approval fixture_only must be boolean or null")
    fields = {
        "gate": record.get("gate"),
        "status": record.get("status", "current"),
        "input_method": record.get("input_method"),
        "fixture_only": fixture_only,
        "approval_id": record.get("approval_id"),
        "actor_role": record.get("actor_role"),
        "result_artifact_ref": record.get("result_artifact_ref"),
    }
    for key, value in fields.items():
        if key == "fixture_only":
            continue
        if value is not None and (not isinstance(value, str) or not value):
            raise IntegrityError(f"Final approval {key} is invalid")
    return fields


def _approved_revision(result_artifact_ref: Any) -> int:
    if not isinstance(result_artifact_ref, str):
        raise IntegrityError("Final approval result_artifact_ref is missing")
    match = _APPROVED_REVISION.search(result_artifact_ref)
    if match is None:
        raise IntegrityError("Final approval result revision cannot be parsed")
    return int(match.group("suffix") or match.group("path"))


def _approval_ancestry(
    store: ArtifactStore,
    *,
    files: Mapping[str, bytes],
    finalized_revision: int,
) -> tuple[dict[str, Any], int, str]:
    approvals = current_approvals(files, gate="final")
    if len(approvals) != 1:
        raise IntegrityError("exactly one current authorizing Final approval is required")
    record = approvals[0]
    summary = _approval_summary(record)
    approval_id = summary["approval_id"]
    if not isinstance(approval_id, str):
        raise IntegrityError("Final approval ID is missing")
    approved_revision = _approved_revision(summary["result_artifact_ref"])
    if approved_revision > finalized_revision:
        raise IntegrityError("Final approval revision is after finalization")

    path = f"approvals/records/{approval_id}.json"
    first_revision: int | None = None
    for revision in range(1, finalized_revision + 1):
        snapshot = store.verify_revision(revision)
        candidate = snapshot / path
        if not candidate.is_file():
            if first_revision is not None:
                raise IntegrityError("Final approval ancestry is interrupted")
            continue
        try:
            value = strict_loads(candidate.read_bytes())
        except (UnicodeError, ValueError) as error:
            raise IntegrityError("Final approval ancestry contains invalid JSON") from error
        if not isinstance(value, Mapping):
            raise IntegrityError("Final approval ancestry contains an invalid record")
        if first_revision is None:
            first_revision = revision
        if value.get("approval_id") != approval_id:
            raise IntegrityError("Final approval ancestry ID mismatch")
        if revision >= approved_revision and value.get("status", "current") != "current":
            raise IntegrityError("Final approval was later invalidated")

    if first_revision != approved_revision:
        raise IntegrityError(
            "Final approval first snapshot does not match its approved revision"
        )

    input_method = summary["input_method"]
    fixture_only = summary["fixture_only"] is True
    if input_method in {"interactive_tty", "web_hitl"} and not fixture_only:
        mode = "trusted_final"
    elif input_method == "test_fixture" and fixture_only:
        mode = "poc_fixture"
    else:
        raise IntegrityError(
            "Final approval is neither trusted human input nor explicit POC"
        )
    return summary, approved_revision, mode


def _sort_collection(
    result: dict[str, Any],
    field: str,
    identifier: str,
) -> None:
    raw = result.get(field)
    if not isinstance(raw, list):
        raise IntegrityError(f"Final Result {field} must be an array")
    if any(not isinstance(item, Mapping) for item in raw):
        raise IntegrityError(f"Final Result {field} entry must be an object")
    result[field] = sorted(
        (copy.deepcopy(dict(item)) for item in raw),
        key=lambda item: str(item.get(identifier, "")),
    )


def _packet_aliases(files: Mapping[str, bytes]) -> dict[str, str]:
    structured = _document(files, "final/structured-output.json")
    aliases: dict[str, str] = {}
    for packet in structured.get("expert_review_packets", []):
        if not isinstance(packet, Mapping):
            raise IntegrityError("structured expert packet must be an object")
        packet_id = packet.get("expert_packet_id")
        trigger_ref = packet.get("_trigger_ref")
        if isinstance(packet_id, str):
            aliases[packet_id] = packet_id
            if isinstance(trigger_ref, str):
                aliases[trigger_ref] = packet_id
    return aliases


def _normalize_final_result(
    raw: Mapping[str, Any],
    *,
    files: Mapping[str, bytes],
    final_approval: Mapping[str, Any],
) -> dict[str, Any]:
    result = copy.deepcopy(dict(raw))
    for field, identifier in _COLLECTION_IDS:
        _sort_collection(result, field, identifier)

    aliases = _packet_aliases(files)
    for issue in result["issues"]:
        for key in (
            "secondary_flags",
            "value_refs",
            "evidence_link_ids",
            "unresolved_conflicts",
            "verification_next_steps",
            "conditional_response_refs",
        ):
            values = issue.get(key, [])
            if not isinstance(values, list):
                raise IntegrityError(f"Final Result issue {key} must be an array")
            issue[key] = sorted(set(values))
        raw_expert_refs = issue.get("expert_review_refs", [])
        if not isinstance(raw_expert_refs, list):
            raise IntegrityError("Final Result issue expert refs must be an array")
        issue["expert_review_refs"] = sorted(
            {aliases.get(str(reference), str(reference)) for reference in raw_expert_refs}
        )
        for key in ("cause_hypotheses", "counter_hypotheses"):
            claims = issue.get(key, [])
            if not isinstance(claims, list):
                raise IntegrityError(f"Final Result issue {key} must be an array")
            issue[key] = sorted(
                (copy.deepcopy(dict(claim)) for claim in claims),
                key=lambda claim: str(claim.get("claim_code", "")),
            )

    raw_approvals = result.get("approvals")
    if not isinstance(raw_approvals, list):
        raise IntegrityError("Final Result approvals must be an array")
    normalized = [_approval_summary(item) for item in raw_approvals]
    matching = [
        item
        for item in normalized
        if item["gate"] == "final" and item["status"] == "current"
    ]
    if len(matching) != 1:
        raise IntegrityError("Final Result must contain one current Final approval")
    for key in ("input_method", "fixture_only"):
        if matching[0][key] != final_approval[key]:
            raise IntegrityError(f"Final Result approval {key} mismatch")
    for key in ("approval_id", "actor_role", "result_artifact_ref"):
        if matching[0][key] is not None and matching[0][key] != final_approval[key]:
            raise IntegrityError(f"Final Result approval {key} mismatch")
        if matching[0][key] is None:
            matching[0][key] = final_approval[key]
    result["approvals"] = sorted(
        normalized,
        key=lambda item: (
            str(item["gate"]),
            str(item["approval_id"]),
        ),
    )
    return result


def _issue_claim_closure(
    final_result: Mapping[str, Any],
    closure: EvidenceClosure,
    packets: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    facts = {str(item["fact_id"]): item for item in closure.facts}
    signals = {str(item["signal_id"]): item for item in closure.signals}
    links = {str(item["evidence_link_id"]): item for item in closure.evidence_links}
    packet_refs: dict[str, list[str]] = {}
    for packet in packets:
        packet_refs.setdefault(str(packet["target_issue_ref"]), []).append(
            str(packet["expert_packet_id"])
        )

    def add_fact(
        fact_id: str,
        *,
        fact_ids: set[str],
        source_ids: set[str],
        visiting: set[str],
    ) -> None:
        if fact_id in fact_ids:
            return
        if fact_id in visiting:
            raise IntegrityError(f"Fact derivation cycle: {fact_id}")
        fact = facts.get(fact_id)
        if fact is None:
            raise IntegrityError(f"issue closure references unknown Fact: {fact_id}")
        visiting.add(fact_id)
        for source_ref in fact.get("source_refs", []):
            if not isinstance(source_ref, Mapping) or not isinstance(
                source_ref.get("source_id"), str
            ):
                raise IntegrityError(f"Fact Source reference is invalid: {fact_id}")
            source_ids.add(str(source_ref["source_id"]))
        derivation = fact.get("derivation")
        if isinstance(derivation, Mapping):
            for nested in derivation.get("input_fact_ids", []):
                if not isinstance(nested, str):
                    raise IntegrityError(f"Fact derivation is invalid: {fact_id}")
                add_fact(
                    nested,
                    fact_ids=fact_ids,
                    source_ids=source_ids,
                    visiting=visiting,
                )
        visiting.remove(fact_id)
        fact_ids.add(fact_id)

    result: list[dict[str, Any]] = []
    for issue in final_result.get("issues", []):
        issue_id = str(issue["issue_id"])
        evidence_ids = sorted(set(issue.get("evidence_link_ids", [])))
        fact_ids: set[str] = set()
        signal_ids: set[str] = set()
        source_ids: set[str] = set()
        for evidence_id in evidence_ids:
            link = links.get(evidence_id)
            if link is None:
                raise IntegrityError(
                    f"issue closure references unknown Evidence Link: {evidence_id}"
                )
            evidence_ref = link.get("evidence_ref")
            if link.get("evidence_kind") == "fact":
                add_fact(
                    str(evidence_ref),
                    fact_ids=fact_ids,
                    source_ids=source_ids,
                    visiting=set(),
                )
            elif link.get("evidence_kind") == "signal":
                signal = signals.get(str(evidence_ref))
                if signal is None:
                    raise IntegrityError(
                        f"issue closure references unknown Signal: {evidence_ref}"
                    )
                signal_ids.add(str(evidence_ref))
                for fact_id in signal.get("input_fact_ids", []):
                    add_fact(
                        str(fact_id),
                        fact_ids=fact_ids,
                        source_ids=source_ids,
                        visiting=set(),
                    )
            else:
                raise IntegrityError(
                    f"Evidence Link kind is invalid: {evidence_id}"
                )
        claims = {
            str(claim["claim_code"])
            for key in ("cause_hypotheses", "counter_hypotheses")
            for claim in issue.get(key, [])
            if isinstance(claim, Mapping) and isinstance(claim.get("claim_code"), str)
        }
        result.append(
            {
                "issue_ref": issue_id,
                "claim_refs": sorted(claims),
                "evidence_link_ids": evidence_ids,
                "fact_refs": sorted(fact_ids),
                "signal_refs": sorted(signal_ids),
                "source_refs": sorted(source_ids),
                "expert_packet_refs": sorted(packet_refs.get(issue_id, [])),
            }
        )
    return sorted(result, key=lambda item: item["issue_ref"])


def _pack_versions(files: Mapping[str, bytes]) -> list[dict[str, str]]:
    if "packs/manifest.json" not in files:
        return []
    manifest = _document(files, "packs/manifest.json")
    result: list[dict[str, str]] = []
    for pack in manifest.get("packs", []):
        if not isinstance(pack, Mapping):
            raise IntegrityError("pack manifest entry must be an object")
        name, version = pack.get("pack_id"), pack.get("pack_version")
        if not isinstance(name, str) or not isinstance(version, str):
            raise IntegrityError("pack manifest version is invalid")
        result.append({"name": name, "version": version})
    return sorted(result, key=lambda item: (item["name"], item["version"]))


def _official_url_policy(
    source_views: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    origins: set[str] = set()
    for source in source_views:
        candidate = source.get("official_url")
        if not isinstance(candidate, str):
            continue
        parsed = urlsplit(candidate)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise IntegrityError("accepted official URL is unsafe")
        origins.add(urlunsplit((parsed.scheme, parsed.netloc, "", "", "")))
    return {
        "allowed_schemes": ["https"],
        "allowed_origins": sorted(origins),
        "allow_redirects": False,
    }


def export_web_report(
    store: ArtifactStore,
    *,
    run_id: str,
    revision: int,
) -> ExportedWebReport:
    state = store.state()
    if state.get("run_id") != run_id:
        raise IntegrityError("registered run ID does not match requested run")
    if _native_int(state.get("revision"), "run state revision") != revision:
        raise IntegrityError("registered run revision does not match requested revision")

    validation = validate_revision(store, revision)
    files = validation.files
    manifest_final_result_hash = final_result_hash_for_revision(store, revision)
    workflow = _document(files, "workflow/state.json")
    if workflow.get("state") != "finalized":
        raise IntegrityError("web report export requires a finalized workflow")
    if workflow.get("run_id") != run_id:
        raise IntegrityError("workflow run ID mismatch")
    if _native_int(workflow.get("revision"), "workflow revision") != revision:
        raise IntegrityError("workflow revision mismatch")

    checks = tuple(sorted(set(validation.checks)))
    missing = sorted(REQUIRED_WEB_REPORT_CHECKS - set(checks))
    if missing:
        raise IntegrityError(
            f"required web report check is missing: {missing[0]}"
        )
    if "packs/manifest.json" in files and "pack_manifest_schema" not in checks:
        raise IntegrityError("required web report check is missing: pack_manifest_schema")
    has_components = any(
        path.startswith("components/runs/") and path.endswith(".json")
        for path in files
    )
    if has_components and "component_run_recomputation" not in checks:
        raise IntegrityError(
            "required web report check is missing: component_run_recomputation"
        )

    raw_result = _document(files, "final/result.json")
    _assert_grade_alignment(raw_result, files)
    summary = raw_result.get("run_summary")
    if not isinstance(summary, Mapping):
        raise IntegrityError("Final Result run summary is missing")
    if summary.get("run_id") != run_id:
        raise IntegrityError("Final Result run ID mismatch")
    if _native_int(summary.get("revision"), "Final Result revision") != revision:
        raise IntegrityError("Final Result revision mismatch")
    integrity = raw_result.get("integrity")
    fingerprint = (
        integrity.get("semantic_fingerprint")
        if isinstance(integrity, Mapping)
        else None
    )
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise IntegrityError("Final Result semantic fingerprint is invalid")

    final_approval, approved_revision, claimed_mode = _approval_ancestry(
        store,
        files=files,
        finalized_revision=revision,
    )
    final_result = _normalize_final_result(
        raw_result,
        files=files,
        final_approval=final_approval,
    )
    core = _document(files, "evidence/core.json")
    closure = build_evidence_closure(final_result, core)
    source_views = build_source_views(validation.snapshot, closure)
    presentation = build_presentation_manifest(final_result, closure)
    expert_packets = build_expert_packet_view(
        files,
        final_result,
        closure,
        run_id=run_id,
        revision=revision,
    )
    revision_artifacts = build_revision_artifacts(
        store,
        current_revision=revision,
    )
    issue_closure = _issue_claim_closure(
        final_result,
        closure,
        expert_packets,
    )
    finalization_times = [
        event["timestamp"]
        for event in revision_artifacts.trust_events
        if event["command"] == "finalize" and event["timestamp"] is not None
    ]
    manifest_hash = validation.snapshot_manifest.get("manifest_hash")
    if not isinstance(manifest_hash, str):
        raise IntegrityError("snapshot manifest hash is missing")
    final_result_hash = hashlib.sha256(files["final/result.json"]).hexdigest()
    if final_result_hash != manifest_final_result_hash:
        raise IntegrityError("Final Result hash does not match its immutable manifest")
    receipt = {
        "receipt_version": "1.0.0",
        "claimed_viewer_mode": claimed_mode,
        "run_id": run_id,
        "approved_revision": approved_revision,
        "finalized_revision": revision,
        "workflow_state": "finalized",
        "snapshot_manifest_hash": manifest_hash,
        "final_result_hash": final_result_hash,
        "result_artifact_ref": final_approval["result_artifact_ref"],
        "revision_ancestry_hash": revision_artifacts.revision_ancestry_hash,
        "validator_version": __version__,
        "completed_checks": list(checks),
        "final_approval_summary": final_approval,
    }
    file_manifest = list(revision_artifacts.file_manifest)
    bundle: dict[str, Any] = {
        "bundle_version": "1.0.0",
        "canonicalization_version": "rfc8785-jcs-1",
        "run": {
            "run_id": run_id,
            "revision": revision,
            "workflow_state": "finalized",
            "semantic_fingerprint": fingerprint,
            "finalization_event_time": (
                sorted(finalization_times)[-1] if finalization_times else None
            ),
        },
        "viewer_eligibility_receipt": receipt,
        "final_result": final_result,
        "presentation_manifest": presentation,
        "evidence_view": {
            "facts": list(closure.facts),
            "signals": list(closure.signals),
            "evidence_links": list(closure.evidence_links),
            "data_quality": list(closure.data_quality),
            "capability_map": closure.capability_map,
            "issue_claim_closure": issue_closure,
        },
        "source_view": list(source_views.sources),
        "source_previews": list(source_views.previews),
        "official_url_policy": _official_url_policy(source_views.sources),
        "trust_view": {
            "plugin_version": __version__,
            "pack_versions": _pack_versions(files),
            "schema_versions": [
                {"name": "web-report-bundle", "version": "1.0.0"}
            ],
            "validator_version": __version__,
            "completed_checks": list(checks),
            "approval_summary": list(final_result["approvals"]),
            "trust_events": list(revision_artifacts.trust_events),
            "file_hashes": file_manifest,
            "limitations": (
                ["fixture_only"] if claimed_mode == "poc_fixture" else []
            ),
            "deidentification": {
                "poc_only": claimed_mode == "poc_fixture",
                "direct_identifiers_removed": claimed_mode == "poc_fixture",
                "notice_ko": (
                    "POC 시연 자료이며 실제 승인 실행본이 아닙니다."
                    if claimed_mode == "poc_fixture"
                    else "등록 실행본 교차 검증이 필요합니다."
                ),
            },
        },
        "expert_packet_view": list(expert_packets),
        "revision_view": revision_artifacts.revision_view,
        "file_manifest": file_manifest,
        "bundle_hash": "0" * 64,
    }
    bundle["bundle_hash"] = jcs_sha256(
        bundle,
        omit_root_field="bundle_hash",
    )
    payload = jcs_bytes(bundle)
    validated = load_bundle_bytes(payload)
    return ExportedWebReport(
        bundle=validated,
        payload=payload,
        checks=checks,
    )
