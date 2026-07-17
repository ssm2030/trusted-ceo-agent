from __future__ import annotations

from typing import Any, Mapping

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.outputs.audit import build_audit_manifest
from trusted_ceo_agent.outputs.validation import validation_summary


GRADE_ORDER = {
    "Decision Required": 0,
    "Immediate Verification": 1,
    "Expert Review Required": 2,
    "Monitor": 3,
    "Appendix Signal": 4,
    "Not Assessable": 5,
}


def render_ceo_brief(result: Mapping[str, Any]) -> str:
    lines = ["# Trusted CEO Brief", "", "근거 기반 진단이며 최종 경영 판단을 대체하지 않습니다.", ""]
    issues = sorted(
        result.get("issues", []),
        key=lambda item: (GRADE_ORDER.get(item["primary_grade"], 99), item["issue_id"]),
    )
    if not issues:
        lines.extend(["## 진단 결과", "", "현재 승인 범위에서 활성 문제를 확정하지 않았습니다.", ""])
    for issue in issues:
        lines.extend(
            [
                f"## {issue['title_template']}",
                "",
                f"- 결과 등급: {issue['primary_grade']}",
                f"- 중요 이유: {issue['why_it_matters_template']}",
                f"- 근거 연결: {', '.join(issue.get('evidence_link_ids', []))}",
                "",
            ]
        )
        if issue.get("unresolved_conflicts"):
            lines.extend(["- 미해결 충돌: " + ", ".join(issue["unresolved_conflicts"]), ""])
    if result.get("blind_spots"):
        lines.extend(["## 판단 한계", ""])
        for item in result["blind_spots"]:
            lines.append(f"- {item.get('description_template', item.get('blind_spot_id', '미확인 범위'))}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_package(result: Mapping[str, Any]) -> dict[str, bytes]:
    summary = validation_summary(result)
    files: dict[str, bytes] = {
        "final/result.json": canonical_bytes(result),
        "final/ceo-brief.md": render_ceo_brief(result).encode("utf-8"),
        "final/issue-tree.json": canonical_bytes(
            {"issues": result.get("issues", []), "relations": result.get("cross_issue_relations", [])}
        ),
        "final/evidence-cards.json": canonical_bytes(
            [
                {
                    "issue_id": item["issue_id"],
                    "evidence_link_ids": item.get("evidence_link_ids", []),
                    "value_refs": item.get("value_refs", []),
                }
                for item in result.get("issues", [])
            ]
        ),
        "final/monitoring-and-blind-spots.json": canonical_bytes(
            {"monitoring": result.get("monitoring", []), "blind_spots": result.get("blind_spots", [])}
        ),
        "final/expert-packets.json": canonical_bytes(result.get("expert_review_packets", [])),
        "final/validation-summary.json": canonical_bytes(summary),
        "final/structured-output.json": canonical_bytes(
            {"final_result": result, "validation": summary, "renderer": "deterministic-v1"}
        ),
    }
    files["final/audit-manifest.json"] = canonical_bytes(build_audit_manifest(files))
    return files
