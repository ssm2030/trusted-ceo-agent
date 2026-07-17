from __future__ import annotations

import copy
import json
import unittest
from functools import lru_cache

from tests.foundry_support import make_initial_release
from tests.integrator_support import FACT_ID, REVISION, RUN_ID
from tests.unit.analysis.test_execution_authority import (
    deployed_release,
    depth_assessment,
    work_policy,
)
from tests.unit.outputs.test_professional_publication import _digest, _fixture
from trusted_ceo_agent.analysis.execution_authority import (
    build_knowledge_release_binding,
    evaluate_execution_authority,
)
from trusted_ceo_agent.analysis.findings import (
    build_finding,
    build_finding_relation,
    build_issue_cluster,
)
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.evidence.core import assemble_evidence_core
from trusted_ceo_agent.evaluation.metrics import QUALITY_SCORE_METRICS
from trusted_ceo_agent.evaluation.non_inferiority import (
    build_concurrency_profile,
    build_quality_policy,
)
from trusted_ceo_agent.errors import IntegrityError


FILE_RUN_ID = "run_20260717T000000Z_0123456789abcdef"


def _source(suffix: str) -> dict:
    return {
        "source_id": "source_" + suffix * 24,
        "source_type": "uploaded_file",
        "access_policy": "permitted",
        "evidence_usage": "primary",
        "observation_roles": ["ledger"],
        "display_name": f"ledger-{suffix}.csv",
        "media_type": "text/csv",
        "sha256": suffix * 64,
        "size_bytes": 1,
        "received_at": "2026-07-17T00:00:00Z",
        "snapshot_ref": "sources/blobs/" + suffix * 64,
        "original_path_token": "path_" + suffix * 24,
        "aliases": [],
        "metadata": {},
    }


def _source_ref(suffix: str) -> dict:
    return {
        "source_id": "source_" + suffix * 24,
        "observation_role": "ledger",
        "locator_type": "csv_records",
        "locator": {"record_indices": [1]},
        "selected_fields": ["amount"],
        "record_count": 1,
        "filters": [],
        "group_by": [],
        "operation": "observe",
        "normalized_rows_hash": suffix * 64,
        "row_multiset_hash": suffix * 64,
        "lineage_set_ref": f"lineage/sets/{suffix * 64}.json",
        "extraction_hash": suffix * 64,
    }


def _fact() -> dict:
    body = {
        "fact_id": FACT_ID,
        "fact_code": "ledger.amount",
        "fact_type": "observed",
        "metric_code": "amount",
        "semantic_role": "observation",
        "observation_role": "ledger",
        "scope": [],
        "time_context": {"period": "2026-06"},
        "value": {
            "value_type": "decimal",
            "canonical_value": "100",
            "unit_code": "currency",
            "currency_code": "KRW",
            "scale": "1",
        },
        "source_refs": [_source_ref("2"), _source_ref("3")],
        "derivation": None,
        "quality": [],
        "producer": "runtime_intake",
    }
    return {**body, "integrity": {"payload_hash": _digest(body)}}


def _signal(suffix: str) -> dict:
    return {
        "signal_id": "signal_" + suffix * 24,
        "signal_code": f"professional.{suffix}",
        "rule_ref": f"rule_{suffix}",
        "component_ref": {
            "component_id": "professional-signal",
            "component_version": "1.0.0",
            "component_run_id": "component_run_" + suffix * 24,
        },
        "threshold_ref": None,
        "input_fact_ids": [FACT_ID],
        "required_fact_codes": ["ledger.amount"],
        "missing_fact_codes": [],
        "scope": [],
        "time_context": {"period": "2026-06"},
        "evaluation": {"matched": True},
        "outcome": "triggered",
        "direction": "increase",
        "impact_band_candidate": "high",
        "urgency_band_candidate": "near_term",
        "reason_codes": [],
        "producer": "deterministic_component",
    }


