from __future__ import annotations

import copy
import hashlib
import unicodedata
from typing import Any, Mapping

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.questions.index import QuestionIndex
from trusted_ceo_agent.questions.scope import ScopeClosure, resolve_scope


PRIVACY_CLASSIFICATIONS = frozenset(
    {"poc_deidentified", "company_restricted"}
)
PRIVACY_EXCLUDED_FIELDS = (
    "absolute_paths",
    "auth_data",
    "model_drafts",
    "raw_source_rows",
    "resolver_internals",
)


def _strings(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item for item in value if isinstance(item, str) and item}


def _forbidden_conclusions(
    index: QuestionIndex,
    closure: ScopeClosure,
) -> list[str]:
    conclusions: set[str] = set()
    for packet_id in closure.expert_packet_ids:
        packet = index.expert_packets[packet_id]
        conclusions.update(_strings(packet.get("forbidden_conclusions")))
    return sorted(conclusions)


def _quality_conditions(index: QuestionIndex) -> list[str]:
    conditions: set[str] = set()
    for item in index.data_quality.values():
        reason = item.get("reason_code")
        if isinstance(reason, str) and reason:
            conditions.add(reason)
    capabilities = index.capability_map.get("capabilities", [])
    if isinstance(capabilities, list):
        for capability in capabilities:
            if isinstance(capability, Mapping):
                conditions.update(_strings(capability.get("reason_codes")))
    return sorted(conditions)


def _not_assessable_conditions(
    index: QuestionIndex,
    closure: ScopeClosure,
) -> list[str]:
    conditions: set[str] = set()
    for issue_id in closure.issue_ids:
        issue = index.issues[issue_id]
        if issue.get("primary_grade") != "Not Assessable":
            continue
        reasons = _strings(issue.get("not_assessable_reason_codes"))
        if reasons:
            conditions.update(reasons)
        else:
            conditions.add(f"{issue_id}:Not Assessable")
    return sorted(conditions)


def _available_scope_ids(index: QuestionIndex) -> list[str]:
    return sorted(
        {
            "run",
            *index.issues.keys(),
            *index.claims.keys(),
            *index.evidence_links.keys(),
            *index.sources.keys(),
            *index.expert_packets.keys(),
            *index.revision_diffs.keys(),
        }
    )


def _scope_payload(closure: ScopeClosure) -> dict[str, Any]:
    issue_id = (
        closure.issue_ids[0]
        if len(closure.issue_ids) == 1
        else None
    )
    return {
        "scope_kind": closure.scope_kind,
        "scope_instance_id": closure.scope_instance_id,
        "start_refs": list(closure.start_refs),
        "issue_id": issue_id,
    }


def _deidentification(
    privacy_classification: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    deidentified = privacy_classification == "poc_deidentified"
    if deidentified:
        notice = "비식별 POC 자료만 원격 처리할 수 있습니다."
    else:
        notice = "회사 제한 자료는 강한 로컬 격리 검증 후에만 처리할 수 있습니다."
    return (
        {
            "poc_only": deidentified,
            "direct_identifiers_removed": deidentified,
            "notice_ko": notice,
        },
        {
            "deidentified": deidentified,
            "excluded_fields": list(PRIVACY_EXCLUDED_FIELDS),
        },
    )


def unsigned_job(job: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in job.items()
        if key not in {"job_id", "job_hash"}
    }


def build_result_question_job(
    *,
    index: QuestionIndex,
    question: str,
    scope_kind: str,
    scope_instance_id: str,
    privacy_classification: str,
    maximum_context_bytes: int = 131_072,
) -> dict[str, Any]:
    if not isinstance(question, str):
        raise ContractError("question must be a string")
    normalized_question = unicodedata.normalize("NFC", question).strip()
    if not normalized_question or len(normalized_question) > 2_000:
        raise ContractError("question must contain 1..2000 Unicode code points")
    if privacy_classification not in PRIVACY_CLASSIFICATIONS:
        raise ContractError("unknown privacy classification")
    closure = resolve_scope(
        index,
        scope_kind,
        scope_instance_id,
        maximum_bytes=maximum_context_bytes,
    )
    deidentification, privacy = _deidentification(privacy_classification)
    body: dict[str, Any] = {
        "job_version": "1.0.0",
        "run_id": index.run_id,
        "revision": index.revision,
        "question": normalized_question,
        "response_locale": "ko-KR",
        "privacy_classification": privacy_classification,
        "scope": _scope_payload(closure),
        "allowed_issue_refs": list(closure.issue_ids),
        "allowed_claim_refs": list(closure.claim_refs),
        "allowed_fact_refs": list(closure.fact_ids),
        "allowed_signal_refs": list(closure.signal_ids),
        "allowed_evidence_link_ids": list(closure.evidence_link_ids),
        "allowed_source_refs": list(closure.source_refs),
        "allowed_value_refs": list(closure.value_refs),
        "allowed_expert_packet_refs": list(closure.expert_packet_ids),
        "allowed_revision_diff_refs": list(closure.revision_diff_ids),
        "context_blocks": [copy.deepcopy(dict(item)) for item in closure.context_blocks],
        "value_table": [
            copy.deepcopy(dict(index.value_table[value_ref]))
            for value_ref in closure.value_refs
        ],
        "forbidden_conclusions": _forbidden_conclusions(index, closure),
        "data_quality_conditions": _quality_conditions(index),
        "not_assessable_conditions": _not_assessable_conditions(index, closure),
        "deidentification": deidentification,
        "privacy": privacy,
        "context_caps": {
            "max_context_bytes": 131_072,
            "actual_context_bytes": closure.actual_context_bytes,
            "excluded_block_count": 0,
            "max_answer_blocks": 12,
            "max_block_characters": 800,
        },
        "excluded_summary": {
            "excluded": False,
            "reason_codes": [],
            "available_scope_instance_ids": _available_scope_ids(index),
        },
        "output_schema_version": "1.0.0",
    }
    job = {
        **body,
        "job_id": make_id("questionjob", body),
        "job_hash": hashlib.sha256(canonical_bytes(body)).hexdigest(),
    }
    SchemaStore().validate("result-question-job.schema.json", job)
    return job
