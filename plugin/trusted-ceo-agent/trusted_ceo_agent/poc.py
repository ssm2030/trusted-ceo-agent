from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.outputs.final_result import build_final_result


def _semantic_normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _semantic_normalize(child)
            for key, child in value.items()
            if not key.startswith("irrelevant_") and not key.startswith("_")
        }
    if isinstance(value, list):
        children = [_semantic_normalize(child) for child in value]
        if children and all(isinstance(child, Mapping) for child in children):
            return sorted(children, key=canonical_bytes)
        return children
    return value


def semantic_fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(_semantic_normalize(value))).hexdigest()


def _decimal(metrics: Mapping[str, Any], key: str) -> Decimal | None:
    raw = metrics.get(key)
    if raw is None:
        return None
    return Decimal(str(raw))


def _issue(
    key: str,
    title: str,
    grade: str,
    evidence_link_id: str,
    *,
    why: str,
    value_refs: list[str],
    causes: list[dict[str, Any]] | None = None,
    counters: list[dict[str, Any]] | None = None,
    conflicts: list[str] | None = None,
    steps: list[str] | None = None,
    expert_refs: list[str] | None = None,
    response_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "issue_id": key,
        "title_template": title,
        "primary_grade": grade,
        "secondary_flags": [],
        "why_it_matters_template": why,
        "value_refs": value_refs,
        "evidence_link_ids": [evidence_link_id],
        "cause_hypotheses": causes or [],
        "counter_hypotheses": counters or [],
        "unresolved_conflicts": conflicts or [],
        "verification_next_steps": steps or [],
        "conditional_response_refs": response_refs or [],
        "expert_review_refs": expert_refs or [],
        "disposition": "accepted",
    }


