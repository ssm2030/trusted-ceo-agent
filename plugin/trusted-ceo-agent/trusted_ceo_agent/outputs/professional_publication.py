from __future__ import annotations

import copy
import hashlib
import hmac
from collections.abc import Mapping, Sequence
from typing import Any
from decimal import Decimal

from trusted_ceo_agent.analysis.execution_authority import verify_execution_authority_gate
from trusted_ceo_agent.analysis.findings import (
    build_issue_cluster,
    validate_finding_graph,
)
from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.evidence.core import EvidenceCoreValidator
from trusted_ceo_agent.errors import ContractError, IntegrityError
from trusted_ceo_agent.grading.grader import grade
from trusted_ceo_agent.workflow.completion import verify_completion_assessment


_EVIDENCE_INDEX_FIELDS = {
    "run_id",
    "revision",
    "fact_refs",
    "signal_refs",
    "evidence_link_refs",
    "source_refs",
    "content_hash",
}
_REFERENCE_FIELDS = (
    ("fact_refs", "fact_refs"),
    ("signal_ids", "signal_refs"),
    ("evidence_link_refs", "evidence_link_refs"),
    ("supporting_evidence_refs", "evidence_link_refs"),
    ("contradicting_evidence_refs", "evidence_link_refs"),
    ("source_refs", "source_refs"),
)
_HASH_LENGTH = 64


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _objects(values: Sequence[Mapping[str, Any]], label: str) -> list[dict[str, Any]]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise ContractError(f"{label} must be an object array")
    result: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise ContractError(f"{label} must be an object array")
        result.append(copy.deepcopy(dict(value)))
    return result


def _verify_evidence_index(
    value: Mapping[str, Any],
    *,
    expected_run_id: str,
    expected_revision: int,
    expected_hash: str,
) -> dict[str, set[str]]:
    if not isinstance(value, Mapping) or set(value) != _EVIDENCE_INDEX_FIELDS:
        raise IntegrityError("Evidence index contract is incomplete")
    document = copy.deepcopy(dict(value))
    if (
        document["run_id"] != expected_run_id
        or document["revision"] != expected_revision
    ):
        raise IntegrityError("Evidence index run or revision mismatch")
    claimed = document.pop("content_hash")
    if (
        not isinstance(claimed, str)
        or len(claimed) != _HASH_LENGTH
        or not hmac.compare_digest(claimed, _digest(document))
        or not hmac.compare_digest(claimed, expected_hash)
    ):
        raise IntegrityError("Evidence index hash mismatch")
    indexes: dict[str, set[str]] = {}
    for field in (
        "fact_refs",
        "signal_refs",
        "evidence_link_refs",
        "source_refs",
    ):
        raw = document[field]
        if (
            not isinstance(raw, list)
            or any(not isinstance(item, str) or not item for item in raw)
            or len(raw) != len(set(raw))
        ):
            raise IntegrityError(f"Evidence index {field} is invalid")
        indexes[field] = set(raw)
    return indexes


