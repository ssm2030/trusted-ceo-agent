from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.web_report.closure import EvidenceClosure
from trusted_ceo_agent.web_report.expert_packets import build_expert_packet_view


RUN_ID = "run_20260717T010203Z_0123456789abcdef"


def _final_result() -> dict:
    return {
        "issues": [
            {
                "issue_id": "issue_professional",
                "cause_hypotheses": [{"claim_code": "claim_cause"}],
                "counter_hypotheses": [{"claim_code": "claim_counter"}],
                "unresolved_conflicts": ["conflict_professional"],
                "expert_review_refs": ["trigger_professional"],
            }
        ],
        "expert_review_packets": [
            {
                "expert_packet_id": "packet_professional",
                "profession": "senior_accountant",
                "question_template": "Review the bound evidence and stated boundary.",
                "forbidden_conclusions": ["unapproved_full_conclusion"],
            }
        ],
    }


def _closure() -> EvidenceClosure:
    return EvidenceClosure(
        facts=(
            {
                "fact_id": "fact_professional",
                "source_refs": [
                    {
                        "source_id": "source_professional",
                        "locator_type": "json_pointer",
                        "locator": {"pointer": "/transactions/0"},
                    }
                ],
                "derivation": None,
                "quality": [],
            },
        ),
        signals=(),
        evidence_links=(
            {
                "evidence_link_id": "link_professional",
                "target_ref": "professional_publication",
                "evidence_ref": "fact_professional",
                "evidence_kind": "fact",
            },
            {
                "evidence_link_id": "link_other_issue",
                "target_ref": "issue_other",
                "evidence_ref": "fact_professional",
                "evidence_kind": "fact",
            },
        ),
        sources=({"source_id": "source_professional"},),
        data_quality=(),
        capability_map={"capability_map_id": "capability_map", "capabilities": []},
    )


def _files() -> dict[str, bytes]:
    return {
        "final/structured-output.json": canonical_bytes(
            {
                "issues": [
                    {
                        "issue_id": "issue_professional",
                        "local_key": "issue_professional_local",
                    }
                ],
                "expert_review_packets": [
                    {
                        "expert_packet_id": "packet_professional",
                        "profession": "senior_accountant",
                        "question_template": (
                            "Review the bound evidence and stated boundary."
                        ),
                        "forbidden_conclusions": [
                            "unapproved_full_conclusion"
                        ],
                        "_target_issue_ref": "issue_professional",
                        "_trigger_ref": "trigger_professional",
                        "_required": True,
                        "_professional_packet": True,
                        "_fact_refs": ["fact_professional"],
                        "_evidence_link_ids": ["link_professional"],
                        "_source_refs": ["source_professional"],
                        "_required_document_refs": ["contract_schedule"],
                    }
                ],
            }
        )
    }


class ProfessionalExpertPacketViewTests(unittest.TestCase):
    def test_professional_packet_uses_only_its_bound_refs(self) -> None:
        packet = build_expert_packet_view(
            _files(),
            _final_result(),
            _closure(),
            run_id=RUN_ID,
            revision=11,
        )[0]

        self.assertEqual(["fact_professional"], packet["fact_refs"])
        self.assertEqual(["link_professional"], packet["evidence_link_ids"])
        self.assertEqual(["source_professional"], packet["source_refs"])
        self.assertEqual(
            ["contract_schedule"],
            packet["required_document_refs"],
        )
        self.assertEqual("issue_professional", packet["target_issue_ref"])

    def test_professional_packet_rejects_unknown_refs(self) -> None:
        cases = (
            ("_fact_refs", ["fact_missing"], "fact_missing"),
            ("_evidence_link_ids", ["link_missing"], "link_missing"),
            ("_source_refs", ["source_missing"], "source_missing"),
        )
        for field, refs, error in cases:
            with self.subTest(field=field, refs=refs):
                files = _files()
                structured = copy.deepcopy(
                    __import__("json").loads(
                        files["final/structured-output.json"].decode("utf-8")
                    )
                )
                structured["expert_review_packets"][0][field] = refs
                files["final/structured-output.json"] = canonical_bytes(structured)
                with self.assertRaisesRegex(IntegrityError, error):
                    build_expert_packet_view(
                        files,
                        _final_result(),
                        _closure(),
                        run_id=RUN_ID,
                        revision=11,
                    )


if __name__ == "__main__":
    unittest.main()
