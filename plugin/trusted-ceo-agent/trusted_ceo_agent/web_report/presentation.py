from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from trusted_ceo_agent.contracts.ids import make_id
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.web_report.canonical import jcs_bytes
from trusted_ceo_agent.web_report.closure import EvidenceClosure
from trusted_ceo_agent.web_report.contracts import CONTRACT_ROOT


GRADE_ORDER = {
    "Decision Required": 0,
    "Immediate Verification": 1,
    "Expert Review Required": 2,
    "Monitor": 3,
    "Appendix Signal": 4,
    "Not Assessable": 5,
}

GRADE_LABELS = {
    "Decision Required": "의사결정 필요",
    "Immediate Verification": "즉시 검증 필요",
    "Expert Review Required": "전문가 검토 필요",
    "Monitor": "모니터링",
    "Appendix Signal": "부록 신호",
    "Not Assessable": "판단 불가",
}

VIEW_LABELS = {
    "view.ceo_summary": "최고경영자 의사결정 요약",
    "view.evidence": "컨설턴트 근거 분석",
    "view.trust": "실행·신뢰 기록",
    "view.expert_packet": "전문가 검토 패킷",
    "view.revision": "변경 이력",
}


def _index(
    items: Sequence[Mapping[str, Any]],
    field: str,
    label: str,
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in items:
        identifier = item.get(field)
        if not isinstance(identifier, str) or not identifier:
            raise IntegrityError(f"{label} has an invalid {field}")
        if identifier in result:
            raise IntegrityError(f"duplicate {label}: {identifier}")
        result[identifier] = item
    return result


def _display_value(fact: Mapping[str, Any]) -> str:
    value = fact.get("value")
    if not isinstance(value, Mapping):
        raise IntegrityError(f"Fact value is missing: {fact.get('fact_id')}")
    canonical = value.get("canonical_value")
    if isinstance(canonical, bool):
        return "true" if canonical else "false"
    if isinstance(canonical, (str, int)):
        return str(canonical)
    raise IntegrityError(
        f"Fact canonical value is invalid: {fact.get('fact_id')}"
    )


def _time_label(fact: Mapping[str, Any]) -> tuple[str, str | None]:
    context = fact.get("time_context")
    if not isinstance(context, Mapping):
        raise IntegrityError(f"Fact time context is invalid: {fact.get('fact_id')}")
    period = context.get("period")
    if isinstance(period, str):
        return period, period
    as_of = context.get("as_of")
    if isinstance(as_of, str):
        return as_of, as_of
    window = context.get("window")
    if isinstance(window, Mapping):
        start, end = window.get("start"), window.get("end")
        if isinstance(start, str) and isinstance(end, str):
            return f"{start}~{end}", f"{start}/{end}"
    raise IntegrityError(f"Fact time context is invalid: {fact.get('fact_id')}")


def _float_safe(facts: Sequence[Mapping[str, Any]]) -> bool:
    for fact in facts:
        value = fact.get("value")
        if not isinstance(value, Mapping) or value.get("value_type") not in {
            "decimal",
            "integer",
        }:
            return False
        try:
            number = Decimal(str(value.get("canonical_value")))
        except (InvalidOperation, ValueError):
            return False
        if not number.is_finite() or abs(number) > Decimal(2**53 - 1):
            return False
        significant = number.normalize().as_tuple().digits
        if len(significant) > 15:
            return False
    return True


def _fact_evidence(
    closure: EvidenceClosure,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    signals = _index(closure.signals, "signal_id", "Signal")
    evidence_by_fact: dict[str, set[str]] = {}
    signals_by_fact: dict[str, set[str]] = {}
    for link in closure.evidence_links:
        link_id = link.get("evidence_link_id")
        evidence_ref = link.get("evidence_ref")
        if not isinstance(link_id, str) or not isinstance(evidence_ref, str):
            raise IntegrityError("Evidence Link has invalid references")
        if link.get("evidence_kind") == "fact":
            evidence_by_fact.setdefault(evidence_ref, set()).add(link_id)
        elif link.get("evidence_kind") == "signal":
            signal = signals.get(evidence_ref)
            if signal is None:
                raise IntegrityError(f"unknown Signal: {evidence_ref}")
            for fact_id in signal.get("input_fact_ids", []):
                if not isinstance(fact_id, str):
                    raise IntegrityError(f"Signal has invalid input Fact: {evidence_ref}")
                evidence_by_fact.setdefault(fact_id, set()).add(link_id)
                signals_by_fact.setdefault(fact_id, set()).add(evidence_ref)
    return evidence_by_fact, signals_by_fact


def _metric_cards(
    selected: Sequence[Mapping[str, Any]],
    facts: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for issue in selected:
        fact_refs = sorted(
            {
                ref
                for ref in issue.get("value_refs", [])
                if isinstance(ref, str) and ref in facts
            }
        )
        if not fact_refs:
            continue
        fact = facts[fact_refs[0]]
        value = fact["value"]
        body = {
            "issue_ref": issue["issue_id"],
            "value_ref": fact["fact_id"],
        }
        cards.append(
            {
                "metric_card_id": make_id("metric_card", body),
                "issue_ref": issue["issue_id"],
                "label_ko": issue["title_template"],
                "value_ref": fact["fact_id"],
                "display_value": _display_value(fact),
                "unit_code": value.get("unit_code"),
                "currency_code": value.get("currency_code"),
            }
        )
    return cards


def _chart_candidates(
    selected: Sequence[Mapping[str, Any]],
    closure: EvidenceClosure,
) -> list[dict[str, Any]]:
    facts = _index(closure.facts, "fact_id", "Fact")
    evidence_by_fact, signals_by_fact = _fact_evidence(closure)
    candidates: list[tuple[tuple[str, str], dict[str, Any]]] = []

    for issue in selected:
        issue_id = str(issue["issue_id"])
        issue_fact_ids = sorted(
            {
                ref
                for ref in issue.get("value_refs", [])
                if isinstance(ref, str) and ref in facts
            }
        )
        groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
        for fact_id in issue_fact_ids:
            fact = facts[fact_id]
            value = fact.get("value")
            if not isinstance(value, Mapping):
                continue
            key = (
                str(fact.get("metric_code")),
                jcs_bytes(fact.get("scope", [])).decode("utf-8"),
                value.get("unit_code"),
                value.get("currency_code"),
                value.get("value_type"),
                value.get("scale"),
            )
            groups.setdefault(key, []).append(fact)

        for key, grouped in groups.items():
            distinct_contexts = {
                jcs_bytes(fact.get("time_context", {})) for fact in grouped
            }
            if len(grouped) < 2 or len(distinct_contexts) < 2:
                continue
            if not _float_safe(grouped):
                continue
            if any(not evidence_by_fact.get(str(fact["fact_id"])) for fact in grouped):
                continue
            ordered = sorted(
                grouped,
                key=lambda fact: (*_time_label(fact), str(fact["fact_id"])),
            )
            metric_code = str(key[0])
            points: list[dict[str, Any]] = []
            for fact in ordered:
                fact_id = str(fact["fact_id"])
                x_label, period_sort_key = _time_label(fact)
                points.append(
                    {
                        "point_id": make_id(
                            "chart_point",
                            {
                                "issue_ref": issue_id,
                                "fact_id": fact_id,
                                "time_context": fact["time_context"],
                            },
                        ),
                        "x_label": x_label,
                        "period_sort_key": period_sort_key,
                        "value_ref": fact_id,
                        "fact_id": fact_id,
                        "display_value": _display_value(fact),
                        "evidence_link_ids": sorted(evidence_by_fact[fact_id]),
                    }
                )
            signal_refs = sorted(
                {
                    signal_id
                    for fact in ordered
                    for signal_id in signals_by_fact.get(str(fact["fact_id"]), set())
                }
            )
            chart = {
                "chart_id": make_id(
                    "chart",
                    {
                        "issue_ref": issue_id,
                        "metric_code": metric_code,
                        "fact_refs": [fact["fact_id"] for fact in ordered],
                    },
                ),
                "title_ko": f"{issue['title_template']} · {metric_code}",
                "description_ko": "플러그인이 검증한 시점별 원값입니다.",
                "chart_kind": "line",
                "issue_refs": [issue_id],
                "fact_refs": sorted(str(fact["fact_id"]) for fact in ordered),
                "signal_refs": signal_refs,
                "x_axis_label_ko": "기간",
                "y_axis_label_ko": metric_code,
                "unit_code": key[2],
                "currency_code": key[3],
                "scale": key[5],
                "display_format": str(key[4]),
                "float_safe": True,
                "points": points,
            }
            candidates.append(((metric_code, issue_id), chart))

    return [chart for _, chart in sorted(candidates, key=lambda item: item[0])[:2]]


def build_presentation_manifest(
    final_result: Mapping[str, Any],
    closure: EvidenceClosure,
) -> dict[str, Any]:
    issues = list(final_result.get("issues", []))
    for issue in issues:
        grade = issue.get("primary_grade")
        if grade not in GRADE_ORDER:
            raise IntegrityError(
                f"issue has unknown primary grade: {issue.get('issue_id')}"
            )
    ordered = sorted(
        issues,
        key=lambda issue: (
            GRADE_ORDER[str(issue["primary_grade"])],
            str(issue["issue_id"]),
        ),
    )
    selected = ordered[:3]
    facts = _index(closure.facts, "fact_id", "Fact")

    nodes = [
        {
            "issue_ref": str(issue["issue_id"]),
            "label_ko": str(issue["title_template"]),
            "grade": str(issue["primary_grade"]),
        }
        for issue in sorted(issues, key=lambda item: str(item["issue_id"]))
    ]
    edges = [
        {
            "relation_id": relation["relation_id"],
            "from_issue_ref": relation["from_issue_ref"],
            "to_issue_ref": relation["to_issue_ref"],
            "relation_type": relation["relation_type"],
        }
        for relation in sorted(
            final_result.get("cross_issue_relations", []),
            key=lambda item: str(item["relation_id"]),
        )
    ]
    labels = [
        {"code": code, "label_ko": label}
        for code, label in sorted({**GRADE_LABELS, **VIEW_LABELS}.items())
    ]
    manifest = {
        "ceo_summary_issue_refs": [
            str(issue["issue_id"]) for issue in selected
        ],
        "selection_basis": "grade_order_then_issue_id",
        "metric_cards": _metric_cards(selected, facts),
        "chart_specs": _chart_candidates(selected, closure),
        "issue_graph": {"nodes": nodes, "edges": edges},
        "korean_labels": labels,
    }
    SchemaStore(CONTRACT_ROOT).validate(
        "presentation-manifest.schema.json",
        manifest,
    )
    return manifest