def _link(suffix: str) -> dict:
    return {
        "evidence_link_id": "evidence_" + suffix * 24,
        "target_ref": "professional-publication",
        "target_type": "integrated_issue",
        "evidence_ref": FACT_ID,
        "evidence_kind": "fact",
        "polarity": "supports" if suffix != "5" else "contradicts",
        "role": "observation" if suffix != "5" else "counter_evidence",
        "rationale_template": "Engine-owned evidence reference.",
        "value_refs": [],
        "stage": "professional_publication",
        "materialized_by": "runtime_integrator",
        "origin": {
            "origin_type": "deterministic_rule",
            "origin_job_id": None,
            "model_profile": None,
            "prompt_hash": None,
            "proposal_hash": suffix * 64,
        },
        "independence_group_id": "independence_" + suffix * 24,
    }


def _core(*, run_id: str = FILE_RUN_ID) -> dict:
    return assemble_evidence_core(
        envelope={
            "schema_version": "1.0.0",
            "artifact_id": "artifact_" + "a" * 24,
            "run_id": run_id,
            "revision": REVISION,
            "parent_artifact_hash": "1" * 64,
            "stage": "professional_analysis",
            "created_at": "2026-07-17T00:00:00Z",
            "semantic_fingerprint": "2" * 64,
            "artifact_hash": "3" * 64,
        },
        mission_contract_ref="mission_" + "4" * 24,
        pack_manifest={"pack_manifest_hash": "5" * 64, "pack_refs": []},
        component_manifest={"component_refs": []},
        source_registry=[_source("2"), _source("3")],
        data_quality_register=[],
        fact_register=[_fact()],
        signal_register=[_signal("2"), _signal("3")],
        evidence_links=[_link(item) for item in ("2", "3", "4", "5")],
        capability_map={
            "capability_map_id": "capability_map_" + "6" * 24,
            "capabilities": [],
        },
    )


@lru_cache(maxsize=2)
def _authority_gate(*, full: bool) -> dict:
    policy = work_policy("sequential")
    quality_policy = build_quality_policy(
        policy_id="quality_policy_professional_publication",
        metric_margins={metric: "0" for metric in QUALITY_SCORE_METRICS},
        min_workload_classes=4,
        min_runs_per_condition=10,
    )
    release = deployed_release() if full else make_initial_release()
    policy_release_id = "policy_release_professional_publication"
    return evaluate_execution_authority(
        run_id=FILE_RUN_ID,
        revision=REVISION,
        policy_release_id=policy_release_id,
        expected_policy_release_id=policy_release_id,
        work_budget_policy=policy,
        depth_assessments=[depth_assessment(full=full)],
        knowledge_release=release,
        knowledge_release_binding=build_knowledge_release_binding(
            run_id=FILE_RUN_ID,
            revision=REVISION,
            policy_release_id=policy_release_id,
            work_budget_policy=policy,
            knowledge_release=release,
        ),
        concurrency_profile=build_concurrency_profile(
            "sequential", quality_policy
        ),
        requested_authority="full" if full else "boundary",
    )


@lru_cache(maxsize=1)
def _runtime_template() -> dict:
    from tests.integration.test_professional_analysis_runtime import (
        _base_input,
        _successful_executor,
    )
    from trusted_ceo_agent.analysis.runtime import ProfessionalAnalysisRuntime

    return ProfessionalAnalysisRuntime().run(
        **_base_input(), task_executor=_successful_executor
    )


def _runtime_result(inputs: dict, authority: dict) -> dict:
    result = copy.deepcopy(_runtime_template())
    result.update({
        "run_id": FILE_RUN_ID,
        "revision": REVISION,
        "execution_authority": copy.deepcopy(authority),
        "findings": copy.deepcopy(inputs["findings"]),
        "grading_inputs": copy.deepcopy(inputs["grading_inputs"]),
        "grade_records": copy.deepcopy(inputs["grade_records"]),
        "relations": copy.deepcopy(inputs["relations"]),
        "clusters": copy.deepcopy(inputs["clusters"]),
        "completion": copy.deepcopy(inputs["completion"]),
        "finalization_allowed": True,
        "finding_join_manifest": None,
        "cross_domain_integration": None,
        "domain_assessments": [],
    })
    body = {key: value for key, value in result.items() if key != "content_hash"}
    return {**body, "content_hash": _digest(body)}


