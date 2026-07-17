from __future__ import annotations

import copy
import hashlib
import unittest
from functools import lru_cache
from tests.foundry_support import make_initial_release
from tests.professional_knowledge_support import make_knowledge_bundle
from trusted_ceo_agent.analysis.execution_authority import (
    build_knowledge_release_binding,
)
from trusted_ceo_agent.evaluation.metrics import QUALITY_SCORE_METRICS
from trusted_ceo_agent.evaluation.non_inferiority import (
    build_concurrency_profile,
    build_quality_policy,
)
from trusted_ceo_agent.grading.grader import grade
from trusted_ceo_agent.knowledge.depth_gate import assess_professional_depth


from tests.integrator_support import finding_spec
from tests.unit.analysis.test_economic_events import (
    bindings,
    bound_facts,
    core_fixture,
)
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.evidence.signals import build_signal
from trusted_ceo_agent.orchestration.budget import build_work_budget_policy


RUN_ID = "run_professional_runtime"
REVISION = 3


def _signal(fact_id: str) -> dict:
    return build_signal(
        signal_code="runtime.material_contract",
        rule_ref="rule_runtime_material_contract",
        component_id="component_runtime_signal_scan",
        component_version="1.0.0",
        component_run_id="component_run_" + "7" * 24,
        threshold_ref="threshold_runtime_material_contract",
        input_fact_ids=[fact_id],
        required_fact_codes=["contract.consideration.amount"],
        missing_fact_codes=[],
        scope=[{"dimension_code": "company", "member_code": "all"}],
        time_context={"period": "2026-Q2"},
        evaluation={"triggered": True},
        outcome="triggered",
        impact_band_candidate="high",
        urgency_band_candidate="near_term",
    )


def _manifest(*, include_legal: bool = False) -> tuple[dict, list[dict]]:
    domains = ("accounting", "legal") if include_legal else ("accounting",)
    packs = []
    catalog = []
    for index, domain in enumerate(domains, start=1):
        digest = f"{index:x}" * 64
        packs.append({
            "pack_type": "domain",
            "pack_id": f"{domain}-core",
            "pack_version": "1.0.0",
            "pack_sha256": digest,
            "effective_authority": "full" if domain == "accounting" else "boundary",
        })
        catalog.append({
            "pack_ref": f"{domain}-core@1.0.0",
            "domain": domain,
            "pack_sha256": digest,
            "effective_authority": "full" if domain == "accounting" else "boundary",
            "jurisdictions": ["KR"],
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": None,
        })
    body = {"schema_version": "1.0.0", "packs": packs}
    return {
        **body,
        "manifest_hash": hashlib.sha256(canonical_bytes(body)).hexdigest(),
    }, catalog


def _candidate_sets(domains: tuple[str, ...]) -> dict:
    return {
        "mandatory_baseline": [
            {"domain": domain, "pack_ref": f"{domain}-core@1.0.0"}
            for domain in domains
        ],
        "mission_requested": [],
        "event_data_account": [],
        "deterministic_signal": [],
        "cross_domain_trigger": [],
        "ai_proposed": [],
    }


def _screen(domain: str, fact_id: str) -> dict:
    return {
        "domain": domain,
        "status": "triggered",
        "trigger_card_refs": [],
        "fact_refs": [fact_id],
        "signal_refs": [],
        "missing_capability_refs": [],
        "routing_reason_codes": [f"screen_{domain}"],
        "estimated_cost_class": "medium",
    }


def _policy() -> dict:
    return build_work_budget_policy(
        policy_id="budget_professional_runtime",
        workload_class="b2b_service_accounting",
        max_active_signal_cases=1,
        max_parallel_workers=1,
        max_model_attempts_per_task=2,
        task_timeout=5,
        case_timeout=120,
        max_optional_issue_families=4,
        evidence_packet_limits={
            "max_facts": 48,
            "max_signals": 48,
            "max_observations": 12,
            "max_problem_candidates": 6,
            "max_causes_per_problem": 4,
            "max_counters_per_cause": 2,
            "max_verifications_per_problem": 3,
            "max_data_requests": 8,
            "max_human_questions": 8,
            "max_expert_candidates": 6,
            "max_payload_bytes": 65536,
        },
        overflow_action="deep_review_pending",
        benchmark_refs=["benchmark_professional_runtime"],
        approved_concurrency_profile_id="sequential",
        effective_from="2026-07-17T00:00:00Z",
    )


