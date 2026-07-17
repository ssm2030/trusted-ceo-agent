from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.web_report.closure import build_evidence_closure


def evidence_core() -> dict:
    source_id = "source_observed"
    observed_id = "fact_observed"
    calculated_id = "fact_calculated"
    signal_id = "signal_main"
    quality_id = "quality_main"
    return {
        "source_registry": [
            {
                "source_id": source_id,
                "access_policy": "permitted",
            }
        ],
        "data_quality_register": [
            {
                "quality_issue_id": quality_id,
                "source_ref": source_id,
            }
        ],
        "fact_register": [
            {
                "fact_id": observed_id,
                "source_refs": [{"source_id": source_id}],
                "derivation": None,
                "quality": [quality_id],
            },
            {
                "fact_id": calculated_id,
                "source_refs": [],
                "derivation": {"input_fact_ids": [observed_id]},
                "quality": [],
            },
        ],
        "signal_register": [
            {
                "signal_id": signal_id,
                "input_fact_ids": [calculated_id],
            }
        ],
        "evidence_links": [
            {
                "evidence_link_id": "evidence_main",
                "evidence_ref": signal_id,
                "evidence_kind": "signal",
            }
        ],
        "capability_map": {
            "capability_map_id": "capability_map_main",
            "capabilities": [
                {
                    "capability_id": "capability_main",
                    "quality_issue_ids": [quality_id],
                }
            ],
        },
    }


def final_result() -> dict:
    return {
        "issues": [
            {
                "issue_id": "issue_main",
                "evidence_link_ids": ["evidence_main"],
            }
        ]
    }


class EvidenceClosureTests(unittest.TestCase):
    def test_signal_and_derived_fact_close_to_observed_source(self) -> None:
        closure = build_evidence_closure(final_result(), evidence_core())

        self.assertEqual(
            ("evidence_main",),
            tuple(item["evidence_link_id"] for item in closure.evidence_links),
        )
        self.assertEqual(
            ("signal_main",),
            tuple(item["signal_id"] for item in closure.signals),
        )
        self.assertEqual(
            ("fact_calculated", "fact_observed"),
            tuple(item["fact_id"] for item in closure.facts),
        )
        self.assertEqual(
            ("source_observed",),
            tuple(item["source_id"] for item in closure.sources),
        )
        self.assertEqual(
            ("quality_main",),
            tuple(item["quality_issue_id"] for item in closure.data_quality),
        )

    def test_missing_derived_fact_is_rejected_instead_of_dropped(self) -> None:
        core = copy.deepcopy(evidence_core())
        core["signal_register"][0]["input_fact_ids"] = ["fact_missing"]

        with self.assertRaisesRegex(IntegrityError, "fact_missing"):
            build_evidence_closure(final_result(), core)

    def test_derivation_cycle_is_rejected(self) -> None:
        core = copy.deepcopy(evidence_core())
        core["fact_register"][0]["derivation"] = {
            "input_fact_ids": ["fact_calculated"]
        }
        core["fact_register"][0]["source_refs"] = []

        with self.assertRaisesRegex(IntegrityError, "cycle"):
            build_evidence_closure(final_result(), core)


if __name__ == "__main__":
    unittest.main()
