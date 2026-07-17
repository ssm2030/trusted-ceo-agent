from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError


RESPONSE_TYPES = (
    "confirm",
    "choose_one",
    "choose_many",
    "free_text",
    "provide_data",
    "provide_alternative_evidence",
    "proceed_limited",
    "exclude_scope",
    "request_explanation",
    "request_changes",
    "stop",
)


_STATE_SPECS: dict[str, dict[str, Any]] = {
    "context_confirmation_required": {
        "gate": "context",
        "action_type": "context_confirmation",
        "title": "분석 맥락을 확인해 주세요",
        "question": "현재 Mission 해석이 맞는지 확인하거나 변경을 요청해 주세요.",
        "why_asked": "확정된 분석 질문과 범위 없이 회사 자료를 판단하지 않기 위해 필요합니다.",
        "current_interpretation": "현재 Mission Contract를 아직 사람이 확인하지 않았습니다.",
        "unanswered_effect": "분석은 Context Gate에서 계속 대기합니다.",
    },
    "data_confirmation_required": {
        "gate": "data",
        "action_type": "data_confirmation",
        "title": "데이터 해석을 확인해 주세요",
        "question": "열, 단위, 기간과 source role 해석이 맞는지 확인해 주세요.",
        "why_asked": "잘못된 매핑이 Fact와 후속 결론으로 승격되는 것을 막기 위해 필요합니다.",
        "current_interpretation": "현재 매핑 제안은 아직 사람의 확인을 받지 않았습니다.",
        "unanswered_effect": "Fact materialization과 전문 분석은 시작되지 않습니다.",
    },
    "scope_narrowing_required": {
        "gate": "scope_narrowing",
        "action_type": "scope_narrowing",
        "title": "분석 범위를 좁혀 주세요",
        "question": "포함·제외 범위와 blind spot을 확인해 주세요.",
        "why_asked": "승인된 범위를 넘거나 카드 한도를 숨긴 분석을 막기 위해 필요합니다.",
        "current_interpretation": "현재 후보 범위가 승인된 분석 한도를 초과합니다.",
        "unanswered_effect": "렌즈 작업은 생성되지 않습니다.",
    },
    "diagnostic_approval_required": {
        "gate": "diagnostic",
        "action_type": "diagnostic_review",
        "title": "진단 후보를 검토해 주세요",
        "question": "후보별 이견과 추가 검증 요청을 기록해 주세요.",
        "why_asked": "사람의 이견과 검증 범위를 승인과 분리해 보존하기 위해 필요합니다.",
        "current_interpretation": "진단 후보는 검증됐지만 아직 최종 승인되지 않았습니다.",
        "unanswered_effect": "심화검사 또는 최종화로 진행하지 않습니다.",
    },
    "final_approval_required": {
        "gate": "final",
        "action_type": "final_review",
        "title": "최종 전달 범위를 검토해 주세요",
        "question": "문구, 전문가 routing과 전달 범위 변경 요청을 기록해 주세요.",
        "why_asked": "최종 승인 전에 전달 내용과 제한을 정확히 고정하기 위해 필요합니다.",
        "current_interpretation": "검증된 결과가 준비됐지만 전달 승인은 아직 없습니다.",
        "unanswered_effect": "Final Result는 publish되지 않습니다.",
    },
}


def _hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def compile_human_action_card(
    *,
    run_id: str,
    base_revision: int,
    workflow_state: str,
    gate: str,
    action_type: str,
    title: str,
    question: str,
    why_asked: str,
    current_interpretation: str,
    evidence_refs: Sequence[str],
    required: bool,
    allowed_response_types: Sequence[str],
    options: Sequence[Mapping[str, Any]],
    recommended_option_id: str | None,
    recommendation_reason: str | None,
    unanswered_effect: str,
    next_step_by_option: Mapping[str, str],
    expires_at: str | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "base_revision": base_revision,
        "workflow_state": workflow_state,
        "gate": gate,
        "action_type": action_type,
        "title": title,
        "question": question,
        "why_asked": why_asked,
        "current_interpretation": current_interpretation,
        "evidence_refs": sorted(set(evidence_refs)),
        "required": required,
        "allowed_response_types": list(allowed_response_types),
        "options": [deepcopy(dict(option)) for option in options],
        "recommended_option_id": recommended_option_id,
        "recommendation_reason": recommendation_reason,
        "unanswered_effect": unanswered_effect,
        "next_step_by_option": dict(next_step_by_option),
        "expires_at": expires_at,
    }
    body["action_id"] = make_id("action", body)
    body["content_hash"] = _hash(body)
    verify_action_card(body)
    return body