@lru_cache(maxsize=1)
def _authority_material() -> tuple[dict, dict, dict]:
    quality_policy = build_quality_policy(
        policy_id="quality_policy_professional_runtime",
        metric_margins={metric: "0" for metric in QUALITY_SCORE_METRICS},
        min_workload_classes=4,
        min_runs_per_condition=10,
    )
    profile = build_concurrency_profile("sequential", quality_policy)
    family, cards, expert, pack_release = make_knowledge_bundle(
        pack_authority="full"
    )
    depth = assess_professional_depth(
        family,
        cards,
        effective_on="2026-06-30",
        jurisdiction="KR",
        industry_scope="b2b_services",
        expert_approval=expert,
        release=pack_release,
    )
    knowledge_release = make_initial_release()
    return profile, depth, knowledge_release


def _execution_authority_inputs(policy: dict) -> dict:
    profile, depth, knowledge_release = copy.deepcopy(_authority_material())
    policy_release_id = "policy_release_professional_runtime"
    return {
        "expected_policy_release_id": policy_release_id,
        "depth_assessments": [depth],
        "knowledge_release": knowledge_release,
        "knowledge_release_binding": build_knowledge_release_binding(
            run_id=RUN_ID,
            revision=REVISION,
            policy_release_id=policy_release_id,
            work_budget_policy=policy,
            knowledge_release=knowledge_release,
        ),
        "concurrency_profile": profile,
        "requested_authority": "full",
    }


def _runtime_control() -> dict:
    return {
        "resume_checkpoints": [],
        "result_payloads": {},
        "cancel_task_ids": [],
        "elapsed_seconds": 0,
    }


