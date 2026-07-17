import copy
import json
import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.evidence.core import assemble_evidence_core
from trusted_ceo_agent.runtime_finalization import build_delivery_package, prepare_finalization
from trusted_ceo_agent.runtime_scan import _pack_artifacts
from tests.support import confirmed_mission


SHA = "a" * 64
RUN_ID = "run_20260717T000000Z_0123456789abcdef"


class RuntimeFinalizationTests(unittest.TestCase):
    def setUp(self) -> None:
        core = assemble_evidence_core(
            envelope={
                "schema_version": "1.0.0", "artifact_id": "artifact_" + "b" * 24,
                "run_id": RUN_ID, "revision": 3, "parent_artifact_hash": SHA,
                "stage": "integrated_draft", "created_at": "2026-07-17T00:00:00Z",
                "semantic_fingerprint": SHA, "artifact_hash": SHA,
            },
            mission_contract_ref="mission_" + "c" * 24,
            pack_manifest={"pack_manifest_hash": SHA, "pack_refs": ["generic-business-boundary@1.0.0"]},
            component_manifest={"component_refs": []}, source_registry=[], data_quality_register=[],
            fact_register=[], signal_register=[], evidence_links=[],
            capability_map={"capability_map_id": "capability_map_" + "d" * 24, "capabilities": []},
        )
        self.files = {
            "mission/mission-contract.json": canonical_bytes({"objective": "diagnose"}),
            "evidence/core.json": canonical_bytes(core),
            "packs/manifest.json": canonical_bytes({
                "schema_version": "1.0.0", "packs": [{
                    "pack_type": "domain", "pack_id": "generic-business-boundary",
                    "pack_version": "1.0.0", "pack_sha256": SHA,
                    "effective_authority": "provisional",
                }], "manifest_hash": SHA,
            }),
            "reasoning/integrated-assessment.json": canonical_bytes({
                "integrated_assessment_id": "integrated_" + "e" * 24,
                "payload": {
                    "integrated_issues": [], "causal_relation_hypotheses": [],
                    "blind_spots": [], "response_type_candidates": [],
                    "expert_review_candidates": [],
                },
            }),
            "workflow/hitl-overlay.json": canonical_bytes({}),
        }

    def test_empty_but_bounded_assessment_can_be_graded_and_finalized(self) -> None:
        updates, data = prepare_finalization(
            self.files, run_id=RUN_ID, revision=4, parent_artifact_hash=SHA,
        )
        self.assertIn("final/structured-output.json", updates)
        self.assertEqual([], data["grade_record_ids"])
        files = {**self.files, **updates}
        files["approvals/records/approval_final.json"] = canonical_bytes({
            "approval_id": "approval_final", "gate": "final", "status": "current",
            "input_method": "interactive_tty", "actor_role": "ceo",
            "result_artifact_ref": f"{RUN_ID}@r0005",
        })
        package = build_delivery_package(files, run_id=RUN_ID, revision=6)
        self.assertIn("final/result.json", package)
        result = json.loads(package["final/result.json"].decode("utf-8"))
        self.assertEqual([], result["issues"])
        self.assertEqual("current", result["approvals"][0]["status"])

    @staticmethod
    def _fact(code: str, role: str, suffix: str, value: str = "1") -> dict:
        return {
            "fact_id": "fact_" + suffix * 24,
            "fact_code": code,
            "fact_type": "observed",
            "metric_code": code,
            "semantic_role": "observation",
            "observation_role": role,
            "scope": [],
            "time_context": {"period": "2026-06"},
            "value": {
                "value_type": "decimal", "canonical_value": value,
                "unit_code": "ratio", "currency_code": None, "scale": "1",
            },
            "source_refs": [{
                "source_id": "source_shared", "locator_type": "json_pointer",
                "locator": f"/{suffix}", "extraction_hash": suffix * 64,
            }],
            "derivation": None,
            "quality": [],
            "producer": "runtime_intake",
            "integrity": {"payload_hash": suffix * 64},
        }

    def pack_aware_files(self) -> dict[str, bytes]:
        mission = confirmed_mission()
        pack_files, manifest, _ = _pack_artifacts(mission)
        facts = [
            self._fact("cross_period_timing_amount_share", "amount", "1", "0.03"),
            self._fact("acceptance_date", "acceptance_date", "2"),
            self._fact("recognition_date", "recognition_date", "3"),
            self._fact("contract_terms", "contract_terms", "4"),
        ]
        signal = {
            "signal_id": "signal_" + "5" * 24,
            "signal_code": "revenue_timing_expert",
            "input_fact_ids": [facts[0]["fact_id"]],
            "outcome": "triggered",
            "impact_band_candidate": "high",
            "urgency_band_candidate": "immediate",
        }
        core = assemble_evidence_core(
            envelope={
                "schema_version": "1.0.0", "artifact_id": "artifact_" + "6" * 24,
                "run_id": RUN_ID, "revision": 3, "parent_artifact_hash": SHA,
                "stage": "integrated_draft", "created_at": "2026-07-17T00:00:00Z",
                "semantic_fingerprint": SHA, "artifact_hash": SHA,
            },
            mission_contract_ref=mission["mission_contract_id"],
            pack_manifest={
                "pack_manifest_hash": manifest["manifest_hash"],
                "pack_refs": [f"{item['pack_id']}@{item['pack_version']}" for item in manifest["packs"]],
            },
            component_manifest={"component_refs": []}, source_registry=[], data_quality_register=[],
            fact_register=facts, signal_register=[signal], evidence_links=[],
            capability_map={
                "capability_map_id": "capability_map_" + "7" * 24,
                "capabilities": [{"capability_id": "timing", "status": "available", "reason_codes": [], "quality_issue_ids": []}],
            },
        )

        def issue(key: str) -> dict:
            return {
                "local_key": key,
                "payload": {
                    "problem_family_ref": "revenue_timing_control",
                    "scope_key": "enterprise", "decision_unit_ref": "control_unit",
                    "source_candidate_ids": ["claim_problem"],
                    "observation_claim_refs": ["claim_observation"],
                    "cause_hypothesis_refs": ["claim_cause"],
                    "counter_hypothesis_refs": ["claim_counter"],
                    "unresolved_conflict_refs": [],
                    "impact_evidence_refs": [signal["signal_id"], *[item["fact_id"] for item in facts]],
                    "urgency_evidence_refs": [signal["signal_id"]],
                    "counter_evidence_refs": [],
                    "decision_need_proposal": {
                        "decision_type_ref": "control_remediation_review",
                        "decision_unit_ref": "control_unit",
                        "basis_claim_refs": ["claim_problem"],
                        "rationale_template": "A control decision may be required.",
                    },
                    "verification_requirement_refs": ["contract_timing_review"],
                    "response_type_refs": ["expert_review_packet"],
                    "expert_trigger_refs": ["revenue_timing_accounting_review"],
                },
            }

        files = {
            **pack_files,
            "mission/mission-contract.json": canonical_bytes(mission),
            "evidence/core.json": canonical_bytes(core),
            "reasoning/integrated-assessment.json": canonical_bytes({
                "integrated_assessment_id": "integrated_" + "8" * 24,
                "payload": {
                    "integrated_issues": [issue("timing_issue"), issue("timing_issue_peer")],
                    "causal_relation_hypotheses": [{
                        "local_key": "relation_timing",
                        "payload": {
                            "from_issue_local_key": "timing_issue",
                            "to_issue_local_key": "timing_issue_peer",
                            "status": "hypothesis", "mechanism_ref": "low_margin_mix_shift",
                            "supports_evidence_proposals": [], "contradicts_evidence_proposals": [],
                            "distinguishing_test_refs": ["contract_timing_review"],
                        },
                    }],
                    "cross_issue_conflicts": [],
                    "blind_spots": [{
                        "local_key": "blind_contract_detail",
                        "payload": {
                            "capability_ref": "contract_terms", "affected_scope_keys": ["enterprise"],
                            "reason_codes": ["contract_detail_review"], "missing_fact_codes": [],
                            "data_request_refs": [],
                            "consequence_template": "Contract detail requires qualified review.",
                        },
                    }],
                    "response_type_candidates": [{
                        "local_key": "response_integrated",
                        "payload": {
                            "target_issue_local_key": "timing_issue",
                            "response_ref": "expert_review_packet",
                            "precondition_refs": ["material timing threshold met"],
                            "disqualifier_refs": ["date role unconfirmed"],
                            "verification_requirement_refs": ["contract_timing_review"],
                        },
                    }],
                    "expert_review_candidates": [{
                        "local_key": "expert_integrated",
                        "payload": {
                            "target_issue_local_key": "timing_issue",
                            "expert_trigger_ref": "revenue_timing_accounting_review",
                            "evidence_proposals": [], "required_document_refs": ["contracts"],
                            "review_question_template": "Review the timing evidence and contract terms.",
                        },
                    }],
                },
            }),
            "reasoning/deep-dive-result.json": canonical_bytes({
                "deep_dive_result_id": "deep_" + "9" * 24,
                "payload": {
                    "approved_scope_ref": "scope_approved", "component_run_refs": ["component_run_approved"],
                    "updated_cause_hypotheses": [],
                    "updated_counter_hypotheses": [],
                    "distinguishing_test_results": [{
                        "local_key": "test_timing", "payload": {
                            "target_issue_ref": "timing_issue", "test_ref": "contract_timing_review",
                            "status": "completed", "result_fact_ids": [facts[0]["fact_id"]],
                            "result_signal_ids": [signal["signal_id"]], "reason_codes": [],
                        },
                    }],
                    "conditional_response_candidates": [{
                        "local_key": "response_deep", "payload": {
                            "target_issue_ref": "timing_issue", "response_ref": "expert_review_packet",
                            "action_template": "Prepare the evidence packet for qualified review.",
                            "value_refs": [], "precondition_refs": ["material timing threshold met"],
                            "disqualifier_refs": ["date role unconfirmed"],
                            "monitoring_metric_refs": ["cross_period_timing_amount_share"],
                            "reversibility": "reversible", "owner_role": "finance_owner",
                            "expert_review_refs": ["revenue_timing_accounting_review"],
                        },
                    }],
                    "expert_review_candidates": [],
                    "remaining_uncertainties": [{
                        "local_key": "uncertainty_contract", "payload": {
                            "target_issue_ref": "timing_issue", "uncertainty_type": "definition",
                            "reason_code": "contract_interpretation", "missing_fact_codes": [],
                            "statement_template": "Contract interpretation remains with the qualified reviewer.",
                        },
                    }],
                    "additional_data_requests": [{
                        "local_key": "request_acceptance", "payload": {
                            "target_issue_ref": "timing_issue", "required_fact_codes": ["acceptance_date"],
                            "requested_source_role": "acceptance_records", "required_fields": ["acceptance_date"],
                            "period": "current_reporting_period",
                            "purpose_template": "Confirm the acceptance evidence used in the review.",
                        },
                    }],
                },
            }),
            "workflow/hitl-overlay.json": canonical_bytes({
                "issue_dispositions": {
                    "timing_issue": "accepted", "timing_issue_peer": "accepted",
                },
                "decision_dispositions": {
                    "timing_issue": "needed", "timing_issue_peer": "needed",
                },
                "verification_authorizations": {},
                "deep_dive_scope": {
                    "issue_ids": ["timing_issue"], "component_ids": ["temporal_alignment"],
                },
            }),
        }
        return files

    def test_pack_rules_and_deep_result_drive_grading_and_structured_output(self) -> None:
        files = self.pack_aware_files()
        updates, _ = prepare_finalization(files, run_id=RUN_ID, revision=4, parent_artifact_hash=SHA)
        inputs = json.loads(updates["grading/inputs.json"].decode("utf-8"))
        self.assertEqual("limited", inputs[0]["evidence_state"])
        self.assertEqual("required", inputs[0]["expert_trigger_state"])
        self.assertEqual("provisional", inputs[0]["pack_authority"])
        structured = json.loads(updates["final/structured-output.json"].decode("utf-8"))
        self.assertEqual(1, len(structured["cross_issue_relations"]))
        self.assertGreaterEqual(len(structured["conditional_responses"]), 1)
        self.assertEqual(1, len(structured["monitoring"]))
        self.assertGreaterEqual(len(structured["blind_spots"]), 3)
        self.assertGreaterEqual(len(structured["expert_review_packets"]), 1)
        self.assertIn("Timing", structured["issues"][0]["title_template"])

    def test_missing_required_role_makes_expert_possible_and_assessment_partial(self) -> None:
        files = self.pack_aware_files()
        core = json.loads(files["evidence/core.json"].decode("utf-8"))
        contract = next(item for item in core["fact_register"] if item["fact_code"] == "contract_terms")
        contract["observation_role"] = "unmapped_contract_field"
        body = {key: value for key, value in core.items() if key != "integrity"}
        import hashlib
        contract_body = {key: value for key, value in contract.items() if key != "integrity"}
        contract["integrity"] = {"payload_hash": hashlib.sha256(canonical_bytes(contract_body)).hexdigest()}
        core["integrity"] = {"payload_hash": hashlib.sha256(canonical_bytes(body)).hexdigest()}
        files["evidence/core.json"] = canonical_bytes(core)
        updates, _ = prepare_finalization(files, run_id=RUN_ID, revision=4, parent_artifact_hash=SHA)
        first = json.loads(updates["grading/inputs.json"].decode("utf-8"))[0]
        self.assertEqual("partial", first["assessability"])
        self.assertEqual("possible", first["expert_trigger_state"])
        self.assertIn("missing_evidence_role:contract_terms", first["not_assessable_reason_codes"])

    def test_writer_and_final_overlay_change_wording_and_disposition_but_never_grade(self) -> None:
        files = self.pack_aware_files()
        updates, _ = prepare_finalization(files, run_id=RUN_ID, revision=4, parent_artifact_hash=SHA)
        files.update(updates)
        structured = json.loads(files["final/structured-output.json"].decode("utf-8"))
        issue = next(item for item in structured["issues"] if item["local_key"] == "timing_issue")
        original_grade = issue["primary_grade"]
        files["reasoning/writer-result.json"] = canonical_bytes({
            "writer_result_id": "writer_" + "a" * 24,
            "payload": {
                "structured_output_ref": "final/structured-output.json",
                "claim_templates": [{"claim_id": issue["issue_id"], "template": "Timing evidence requires executive attention."}],
                "expert_packet_templates": [], "ceo_brief_section_order": [],
            },
        })
        overlay = json.loads(files["workflow/hitl-overlay.json"].decode("utf-8"))
        overlay.update({
            "response_dispositions": {"response_integrated": "rejected", "response_deep": "accepted"},
            "expert_routing": {"revenue_timing_accounting_review": "accepted"},
            "ceo_wording": {"timing_issue": {"title_template": "Timing control review"}},
            "delivery_scope": {"sections": ["issues", "expert_review_packets"]},
        })
        files["workflow/hitl-overlay.json"] = canonical_bytes(overlay)
        files["approvals/records/approval_final.json"] = canonical_bytes({
            "approval_id": "approval_final", "gate": "final", "status": "current",
            "decision": "approve_with_edits", "input_method": "interactive_tty", "actor_role": "ceo",
            "result_artifact_ref": f"{RUN_ID}@r0005",
        })
        package = build_delivery_package(files, run_id=RUN_ID, revision=6)
        result = json.loads(package["final/result.json"].decode("utf-8"))
        delivered = next(item for item in result["issues"] if item["issue_id"] == issue["issue_id"])
        self.assertEqual(original_grade, delivered["primary_grade"])
        self.assertEqual("Timing control review", delivered["title_template"])
        self.assertEqual("Timing evidence requires executive attention.", delivered["why_it_matters_template"])
        self.assertEqual(1, len(result["conditional_responses"]))

        forged = copy.deepcopy(overlay)
        forged["ceo_wording"]["timing_issue"]["primary_grade"] = "Decision Required"
        files["workflow/hitl-overlay.json"] = canonical_bytes(forged)
        with self.assertRaises(Exception):
            build_delivery_package(files, run_id=RUN_ID, revision=6)

        files["workflow/hitl-overlay.json"] = canonical_bytes(overlay)
        tampered = copy.deepcopy(structured)
        target = next(item for item in tampered["issues"] if item["local_key"] == "timing_issue")
        target["primary_grade"] = "Monitor"
        files["final/structured-output.json"] = canonical_bytes(tampered)
        with self.assertRaises(Exception):
            build_delivery_package(files, run_id=RUN_ID, revision=6)


if __name__ == "__main__":
    unittest.main()
