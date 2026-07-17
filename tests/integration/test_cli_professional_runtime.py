from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tests.integration.test_cli_components import call, prepare_authorized_scope
from tests.integration.test_professional_analysis_runtime import (
    _authority_material,
    _manifest,
    _policy,
)
from tests.integrator_support import finding_spec
from trusted_ceo_agent.analysis.economic_events import (
    EVENT_FACT_FIELDS,
    materialize_economic_event,
)
from trusted_ceo_agent.analysis.execution_authority import (
    build_knowledge_release_binding,
)
from trusted_ceo_agent.analysis.signal_queue import materialize_signal_cases
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.grading.grader import grade
from trusted_ceo_agent.evidence.signals import build_signal


ROOT = Path(__file__).resolve().parents[2]


def professional_request(
    store,
    *,
    run_id: str,
    scope_ref: str,
    declared_failure: bool = False,
) -> dict:
    snapshot = store.verify_revision(3)
    core = json.loads((snapshot / "evidence" / "core.json").read_text("utf-8"))
    fact = sorted(core["fact_register"], key=lambda item: item["fact_id"])[0]
    signal = build_signal(
        signal_code="runtime.cli.professional",
        rule_ref="rule_runtime_cli_professional",
        component_id="component_runtime_cli_signal",
        component_version="1.0.0",
        component_run_id="component_run_" + "6" * 24,
        threshold_ref="threshold_runtime_cli_professional",
        input_fact_ids=[fact["fact_id"]],
        required_fact_codes=[fact["fact_code"]],
        missing_fact_codes=[],
        scope=[{"dimension_code": "company", "member_code": "all"}],
        time_context={"period": "2026-Q2"},
        evaluation={"triggered": True},
        outcome="triggered",
        impact_band_candidate="high",
        urgency_band_candidate="near_term",
    )
    manifest, catalog = _manifest()
    bindings = {field: [] for field in EVENT_FACT_FIELDS}
    bindings["performance_state"] = [fact["fact_id"]]
    case_plan = {
        "case_key": "runtime-cli-professional",
        "signal_ids": [signal["signal_id"]],
        "required_domain_routes": ["accounting"],
        "optional_domain_routes": [],
        "related_case_keys": [],
        "priority_dimensions": {
            "deterministic_risk": 90,
            "amount_cash_impact": 80,
            "legal_human_impact": 40,
            "control_failure": 60,
            "urgency": 80,
            "data_sufficiency": 90,
            "ceo_question_relevance": 90,
        },
    }
    event = materialize_economic_event(
        evidence_core=core,
        expected_revision=3,
        expected_artifact_hash=core["envelope"]["artifact_hash"],
        event_type="periodic_performance",
        field_fact_refs=bindings,
    )
    cases, _ = materialize_signal_cases(
        run_id=run_id,
        base_revision=4,
        signals=[signal],
        case_specs=[{**case_plan, "event_id": event["event_id"]}],
        priority_policy_ref="priority_policy_v1",
    )
    case_id = cases[0]["case_id"]
    spec = copy.deepcopy(finding_spec("6", "accounting"))
    for field in (
        "run_id",
        "revision",
        "case_id",
        "event_id",
        "signal_ids",
        "domain_assessment_refs",
    ):
        spec.pop(field)
    spec["fact_refs"] = [fact["fact_id"]]
    grading_input = {
        "issue_id": case_id,
        "assessability": "assessable",
        "not_assessable_reason_codes": [],
        "evidence_state": "sufficient",
        "impact_band": "high",
        "urgency_band": "near_term",
        "mission_priority_match": True,
        "executive_materiality": True,
        "decision_needed": True,
        "expert_trigger_state": "none",
        "pack_authority": "boundary",
        "diagnostic_disposition": "accepted",
        "verification_authorized": True,
        "issue_disposition": "standalone",
        "trackable": True,
        "response_eligibility": "eligible",
        "provenance_refs": [fact["fact_id"]],
    }
    grade_record = grade(grading_input)
    spec["grade"] = {
        "status": grade_record["publication_status"],
        "grade_record_ref": grade_record["grade_record_id"],
    }
    work_key = "accounting-deep-case"
    task_result = {
        "status": "succeeded",
        "findings": [{
            "finding_key": "primary-accounting",
            "assessment_domains": ["accounting"],
            "grading_input": grading_input,
            "grade_record": grade_record,
            "spec": spec,
        }],
        "expert_packet_refs": [],
    }
    policy = _policy()
    profile, depth, knowledge_release = copy.deepcopy(_authority_material())
    authority_inputs = {
        "expected_policy_release_id": "policy_release_professional_runtime",
        "depth_assessments": [depth],
        "knowledge_release": knowledge_release,
        "knowledge_release_binding": build_knowledge_release_binding(
            run_id=run_id,
            revision=4,
            policy_release_id="policy_release_professional_runtime",
            work_budget_policy=policy,
            knowledge_release=knowledge_release,
        ),
        "concurrency_profile": profile,
        "requested_authority": "full",
    }
    return {
        "scope_ref": scope_ref,
        "runtime_input": {
            "event_type": "periodic_performance",
            "field_fact_refs": bindings,
            "registered_domains": ["accounting"],
            "candidate_sets": {
                "mandatory_baseline": [{
                    "domain": "accounting",
                    "pack_ref": "accounting-core@1.0.0",
                }],
                "mission_requested": [],
                "event_data_account": [],
                "deterministic_signal": [],
                "cross_domain_trigger": [],
                "ai_proposed": [],
            },
            "screen_results": [{
                "domain": "accounting",
                "status": "triggered",
                "trigger_card_refs": [],
                "fact_refs": [fact["fact_id"]],
                "signal_refs": [signal["signal_id"]],
                "missing_capability_refs": [],
                "routing_reason_codes": ["runtime_cli_professional"],
                "estimated_cost_class": "medium",
            }],
            "pack_manifest": manifest,
            "pack_catalog": catalog,
            "jurisdiction": "KR",
            "effective_at": "2026-07-17T00:00:00Z",
            "signals": [signal],
            "case_plans": [case_plan],
            "work_plans": [{
                "local_key": work_key,
                "signal_id": signal["signal_id"],
                "domain": "accounting",
                "issue_family": "AC-01",
                "procedure_refs": ["P-AC-01"],
                "dependency_keys": [],
                "required": True,
                "packet_ref": "packets/accounting-deep-case.json",
                "packet_hash": "8" * 64,
                "pack_release_id": "accounting-core@1.0.0",
                "timeout_policy": {
                    "timeout_seconds": 5,
                    "retryable_failure_codes": ["contract_invalid"],
                },
            }],
            "priority_policy_ref": "priority_policy_v1",
            "policy": policy,
            "policy_release_id": "policy_release_professional_runtime",
            "concurrency_profile_id": "sequential",
            "execution_authority_inputs": authority_inputs,
            "runtime_control": {
                "resume_checkpoints": [],
                "result_payloads": {},
                "cancel_task_ids": [],
                "elapsed_seconds": 0,
            },
            "relation_plans": [],
            "cluster_plans": [{
                "cluster_key": "primary",
                "finding_keys": ["primary-accounting"],
                "relation_keys": [],
                "decision_unit": {
                    "title": "Review the supported accounting finding",
                    "decision_required": True,
                    "owner_role": "ceo",
                    "option_refs": ["decision_option_review"],
                },
                "unresolved_conflicts": [],
            }],
            "boundary_packet_refs": {},
            "limited_basis": "none",
            "user_confirmed_limitations": False,
            "final_validator_passed": True,
            "tty_final_approval_ready": True,
        },
        "task_results": {} if declared_failure else {work_key: task_result},
        "task_failures": {work_key: "contract_invalid"} if declared_failure else {},
    }


