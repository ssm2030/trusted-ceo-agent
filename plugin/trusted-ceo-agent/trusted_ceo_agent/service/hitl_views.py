from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from trusted_ceo_agent.application.models import ApplicationResult
from trusted_ceo_agent.canonical import strict_loads
from trusted_ceo_agent.errors import ContractError, IntegrityError
from trusted_ceo_agent.mission import CONTEXT_EDITABLE_FIELDS
from trusted_ceo_agent.service.contracts import HitlCard, HitlSection
from trusted_ceo_agent.service.run_store import ServiceManifest


DATA_FIELDS = (
    "observation_role",
    "unit_code",
    "scale",
    "time_role",
    "dimension_code",
)
_DATA_FIELDS = DATA_FIELDS


def _json_value(payload: bytes | None, *, label: str, default: Any) -> Any:
    if payload is None:
        return default
    value = strict_loads(payload)
    if value is None:
        raise ContractError(f"{label} must not be null")
    return value


def pending_gate(manifest: ServiceManifest) -> str:
    if manifest.stage == "context_hitl":
        return "context"
    if manifest.stage == "data_hitl":
        return "data"
    if manifest.stage == "diagnostic_hitl":
        return "diagnostic"
    if manifest.stage == "final_hitl":
        return "final"
    raise ContractError("pending approval gate is unsupported")