def _files(*, full_authority: bool = True) -> tuple[dict[str, bytes], dict]:
    inputs = _fixture(run_id=FILE_RUN_ID)
    core = _core(run_id=FILE_RUN_ID)
    authority = copy.deepcopy(_authority_gate(full=full_authority))
    runtime_result = _runtime_result(inputs, authority)
    files = {
        "analysis/professional/findings.json": canonical_bytes(inputs["findings"]),
        "analysis/professional/relations.json": canonical_bytes(inputs["relations"]),
        "analysis/professional/issue-clusters.json": canonical_bytes(inputs["clusters"]),
        "analysis/professional/completion-assessment.json": canonical_bytes(
            inputs["completion"]
        ),
        "analysis/professional/grading-inputs.json": canonical_bytes(
            inputs["grading_inputs"]
        ),
        "analysis/professional/grade-records.json": canonical_bytes(
            inputs["grade_records"]
        ),
        "analysis/professional/execution-authority.json": canonical_bytes(
            authority
        ),
        "analysis/professional/runtime-result.json": canonical_bytes(
            runtime_result
        ),
        "evidence/core.json": canonical_bytes(core),
    }
    inputs["execution_authority"] = authority
    inputs["runtime_result"] = runtime_result
    return files, inputs


class ProfessionalPublicationFromFilesTests(unittest.TestCase):
    def _api(self):
        try:
            from trusted_ceo_agent.outputs.professional_publication import (
                build_professional_publication_from_files,
            )
        except ImportError:
            self.fail("file-backed professional publication adapter is missing")
        return build_professional_publication_from_files

    def test_builds_the_same_projection_from_required_artifacts(self) -> None:
        build_from_files = self._api()
        files, inputs = _files()

        actual = build_from_files(
            files,
            expected_run_id=FILE_RUN_ID,
            expected_revision=REVISION,
        )

        self.assertEqual(
            [item["case_id"] for item in inputs["findings"]],
            [item["issue_id"] for item in actual["structured_output"]["issues"]],
        )
        self.assertEqual(
            _core(run_id=FILE_RUN_ID)["integrity"]["payload_hash"],
            actual["input_manifest"]["evidence_core_hash"],
        )
        self.assertEqual(
            inputs["execution_authority"]["content_hash"],
            actual["input_manifest"]["execution_authority_hash"],
        )
        self.assertEqual(
            inputs["runtime_result"]["content_hash"],
            actual["input_manifest"]["runtime_result_hash"],
        )
        self.assertEqual("full", actual["effective_authority"])
        self.assertEqual("Full", actual["product_display"])

    def test_missing_or_invalid_required_artifact_fails_closed(self) -> None:
        build_from_files = self._api()
        valid, _ = _files()
        missing = copy.deepcopy(valid)
        missing.pop("analysis/professional/execution-authority.json")
        invalid = copy.deepcopy(valid)
        invalid["analysis/professional/findings.json"] = b"{"

        duplicate = copy.deepcopy(valid)
        duplicate["analysis/professional/findings.json"] = (
            b'{"duplicate":1,"duplicate":2}'
        )
        for label, files in (
            ("missing", missing),
            ("invalid JSON", invalid),
            ("invalid JSON", duplicate),
        ):
            with self.subTest(label=label):
                with self.assertRaisesRegex(IntegrityError, label):
                    build_from_files(
                        files,
                        expected_run_id=FILE_RUN_ID,
                        expected_revision=REVISION,
                    )

    def test_runtime_join_mismatch_fails_closed(self) -> None:
        build_from_files = self._api()
        files, _ = _files()
        foreign = json.loads(
            files["analysis/professional/runtime-result.json"].decode("utf-8")
        )
        foreign["completion"]["content_hash"] = "0" * 64
        foreign["content_hash"] = _digest({
            key: value
            for key, value in foreign.items()
            if key != "content_hash"
        })
        files["analysis/professional/runtime-result.json"] = canonical_bytes(
            foreign
        )

        with self.assertRaisesRegex(IntegrityError, "runtime result"):
            build_from_files(
                files,
                expected_run_id=FILE_RUN_ID,
                expected_revision=REVISION,
            )

    def test_authority_overclaim_and_blocked_execution_fail_closed(self) -> None:
        build_from_files = self._api()
        overclaim, _ = _files(full_authority=False)
        with self.assertRaisesRegex(IntegrityError, "exceeds execution authority"):
            build_from_files(
                overclaim,
                expected_run_id=FILE_RUN_ID,
                expected_revision=REVISION,
            )

        blocked, _ = _files()
        gate = json.loads(
            blocked[
                "analysis/professional/execution-authority.json"
            ].decode("utf-8")
        )
        gate["effective_authority"] = "machine_draft"
        gate["product_display"] = "machine_draft"
        gate["execution_allowed"] = False
        gate["requested_authority_allowed"] = False
        gate["full_allowed"] = False
        gate["blockers"] = sorted(set(gate["blockers"]) | {"execution_blocked"})
        gate_body = {
            key: value
            for key, value in gate.items()
            if key not in {"gate_id", "content_hash"}
        }
        gate["gate_id"] = "executionauthority_" + _digest(gate_body)[:24]
        gate["content_hash"] = _digest({
            key: value for key, value in gate.items() if key != "content_hash"
        })
        blocked["analysis/professional/execution-authority.json"] = canonical_bytes(
            gate
        )
        runtime = json.loads(
            blocked["analysis/professional/runtime-result.json"].decode("utf-8")
        )
        runtime["execution_authority"] = gate
        runtime["content_hash"] = _digest({
            key: value for key, value in runtime.items() if key != "content_hash"
        })
        blocked["analysis/professional/runtime-result.json"] = canonical_bytes(
            runtime
        )

        with self.assertRaisesRegex(IntegrityError, "does not permit publication"):
            build_from_files(
                blocked,
                expected_run_id=FILE_RUN_ID,
                expected_revision=REVISION,
            )

    def test_finding_disposition_and_expert_boundary_are_preserved(self) -> None:
        build_from_files = self._api()
        files, inputs = _files()
        old_findings = inputs["findings"]
        first_body = {
            key: copy.deepcopy(value)
            for key, value in old_findings[0].items()
            if key not in {
                "schema_version",
                "finding_id",
                "created_from_hash",
                "content_hash",
                "producer",
            }
        }
        first_body["disposition"] = "expert_review_required"
        first_body["conclusion"]["qualifier"] = "expert_judgment_required"
        first_body["expert_review"] = {
            "required": True,
            "packet_ref": "expert_packet_accounting_review",
            "decision_boundary": "Do not conclude statutory compliance.",
            "owner": "senior_accountant",
        }
        expert_finding = build_finding(first_body)
        findings = [expert_finding, old_findings[1]]
        relation_body = {
            key: copy.deepcopy(value)
            for key, value in inputs["relations"][0].items()
            if key not in {
                "schema_version",
                "relation_id",
                "created_from_hash",
                "content_hash",
                "producer",
            }
        }
        relation_body["source_finding_id"] = expert_finding["finding_id"]
        relation = build_finding_relation(relation_body, findings)
        cluster_body = {
            key: copy.deepcopy(value)
            for key, value in inputs["clusters"][0].items()
            if key not in {
                "schema_version",
                "cluster_id",
                "created_from_hash",
                "content_hash",
                "producer",
            }
        }
        cluster_body["finding_ids"] = sorted(
            item["finding_id"] for item in findings
        )
        cluster_body["relation_ids"] = [relation["relation_id"]]
        cluster = build_issue_cluster(
            cluster_body, findings=findings, relations=[relation]
        )
        updated = copy.deepcopy(inputs)
        updated.update({
            "findings": findings,
            "relations": [relation],
            "clusters": [cluster],
        })
        runtime = _runtime_result(updated, inputs["execution_authority"])
        files.update({
            "analysis/professional/findings.json": canonical_bytes(findings),
            "analysis/professional/relations.json": canonical_bytes([relation]),
            "analysis/professional/issue-clusters.json": canonical_bytes([cluster]),
            "analysis/professional/runtime-result.json": canonical_bytes(runtime),
        })

        actual = build_from_files(
            files,
            expected_run_id=FILE_RUN_ID,
            expected_revision=REVISION,
        )

        expert_issue = next(
            item
            for item in actual["structured_output"]["issues"]
            if item["issue_id"] == expert_finding["case_id"]
        )
        self.assertEqual(
            "expert_review_required", expert_issue["_finding_disposition"]
        )
        packet = actual["structured_output"]["expert_review_packets"][0]
        self.assertEqual("expert_packet_accounting_review", packet["expert_packet_id"])
        self.assertEqual(
            "Do not conclude statutory compliance.",
            packet["_decision_boundary"],
        )


if __name__ == "__main__":
    unittest.main()