class CliProfessionalRuntimeTests(unittest.TestCase):
    def test_approved_component_path_publishes_verified_professional_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            _, run_id, store, common, _, scope_ref, _, _ = prepare_authorized_scope(root)
            request_path = root / "professional.json"
            request_path.write_bytes(canonical_bytes(
                professional_request(store, run_id=run_id, scope_ref=scope_ref)
            ))

            code, result = call([
                "run-components",
                *common,
                "--scope-ref",
                scope_ref,
                "--professional-input",
                str(request_path),
                "--expected-revision",
                "3",
            ])

            self.assertEqual(0, code, result)
            self.assertEqual(
                "finalization_ready",
                result["data"]["professional_completion_status"],
            )
            self.assertTrue(result["data"]["professional_finalization_allowed"])
            snapshot = store.verify_revision(4)
            completion = json.loads(
                (
                    snapshot
                    / "analysis"
                    / "professional"
                    / "completion-assessment.json"
                ).read_text("utf-8")
            )
            findings = json.loads(
                (
                    snapshot
                    / "analysis"
                    / "professional"
                    / "findings.json"
                ).read_text("utf-8")
            )
            self.assertEqual("finalization_ready", completion["status"])
            self.assertEqual(1, len(findings))
            runtime_result = json.loads(
                (
                    snapshot / "analysis" / "professional"
                    / "runtime-result.json"
                ).read_text("utf-8")
            )
            self.assertEqual(findings, runtime_result["findings"])
            authority = json.loads(
                (
                    snapshot / "analysis" / "professional"
                    / "execution-authority.json"
                ).read_text("utf-8")
            )
            self.assertEqual(authority["product_display"], result["data"][
                "professional_product_display"

            ])
    def test_declared_required_failure_is_published_but_blocks_finalization(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            _, run_id, store, common, _, scope_ref, _, _ = prepare_authorized_scope(root)
            request_path = root / "professional.json"
            request_path.write_bytes(canonical_bytes(professional_request(
                store,
                run_id=run_id,
                scope_ref=scope_ref,
                declared_failure=True,
            )))

            code, result = call([
                "run-components",
                *common,
                "--scope-ref",
                scope_ref,
                "--professional-input",
                str(request_path),
                "--expected-revision",
                "3",
            ])

            self.assertEqual(3, code, result)
            self.assertFalse(result["data"]["professional_finalization_allowed"])
            self.assertEqual("blocked", result["state"])
            self.assertEqual(4, store.state()["revision"])
            completion = json.loads(
                (
                    store.verify_revision(4)
                    / "analysis"
                    / "professional"
                    / "completion-assessment.json"
                ).read_text("utf-8")
            )
            self.assertEqual("not_ready", completion["status"])


if __name__ == "__main__":
    unittest.main()