def run_scenario(fixture_root: Path) -> dict[str, Any]:
    company_path = fixture_root / "inputs" / "company.json"
    mission_path = fixture_root / "mission-contract.json"
    draft_path = fixture_root / "fixed-drafts" / "lens.json"
    company = strict_loads(company_path.read_bytes())
    mission = strict_loads(mission_path.read_bytes())
    draft = strict_loads(draft_path.read_bytes())
    metrics = company.get("metrics", {})
    domain = company.get("domain")
    source_hash = hashlib.sha256(company_path.read_bytes()).hexdigest()
    source_id = f"source_{source_hash[:24]}"

    fact_codes: list[str] = []
    signal_codes: list[str] = []
    issues: list[dict[str, Any]] = []
    evidence_links: dict[str, dict[str, Any]] = {}
    conditional_responses: list[dict[str, Any]] = []
    expert_packets: list[dict[str, Any]] = []
    blind_spots: list[dict[str, Any]] = []

    def add_link(issue_key: str, fact_refs: list[str]) -> str:
        link_id = f"evidence_{issue_key}"
        evidence_links[link_id] = {
            "evidence_link_id": link_id,
            "evidence_refs": fact_refs,
            "source_ids": [source_id],
            "polarity": "supports",
        }
        return link_id

    if domain != "b2b_services":
        fact_codes.append("data_presence")
        signal_codes.append("unsupported_domain_boundary")
        key = "unsupported_domain_boundary"
        issues.append(
            _issue(
                key,
                "지원 도메인 경계 확인 필요",
                "Not Assessable",
                add_link(key, ["fact_data_presence"]),
                why="승인된 Domain Pack이 없어 일반 데이터 존재 사실만 확인했습니다.",
                value_refs=["fact_data_presence"],
                steps=["승인된 Domain Pack과 필수 source role을 확인합니다."],
            )
        )
        blind_spots.append({"blind_spot_id": "unsupported_domain", "description_template": "도메인별 원인과 대응은 평가하지 않았습니다."})
    else:
        margin_start = _decimal(metrics, "gross_margin_start")
        margin_end = _decimal(metrics, "gross_margin_end")
        if margin_start is not None and margin_end is not None:
            fact_codes.append("gross_margin")
            if margin_start - margin_end >= Decimal("0.03"):
                signal_codes.append("margin_deterioration")

        if "revenue_growth" in metrics:
            fact_codes.append("revenue_growth")
        if "custom_contract_share_end" in metrics:
            fact_codes.append("custom_contract_share")
        if "top3_customer_share_end" in metrics:
            fact_codes.append("top3_customer_share")
        if "timing_mismatch_share" in metrics:
            fact_codes.append("timing_mismatch_share")
        if "price_mix_explanation" in metrics:
            fact_codes.append("price_mix_explanation")
        if "overtime_explanation" in metrics:
            fact_codes.append("overtime_explanation")

        custom_start = _decimal(metrics, "custom_contract_share_start")
        custom_end = _decimal(metrics, "custom_contract_share_end")
        top_start = _decimal(metrics, "top3_customer_share_start")
        top_end = _decimal(metrics, "top3_customer_share_end")
        timing = _decimal(metrics, "timing_mismatch_share")
        if custom_start is not None and custom_end is not None and custom_end - custom_start >= Decimal("0.15"):
            signal_codes.append("mix_shift")
        if top_start is not None and top_end is not None and top_end - top_start >= Decimal("0.10"):
            signal_codes.append("customer_concentration")
        if timing is not None and timing >= Decimal("0.02"):
            signal_codes.append("revenue_timing_mismatch")

        price_mix = _decimal(metrics, "price_mix_explanation")
        overtime = _decimal(metrics, "overtime_explanation")
        if price_mix is not None and overtime is not None and company.get("metrics", {}).get("cause_scope_aligned") is False:
            signal_codes.append("cause_scope_conflict")
            key = "profitability_cause_conflict"
            issues.append(
                _issue(
                    key,
                    "수익성 저하 원인 간 범위 충돌",
                    "Immediate Verification",
                    add_link(key, ["fact_gross_margin", "fact_price_mix_explanation", "fact_overtime_explanation"]),
                    why="두 설명이 모두 유의하지만 기간·범위가 일치하지 않아 단일 원인 확정이 불가합니다.",
                    value_refs=["fact_gross_margin", "fact_price_mix_explanation", "fact_overtime_explanation"],
                    causes=[{"claim_code": "price_mix_hypothesis"}, {"claim_code": "overtime_hypothesis"}],
                    counters=[{"claim_code": "scope_mismatch_counter"}],
                    conflicts=["cause_scope_conflict"],
                    steps=["동일 기간·범위로 bridge를 재계산합니다."],
                )
            )
        elif "margin_deterioration" in signal_codes and not any(
            key in metrics for key in ("mix_margin_explanation", "price_mix_explanation", "overtime_explanation")
        ):
            signal_codes.append("missing_causal_data")
            key = "profitability_not_assessable"
            issues.append(
                _issue(
                    key,
                    "수익성 저하 원인 판단 불가",
                    "Not Assessable",
                    add_link(key, ["fact_gross_margin"]),
                    why="마진 저하는 관찰됐지만 원인을 구별할 필수 source role이 없습니다.",
                    value_refs=["fact_gross_margin"],
                    steps=[f"필요 source role: {role}" for role in company.get("missing_source_roles", [])],
                )
            )
        else:
            if {"margin_deterioration", "mix_shift", "customer_concentration"}.issubset(signal_codes):
                key = "portfolio_profitability_concentration"
                issues.append(
                    _issue(
                        key,
                        "계약 믹스와 고객 집중이 결합된 포트폴리오 문제",
                        "Decision Required",
                        add_link(key, ["fact_gross_margin", "fact_custom_contract_share", "fact_top3_customer_share"]),
                        why="수익성 저하와 저마진 계약 믹스·고객 집중이 같은 기간에 함께 관찰됐습니다.",
                        value_refs=["fact_gross_margin", "fact_custom_contract_share", "fact_top3_customer_share"],
                        causes=[{"claim_code": "mix_portfolio_pressure"}],
                        counters=[{"claim_code": "wage_only_challenged"}],
                        response_refs=["response_portfolio_review"],
                    )
                )
                conditional_responses.append(
                    {
                        "response_id": "response_portfolio_review",
                        "condition_template": "동일 범위 bridge가 재검증되면",
                        "direction_template": "계약 포트폴리오와 집중 한도를 경영진이 검토합니다.",
                    }
                )
            if "revenue_timing_mismatch" in signal_codes:
                key = "revenue_timing_control"
                issues.append(
                    _issue(
                        key,
                        "매출 시점 통제 전문가 검토 필요",
                        "Expert Review Required",
                        add_link(key, ["fact_timing_mismatch_share"]),
                        why="인식일과 검수일의 기간 경계 불일치가 규칙 임계값을 충족했습니다.",
                        value_refs=["fact_timing_mismatch_share"],
                        expert_refs=["expert_packet_revenue_timing"],
                    )
                )
                expert_packets.append(
                    {
                        "expert_packet_id": "expert_packet_revenue_timing",
                        "profession": "accounting",
                        "question_template": "보고기간 경계 거래의 계약·검수 증빙과 적용 기준을 검토해 주십시오.",
                        "forbidden_conclusions": ["final_accounting_treatment", "audit_opinion"],
                    }
                )

    approvals = [{"gate": "final", "status": "current", "input_method": "test_fixture", "fixture_only": True}]
    result = build_final_result(
        run_summary={"run_id": f"fixture_{fixture_root.name}", "revision": 1},
        mission_summary={"objective": mission.get("objective", "")},
        capability_summary={"status": "boundary" if domain != "b2b_services" else "evaluated"},
        issues=issues,
        evidence_links=evidence_links,
        approvals=approvals,
        conditional_responses=conditional_responses,
        blind_spots=blind_spots,
        expert_review_packets=expert_packets,
    )
    return {
        "scenario_id": fixture_root.name,
        "semantic_fingerprint": semantic_fingerprint(company),
        "fact_codes": sorted(set(fact_codes)),
        "signal_codes": sorted(set(signal_codes)),
        "issue_keys": [item["issue_id"] for item in result["issues"]],
        "primary_grades": {item["issue_id"]: item["primary_grade"] for item in result["issues"]},
        "claim_codes": sorted(set(draft.get("claim_codes", []))),
        "professional_conclusions": [],
        "result": result,
    }
