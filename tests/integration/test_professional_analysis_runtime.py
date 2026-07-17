from __future__ import annotations

import copy
import hashlib
import unittest

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


def _base_input(*, legal_boundary: bool = False) -> dict:
    core = core_fixture()
    party, amount = bound_facts(core)
    signal = _signal(amount["fact_id"])
    manifest, catalog = _manifest(include_legal=False)
    domains = ("accounting", "legal") if legal_boundary else ("accounting",)
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
        "policy": _policy(),
        "policy_release_id": "policy_release_professional_runtime",
        "concurrency_profile_id": "sequential",
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
    return {
        "status": "succeeded",
        "findings": [{
            "finding_key": "primary-accounting",
            "assessment_domains": ["accounting"],
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