def _verify_clusters(
    clusters: Sequence[Mapping[str, Any]],
    *,
    findings: Sequence[Mapping[str, Any]],
    relations: Sequence[Mapping[str, Any]],
    run_id: str,
    revision: int,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    records = _objects(clusters, "IssueClusters")
    cluster_by_id: dict[str, dict[str, Any]] = {}
    membership: dict[str, str] = {}
    relation_membership: dict[str, str] = {}
    for record in records:
        SchemaStore().validate("issue-cluster.schema.json", record)
        if record["run_id"] != run_id or record["revision"] != revision:
            raise IntegrityError("IssueCluster run or revision mismatch")
        cluster_id = str(record["cluster_id"])
        if cluster_id in cluster_by_id:
            raise IntegrityError(f"duplicate IssueCluster: {cluster_id}")
        rebuilt = build_issue_cluster(
            {
                key: copy.deepcopy(record[key])
                for key in (
                    "run_id",
                    "revision",
                    "finding_ids",
                    "relation_ids",
                    "decision_unit",
                    "unresolved_conflicts",
                )
            },
            findings=findings,
            relations=relations,
        )
        if canonical_bytes(rebuilt) != canonical_bytes(record):
            raise IntegrityError(f"IssueCluster hash mismatch: {cluster_id}")
        cluster_by_id[cluster_id] = record
        for finding_id in record["finding_ids"]:
            if finding_id in membership:
                raise IntegrityError(f"Finding appears in multiple IssueClusters: {finding_id}")
            membership[str(finding_id)] = cluster_id
        for relation_id in record["relation_ids"]:
            if relation_id in relation_membership:
                raise IntegrityError(
                    f"relation appears in multiple IssueClusters: {relation_id}"
                )
            relation_membership[str(relation_id)] = cluster_id

    expected_findings = {str(item["finding_id"]) for item in findings}
    expected_relations = {str(item["relation_id"]) for item in relations}
    if set(membership) != expected_findings:
        raise IntegrityError("IssueCluster Finding coverage is incomplete")
    if set(relation_membership) != expected_relations:
        raise IntegrityError("IssueCluster relation coverage is incomplete")
    return (
        sorted(cluster_by_id.values(), key=lambda item: item["cluster_id"]),
        membership,
    )


def _verify_grades(
    *,
    findings: Sequence[Mapping[str, Any]],
    grading_inputs: Sequence[Mapping[str, Any]],
    grade_records: Sequence[Mapping[str, Any]],
    evidence: Mapping[str, set[str]],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    schemas = SchemaStore()
    inputs = _objects(grading_inputs, "grading inputs")
    records = _objects(grade_records, "Grade Records")
    inputs_by_issue: dict[str, dict[str, Any]] = {}
    records_by_id: dict[str, dict[str, Any]] = {}
    for item in inputs:
        schemas.validate("grading-input.schema.json", item)
        issue_id = str(item["issue_id"])
        if issue_id in inputs_by_issue:
            raise IntegrityError(f"duplicate grading input: {issue_id}")
        inputs_by_issue[issue_id] = item
    for record in records:
        schemas.validate("grade-record.schema.json", record)
        record_id = str(record["grade_record_id"])
        if record_id in records_by_id:
            raise IntegrityError(f"duplicate Grade Record: {record_id}")
        records_by_id[record_id] = record

    used_records: dict[str, dict[str, Any]] = {}
    for finding in findings:
        issue_id = str(finding["case_id"])
        grade_ref = finding["grade"]["grade_record_ref"]
        if finding["grade"]["status"] != "published" or not isinstance(grade_ref, str):
            raise IntegrityError(f"Finding lacks a published Grade Record: {finding['finding_id']}")
        record = records_by_id.get(grade_ref)
        grading_input = inputs_by_issue.get(issue_id)
        if record is None or grading_input is None:
            raise IntegrityError(f"Grade Record is missing: {grade_ref}")
        if record["issue_id"] != issue_id:
            raise IntegrityError(f"Grade Record issue mismatch: {grade_ref}")
        recomputed = grade(grading_input)
        if canonical_bytes(record) != canonical_bytes(recomputed):
            raise IntegrityError(f"Grade Record recomputation mismatch: {grade_ref}")
        allowed_provenance = (
            set(finding["fact_refs"])
            | set(finding["signal_ids"])
            | set(finding["evidence_link_refs"])
            | set(finding["procedure_result_refs"])
            | set(finding["norm_refs"])
            | set(finding["calculation_refs"])
        )
        if not set(grading_input["provenance_refs"]).issubset(allowed_provenance):
            raise IntegrityError(f"Grade Record provenance mismatch: {grade_ref}")
        used_records[issue_id] = record

    expected_issue_ids = {str(item["case_id"]) for item in findings}
    if set(inputs_by_issue) != expected_issue_ids:
        raise IntegrityError("grading input coverage does not match Findings")
    if set(records_by_id) != {
        str(item["grade"]["grade_record_ref"]) for item in findings
    }:
        raise IntegrityError("Grade Record coverage does not match Findings")
    return used_records, sorted(records_by_id)


def _issue(
    finding: Mapping[str, Any],
    grade_record: Mapping[str, Any],
) -> dict[str, Any]:
    expert_ref = finding["expert_review"]["packet_ref"]
    return {
        "issue_id": str(finding["case_id"]),
        "_finding_disposition": str(finding["disposition"]),
        "title_template": str(finding["conclusion"]["statement"]),
        "primary_grade": str(grade_record["primary_grade"]),
        "secondary_flags": sorted(set(grade_record["secondary_flags"])),
        "why_it_matters_template": str(finding["conclusion"]["scope"]),
        "value_refs": sorted(set(finding["fact_refs"])),
        "evidence_link_ids": sorted(set(finding["evidence_link_refs"])),
        "cause_hypotheses": [
            {"claim_code": item} for item in sorted(set(finding["hypotheses"]))
        ],
        "counter_hypotheses": [
            {"claim_code": item}
            for item in sorted(set(finding["counter_hypotheses"]))
        ],
        "unresolved_conflicts": sorted(set(finding["unresolved_conflicts"])),
        "verification_next_steps": sorted(
            set(finding["verification"]["verification_step_refs"])
        ),
        "conditional_response_refs": [],
        "expert_review_refs": [expert_ref] if expert_ref is not None else [],
        "disposition": "accepted",
    }


def _expert_packet(finding: Mapping[str, Any]) -> dict[str, Any] | None:
    review = finding["expert_review"]
    packet_ref = review["packet_ref"]
    if finding["disposition"] != "expert_review_required" or packet_ref is None:
        return None
    return {
        "expert_packet_id": packet_ref,
        "profession": review["owner"],
        "question_template": review["decision_boundary"],
        "forbidden_conclusions": [],
        "_target_issue_ref": finding["case_id"],
        "_trigger_ref": packet_ref,
        "_required": True,
        "_professional_packet": True,
        "_fact_refs": sorted(set(finding["fact_refs"])),
        "_evidence_link_ids": sorted(set(finding["evidence_link_refs"])),
        "_source_refs": sorted(set(finding["source_refs"])),
        "_required_document_refs": [],
        "_decision_boundary": review["decision_boundary"],
    }


def build_professional_publication(
    *,
    expected_run_id: str,
    expected_revision: int,
    findings: Sequence[Mapping[str, Any]],
    relations: Sequence[Mapping[str, Any]],
    clusters: Sequence[Mapping[str, Any]],
    completion: Mapping[str, Any],
    grading_inputs: Sequence[Mapping[str, Any]],
    grade_records: Sequence[Mapping[str, Any]],
    evidence_index: Mapping[str, Any],
    expected_evidence_index_hash: str,
) -> dict[str, Any]:
    """Project verified professional artifacts without analytical inference."""

    finding_records = _objects(findings, "Findings")
    relation_records = _objects(relations, "FindingRelations")
    validate_finding_graph(finding_records, relation_records)
    for record in [*finding_records, *relation_records]:
        if (
            record["run_id"] != expected_run_id
            or record["revision"] != expected_revision
        ):
            raise IntegrityError("professional artifact run or revision mismatch")
    if any(item["confidence_status"] != "verified" for item in relation_records):
        raise IntegrityError("unverified FindingRelation cannot be published")

    evidence = _verify_evidence_index(
        evidence_index,
        expected_run_id=expected_run_id,
        expected_revision=expected_revision,
        expected_hash=expected_evidence_index_hash,
    )
    for finding in finding_records:
        for source_field, index_field in _REFERENCE_FIELDS:
            missing = set(finding[source_field]) - evidence[index_field]
            if missing:
                raise IntegrityError(
                    f"Finding references missing evidence: {sorted(missing)}"
                )
    for relation in relation_records:
        missing = (
            set(relation["evidence_refs"])
            | set(relation["contradicting_evidence_refs"])
        ) - evidence["evidence_link_refs"]
        if missing:
            raise IntegrityError(
                f"FindingRelation references missing evidence: {sorted(missing)}"
            )

    cluster_records, cluster_membership = _verify_clusters(
        clusters,
        findings=finding_records,
        relations=relation_records,
        run_id=expected_run_id,
        revision=expected_revision,
    )
    completion_record = copy.deepcopy(dict(completion))
    verify_completion_assessment(completion_record)
    if (
        completion_record["run_id"] != expected_run_id
        or completion_record["revision"] != expected_revision
    ):
        raise IntegrityError("Completion Assessment run or revision mismatch")
    if completion_record["status"] not in {
        "finalization_ready",
        "limited_completion_ready",
    }:
        raise IntegrityError("Completion Assessment does not permit publication")

    records_by_issue, grade_record_ids = _verify_grades(
        findings=finding_records,
        grading_inputs=grading_inputs,
        grade_records=grade_records,
        evidence=evidence,
    )
    finding_by_id = {
        str(item["finding_id"]): item for item in finding_records
    }
    issue_by_finding = {
        finding_id: str(finding["case_id"])
        for finding_id, finding in finding_by_id.items()
    }
    omitted_dispositions = {"merged", "failed", "cancelled"}
    publishable_findings = [
        finding
        for finding in finding_records
        if finding["disposition"] not in omitted_dispositions
    ]
    publishable_ids = {item["finding_id"] for item in publishable_findings}
    issues = [
        _issue(finding, records_by_issue[str(finding["case_id"])])
        for finding in sorted(publishable_findings, key=lambda item: item["case_id"])
    ]
    expert_packets = [
        packet for finding in publishable_findings
        if (packet := _expert_packet(finding)) is not None
    ]
    mapped_relations = [
        {
            "relation_id": relation["relation_id"],
            "from_issue_ref": issue_by_finding[relation["source_finding_id"]],
            "to_issue_ref": issue_by_finding[relation["target_finding_id"]],
            "relation_type": relation["relation_type"],
        }
        for relation in sorted(
            relation_records, key=lambda item: item["relation_id"]
        )
        if relation["source_finding_id"] in publishable_ids
        and relation["target_finding_id"] in publishable_ids
    ]
    final_candidate = {
        "run_summary": {
            "run_id": expected_run_id,
            "revision": expected_revision,
        },
        "mission_summary": {},
        "capability_summary": {},
        "issues": [
            {
                key: value for key, value in issue.items()
                if key != "disposition" and not key.startswith("_")
            }
            for issue in issues
        ],
        "cross_issue_relations": mapped_relations,
        "conditional_responses": [],
        "monitoring": [],
        "blind_spots": [],
        "expert_review_packets": [
            {
                key: value for key, value in packet.items()
                if not key.startswith("_")
            }
            for packet in expert_packets
        ],
        "approvals": [],
        "integrity": {"semantic_fingerprint": "0" * 64},
    }
    SchemaStore().validate("final-result.schema.json", final_candidate)

    structured_output = {
        "schema_version": "1.0.0",
        "issues": issues,
        "grade_record_ids": grade_record_ids,
        "diagnostic_audit": [
            {
                "issue_id": finding["case_id"],
                "finding_id": finding["finding_id"],
                "cluster_id": cluster_membership[finding["finding_id"]],
                "finding_content_hash": finding["content_hash"],
                "grade_record_id": finding["grade"]["grade_record_ref"],
                "finding_disposition": finding["disposition"],
                "publication_disposition": (
                    "omitted" if finding["finding_id"] not in publishable_ids else "accepted"
                ),
            }
            for finding in sorted(
                finding_records, key=lambda item: item["case_id"]
            )
        ],
        "cross_issue_relations": mapped_relations,
        "conditional_responses": [],
        "monitoring": [],
        "blind_spots": [],
        "expert_review_packets": expert_packets,
    }
    manifest = {
        "evidence_index_hash": expected_evidence_index_hash,
        "completion_hash": completion_record["content_hash"],
        "finding_hashes": [
            item["content_hash"]
            for item in sorted(
                finding_records, key=lambda item: item["finding_id"]
            )
        ],
        "relation_hashes": [
            item["content_hash"]
            for item in sorted(
                relation_records, key=lambda item: item["relation_id"]
            )
        ],
        "cluster_hashes": [
            item["content_hash"] for item in cluster_records
        ],
        "grade_record_ids": grade_record_ids,
    }
    body = {
        "schema_version": "1.0.0",
        "run_id": expected_run_id,
        "revision": expected_revision,
        "input_manifest": manifest,
        "structured_output": structured_output,
        "issue_clusters": cluster_records,
        "completion": completion_record,
    }
    return {**body, "content_hash": _digest(body)}


_PROFESSIONAL_FILE_PATHS = {
    "findings": "analysis/professional/findings.json",
    "relations": "analysis/professional/relations.json",
    "clusters": "analysis/professional/issue-clusters.json",
    "completion": "analysis/professional/completion-assessment.json",
    "grading_inputs": "analysis/professional/grading-inputs.json",
    "grade_records": "analysis/professional/grade-records.json",
    "execution_authority": "analysis/professional/execution-authority.json",
    "runtime_result": "analysis/professional/runtime-result.json",
    "evidence_core": "evidence/core.json",
}


def _native_numbers(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return value
    if isinstance(value, dict):
        return {key: _native_numbers(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_native_numbers(child) for child in value]
    return value


def _load_json_file(files: Mapping[str, bytes], path: str) -> Any:
    payload = files.get(path)
    if payload is None:
        raise IntegrityError(f"missing required artifact: {path}")
    if not isinstance(payload, bytes):
        raise IntegrityError(f"invalid required artifact bytes: {path}")
    try:
        return _native_numbers(strict_loads(payload))
    except (UnicodeDecodeError, ValueError) as exc:
        raise IntegrityError(f"invalid JSON artifact: {path}") from exc


def build_professional_publication_from_files(
    files: Mapping[str, bytes],
    *,
    expected_run_id: str,
    expected_revision: int,
) -> dict[str, Any]:
    """Load the complete professional publication input set and fail closed."""

    loaded = {
        name: _load_json_file(files, path)
        for name, path in _PROFESSIONAL_FILE_PATHS.items()
    }
    authority = loaded.pop("execution_authority")
    runtime_result = loaded.pop("runtime_result")
    if not isinstance(authority, Mapping):
        raise IntegrityError("execution authority must be an object")
    verify_execution_authority_gate(authority)
    if (
        authority["run_id"] != expected_run_id
        or authority["revision"] != expected_revision
    ):
        raise IntegrityError("execution authority run or revision mismatch")
    if (
        not authority["execution_allowed"]
        or authority["effective_authority"] == "machine_draft"
    ):
        raise IntegrityError("execution authority does not permit publication")
    if not isinstance(runtime_result, Mapping):
        raise IntegrityError("runtime result must be an object")
    SchemaStore().validate(
        "professional-analysis-runtime-result.schema.json", runtime_result
    )
    runtime_body = {
        key: value for key, value in runtime_result.items() if key != "content_hash"
    }
    if not hmac.compare_digest(
        str(runtime_result["content_hash"]), _digest(runtime_body)
    ):
        raise IntegrityError("runtime result content hash mismatch")
    if (
        runtime_result["run_id"] != expected_run_id
        or runtime_result["revision"] != expected_revision
        or not runtime_result["finalization_allowed"]
    ):
        raise IntegrityError("runtime result does not permit publication")
    if canonical_bytes(runtime_result["execution_authority"]) != canonical_bytes(authority):
        raise IntegrityError("runtime result execution authority mismatch")
    for field in (
        "findings",
        "relations",
        "clusters",
        "completion",
        "grading_inputs",
        "grade_records",
    ):
        if canonical_bytes(runtime_result[field]) != canonical_bytes(loaded[field]):
            raise IntegrityError(f"runtime result {field} mismatch")
    authority_order = {
        "machine_draft": 0, "boundary": 1, "provisional": 2, "full": 3,
    }
    for grading_input in loaded["grading_inputs"]:
        if authority_order[grading_input["pack_authority"]] > authority_order[authority["effective_authority"]]:
            raise IntegrityError("grading input pack authority exceeds execution authority")
    core = loaded.pop("evidence_core")
    if not isinstance(core, Mapping):
        raise IntegrityError("invalid JSON artifact: evidence/core.json")
    EvidenceCoreValidator().validate(core)
    envelope = core["envelope"]
    if (
        envelope["run_id"] != expected_run_id
        or envelope["revision"] != expected_revision
    ):
        raise IntegrityError("Evidence Core run or revision mismatch")
    evidence_body = {
        "run_id": expected_run_id,
        "revision": expected_revision,
        "fact_refs": sorted(item["fact_id"] for item in core["fact_register"]),
        "signal_refs": sorted(item["signal_id"] for item in core["signal_register"]),
        "evidence_link_refs": sorted(
            item["evidence_link_id"] for item in core["evidence_links"]
        ),
        "source_refs": sorted(
            item["source_id"] for item in core["source_registry"]
        ),
    }
    evidence_index = {**evidence_body, "content_hash": _digest(evidence_body)}
    publication = build_professional_publication(
        expected_run_id=expected_run_id,
        expected_revision=expected_revision,
        evidence_index=evidence_index,
        expected_evidence_index_hash=evidence_index["content_hash"],
        **loaded,
    )
    body = {
        key: copy.deepcopy(value)
        for key, value in publication.items()
        if key != "content_hash"
    }
    body["input_manifest"]["evidence_core_hash"] = core["integrity"]["payload_hash"]
    body["input_manifest"]["execution_authority_hash"] = authority["content_hash"]
    body["input_manifest"]["runtime_result_hash"] = runtime_result["content_hash"]
    body["effective_authority"] = authority["effective_authority"]
    body["product_display"] = authority["product_display"]
    return {**body, "content_hash": _digest(body)}


__all__ = [
    "build_professional_publication",
    "build_professional_publication_from_files",
]