def verify_action_card(card: Mapping[str, Any]) -> None:
    value = deepcopy(dict(card))
    SchemaStore().validate("human-action-card.schema.json", value)
    content_hash = value.pop("content_hash")
    if _hash(value) != content_hash:
        raise ContractError("Human Action Card content hash is invalid")
    expected_id_body = dict(value)
    action_id = expected_id_body.pop("action_id")
    if make_id("action", expected_id_body) != action_id:
        raise ContractError("Human Action Card action ID is invalid")
    allowed = set(value["allowed_response_types"])
    option_ids = [str(option["option_id"]) for option in value["options"]]
    if len(option_ids) != len(set(option_ids)):
        raise ContractError("Human Action Card option IDs must be unique")
    if any(option["response_type"] not in allowed for option in value["options"]):
        raise ContractError("Human Action Card option response is not allowlisted")
    if set(option_ids) != set(value["next_step_by_option"]):
        raise ContractError("Human Action Card must describe every option next step")
    recommended = value["recommended_option_id"]
    reason = value["recommendation_reason"]
    if recommended is None and reason is not None:
        raise ContractError("recommendation reason requires a recommended option")
    if recommended is not None and (recommended not in option_ids or reason is None):
        raise ContractError("recommended option and reason must be valid together")


def pending_action_for_state(
    *,
    run_id: str,
    revision: int,
    workflow_state: str,
    evidence_refs: Sequence[str],
    expires_at: str | None,
) -> dict[str, Any] | None:
    spec = _STATE_SPECS.get(workflow_state)
    if spec is None:
        return None
    options = [
        {"option_id": "confirm", "label": "현재 해석 확인", "response_type": "confirm", "description": "현재 해석을 응답으로 기록합니다."},
        {"option_id": "request_changes", "label": "변경 요청", "response_type": "request_changes", "description": "사실·맥락·범위의 변경 내용을 기록합니다."},
        {"option_id": "stop", "label": "분석 중단", "response_type": "stop", "description": "현재 실행을 명시적으로 중단합니다."},
    ]
    return compile_human_action_card(
        run_id=run_id,
        base_revision=revision,
        workflow_state=workflow_state,
        evidence_refs=evidence_refs,
        required=True,
        allowed_response_types=("confirm", "request_changes", "request_explanation", "stop"),
        options=options,
        recommended_option_id=None,
        recommendation_reason=None,
        next_step_by_option={
            "confirm": "별도 terminal approval이 필요한지 안내합니다.",
            "request_changes": "영향받는 downstream 승인을 무효화하고 현재 Gate에 남습니다.",
            "stop": "실행을 stopped_by_human으로 종결합니다.",
        },
        expires_at=expires_at,
        **spec,
    )


def compile_data_request_card(
    *,
    run_id: str,
    base_revision: int,
    missing_source_roles: Sequence[str],
    missing_capabilities: Sequence[str],
    affected_issue_family_refs: Sequence[str],
    affected_domains: Sequence[str],
    evidence_refs: Sequence[str],
    expires_at: str | None,
) -> dict[str, Any]:
    options = [
        {"option_id": "provide_now", "label": "지금 제공", "response_type": "provide_data", "description": "요청 자료를 현재 실행에 추가합니다."},
        {"option_id": "use_alternative", "label": "다른 자료로 대체", "response_type": "provide_alternative_evidence", "description": "대체 근거의 범위와 한계를 기록합니다."},
        {"option_id": "proceed_limited", "label": "자료 없이 제한 분석", "response_type": "proceed_limited", "description": "불가능한 절차와 제품 경계를 명시합니다."},
        {"option_id": "exclude_scope", "label": "이번 범위에서 제외", "response_type": "exclude_scope", "description": "제외 범위와 blind spot을 기록합니다."},
        {"option_id": "stop", "label": "분석 중단", "response_type": "stop", "description": "현재 실행을 명시적으로 중단합니다."},
    ]
    roles = ", ".join(sorted(set(missing_source_roles))) or "없음"
    capabilities = ", ".join(sorted(set(missing_capabilities))) or "없음"
    families = ", ".join(sorted(set(affected_issue_family_refs))) or "없음"
    domains = ", ".join(sorted(set(affected_domains))) or "없음"
    return compile_human_action_card(
        run_id=run_id,
        base_revision=base_revision,
        workflow_state="data_confirmation_required",
        gate="data",
        action_type="data_request",
        title="추가 자료가 필요합니다",
        question="자료를 제공하거나 제한 분석 방식을 선택해 주세요.",
        why_asked=f"부족한 source role: {roles}; capability: {capabilities}.",
        current_interpretation=f"영향 Issue Family: {families}; domain: {domains}.",
        evidence_refs=evidence_refs,
        required=True,
        allowed_response_types=(
            "provide_data", "provide_alternative_evidence", "proceed_limited",
            "exclude_scope", "request_explanation", "stop",
        ),
        options=options,
        recommended_option_id=None,
        recommendation_reason=None,
        unanswered_effect="필수 절차는 실행되지 않으며 영향 범위는 Boundary 또는 Not Assessable로 남습니다.",
        next_step_by_option={
            "provide_now": "새 Source snapshot과 Capability 검증을 수행합니다.",
            "use_alternative": "대체 근거의 적합성과 독립성을 검증합니다.",
            "proceed_limited": "실행 가능 절차만 수행하고 제한 완료 후보로 보냅니다.",
            "exclude_scope": "Coverage와 blind spot에 제외 범위를 표시합니다.",
            "stop": "실행을 stopped_by_human으로 종결합니다.",
        },
        expires_at=expires_at,
    )
