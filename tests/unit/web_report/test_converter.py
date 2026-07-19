from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent import cli
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.evidence.core import assemble_evidence_core
from trusted_ceo_agent.evidence.facts import build_observed_fact
from trusted_ceo_agent.evidence.links import build_evidence_link
from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError, IntegrityError
from trusted_ceo_agent.grading.grader import grade
from trusted_ceo_agent.intake.adapters.csv import CsvAdapter
from trusted_ceo_agent.outputs.final_result import build_final_result
from trusted_ceo_agent.outputs.render import render_package
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from trusted_ceo_agent.web_report.contracts import load_bundle_bytes
from trusted_ceo_agent.web_report.converter import convert_final_revision


ROOT = Path(__file__).resolve().parents[3]
RUN_ID = "run_20260717T010203Z_0123456789abcdef"
SHA = "a" * 64


def _policy() -> dict:
    body = {
        "schema_version": "1.0.0",
        "policy_id": "local-owner",
        "policy_version": "1.0.0",
        "transport_principal": "tester",
        "authorized_actors": [{
            "actor_id": "ceo-1",
            "roles": ["run_owner"],
            "allowed_gates": [
                "context",
                "data",
                "scope_narrowing",
                "diagnostic",
                "final",
            ],
        }],
        "restricted_source_allowlist": [],
        "privacy_policy": {
            "direct_identifier_reasoning": "forbidden",
            "minimum_group_size": 5,
        },
    }
    return {
        **body,
        "policy_hash": hashlib.sha256(canonical_bytes(body)).hexdigest(),
    }


def _approval() -> dict:
    body = {
        "approval_id": "approval_final",
        "approval_request_id": "approval_request_final",
        "gate": "final",
        "base_artifact_ref": "final/structured-output.json",
        "result_artifact_ref": "final/structured-output.json@r0001",
        "decision": "approve",
        "confirmed": True,
        "actor_id": "ceo-1",
        "actor_role": "ceo",
        "target_refs": [],
        "authorized_component_ids": [],
        "patch_operations": [],
        "rationale": "interactive approval",
        "created_at": "2026-07-17T01:02:03Z",
        "input_method": "interactive_tty",
        "nonce_hash": "b" * 64,
        "tty_session_fingerprint": "b" * 64,
        "supersedes_approval_id": None,
        "status": "current",
    }
    return {
        **body,
        "approval_hash": hashlib.sha256(canonical_bytes(body)).hexdigest(),
    }


def _approval_summary(approval: dict) -> dict:
    return {
        "gate": approval["gate"],
        "status": approval["status"],
        "input_method": approval["input_method"],
        "fixture_only": False,
        "approval_id": approval["approval_id"],
        "actor_role": approval["actor_role"],
        "result_artifact_ref": approval["result_artifact_ref"],
    }


def _grading_input(issue_id: str, evidence_link_id: str) -> dict:
    return {
        "issue_id": issue_id,
        "assessability": "assessable",
        "not_assessable_reason_codes": [],
        "evidence_state": "sufficient",
        "impact_band": "high",
        "urgency_band": "near_term",
        "mission_priority_match": False,
        "executive_materiality": True,
        "decision_needed": True,
        "expert_trigger_state": "none",
        "pack_authority": "full",
        "diagnostic_disposition": "accepted",
        "verification_authorized": False,
        "issue_disposition": "standalone",
        "trackable": True,
        "response_eligibility": "eligible",
        "provenance_refs": [evidence_link_id],
    }


