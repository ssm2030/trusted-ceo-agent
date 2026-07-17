from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.web_report.canonical import jcs_sha256
from trusted_ceo_agent.web_report.closure import EvidenceClosure
from trusted_ceo_agent.web_report.expert_packets import build_expert_packet_view


RUN_ID = "run_20260717T010203Z_0123456789abcdef"


def final_result() -> dict:
    return {
        "issues": [
            {
                "issue_id": "issue_main",
                "cause_hypotheses": [{"claim_code": "claim_cause"}],
                "counter_hypotheses": [{"claim_code": "claim_counter"}],
                "unresolved_conflicts": ["conflict_main"],
                "expert_review_refs": ["trigger_main"],
            }
        ],
        "expert_review_packets": [
            {
                "expert_packet_id": "expert_packet_main",
                "profession": "공인회계사",
                "question_template": "계약과 매출 인식 시점을 검토해 주세요.",
                "forbidden_conclusions": ["법률 결론"],
            }
        ],
    }


def closure() -> EvidenceClosure:
    return EvidenceClosure(
        facts=(
            {
                "fact_id": "fact_main",
                "source_refs": [
                    {
                        "source_id": "source_main",
                        "locator_type": "json_pointer",
                        "locator": {"pointer": "/0"},
                    }
                ],
                "derivation": None,
                "quality": [],
            },
        ),
        signals=(),
        evidence_links=(
            {
                "evidence_link_id": "evidence_main",
                "target_ref": "issue_main",
                "evidence_ref": "fact_main",
                "evidence_kind": "fact",
            },
        ),
        sources=({"source_id": "source_main"},),
        data_quality=(),
        capability_map={"capability_map_id": "capability_map", "capabilities": []},
    )


def files() -> dict[str, bytes]:
    return {
        "final/structured-output.json": canonical_bytes(
            {
                "issues": [
                    {
                        "issue_id": "issue_main",
                        "local_key": "issue_local",
                    }
                ],
                "expert_review_packets": [
                    {
                        "expert_packet_id": "expert_packet_main",
                        "profession": "공인회계사",
                        "question_template": "계약과 매출 인식 시점을 검토해 주세요.",
                        "forbidden_conclusions": ["법률 결론"],
                        "_trigger_ref": "trigger_main",
                        "_target_issue_ref": "issue_main",
                        "_required": True,
                    }
                ],
            }
        ),
        "reasoning/integrated-assessment.json": canonical_bytes(
            {
                "payload": {
                    "expert_review_candidates": [
                        {
                            "local_key": "expert_candidate",
                            "payload": {
                                "target_issue_local_key": "issue_local",
                                "expert_trigger_ref": "trigger_main",
                                "evidence_proposals": [
                                    {"evidence_ref": "fact_main"}
                                ],
                                "required_document_refs": ["contracts"],
                                "review_question_template": (
                                    "계약과 매출 인식 시점을 검토해 주세요."
                                ),
                            },
                        }
                    ]
                }
            }
        ),
        "reasoning/deep-dive-result.json": canonical_bytes(
            {
                "payload": {
                    "remaining_uncertainties": [
                        {
                            "local_key": "uncertainty_main",
                            "payload": {
                                "target_issue_ref": "issue_local",
                                "reason_code": "contract_interpretation",
                            },
                        }
                    ]
                }
            }
        ),
    }


class ExpertPacketViewTests(unittest.TestCase):
    def test_packet_expands_only_from_accepted_structured_candidate(self) -> None:
        packets = build_expert_packet_view(
            files(),
            final_result(),
            closure(),
            run_id=RUN_ID,
            revision=10,
        )

        packet = packets[0]
        self.assertEqual("expert_packet_main", packet["expert_packet_id"])
        self.assertEqual(["fact_main"], packet["fact_refs"])
        self.assertEqual(["evidence_main"], packet["evidence_link_ids"])
        self.assertEqual(["contracts"], packet["required_document_refs"])
        self.assertEqual(["source_main"], packet["source_refs"])
        self.assertEqual(
            jcs_sha256(packet, omit_root_field="packet_hash"),
            packet["packet_hash"],
        )

    def test_unmatched_candidate_and_unknown_evidence_are_rejected(self) -> None:
        no_candidate = files()
        no_candidate["reasoning/integrated-assessment.json"] = canonical_bytes(
            {"payload": {"expert_review_candidates": []}}
        )
        with self.assertRaisesRegex(IntegrityError, "candidate"):
            build_expert_packet_view(
                no_candidate,
                final_result(),
                closure(),
                run_id=RUN_ID,
                revision=10,
            )

        unknown = files()
        integrated = copy.deepcopy(
            __import__("json").loads(
                unknown["reasoning/integrated-assessment.json"].decode("utf-8")
            )
        )
        integrated["payload"]["expert_review_candidates"][0]["payload"][
            "evidence_proposals"
        ] = [{"evidence_ref": "fact_missing"}]
        unknown["reasoning/integrated-assessment.json"] = canonical_bytes(integrated)
        with self.assertRaisesRegex(IntegrityError, "fact_missing"):
            build_expert_packet_view(
                unknown,
                final_result(),
                closure(),
                run_id=RUN_ID,
                revision=10,
            )


if __name__ == "__main__":
    unittest.main()
