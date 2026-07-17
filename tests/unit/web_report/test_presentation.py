from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.web_report.closure import EvidenceClosure
from trusted_ceo_agent.web_report.presentation import build_presentation_manifest


def issue(issue_id: str, grade: str, value_refs: list[str]) -> dict:
    return {
        "issue_id": issue_id,
        "title_template": f"{issue_id} 제목",
        "primary_grade": grade,
        "value_refs": value_refs,
        "evidence_link_ids": [f"evidence_{issue_id}"],
    }


def fact(fact_id: str, period: str, value: str) -> dict:
    return {
        "fact_id": fact_id,
        "metric_code": "gross_margin",
        "scope": [{"dimension_code": "company", "member_code": "all"}],
        "time_context": {"period": period},
        "value": {
            "value_type": "decimal",
            "canonical_value": value,
            "unit_code": "percent",
            "currency_code": None,
            "scale": "0.1",
        },
    }


def closure() -> EvidenceClosure:
    facts = (
        fact("fact_2025", "2025", "10.2"),
        fact("fact_2026", "2026", "12.4"),
    )
    links = (
        {
            "evidence_link_id": "evidence_issue_a",
            "target_ref": "issue_a",
            "evidence_ref": "fact_2025",
            "evidence_kind": "fact",
        },
        {
            "evidence_link_id": "evidence_issue_a_2",
            "target_ref": "issue_a",
            "evidence_ref": "fact_2026",
            "evidence_kind": "fact",
        },
    )
    return EvidenceClosure(
        facts=facts,
        signals=(),
        evidence_links=links,
        sources=(),
        data_quality=(),
        capability_map={"capability_map_id": "capability_map", "capabilities": []},
    )


class PresentationManifestTests(unittest.TestCase):
    def test_ceo_summary_uses_grade_then_id_and_caps_at_three(self) -> None:
        result = {
            "issues": [
                issue("issue_e", "Monitor", []),
                issue("issue_c", "Immediate Verification", []),
                issue("issue_b", "Decision Required", []),
                issue("issue_a", "Decision Required", ["fact_2025", "fact_2026"]),
                issue("issue_d", "Expert Review Required", []),
            ],
            "cross_issue_relations": [],
        }

        manifest = build_presentation_manifest(result, closure())

        self.assertEqual(
            ["issue_a", "issue_b", "issue_c"],
            manifest["ceo_summary_issue_refs"],
        )
        self.assertEqual("grade_order_then_issue_id", manifest["selection_basis"])

    def test_chart_uses_existing_values_and_evidence_without_calculation(self) -> None:
        result = {
            "issues": [
                issue("issue_a", "Decision Required", ["fact_2025", "fact_2026"])
            ],
            "cross_issue_relations": [],
        }

        manifest = build_presentation_manifest(result, closure())

        self.assertEqual(1, len(manifest["chart_specs"]))
        points = manifest["chart_specs"][0]["points"]
        self.assertEqual(
            ["fact_2025", "fact_2026"],
            [point["value_ref"] for point in points],
        )
        self.assertEqual(["10.2", "12.4"], [point["display_value"] for point in points])
        self.assertTrue(all(point["evidence_link_ids"] for point in points))

    def test_incompatible_unit_produces_no_chart(self) -> None:
        incompatible = closure()
        facts = [copy.deepcopy(item) for item in incompatible.facts]
        facts[1]["value"]["unit_code"] = "currency"
        incompatible = EvidenceClosure(
            facts=tuple(facts),
            signals=incompatible.signals,
            evidence_links=incompatible.evidence_links,
            sources=incompatible.sources,
            data_quality=incompatible.data_quality,
            capability_map=incompatible.capability_map,
        )
        result = {
            "issues": [
                issue("issue_a", "Decision Required", ["fact_2025", "fact_2026"])
            ],
            "cross_issue_relations": [],
        }

        self.assertEqual(
            [],
            build_presentation_manifest(result, incompatible)["chart_specs"],
        )


if __name__ == "__main__":
    unittest.main()