def _build_finalized_run(
    root: Path,
    *,
    state: str = "finalized",
    dangling_evidence: bool = False,
) -> tuple[ArtifactStore, str]:
    artifacts = root / "artifacts"
    source_path = root / "ledger.csv"
    source_path.write_text("revenue\n100\n", encoding="utf-8")
    source_payload = source_path.read_bytes()
    source_sha = hashlib.sha256(source_payload).hexdigest()
    source_id = "source_" + source_sha[:24]
    dataset = CsvAdapter().parse(source_path, source_id)
    source_ref = dataset.source_reference(
        dataset.records[0],
        ["revenue"],
        "observe",
        f"lineage/sets/{SHA}.json",
        observation_role="ledger",
    )
    source = {
        "source_id": source_id,
        "source_type": "uploaded_file",
        "access_policy": "permitted",
        "evidence_usage": "primary",
        "observation_roles": ["ledger"],
        "display_name": "매출 원장",
        "media_type": "text/csv",
        "sha256": source_sha,
        "size_bytes": len(source_payload),
        "received_at": "2026-07-17T01:02:03Z",
        "snapshot_ref": f"sources/blobs/{source_sha}",
        "original_path_token": "path_" + "c" * 24,
        "aliases": [],
        "metadata": {"extension": ".csv"},
    }
    fact = build_observed_fact(
        fact_code="revenue.observed",
        metric_code="revenue",
        semantic_role="observation",
        observation_role="ledger",
        scope=[{"dimension_code": "company", "member_code": "all"}],
        time_context={"period": "2026-06"},
        value={
            "value_type": "decimal",
            "canonical_value": "100",
            "unit_code": "currency",
            "currency_code": "KRW",
            "scale": "1",
        },
        source_refs=[source_ref],
    )
    issue_id = "issue_main"
    link = build_evidence_link(
        target_ref=issue_id,
        target_type="integrated_issue",
        evidence_ref=fact["fact_id"],
        evidence_kind="fact",
        evidence_outcome=None,
        polarity="supports",
        role="observation",
        rationale_template="검증된 원장 관찰값입니다.",
        value_refs=[{
            "token": "revenue",
            "fact_or_signal_id": fact["fact_id"],
            "display_field": "value.canonical_value",
            "display_format_ref": "currency",
        }],
        stage="final",
        materialized_by="runtime_grader",
        origin={
            "origin_type": "deterministic_rule",
            "origin_job_id": None,
            "model_profile": None,
            "prompt_hash": None,
            "proposal_hash": "d" * 64,
        },
        independence_group_id="independence_" + "5" * 24,
    )
    core = assemble_evidence_core(
        envelope={
            "schema_version": "1.0.0",
            "artifact_id": "artifact_" + "e" * 24,
            "run_id": RUN_ID,
            "revision": 1,
            "parent_artifact_hash": None,
            "stage": "finalization_jobs_ready",
            "created_at": "2026-07-17T01:02:03Z",
            "semantic_fingerprint": "f" * 64,
            "artifact_hash": "1" * 64,
        },
        mission_contract_ref="mission_" + "2" * 24,
        pack_manifest={"pack_manifest_hash": "3" * 64, "pack_refs": []},
        component_manifest={"component_refs": []},
        source_registry=[source],
        data_quality_register=[],
        fact_register=[fact],
        signal_register=[],
        evidence_links=[link],
        capability_map={
            "capability_map_id": "capability_map_" + "4" * 24,
            "capabilities": [],
        },
    )
    grading_input = _grading_input(issue_id, link["evidence_link_id"])
    grade_record = grade(grading_input)
    approval = _approval()
    result = build_final_result(
        run_summary={"run_id": RUN_ID, "revision": 2},
        mission_summary={"objective": "검증된 핵심 문제를 확인합니다."},
        capability_summary={"status": "evaluated"},
        issues=[{
            "issue_id": issue_id,
            "title_template": "매출 검토 필요",
            "primary_grade": grade_record["primary_grade"],
            "secondary_flags": grade_record["secondary_flags"],
            "why_it_matters_template": "검증된 관찰값을 경영진이 검토해야 합니다.",
            "value_refs": [fact["fact_id"]],
            "evidence_link_ids": [link["evidence_link_id"]],
            "cause_hypotheses": [{"claim_code": "cause_main"}],
            "counter_hypotheses": [],
            "unresolved_conflicts": [],
            "verification_next_steps": [],
            "conditional_response_refs": [],
            "expert_review_refs": [],
            "disposition": "accepted",
        }],
        evidence_links={link["evidence_link_id"]: link},
        approvals=[_approval_summary(approval)],
    )
    if dangling_evidence:
        result["issues"][0]["evidence_link_ids"] = ["evidence_missing"]
        semantic_body = {
            key: value for key, value in result.items() if key != "integrity"
        }
        result["integrity"]["semantic_fingerprint"] = hashlib.sha256(
            canonical_bytes(semantic_body)
        ).hexdigest()
    files = {
        "workflow/state.json": canonical_bytes({
            "run_id": RUN_ID,
            "revision": 1,
            "state": "delivery_approved",
        }),
        "workflow/human-response-policy.json": canonical_bytes(_policy()),
        "evidence/core.json": canonical_bytes(core),
        "final/structured-output.json": canonical_bytes({
            "issues": [{"issue_id": issue_id, "local_key": "issue_local"}],
            "expert_review_packets": [],
        }),
        "grading/inputs.json": canonical_bytes([grading_input]),
        f"grading/records/{grade_record['grade_record_id']}.json": canonical_bytes(
            grade_record
        ),
        f"approvals/records/{approval['approval_id']}.json": canonical_bytes(approval),
        f"sources/blobs/{source_sha}": source_payload,
        "audit/events/r0001-approve-interactive.json": canonical_bytes({
            "command": "approve-interactive",
            "gate": "final",
            "timestamp": "2026-07-17T01:02:03Z",
        }),
    }
    store = ArtifactStore(artifacts)
    store.create_run(RUN_ID)
    store.publish(0, files)
    files.update(render_package(result))
    files["workflow/state.json"] = canonical_bytes({
        "run_id": RUN_ID,
        "revision": 2,
        "state": state,
    })
    files["audit/events/r0002-finalize.json"] = canonical_bytes({
        "command": "finalize",
        "from_revision": 1,
        "to_revision": 2,
        "timestamp": "2026-07-17T01:02:04Z",
    })
    store.publish(1, files)
    result_hash = hashlib.sha256(files["final/result.json"]).hexdigest()
    return store, result_hash