def _base_input(*, legal_boundary: bool = False) -> dict:
    core = core_fixture()
    party, amount = bound_facts(core)
    signal = _signal(amount["fact_id"])
    manifest, catalog = _manifest(include_legal=False)
    domains = ("accounting", "legal") if legal_boundary else ("accounting",)
    policy = _policy()
    return {
        "run_id": RUN_ID,
        "revision": REVISION,
        "evidence_core": core,
        "expected_evidence_core_hash": "b" * 64,
        "event_type": "contract_performance",
        "field_fact_refs": bindings(party["fact_id"], amount["fact_id"]),
        "registered_domains": domains,
        "candidate_sets": _candidate_sets(domains),
        "screen_results": [_screen(domain, amount["fact_id"]) for domain in domains],
        "pack_manifest": manifest,
        "pack_catalog": catalog,
        "jurisdiction": "KR",
        "effective_at": "2026-07-17T00:00:00Z",
        "signals": [signal],
        "case_plans": [{
            "case_key": "material-contract",
            "signal_ids": [signal["signal_id"]],
            "required_domain_routes": list(domains),
            "optional_domain_routes": [],
            "related_case_keys": [],
            "priority_dimensions": {
                "deterministic_risk": 90,
                "amount_cash_impact": 80,
                "legal_human_impact": 70,
                "control_failure": 60,
                "urgency": 80,
                "data_sufficiency": 90,
                "ceo_question_relevance": 90,
            },
        }],
        "work_plans": [{
            "local_key": "accounting-deep-case",
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
        "execution_authority_inputs": _execution_authority_inputs(policy),
        "runtime_control": _runtime_control(),
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
        "boundary_packet_refs": (
            {"legal": ["expert_packet_legal_boundary"]} if legal_boundary else {}
        ),
        "limited_basis": "data_unavailable" if legal_boundary else "none",
        "user_confirmed_limitations": legal_boundary,
        "final_validator_passed": True,
        "tty_final_approval_ready": True,
    }


def _successful_executor(request: dict) -> dict:
    spec = finding_spec("2", "accounting")
    for field in (
        "run_id",
        "revision",
        "case_id",
        "event_id",
        "signal_ids",
        "domain_assessment_refs",
    ):
        spec.pop(field)
    spec["fact_refs"] = [request["event"]["fact_refs"][0]]
    grading_input = {
        "issue_id": request["signal_case"]["case_id"],
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
        "provenance_refs": list(spec["fact_refs"]),
    }
    grade_record = grade(grading_input)
    spec["grade"] = {
        "status": grade_record["publication_status"],
        "grade_record_ref": grade_record["grade_record_id"],
    }
    return {
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


class ProfessionalAnalysisRuntimeTests(unittest.TestCase):
    def test_full_vertical_run_is_deterministic_and_content_addressed(self) -> None:
        from trusted_ceo_agent.analysis.runtime import ProfessionalAnalysisRuntime

        runtime = ProfessionalAnalysisRuntime()
        first = runtime.run(**_base_input(), task_executor=_successful_executor)
        second = runtime.run(
            **copy.deepcopy(_base_input()),
            task_executor=_successful_executor,
        )

        self.assertEqual(canonical_bytes(first), canonical_bytes(second))
        self.assertEqual("finalization_ready", first["completion"]["status"])
        self.assertTrue(first["finalization_allowed"])
        self.assertEqual("succeeded", first["graphs"][0]["status"])
        self.assertEqual("terminal", first["signal_cases"][0]["status"])
        self.assertEqual("substantiated", first["signal_cases"][0]["disposition"])
        self.assertEqual(1, len(first["findings"]))
        self.assertTrue(first["execution_authority"]["execution_allowed"])
        self.assertEqual(1, len(first["grading_inputs"]))
        self.assertEqual(1, len(first["grade_records"]))
        self.assertEqual(1, len(first["result_cas"]))
        cas = first["result_cas"][0]
        self.assertEqual(
            f"cas/results/{cas['result_hash']}.json",
            cas["result_ref"],
        )
        self.assertEqual(
            cas["result_hash"],
            hashlib.sha256(canonical_bytes(cas["payload"])).hexdigest(),
        )
        self.assertEqual(
            first["finding_join_manifest"]["integrity"]["payload_hash"],
            first["cross_domain_integration"]["manifest_hash"],
        )

    def test_blocked_execution_authority_never_calls_pack_executor(self) -> None:
        from trusted_ceo_agent.analysis.runtime import ProfessionalAnalysisRuntime

        arguments = _base_input()
        arguments["execution_authority_inputs"]["knowledge_release_binding"] = None
        calls = 0

        def executor(request: dict) -> dict:
            nonlocal calls
            calls += 1
            return _successful_executor(request)

        result = ProfessionalAnalysisRuntime().run(
            **arguments,
            task_executor=executor,
        )

        self.assertEqual(0, calls)
        self.assertFalse(result["execution_authority"]["execution_allowed"])
        self.assertEqual("not_ready", result["completion"]["status"])
        self.assertFalse(result["finalization_allowed"])

    def test_forged_grade_record_is_rejected_before_finding_build(self) -> None:
        from trusted_ceo_agent.analysis.runtime import ProfessionalAnalysisRuntime
        from trusted_ceo_agent.errors import ContractError

        def forged(request: dict) -> dict:
            result = _successful_executor(request)
            result["findings"][0]["grade_record"]["primary_grade"] = "Monitor"
            return result

        with self.assertRaisesRegex(ContractError, "Grade Record"):
            ProfessionalAnalysisRuntime().run(
                **_base_input(),
                task_executor=forged,
            )

    def test_grade_cannot_exceed_execution_authority(self) -> None:
        from trusted_ceo_agent.analysis.runtime import ProfessionalAnalysisRuntime
        from trusted_ceo_agent.errors import ContractError

        def overclaimed(request: dict) -> dict:
            result = _successful_executor(request)
            entry = result["findings"][0]
            entry["grading_input"]["pack_authority"] = "full"
            entry["grade_record"] = grade(entry["grading_input"])
            entry["spec"]["grade"] = {
                "status": entry["grade_record"]["publication_status"],
                "grade_record_ref": entry["grade_record"]["grade_record_id"],
            }
            return result

        with self.assertRaisesRegex(
            ContractError,
            "pack authority exceeds",
        ):
            ProfessionalAnalysisRuntime().run(
                **_base_input(),
                task_executor=overclaimed,
            )

    def test_required_budget_overflow_blocks_executor_and_records_assessment(self) -> None:
        from trusted_ceo_agent.analysis.runtime import ProfessionalAnalysisRuntime

        arguments = _base_input()
        arguments["runtime_control"]["elapsed_seconds"] = arguments["policy"][
            "case_timeout"
        ]
        calls = 0

        def executor(request: dict) -> dict:
            nonlocal calls
            calls += 1
            return _successful_executor(request)

        result = ProfessionalAnalysisRuntime().run(
            **arguments,
            task_executor=executor,
        )

        self.assertEqual(0, calls)
        self.assertEqual(
            "deep_review_pending", result["budget_assessments"][0]["status"]
        )
        self.assertEqual("not_ready", result["completion"]["status"])
        self.assertFalse(result["finalization_allowed"])

    def test_cancellation_propagates_without_pack_execution(self) -> None:
        from trusted_ceo_agent.analysis.runtime import ProfessionalAnalysisRuntime

        source = ProfessionalAnalysisRuntime().run(
            **_base_input(), task_executor=_successful_executor
        )
        arguments = _base_input()
        arguments["runtime_control"]["cancel_task_ids"] = [
            source["work_items"][0]["task_id"]
        ]
        calls = 0

        def executor(request: dict) -> dict:
            nonlocal calls
            calls += 1
            return _successful_executor(request)

        result = ProfessionalAnalysisRuntime().run(
            **arguments,
            task_executor=executor,
        )

        self.assertEqual(0, calls)
        self.assertEqual("cancelled", result["work_items"][0]["status"])
        self.assertEqual("not_ready", result["completion"]["status"])
        self.assertTrue(result["checkpoints"])

    def test_resume_reuses_verified_success_without_pack_execution(self) -> None:
        from trusted_ceo_agent.analysis.runtime import ProfessionalAnalysisRuntime

        source = ProfessionalAnalysisRuntime().run(
            **_base_input(), task_executor=_successful_executor
        )
        checkpoint = source["checkpoints"][-1]
        arguments = _base_input()
        arguments["runtime_control"] = {
            "resume_checkpoints": [checkpoint],
            "result_payloads": {
                item["result_ref"]: canonical_bytes(item["payload"])
                for item in source["result_cas"]
            },
            "cancel_task_ids": [],
            "elapsed_seconds": 0,
        }
        calls = 0

        def executor(_request: dict) -> dict:
            nonlocal calls
            calls += 1
            raise AssertionError("a verified terminal result must not execute twice")

        resumed = ProfessionalAnalysisRuntime().run(
            **arguments,
            task_executor=executor,
        )

        self.assertEqual(0, calls)
        self.assertEqual(source["findings"], resumed["findings"])
        self.assertEqual(source["grade_records"], resumed["grade_records"])
        self.assertEqual(
            f"checkpoints/{checkpoint['checkpoint_id']}.json",
            resumed["checkpoints"][0]["previous_checkpoint_ref"],
        )

    def test_required_task_failure_blocks_join_and_finalization(self) -> None:
        from trusted_ceo_agent.analysis.runtime import (
            ProfessionalAnalysisRuntime,
            TaskExecutionFailure,
        )

        attempts = 0

        def fail(_request: dict) -> dict:
            nonlocal attempts
            attempts += 1
            raise TaskExecutionFailure("contract_invalid")

        result = ProfessionalAnalysisRuntime().run(
            **_base_input(),
            task_executor=fail,
        )

        self.assertEqual(2, attempts)
        self.assertEqual("not_ready", result["completion"]["status"])
        self.assertFalse(result["finalization_allowed"])
        self.assertIsNone(result["finding_join_manifest"])
        self.assertIsNone(result["cross_domain_integration"])
        self.assertEqual([], result["result_cas"])
        self.assertEqual(
            ["deep_review_pending"],
            [item["status"] for item in result["work_items"]],
        )

    def test_unsupported_domain_requires_packet_and_only_allows_limited_completion(self) -> None:
        from trusted_ceo_agent.analysis.runtime import ProfessionalAnalysisRuntime

        result = ProfessionalAnalysisRuntime().run(
            **_base_input(legal_boundary=True),
            task_executor=_successful_executor,
        )

        self.assertEqual("limited_completion_ready", result["completion"]["status"])
        self.assertTrue(result["finalization_allowed"])
        legal_route = next(
            item for item in result["domain_routes"] if item["domain"] == "legal"
        )
        self.assertEqual("unsupported_pack", legal_route["status"])
        self.assertEqual("boundary", legal_route["effective_authority"])
        self.assertEqual(
            [{
                "domain": "legal",
                "expert_role": "licensed_attorney",
                "status": "unsupported_pack",
                "additional_data_refs": ["expert_packet_legal_boundary"],
            }],
            result["cross_domain_integration"]["expert_requirements"],
        )
        self.assertEqual(
            {"accounting"},
            {
                assessment["domain"]
                for assessment in result["domain_assessments"]
                if assessment["finding_ids"]
            },
        )


if __name__ == "__main__":
    unittest.main()