def build_hitl_card(
    manifest: ServiceManifest,
    state: ApplicationResult,
    files: Mapping[str, bytes],
) -> HitlCard:
    if manifest.pending_approval_request_id is None or state.revision is None:
        raise IntegrityError("pending approval metadata is incomplete")
    gate = pending_gate(manifest)
    mission = _json_value(
        files.get("mission/mission-contract.json"),
        label="mission contract",
        default={},
    )
    sources = _json_value(
        files.get("sources/registry.json"),
        label="source registry",
        default=[],
    )
    source_refs = [str(source["source_id"]) for source in sources]
    source_items = [
        (
            f"{source.get('display_name', '이름 없는 파일')} · "
            f"{source.get('media_type', 'unknown')} · "
            f"{source.get('size_bytes', 0)} bytes"
        )
        for source in sources
    ] or ["첨부된 데이터 파일이 없습니다."]
    sections = [
        HitlSection(
            kind="source_summary",
            title="파일과 테이블 요약",
            items=source_items,
            target_refs=source_refs,
        ),
    ]
    target_refs = list(source_refs)
    if gate == "context":
        mission_ref = str(mission.get("mission_contract_id", "mission_draft"))
        sections.insert(0, HitlSection(
            kind="mission",
            title="목표와 판단 기준 초안",
            items=[
                f"핵심 질문: {mission.get('business_question', '미정')}",
                f"판단 맥락: {mission.get('decision_context', '미정')}",
                (
                    "분석 기간: "
                    + json.dumps(
                        mission.get("analysis_horizon", {}),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                ),
            ],
            target_refs=[mission_ref],
        ))
        sections.append(HitlSection(
            kind="risk",
            title="승인 전 확인",
            items=["이 승인이 기록되기 전에는 데이터 분석을 시작하지 않습니다."],
            target_refs=[mission_ref],
        ))
        target_refs.insert(0, mission_ref)
        return HitlCard(
            hitl_kind="context_data",
            request_id=manifest.pending_approval_request_id,
            base_revision=state.revision,
            title="분석 목표와 범위를 확인해 주세요",
            summary="검증된 Mission 초안과 첨부 파일 요약입니다.",
            target_refs=target_refs,
            allowed_decisions=["approve", "approve_with_edits", "stop"],
            editable_fields=sorted(CONTEXT_EDITABLE_FIELDS),
            sections=sections,
        )
    if gate == "diagnostic":
        integrated = _json_value(
            files.get("reasoning/integrated-assessment.json"),
            label="integrated assessment",
            default={},
        )
        payload = integrated.get("payload", integrated)
        issues = payload.get("integrated_issues", [])
        issue_refs = [str(issue["local_key"]) for issue in issues]
        issue_items = [
            (
                f"{issue['local_key']}: "
                f"{issue.get('payload', {}).get('problem_family_ref', '검증된 이슈')}"
            )
            for issue in issues
        ] or ["통합 분석에서 승인할 이슈가 없습니다."]
        verification_items = [
            (
                f"{issue['local_key']}: "
                + ", ".join(
                    issue.get("payload", {}).get("verification_requirement_refs", [])
                )
            )
            for issue in issues
            if issue.get("payload", {}).get("verification_requirement_refs")
        ] or ["추가 심층 검증 범위는 기본적으로 비어 있습니다."]
        sections.extend([
            HitlSection(
                kind="diagnostic",
                title="문제와 원인 진단",
                items=issue_items,
                target_refs=issue_refs,
            ),
            HitlSection(
                kind="priorities",
                title="의사결정 우선순위",
                items=["승인된 이슈를 최종 보고서 작성 대상으로 사용합니다."],
                target_refs=issue_refs,
            ),
            HitlSection(
                kind="verification",
                title="검증 계획",
                items=verification_items,
                target_refs=issue_refs,
            ),
        ])
        target_refs.extend(issue_refs)
        editable = [
            token
            for issue_ref in issue_refs
            for token in (
                f"issue_dispositions.{issue_ref}",
                f"decision_dispositions.{issue_ref}",
                f"verification_authorizations.{issue_ref}",
            )
        ] + ["deep_dive_scope.component_ids", "deep_dive_scope.issue_ids"]
        return HitlCard(
            hitl_kind="diagnostic_final",
            request_id=manifest.pending_approval_request_id,
            base_revision=state.revision,
            title="진단 결과와 검증 범위를 확인해 주세요",
            summary="검증된 카드와 통합 validator를 통과한 진단만 표시합니다.",
            target_refs=target_refs,
            allowed_decisions=["approve", "approve_with_edits", "reanalyze", "stop"],
            editable_fields=editable,
            sections=sections,
        )
    if gate == "final":
        writer = _json_value(
            files.get("reasoning/writer-result.json"),
            label="writer result",
            default={},
        )
        payload = writer.get("payload", writer)
        templates = payload.get("claim_templates", [])
        claim_refs = [str(item["claim_id"]) for item in templates]
        claim_items = [
            f"{item['claim_id']}: {item.get('template', '')}"
            for item in templates
        ] or ["승인된 구조화 결과를 결정론적 기본 문구로 전달합니다."]
        sections.extend([
            HitlSection(
                kind="final_wording",
                title="최종 문구",
                items=claim_items,
                target_refs=claim_refs,
            ),
            HitlSection(
                kind="verification",
                title="전달 범위",
                items=["CEO 브리프 패키지를 최종 전달 대상으로 승인합니다."],
                target_refs=claim_refs,
            ),
        ])
        target_refs.extend(claim_refs)
        return HitlCard(
            hitl_kind="diagnostic_final",
            request_id=manifest.pending_approval_request_id,
            base_revision=state.revision,
            title="최종 문구와 전달 범위를 확인해 주세요",
            summary="등급과 근거는 수정하지 않고 승인 가능한 문구와 전달 범위만 표시합니다.",
            target_refs=target_refs,
            allowed_decisions=["approve", "approve_with_edits", "reanalyze", "stop"],
            editable_fields=["delivery_scope.package"],
            sections=sections,
        )
    proposal = _json_value(
        files.get("intake/canonical-mapping-proposal.json"),
        label="mapping proposal",
        default={},
    )
    mappings = proposal.get("mappings", [])
    mapping_refs = [str(item["mapping_question_ref"]) for item in mappings]
    mapping_items = [
        (
            f"{item.get('source_field_ref', '필드')} → "
            f"{item.get('candidate_mappings', [{}])[0].get('observation_role', '미정')}"
        )
        for item in mappings
    ] or ["검토할 스키마 매핑이 없습니다."]
    quality = _json_value(
        files.get("evidence/data-quality-register.json"),
        label="data quality register",
        default=[],
    )
    risk_items = [
        str(item.get("message", item.get("reason_code", "데이터 품질 경고")))
        for item in quality
        if isinstance(item, Mapping)
    ] or ["추가로 감지된 데이터 품질 경고가 없습니다."]
    facts = _json_value(
        files.get("evidence/fact-register.json"),
        label="fact register",
        default=[],
    )
    fact_refs = [str(item["fact_id"]) for item in facts]
    fact_items = [
        (
            f"{item.get('fact_code', 'fact')}: "
            f"{item.get('value', {}).get('canonical_value', '확인됨')}"
        )
        for item in facts[:20]
    ] or ["데이터 승인 후 결정론적 Fact를 생성합니다."]
    sections.extend([
        HitlSection(
            kind="mapping",
            title="스키마 매핑 제안",
            items=mapping_items,
            target_refs=mapping_refs,
        ),
        HitlSection(
            kind="risk",
            title="누락 및 품질 경고",
            items=risk_items,
            target_refs=mapping_refs,
        ),
        HitlSection(
            kind="facts",
            title="현재 근거 Fact 요약",
            items=fact_items,
            target_refs=fact_refs,
        ),
    ])
    target_refs.extend(mapping_refs)
    target_refs.extend(fact_refs)
    editable = [
        f"columns.{reference}.{field}"
        for reference in mapping_refs
        for field in _DATA_FIELDS
    ] + [f"sources.{source_id}.included" for source_id in source_refs]
    return HitlCard(
        hitl_kind="context_data",
        request_id=manifest.pending_approval_request_id,
        base_revision=state.revision,
        title="데이터 해석과 매핑을 확인해 주세요",
        summary="검증된 파일 요약과 후보 매핑만 표시합니다.",
        target_refs=target_refs,
        allowed_decisions=["approve", "approve_with_edits", "reanalyze", "stop"],
        editable_fields=editable,
        sections=sections,
    )