class FinalResultConverterTests(unittest.TestCase):
    def test_input_manifest_is_closed_and_pins_one_final_result(self) -> None:
        manifest = {
            "schema_version": "1.0.0",
            "run_id": RUN_ID,
            "revision": 2,
            "files": [{"path": "final/result.json", "sha256": SHA}],
        }
        SchemaStore().validate("web-report-input-manifest.schema.json", manifest)

        unknown = dict(manifest)
        unknown["unexpected"] = True
        with self.assertRaises(ContractError):
            SchemaStore().validate("web-report-input-manifest.schema.json", unknown)

        wrong_path = dict(manifest)
        wrong_path["files"] = [{"path": "other.json", "sha256": SHA}]
        with self.assertRaises(ContractError):
            SchemaStore().validate("web-report-input-manifest.schema.json", wrong_path)

    def test_export_is_valid_byte_equivalent_and_does_not_infer_conclusions(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            store, result_hash = _build_finalized_run(Path(directory))
            before_state = (store.run_dir / "state.json").read_bytes()
            before_snapshot = (
                store.verify_revision(2) / "snapshot-manifest.json"
            ).read_bytes()

            first = convert_final_revision(
                store,
                run_id=RUN_ID,
                revision=2,
                expected_final_result_hash=result_hash,
            )
            second = convert_final_revision(
                store,
                run_id=RUN_ID,
                revision=2,
                expected_final_result_hash=result_hash,
            )

            self.assertEqual(first, second)
            bundle = load_bundle_bytes(first)
            result = json.loads(
                (store.verify_revision(2) / "final/result.json").read_text("utf-8")
            )
            self.assertEqual(result["issues"], bundle["final_result"]["issues"])
            self.assertEqual(
                result["cross_issue_relations"],
                bundle["final_result"]["cross_issue_relations"],
            )
            self.assertEqual(
                result["issues"][0]["primary_grade"],
                bundle["final_result"]["issues"][0]["primary_grade"],
            )
            self.assertEqual(
                result["issues"][0]["evidence_link_ids"],
                bundle["final_result"]["issues"][0]["evidence_link_ids"],
            )
            self.assertEqual("trusted_final", bundle["viewer_eligibility_receipt"]["claimed_viewer_mode"])
            self.assertEqual(1, bundle["viewer_eligibility_receipt"]["approved_revision"])
            self.assertTrue(
                bundle["viewer_eligibility_receipt"]["result_artifact_ref"].endswith(
                    "@r0001"
                )
            )
            self.assertEqual(before_state, (store.run_dir / "state.json").read_bytes())
            self.assertEqual(
                before_snapshot,
                (store.verify_revision(2) / "snapshot-manifest.json").read_bytes(),
            )

    def test_hash_state_and_required_reference_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            store, result_hash = _build_finalized_run(Path(directory))
            with self.assertRaisesRegex(IntegrityError, "Final Result hash"):
                convert_final_revision(
                    store,
                    run_id=RUN_ID,
                    revision=2,
                    expected_final_result_hash="0" * 64,
                )

            invalid_root = Path(directory) / "invalid"
            invalid_root.mkdir()
            invalid_store, invalid_hash = _build_finalized_run(
                invalid_root,
                state="writer_ready",
            )
            with self.assertRaisesRegex(IntegrityError, "finalized"):
                convert_final_revision(
                    invalid_store,
                    run_id=RUN_ID,
                    revision=2,
                    expected_final_result_hash=invalid_hash,
                )

            dangling_root = Path(directory) / "dangling"
            dangling_root.mkdir()
            dangling_store, dangling_hash = _build_finalized_run(
                dangling_root,
                dangling_evidence=True,
            )
            with self.assertRaisesRegex(IntegrityError, "Evidence|evidence"):
                convert_final_revision(
                    dangling_store,
                    run_id=RUN_ID,
                    revision=2,
                    expected_final_result_hash=dangling_hash,
                )

    def test_cli_exports_to_workspace_without_mutating_snapshot(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            store, result_hash = _build_finalized_run(root)
            output = root / "web-report-bundle.json"
            state_before = (store.run_dir / "state.json").read_bytes()
            input_manifest = root / "web-report-input-manifest.json"
            input_manifest.write_bytes(canonical_bytes({
                "schema_version": "1.0.0",
                "run_id": RUN_ID,
                "revision": 2,
                "files": [{
                    "path": "final/result.json",
                    "sha256": result_hash,
                }],
            }))
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main([
                    "export-web-report",
                    "--artifact-root",
                    str(root / "artifacts"),
                    "--run-id",
                    RUN_ID,
                    "--revision",
                    "2",
                    "--output",
                    str(output),
                    "--input-manifest",
                    str(input_manifest),
                ])

            self.assertEqual(0, code, stdout.getvalue())
            response = json.loads(stdout.getvalue())
            self.assertEqual("export-web-report", response["command"])
            self.assertEqual(2, response["revision"])
            load_bundle_bytes(output.read_bytes())
            self.assertEqual(state_before, (store.run_dir / "state.json").read_bytes())

    def test_cli_rejects_manifest_identity_and_hash_mismatches_without_output(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            _build_finalized_run(root)
            cases = (
                (
                    "run",
                    "run_20260717T010203Z_ffffffffffffffff",
                    2,
                    SHA,
                    "run or revision mismatch",
                ),
                ("revision", RUN_ID, 1, SHA, "run or revision mismatch"),
                ("sha256", RUN_ID, 2, "0" * 64, "Final Result hash"),
            )
            for name, manifest_run_id, revision, sha256, message in cases:
                with self.subTest(name=name):
                    output = root / f"{name}-web-report-bundle.json"
                    input_manifest = root / f"{name}-input-manifest.json"
                    input_manifest.write_bytes(canonical_bytes({
                        "schema_version": "1.0.0",
                        "run_id": manifest_run_id,
                        "revision": revision,
                        "files": [{
                            "path": "final/result.json",
                            "sha256": sha256,
                        }],
                    }))
                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        code = cli.main([
                            "export-web-report",
                            "--artifact-root",
                            str(root / "artifacts"),
                            "--run-id",
                            RUN_ID,
                            "--revision",
                            "2",
                            "--output",
                            str(output),
                            "--input-manifest",
                            str(input_manifest),
                        ])

                    response = json.loads(stdout.getvalue())
                    self.assertEqual(cli.EXIT_INTEGRITY, code)
                    self.assertFalse(response["ok"])
                    self.assertEqual(cli.EXIT_INTEGRITY, response["code"])
                    self.assertRegex(response["message"], message)
                    self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
