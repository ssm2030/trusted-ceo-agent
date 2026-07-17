from __future__ import annotations

import copy
import hashlib
import hmac
from collections.abc import Mapping, Sequence
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


FINDING_INPUT_FIELDS = frozenset({
    "run_id",
    "revision",
    "case_id",
    "event_id",
    "signal_ids",
    "domain_assessment_refs",
    "issue_family_refs",
    "fact_refs",
    "evidence_link_refs",
    "source_refs",
    "procedure_result_refs",
    "norm_refs",
    "calculation_refs",
    "hypotheses",
    "counter_hypotheses",
    "supporting_evidence_refs",
    "contradicting_evidence_refs",
    "unresolved_conflicts",
    "disposition",
    "conclusion",
    "conclusion_strength",
    "impact_dimensions",
    "coverage",
    "data_gaps",
    "expert_review",
    "grade",
    "authority",
    "uncertainty",
    "verification",
    "related_finding_ids",
    "supersedes_finding_id",
})
FINDING_LIST_FIELDS = (
    "signal_ids",
    "domain_assessment_refs",
    "issue_family_refs",
    "fact_refs",
    "evidence_link_refs",
    "source_refs",
    "procedure_result_refs",
    "norm_refs",
    "calculation_refs",
    "hypotheses",
    "counter_hypotheses",
    "supporting_evidence_refs",
    "contradicting_evidence_refs",
    "unresolved_conflicts",
    "data_gaps",
    "related_finding_ids",
)
DISPOSITIONS = frozenset({
    "substantiated",
    "not_substantiated",
    "inconclusive",
    "merged",
    "out_of_scope",
    "expert_review_required",
    "deferred",
    "failed",
    "cancelled",
})
CONCLUSION_QUALIFIERS = frozenset({
    "supported_within_current_scope",
    "not_supported_within_current_scope",
    "insufficient_evidence",
    "expert_judgment_required",
    "merged_into_other_finding",
    "outside_approved_scope",
    "deferred_follow_up",
    "required_work_failed",
    "cancelled_by_human",
})
IMPACT_DIMENSIONS = (
    "amount", "cash", "legal", "tax", "human", "operations", "control",
)
IMPACT_VALUES = frozenset({
    "material", "possible", "immaterial", "unknown", "not_assessed",
})
RELATION_TYPES = frozenset({
    "duplicate_of",
    "supports",
    "contradicts",
    "possible_cause_of",
    "possible_consequence_of",
    "shares_driver_with",
    "depends_on",
    "requires_joint_decision_with",
})
RELATION_INPUT_FIELDS = frozenset({
    "run_id",
    "revision",
    "source_finding_id",
    "target_finding_id",
    "relation_type",
    "evidence_refs",
    "confidence_status",
    "contradicting_evidence_refs",
})
SYMMETRIC_RELATIONS = frozenset({
    "duplicate_of", "shares_driver_with", "requires_joint_decision_with",
})
CLUSTER_INPUT_FIELDS = frozenset({
    "run_id",
    "revision",
    "finding_ids",
    "relation_ids",
    "decision_unit",
    "unresolved_conflicts",
})


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _content_hash(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_hash", None)
    return _digest(body)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value


def _nullable_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _integer(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContractError(f"{field} must be an integer >= {minimum}")
    return value


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError(f"{field} must be boolean")
    return value


def _string_set(
    values: Any,
    field: str,
    *,
    non_empty: bool = False,
) -> list[str]:
    if not isinstance(values, (list, tuple)):
        raise ContractError(f"{field} must be an array")
    result = [_text(item, field) for item in values]
    if len(result) != len(set(result)):
        raise ContractError(f"{field} contains duplicates")
    if non_empty and not result:
        raise ContractError(f"{field} must not be empty")
    return sorted(result)


def _exact_object(value: Any, fields: set[str] | frozenset[str], name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(fields):
        if isinstance(value, Mapping):
            missing = sorted(set(fields) - set(value))
            extra = sorted(set(value) - set(fields))
        else:
            missing = sorted(fields)
            extra = []
        raise ContractError(f"{name} fields are invalid: missing={missing}, extra={extra}")
    return value


def _normalize_conclusion(value: Any) -> dict[str, Any]:
    raw = _exact_object(
        value, {"statement", "scope", "basis_refs", "qualifier"}, "conclusion"
    )
    qualifier = _text(raw["qualifier"], "conclusion.qualifier")
    if qualifier not in CONCLUSION_QUALIFIERS:
        raise ContractError(f"invalid conclusion qualifier: {qualifier}")
    return {
        "statement": _text(raw["statement"], "conclusion.statement"),
        "scope": _text(raw["scope"], "conclusion.scope"),
        "basis_refs": _string_set(raw["basis_refs"], "conclusion.basis_refs"),
        "qualifier": qualifier,
    }


def _normalize_coverage(value: Any) -> dict[str, Any]:
    raw = _exact_object(
        value,
        {
            "required_procedures_complete",
            "counter_evidence_complete",
            "evidence_coverage_complete",
            "missing_evidence_refs",
            "missing_procedure_refs",
            "scope_note",
        },
        "coverage",
    )
    return {
        "required_procedures_complete": _boolean(
            raw["required_procedures_complete"], "coverage.required_procedures_complete"
        ),
        "counter_evidence_complete": _boolean(
            raw["counter_evidence_complete"], "coverage.counter_evidence_complete"
        ),
        "evidence_coverage_complete": _boolean(
            raw["evidence_coverage_complete"], "coverage.evidence_coverage_complete"
        ),
        "missing_evidence_refs": _string_set(
            raw["missing_evidence_refs"], "coverage.missing_evidence_refs"
        ),
        "missing_procedure_refs": _string_set(
            raw["missing_procedure_refs"], "coverage.missing_procedure_refs"
        ),
        "scope_note": _text(raw["scope_note"], "coverage.scope_note"),
    }


def _normalize_expert_review(value: Any) -> dict[str, Any]:
    raw = _exact_object(
        value, {"required", "packet_ref", "decision_boundary", "owner"}, "expert_review"
    )
    return {
        "required": _boolean(raw["required"], "expert_review.required"),
        "packet_ref": _nullable_text(raw["packet_ref"], "expert_review.packet_ref"),
        "decision_boundary": _nullable_text(
            raw["decision_boundary"], "expert_review.decision_boundary"
        ),
        "owner": _nullable_text(raw["owner"], "expert_review.owner"),
    }


def _normalize_grade(value: Any) -> dict[str, Any]:
    raw = _exact_object(value, {"status", "grade_record_ref"}, "grade")
    status = _text(raw["status"], "grade.status")
    if status not in {"published", "withheld"}:
        raise ContractError(f"invalid Grade status: {status}")
    grade_record_ref = _nullable_text(raw["grade_record_ref"], "grade.grade_record_ref")
    if status == "published" and grade_record_ref is None:
        raise ContractError("published Grade requires a GradeRecord reference")
    if status == "withheld" and grade_record_ref is not None:
        raise ContractError("withheld Grade cannot expose a GradeRecord reference")
    return {"status": status, "grade_record_ref": grade_record_ref}


def _normalize_authority(value: Any) -> dict[str, Any]:
    raw = _exact_object(
        value, {"effective_level", "pack_release_refs", "approval_refs"}, "authority"
    )
    level = _text(raw["effective_level"], "authority.effective_level")
    if level not in {"machine_draft", "Boundary", "Provisional", "Full"}:
        raise ContractError(f"invalid authority level: {level}")
    pack_refs = _string_set(
        raw["pack_release_refs"], "authority.pack_release_refs", non_empty=True
    )
    approval_refs = _string_set(raw["approval_refs"], "authority.approval_refs")
    if level == "Full" and not approval_refs:
        raise ContractError("Full authority requires an expert Approval reference")
    return {
        "effective_level": level,
        "pack_release_refs": pack_refs,
        "approval_refs": approval_refs,
    }


def _normalize_uncertainty(value: Any) -> dict[str, Any]:
    raw = _exact_object(value, {"status", "reason_codes"}, "uncertainty")
    status = _text(raw["status"], "uncertainty.status")
    if status not in {"resolved", "partial", "material"}:
        raise ContractError(f"invalid uncertainty status: {status}")
    reasons = _string_set(raw["reason_codes"], "uncertainty.reason_codes")
    if status != "resolved" and not reasons:
        raise ContractError("unresolved uncertainty requires reason codes")
    return {"status": status, "reason_codes": reasons}


def _normalize_verification(value: Any) -> dict[str, Any]:
    raw = _exact_object(
        value,
        {
            "required_procedure_refs",
            "completed_procedure_refs",
            "counter_evidence_checked",
            "counter_evidence_refs",
            "verification_step_refs",
        },
        "verification",
    )
    return {
        "required_procedure_refs": _string_set(
            raw["required_procedure_refs"], "verification.required_procedure_refs"
        ),
        "completed_procedure_refs": _string_set(
            raw["completed_procedure_refs"], "verification.completed_procedure_refs"
        ),
        "counter_evidence_checked": _boolean(
            raw["counter_evidence_checked"], "verification.counter_evidence_checked"
        ),
        "counter_evidence_refs": _string_set(
            raw["counter_evidence_refs"], "verification.counter_evidence_refs"
        ),
        "verification_step_refs": _string_set(
            raw["verification_step_refs"], "verification.verification_step_refs"
        ),
    }


def _normalize_finding_spec(raw: Mapping[str, Any]) -> dict[str, Any]:
    if set(raw) != FINDING_INPUT_FIELDS:
        missing = sorted(FINDING_INPUT_FIELDS - set(raw))
        extra = sorted(set(raw) - FINDING_INPUT_FIELDS)
        raise ContractError(
            f"Finding input fields are invalid: missing={missing}, extra={extra}"
        )
    run_id = _text(raw["run_id"], "run_id")
    if not run_id.startswith("run_"):
        raise ContractError("run_id must begin with run_")
    disposition = _text(raw["disposition"], "disposition")
    if disposition not in DISPOSITIONS:
        raise ContractError(f"invalid Finding disposition: {disposition}")
    strength = _text(raw["conclusion_strength"], "conclusion_strength")
    if strength not in {"tentative", "supported", "strong"}:
        raise ContractError(f"invalid conclusion strength: {strength}")
    impacts = _exact_object(raw["impact_dimensions"], set(IMPACT_DIMENSIONS), "impact_dimensions")
    normalized_impacts: dict[str, str] = {}
    for name in IMPACT_DIMENSIONS:
        impact = _text(impacts[name], f"impact_dimensions.{name}")
        if impact not in IMPACT_VALUES:
            raise ContractError(f"invalid impact value for {name}: {impact}")
        normalized_impacts[name] = impact

    normalized: dict[str, Any] = {
        "run_id": run_id,
        "revision": _integer(raw["revision"], "revision"),
        "case_id": _text(raw["case_id"], "case_id"),
        "event_id": _text(raw["event_id"], "event_id"),
        "disposition": disposition,
        "conclusion": _normalize_conclusion(raw["conclusion"]),
        "conclusion_strength": strength,
        "impact_dimensions": normalized_impacts,
        "coverage": _normalize_coverage(raw["coverage"]),
        "expert_review": _normalize_expert_review(raw["expert_review"]),
        "grade": _normalize_grade(raw["grade"]),
        "authority": _normalize_authority(raw["authority"]),
        "uncertainty": _normalize_uncertainty(raw["uncertainty"]),
        "verification": _normalize_verification(raw["verification"]),
        "supersedes_finding_id": _nullable_text(
            raw["supersedes_finding_id"], "supersedes_finding_id"
        ),
    }
    for field in FINDING_LIST_FIELDS:
        normalized[field] = _string_set(
            raw[field], field, non_empty=field == "signal_ids"
        )
    return normalized


def _validate_finding_semantics(record: Mapping[str, Any]) -> None:
    disposition = record["disposition"]
    coverage = record["coverage"]
    verification = record["verification"]
    conclusion = record["conclusion"]
    required = set(verification["required_procedure_refs"])
    completed = set(verification["completed_procedure_refs"])
    if disposition in {"substantiated", "not_substantiated"} and not required.issubset(completed):
        raise ContractError("terminal supported Finding has incomplete required Procedures")
    if disposition == "substantiated":
        if not record["fact_refs"]:
            raise ContractError("substantiated Finding requires Fact references")
        if not record["evidence_link_refs"] or not record["supporting_evidence_refs"]:
            raise ContractError("substantiated Finding requires supporting Evidence")
        if not record["procedure_result_refs"]:
            raise ContractError("substantiated Finding requires Procedure results")
        if not (
            coverage["required_procedures_complete"]
            and coverage["counter_evidence_complete"]
            and coverage["evidence_coverage_complete"]
            and verification["counter_evidence_checked"]
        ):
            raise ContractError(
                "substantiated Finding requires Procedure, counter-evidence, and Coverage"
            )
        if conclusion["qualifier"] != "supported_within_current_scope":
            raise ContractError("substantiated Finding has an invalid scope qualifier")
    if disposition == "not_substantiated":
        if conclusion["qualifier"] != "not_supported_within_current_scope":
            raise ContractError(
                "not_substantiated means not supported within the current scope"
            )
        if not coverage["required_procedures_complete"]:
            raise ContractError("not_substantiated requires completed Procedures")
    if disposition == "inconclusive":
        if conclusion["qualifier"] != "insufficient_evidence":
            raise ContractError("inconclusive Finding requires insufficient_evidence")
        if not record["data_gaps"]:
            raise ContractError("inconclusive Finding requires explicit data gaps")
        if not (
            coverage["missing_evidence_refs"] or coverage["missing_procedure_refs"]
        ):
            raise ContractError(
                "inconclusive Finding requires missing Evidence or Procedure references"
            )
        if record["uncertainty"]["status"] != "material":
            raise ContractError("inconclusive Finding requires material uncertainty")
    if disposition == "expert_review_required":
        expert = record["expert_review"]
        if not (
            expert["required"]
            and expert["packet_ref"]
            and expert["decision_boundary"]
            and expert["owner"]
        ):
            raise ContractError(
                "expert_review_required needs packet, decision boundary, and owner"
            )
        if conclusion["qualifier"] != "expert_judgment_required":
            raise ContractError("expert_review_required has an invalid qualifier")
    if record["authority"]["effective_level"] == "Full" and not record["authority"]["approval_refs"]:
        raise ContractError("Full authority requires an expert Approval reference")
    if record["conclusion_strength"] == "strong" and record["authority"]["effective_level"] != "Full":
        raise ContractError("strong conclusion requires Full authority")


def _finding_source(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(record[key])
        for key in FINDING_INPUT_FIELDS
    }


def _verify_finding(record: Mapping[str, Any]) -> None:
    SchemaStore().validate("finding-record.schema.json", dict(record))
    expected_source_hash = _digest(_finding_source(record))
    if not hmac.compare_digest(str(record["created_from_hash"]), expected_source_hash):
        raise ContractError("Finding created_from_hash mismatch")
    if record["finding_id"] != f"finding_{expected_source_hash[:24]}":
        raise ContractError("Finding ID does not match created_from_hash")
    if not hmac.compare_digest(str(record["content_hash"]), _content_hash(record)):
        raise ContractError("Finding content hash mismatch")
    _validate_finding_semantics(record)


def build_finding(
    spec: Mapping[str, Any],
    *,
    prior_findings: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build one immutable D09 §10.2 Finding from runtime-owned references."""

    if not isinstance(spec, Mapping):
        raise ContractError("Finding input must be an object")
    normalized = _normalize_finding_spec(spec)
    priors = [copy.deepcopy(dict(item)) for item in prior_findings]
    if priors:
        validate_finding_records(priors)
    prior_by_id = {item["finding_id"]: item for item in priors}
    supersedes = normalized["supersedes_finding_id"]
    same_case = [
        item
        for item in priors
        if item["run_id"] == normalized["run_id"]
        and item["case_id"] == normalized["case_id"]
    ]
    if supersedes is None and same_case:
        raise ContractError("new conclusion for an existing case must supersede a Finding")
    if supersedes is not None:
        prior = prior_by_id.get(supersedes)
        if prior is None:
            raise ContractError(f"superseded Finding does not exist: {supersedes}")
        if (
            prior["run_id"] != normalized["run_id"]
            or prior["case_id"] != normalized["case_id"]
            or prior["event_id"] != normalized["event_id"]
        ):
            raise ContractError("Finding supersession cannot cross run, case, or event")
        if normalized["revision"] <= prior["revision"]:
            raise ContractError("superseding Finding must use a later revision")

    _validate_finding_semantics(normalized)
    created_from_hash = _digest(normalized)
    record: dict[str, Any] = {
        "finding_id": f"finding_{created_from_hash[:24]}",
        "schema_version": "1.0.0",
        **copy.deepcopy(normalized),
        "created_from_hash": created_from_hash,
        "content_hash": "",
        "producer": "analysis_runtime",
    }
    record["content_hash"] = _content_hash(record)
    _verify_finding(record)
    validate_finding_records([*priors, record])
    return record


def validate_finding_records(findings: Sequence[Mapping[str, Any]]) -> None:
    records = [copy.deepcopy(dict(item)) for item in findings]
    by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        _verify_finding(record)
        finding_id = record["finding_id"]
        if finding_id in by_id:
            raise ContractError(f"duplicate Finding: {finding_id}")
        by_id[finding_id] = record

    roots: dict[tuple[str, str], str] = {}
    child_by_parent: dict[str, str] = {}
    parent_by_child: dict[str, str] = {}
    for finding_id, record in by_id.items():
        parent_id = record["supersedes_finding_id"]
        if parent_id is None:
            key = (record["run_id"], record["case_id"])
            if key in roots:
                raise ContractError(f"multiple root Findings for one SignalCase: {key}")
            roots[key] = finding_id
        else:
            parent = by_id.get(parent_id)
            if parent is None:
                raise ContractError(f"dangling supersession: {parent_id}")
            if (
                parent["run_id"] != record["run_id"]
                or parent["case_id"] != record["case_id"]
                or parent["event_id"] != record["event_id"]
            ):
                raise ContractError("Finding supersession crossed an immutable boundary")
            if record["revision"] <= parent["revision"]:
                raise ContractError("Finding supersession revision did not advance")
            if parent_id in child_by_parent:
                raise ContractError(f"Finding supersession fork: {parent_id}")
            child_by_parent[parent_id] = finding_id
            parent_by_child[finding_id] = parent_id
        dangling_related = set(record["related_finding_ids"]) - set(by_id)
        if dangling_related:
            raise ContractError(
                f"Finding has dangling related references: {sorted(dangling_related)}"
            )

    for finding_id in by_id:
        seen: set[str] = set()
        cursor = finding_id
        while cursor in parent_by_child:
            if cursor in seen:
                raise ContractError("Finding supersession cycle")
            seen.add(cursor)
            cursor = parent_by_child[cursor]


def _normalize_relation_spec(raw: Mapping[str, Any]) -> dict[str, Any]:
    if set(raw) != RELATION_INPUT_FIELDS:
        missing = sorted(RELATION_INPUT_FIELDS - set(raw))
        extra = sorted(set(raw) - RELATION_INPUT_FIELDS)
        raise ContractError(
            f"FindingRelation input fields are invalid: missing={missing}, extra={extra}"
        )
    relation_type = _text(raw["relation_type"], "relation_type")
    if relation_type not in RELATION_TYPES:
        raise ContractError(f"invalid Finding relation type: {relation_type}")
    confidence = _text(raw["confidence_status"], "confidence_status")
    if confidence not in {"candidate", "provisional", "verified", "contested"}:
        raise ContractError(f"invalid relation confidence: {confidence}")
    normalized = {
        "run_id": _text(raw["run_id"], "run_id"),
        "revision": _integer(raw["revision"], "revision"),
        "source_finding_id": _text(raw["source_finding_id"], "source_finding_id"),
        "target_finding_id": _text(raw["target_finding_id"], "target_finding_id"),
        "relation_type": relation_type,
        "evidence_refs": _string_set(
            raw["evidence_refs"], "evidence_refs", non_empty=True
        ),
        "confidence_status": confidence,
        "contradicting_evidence_refs": _string_set(
            raw["contradicting_evidence_refs"], "contradicting_evidence_refs"
        ),
    }
    if relation_type in {"possible_cause_of", "possible_consequence_of"}:
        if confidence != "verified":
            raise ContractError("causal relation requires verified confidence")
    if relation_type in SYMMETRIC_RELATIONS:
        if normalized["source_finding_id"] > normalized["target_finding_id"]:
            normalized["source_finding_id"], normalized["target_finding_id"] = (
                normalized["target_finding_id"],
                normalized["source_finding_id"],
            )
    return normalized


def _relation_source(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(record[key])
        for key in RELATION_INPUT_FIELDS
    }


def _verify_relation(record: Mapping[str, Any]) -> None:
    SchemaStore().validate("finding-relation.schema.json", dict(record))
    expected_source_hash = _digest(_relation_source(record))
    if not hmac.compare_digest(str(record["created_from_hash"]), expected_source_hash):
        raise ContractError("FindingRelation created_from_hash mismatch")
    if record["relation_id"] != f"relation_{expected_source_hash[:24]}":
        raise ContractError("FindingRelation ID does not match created_from_hash")
    if not hmac.compare_digest(str(record["content_hash"]), _content_hash(record)):
        raise ContractError("FindingRelation content hash mismatch")


def build_finding_relation(
    spec: Mapping[str, Any],
    findings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not isinstance(spec, Mapping):
        raise ContractError("FindingRelation input must be an object")
    validate_finding_records(findings)
    finding_by_id = {item["finding_id"]: item for item in findings}
    normalized = _normalize_relation_spec(spec)
    source = finding_by_id.get(normalized["source_finding_id"])
    target = finding_by_id.get(normalized["target_finding_id"])
    if source is None or target is None:
        raise ContractError("FindingRelation has a dangling endpoint")
    if source["finding_id"] == target["finding_id"]:
        raise ContractError("FindingRelation cannot point to itself")
    if source["run_id"] != target["run_id"] or source["run_id"] != normalized["run_id"]:
        raise ContractError("FindingRelation endpoints must share a run")
    if normalized["revision"] < max(source["revision"], target["revision"]):
        raise ContractError("FindingRelation revision predates an endpoint")

    created_from_hash = _digest(normalized)
    record = {
        "relation_id": f"relation_{created_from_hash[:24]}",
        "schema_version": "1.0.0",
        **copy.deepcopy(normalized),
        "created_from_hash": created_from_hash,
        "content_hash": "",
        "producer": "analysis_runtime",
    }
    record["content_hash"] = _content_hash(record)
    _verify_relation(record)
    return record


def _reject_directed_cycle(edges: Sequence[tuple[str, str]]) -> None:
    successors: dict[str, set[str]] = {}
    nodes: set[str] = set()
    for source, target in edges:
        successors.setdefault(source, set()).add(target)
        nodes.update((source, target))
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ContractError("Finding relation graph contains a directed cycle")
        if node in visited:
            return
        visiting.add(node)
        for successor in sorted(successors.get(node, ())):
            visit(successor)
        visiting.remove(node)
        visited.add(node)

    for node in sorted(nodes):
        visit(node)


def validate_finding_graph(
    findings: Sequence[Mapping[str, Any]],
    relations: Sequence[Mapping[str, Any]],
) -> None:
    validate_finding_records(findings)
    finding_by_id = {item["finding_id"]: item for item in findings}
    relation_by_id: dict[str, dict[str, Any]] = {}
    types_by_directed_pair: dict[tuple[str, str], set[str]] = {}
    types_by_undirected_pair: dict[tuple[str, str], set[str]] = {}
    directed_edges: list[tuple[str, str]] = []
    semantic_edges: set[tuple[str, str, str]] = set()

    for raw in relations:
        relation = copy.deepcopy(dict(raw))
        _verify_relation(relation)
        relation_id = relation["relation_id"]
        if relation_id in relation_by_id:
            raise ContractError(f"duplicate FindingRelation: {relation_id}")
        relation_by_id[relation_id] = relation
        source_id = relation["source_finding_id"]
        target_id = relation["target_finding_id"]
        source = finding_by_id.get(source_id)
        target = finding_by_id.get(target_id)
        if source is None or target is None:
            raise ContractError(f"FindingRelation has dangling endpoints: {relation_id}")
        if source_id == target_id:
            raise ContractError("FindingRelation cannot point to itself")
        if source["run_id"] != target["run_id"] or relation["run_id"] != source["run_id"]:
            raise ContractError("FindingRelation endpoints must share a run")
        if relation["revision"] < max(source["revision"], target["revision"]):
            raise ContractError("FindingRelation revision predates an endpoint")

        directed_pair = (source_id, target_id)
        undirected_pair = tuple(sorted((source_id, target_id)))
        types_by_directed_pair.setdefault(directed_pair, set()).add(
            relation["relation_type"]
        )
        types_by_undirected_pair.setdefault(undirected_pair, set()).add(
            relation["relation_type"]
        )
        relation_type = relation["relation_type"]
        if relation_type == "possible_cause_of":
            edge = (source_id, target_id)
            semantic = ("causal", *edge)
            directed_edges.append(edge)
            if semantic in semantic_edges:
                raise ContractError("duplicate semantic causal relation")
            semantic_edges.add(semantic)
        elif relation_type == "possible_consequence_of":
            edge = (target_id, source_id)
            semantic = ("causal", *edge)
            directed_edges.append(edge)
            if semantic in semantic_edges:
                raise ContractError("duplicate semantic causal relation")
            semantic_edges.add(semantic)
        elif relation_type == "depends_on":
            directed_edges.append((source_id, target_id))

    for pair, types in types_by_directed_pair.items():
        if {"supports", "contradicts"}.issubset(types):
            raise ContractError(f"conflicting support relations for {pair}")
    for pair, types in types_by_undirected_pair.items():
        if "duplicate_of" in types and len(types) > 1:
            raise ContractError(f"duplicate_of conflicts with another relation for {pair}")
    _reject_directed_cycle(directed_edges)


def _normalize_cluster_spec(raw: Mapping[str, Any]) -> dict[str, Any]:
    if set(raw) != CLUSTER_INPUT_FIELDS:
        missing = sorted(CLUSTER_INPUT_FIELDS - set(raw))
        extra = sorted(set(raw) - CLUSTER_INPUT_FIELDS)
        raise ContractError(
            f"IssueCluster input fields are invalid: missing={missing}, extra={extra}"
        )
    decision = _exact_object(
        raw["decision_unit"],
        {"title", "decision_required", "owner_role", "option_refs"},
        "decision_unit",
    )
    return {
        "run_id": _text(raw["run_id"], "run_id"),
        "revision": _integer(raw["revision"], "revision"),
        "finding_ids": _string_set(raw["finding_ids"], "finding_ids", non_empty=True),
        "relation_ids": _string_set(raw["relation_ids"], "relation_ids"),
        "decision_unit": {
            "title": _text(decision["title"], "decision_unit.title"),
            "decision_required": _boolean(
                decision["decision_required"], "decision_unit.decision_required"
            ),
            "owner_role": _text(decision["owner_role"], "decision_unit.owner_role"),
            "option_refs": _string_set(
                decision["option_refs"], "decision_unit.option_refs"
            ),
        },
        "unresolved_conflicts": _string_set(
            raw["unresolved_conflicts"], "unresolved_conflicts"
        ),
    }


def build_issue_cluster(
    spec: Mapping[str, Any],
    *,
    findings: Sequence[Mapping[str, Any]],
    relations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not isinstance(spec, Mapping):
        raise ContractError("IssueCluster input must be an object")
    validate_finding_graph(findings, relations)
    normalized = _normalize_cluster_spec(spec)
    finding_by_id = {item["finding_id"]: item for item in findings}
    relation_by_id = {item["relation_id"]: item for item in relations}
    missing_findings = set(normalized["finding_ids"]) - set(finding_by_id)
    missing_relations = set(normalized["relation_ids"]) - set(relation_by_id)
    if missing_findings:
        raise ContractError(f"IssueCluster has dangling Findings: {sorted(missing_findings)}")
    if missing_relations:
        raise ContractError(f"IssueCluster has dangling relations: {sorted(missing_relations)}")
    selected_findings = set(normalized["finding_ids"])
    for finding_id in selected_findings:
        finding = finding_by_id[finding_id]
        if finding["run_id"] != normalized["run_id"]:
            raise ContractError("IssueCluster cannot cross runs")
        if finding["revision"] > normalized["revision"]:
            raise ContractError("IssueCluster revision predates a Finding")

    adjacency = {finding_id: set() for finding_id in selected_findings}
    for relation_id in normalized["relation_ids"]:
        relation = relation_by_id[relation_id]
        endpoints = {
            relation["source_finding_id"], relation["target_finding_id"],
        }
        if not endpoints.issubset(selected_findings):
            raise ContractError("IssueCluster relation escapes its Finding set")
        if relation["confidence_status"] != "verified":
            raise ContractError("IssueCluster may only use verified relations")
        source, target = tuple(endpoints)
        adjacency[source].add(target)
        adjacency[target].add(source)

    if len(selected_findings) > 1:
        if not normalized["relation_ids"]:
            raise ContractError("multi-Finding IssueCluster must be relation-connected")
        start = min(selected_findings)
        seen = {start}
        stack = [start]
        while stack:
            current = stack.pop()
            for neighbor in sorted(adjacency[current]):
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        if seen != selected_findings:
            raise ContractError("IssueCluster relation graph is disconnected")

    created_from_hash = _digest(normalized)
    record = {
        "cluster_id": f"cluster_{created_from_hash[:24]}",
        "schema_version": "1.0.0",
        **copy.deepcopy(normalized),
        "created_from_hash": created_from_hash,
        "content_hash": "",
    }
    record["content_hash"] = _content_hash(record)
    SchemaStore().validate("issue-cluster.schema.json", record)
    if not hmac.compare_digest(str(record["content_hash"]), _content_hash(record)):
        raise ContractError("IssueCluster content hash mismatch")
    return record
