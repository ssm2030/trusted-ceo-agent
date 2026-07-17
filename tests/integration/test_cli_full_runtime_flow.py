from __future__ import annotations

import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from trusted_ceo_agent import cli
from trusted_ceo_agent.canonical import canonical_bytes, strict_loads
from trusted_ceo_agent.packs.runtime_index import RuntimePackIndex
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from tests.support import confirmed_mission


ROOT = Path(__file__).resolve().parents[2]


class TTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def _call(arguments: list[str], input_text: str = "") -> tuple[int, dict[str, Any]]:
    old_in, old_out, old_err = cli.sys.stdin, cli.sys.stdout, cli.sys.stderr
    stdin, stdout, stderr = TTY(input_text), TTY(), TTY()
    try:
        cli.sys.stdin, cli.sys.stdout, cli.sys.stderr = stdin, stdout, stderr
        code = cli.main(arguments)
        payload = json.loads(stdout.getvalue())
        if stderr.getvalue():
            payload["_stderr"] = stderr.getvalue()
        return code, payload
    finally:
        cli.sys.stdin, cli.sys.stdout, cli.sys.stderr = old_in, old_out, old_err


def _snapshot_files(store: ArtifactStore, revision: int) -> dict[str, bytes]:
    snapshot = store.verify_revision(revision)
    manifest = json.loads((snapshot / "snapshot-manifest.json").read_text("utf-8"))
    return {
        item["path"]: (snapshot / item["path"]).read_bytes()
        for item in manifest["files"]
    }


def _pointer_segment(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _mission_with_enterprise_decision_unit() -> dict[str, Any]:
    mission = copy.deepcopy(confirmed_mission())
    mission["decision_units"] = [{
        "decision_unit_ref": "unit_enterprise",
        "unit_type": "enterprise",
        "scope_key": "enterprise",
        "owner_role": "ceo",
        "deadline": None,
    }]
    body = copy.deepcopy(mission)
    body.pop("confirmation")
    mission["confirmation"]["contract_hash"] = hashlib.sha256(
        canonical_bytes(body)
    ).hexdigest()
    return mission


def _lens_draft(job: dict[str, Any], evidence_ref: str) -> dict[str, Any]:
    family_ref = (
        "profitability_erosion"
        if "profitability_erosion" in job["allowed_problem_family_refs"]
        else job["allowed_problem_family_refs"][0]
    )
    required_signals = list(job["required_signal_ids"])
    return {
        "assessment_status": "partial",
        "status_reason_codes": ["counter_hypothesis_pending"],
        "observations": [{
            "local_key": "observation_margin_movement",
            "statement_template": "Gross margin movement is present in the approved evidence.",
            "value_refs": [],
            "fact_ids": [evidence_ref],
            "signal_ids": required_signals,
        }],
        "business_meanings": [{
            "local_key": "meaning_profitability_pressure",
            "statement_template": "The observed movement may affect enterprise profitability.",
            "value_refs": [],
            "evidence_proposals": [{
                "evidence_ref": evidence_ref,
                "polarity": "supports",
                "role": "observation",
            }],
            "observation_local_keys": ["observation_margin_movement"],
        }],
        "problem_candidates": [{
            "local_key": "problem_profitability_erosion",
            "business_meaning_local_keys": ["meaning_profitability_pressure"],
            "problem_family_ref": family_ref,
            "statement_template": "Profitability erosion warrants bounded verification.",
            "value_refs": [],
            "evidence_proposals": [{
                "evidence_ref": evidence_ref,
                "polarity": "supports",
                "role": "observation",
            }],
        }],
        "cause_hypotheses": [],
        "counter_hypotheses": [],
        "challenge_reviews": [],
        "verification_tests": [],
        "signal_dispositions": [{
            "signal_id": signal_id,
            "disposition": "used_support",
            "target_local_keys": ["problem_profitability_erosion"],
            "duplicate_of_signal_id": None,
            "context_evidence_ids": [],
            "rationale_template": "The deterministic signal supports bounded review.",
        } for signal_id in required_signals],
        "uncertainties": [],
        "data_requests": [],
        "human_questions": [],
        "expert_trigger_candidates": [],
        "limitations": [{
            "local_key": "limitation_cause_unverified",
            "statement_template": "A leading cause has not yet been independently verified.",
        }],
    }


class CliFullRuntimeFlowTests(unittest.TestCase):
    def test_real_pack_scan_reasoning_hitl_and_final_package(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            mission_path = root / "mission.json"
            source_path = root / "monthly.json"
            artifacts = root / "artifacts"
            mission_path.write_bytes(canonical_bytes(_mission_with_enterprise_decision_unit()))
            source_path.write_text(json.dumps([
                {"period": "2026-01", "gross_margin": "0.42"},
                {"period": "2026-02", "gross_margin": "0.39"},
                {"period": "2026-03", "gross_margin": "0.36"},
            ]), "utf-8")

            code, started = _call([
                "start", "--artifact-root", str(artifacts),
                "--mission-contract", str(mission_path), "--input", str(source_path),
            ])
            self.assertEqual(0, code, started)
            run_id = started["run_id"]
            revision = started["revision"]
            common = ["--artifact-root", str(artifacts), "--run-id", run_id]
            store = ArtifactStore(artifacts)
            store.open_run(run_id)

            code, scanned = _call([
                "scan", *common, "--expected-revision", str(revision),
            ])
            self.assertEqual(2, code, scanned)
            self.assertEqual("schema_mapping_job_ready", scanned["state"])
            revision = scanned["revision"]

            code, prepared_mapping = _call([
                "prepare-jobs", *common, "--stage", "schema_mapping",
                "--expected-revision", str(revision),
            ])
            self.assertEqual(0, code, prepared_mapping)
            revision = prepared_mapping["revision"]
            self.assertEqual(1, len(prepared_mapping["data"]["job_ids"]))
            mapping_job_id = prepared_mapping["data"]["job_ids"][0]
            files = _snapshot_files(store, revision)
            proposal = strict_loads(files["intake/canonical-mapping-proposal.json"])
            mapping_draft = root / "schema-mapping.json"
            mapping_draft.write_bytes(canonical_bytes(proposal))

            code, ingested_mapping = _call([
                "ingest-result", *common, "--job-id", mapping_job_id,
                "--draft", str(mapping_draft), "--expected-revision", str(revision),
            ])
            self.assertEqual(0, code, ingested_mapping)
            revision = ingested_mapping["revision"]
            code, reduced_mapping = _call([
                "reduce-stage", *common, "--stage", "schema_mapping",
                "--expected-revision", str(revision),
            ])
            self.assertEqual(0, code, reduced_mapping)
            self.assertEqual("mapping_proposal_ready", reduced_mapping["state"])
            revision = reduced_mapping["revision"]

            files = _snapshot_files(store, revision)
            source = strict_loads(files["sources/registry.json"])[0]
            operations: list[dict[str, Any]] = [{
                "op": "add",
                "path": f"/mapping/sources/{_pointer_segment(source['source_id'])}/included",
                "value": True,
            }]
            for question in proposal["mappings"]:
                self.assertTrue(question["candidate_mappings"], question)
                candidate = question["candidate_mappings"][0]
                question_ref = _pointer_segment(question["mapping_question_ref"])
                for field in (
                    "observation_role", "unit_code", "scale", "time_role", "dimension_code",
                ):
                    operations.append({
                        "op": "add",
                        "path": f"/mapping/columns/{question_ref}/{field}",
                        "value": candidate[field],
                    })
            data_overlay = root / "data-overlay.json"
            data_overlay.write_bytes(canonical_bytes({"patch_operations": operations}))
            code, data_request = _call([
                "approval-request", *common, "--gate", "data",
                "--overlay", str(data_overlay), "--expected-revision", str(revision),
            ])
            self.assertEqual(2, code, data_request)
            revision = data_request["revision"]
            data_input = (
                f"data-owner-1\ndata_owner\n{data_request['data']['nonce']}\nAPPROVE\n"
            )
            code, data_approved = _call([
                "approve-interactive", *common,
                "--request-id", data_request["data"]["approval_request_id"],
                "--expected-revision", str(revision),
            ], data_input)
            self.assertEqual(0, code, data_approved)
            self.assertEqual("evidence_ready", data_approved["state"])
            revision = data_approved["revision"]

            files = _snapshot_files(store, revision)
            pack_index = RuntimePackIndex.from_files(files)
            self.assertEqual("b2b-services", pack_index.domain_pack["pack_id"])
            selection = strict_loads(files["packs/selection.json"])
            core = strict_loads(files["evidence/core.json"])
            self.assertIn(
                "profitability-erosion@1.0.0", selection["selected_problem_refs"],
                {"selection": selection, "capability_map": core["capability_map"]},
            )
            margin_change = next(
                fact for fact in core["fact_register"]
                if fact["fact_code"] == "gross_margin_change_pp"
            )
            evidence_ref = margin_change["fact_id"]

            code, prepared_lens = _call([
                "prepare-jobs", *common, "--stage", "lens",
                "--expected-revision", str(revision),
            ])
            self.assertEqual(0, code, prepared_lens)
            self.assertEqual("lens_jobs_ready", prepared_lens["state"])
            revision = prepared_lens["revision"]
            lens_job_ids = prepared_lens["data"]["job_ids"]
            self.assertEqual(2, len(lens_job_ids))
            for index, job_id in enumerate(lens_job_ids):
                files = _snapshot_files(store, revision)
                job = strict_loads(files[f"tasks/{job_id}/job.json"])
                self.assertIn(evidence_ref, job["allowed_fact_ids"])
                lens_path = root / f"lens-{index}.json"
                lens_path.write_bytes(canonical_bytes(_lens_draft(job, evidence_ref)))
                code, ingested_lens = _call([
                    "ingest-result", *common, "--job-id", job_id,
                    "--draft", str(lens_path), "--expected-revision", str(revision),
                ])
                self.assertEqual(0, code, ingested_lens)
                revision = ingested_lens["revision"]

            code, reduced_lens = _call([
                "reduce-stage", *common, "--stage", "lens",
                "--expected-revision", str(revision),
            ])
            self.assertEqual(0, code, reduced_lens)
            self.assertEqual("lens_ready", reduced_lens["state"])
            revision = reduced_lens["revision"]

            code, prepared_integrated = _call([
                "prepare-jobs", *common, "--stage", "integrated",
                "--expected-revision", str(revision),
            ])
            self.assertEqual(0, code, prepared_integrated)
            revision = prepared_integrated["revision"]
            integrated_job_id = prepared_integrated["data"]["job_ids"][0]
            files = _snapshot_files(store, revision)
            integrated_job = strict_loads(files[f"tasks/{integrated_job_id}/job.json"])
            joined = strict_loads(files["reasoning/join-result.json"])
            problem_claims = sorted(
                item["claim_id"]
                for path, payload in files.items()
                if path.startswith("tasks/") and path.endswith("/card.json")
                for item in strict_loads(payload)["normalized_payload"]["problem_candidates"]
            )
            family_ref = (
                "profitability_erosion"
                if "profitability_erosion" in integrated_job["allowed_problem_family_refs"]
                else integrated_job["allowed_problem_family_refs"][0]
            )
            issue_payload = {
                "problem_family_ref": family_ref,
                "scope_key": "enterprise",
                "decision_unit_ref": "unit_enterprise",
                "source_candidate_ids": [problem_claims[0]],
                "observation_claim_refs": [],
                "cause_hypothesis_refs": [],
                "counter_hypothesis_refs": [],
                "unresolved_conflict_refs": [],
                "impact_evidence_refs": [evidence_ref],
                "urgency_evidence_refs": [],
                "counter_evidence_refs": [],
                "decision_need_proposal": {
                    "decision_type_ref": "portfolio_action",
                    "decision_unit_ref": "unit_enterprise",
                    "basis_claim_refs": [problem_claims[0]],
                    "rationale_template": "The accepted issue may require a portfolio decision.",
                },
                "verification_requirement_refs": ["bridge_mix_and_delivery"],
                "response_type_refs": [],
                "expert_trigger_refs": [],
            }
            integrated_draft = {
                "join_manifest_ref": integrated_job["join_manifest_ref"],
                "card_refs": joined["card_refs"],
                "issue_clusters": [],
                "integrated_issues": [{
                    "local_key": "issue_profitability",
                    "payload": issue_payload,
                }],
                "causal_relation_hypotheses": [],
                "cross_issue_conflicts": [],
                "blind_spots": [],
                "response_type_candidates": [],
                "expert_review_candidates": [],
            }
            integrated_path = root / "integrated.json"
            integrated_path.write_bytes(canonical_bytes(integrated_draft))
            code, ingested_integrated = _call([
                "ingest-result", *common, "--job-id", integrated_job_id,
                "--draft", str(integrated_path), "--expected-revision", str(revision),
            ])
            self.assertEqual(0, code, ingested_integrated)
            revision = ingested_integrated["revision"]
            code, reduced_integrated = _call([
                "reduce-stage", *common, "--stage", "integrated",
                "--expected-revision", str(revision),
            ])
            self.assertEqual(0, code, reduced_integrated)
            self.assertEqual("integrated_draft", reduced_integrated["state"])
            revision = reduced_integrated["revision"]

            diagnostic_overlay = root / "diagnostic-overlay.json"
            diagnostic_overlay.write_bytes(canonical_bytes({"patch_operations": [
                {"op": "add", "path": "/issue_dispositions/issue_profitability", "value": "accepted"},
                {"op": "add", "path": "/decision_dispositions/issue_profitability", "value": "needed"},
                {"op": "add", "path": "/verification_authorizations/issue_profitability", "value": False},
                {"op": "add", "path": "/deep_dive_scope/component_ids", "value": []},
                {"op": "add", "path": "/deep_dive_scope/issue_ids", "value": []},
            ]}))
            code, diagnostic_request = _call([
                "approval-request", *common, "--gate", "diagnostic",
                "--overlay", str(diagnostic_overlay), "--expected-revision", str(revision),
            ])
            self.assertEqual(2, code, diagnostic_request)
            revision = diagnostic_request["revision"]
            diagnostic_input = (
                f"ceo-1\nceo\n{diagnostic_request['data']['nonce']}\nAPPROVE\n"
            )
            code, diagnostic_approved = _call([
                "approve-interactive", *common,
                "--request-id", diagnostic_request["data"]["approval_request_id"],
                "--expected-revision", str(revision),
            ], diagnostic_input)
            self.assertEqual(0, code, diagnostic_approved)
            self.assertEqual("finalization_jobs_ready", diagnostic_approved["state"])
            revision = diagnostic_approved["revision"]

            code, prepared_finalization = _call([
                "prepare-finalization", *common, "--expected-revision", str(revision),
            ])
            self.assertEqual(0, code, prepared_finalization)
            self.assertEqual(1, len(prepared_finalization["data"]["grade_record_ids"]))
            self.assertEqual(1, prepared_finalization["data"]["active_issue_count"])
            revision = prepared_finalization["revision"]

            code, prepared_writer = _call([
                "prepare-jobs", *common, "--stage", "writer",
                "--expected-revision", str(revision),
            ])
            self.assertEqual(0, code, prepared_writer)
            revision = prepared_writer["revision"]
            writer_job_id = prepared_writer["data"]["job_ids"][0]
            files = _snapshot_files(store, revision)
            writer_job = strict_loads(files[f"tasks/{writer_job_id}/job.json"])
            self.assertEqual(1, len(writer_job["allowed_claim_ids"]))
            writer_path = root / "writer.json"
            writer_path.write_bytes(canonical_bytes({
                "structured_output_ref": "final/structured-output.json",
                "claim_templates": [{
                    "claim_id": writer_job["allowed_claim_ids"][0],
                    "template": "The approved evidence supports a bounded executive review.",
                }],
                "expert_packet_templates": [],
                "ceo_brief_section_order": [],
            }))
            code, ingested_writer = _call([
                "ingest-result", *common, "--job-id", writer_job_id,
                "--draft", str(writer_path), "--expected-revision", str(revision),
            ])
            self.assertEqual(0, code, ingested_writer)
            revision = ingested_writer["revision"]
            code, reduced_writer = _call([
                "reduce-stage", *common, "--stage", "writer",
                "--expected-revision", str(revision),
            ])
            self.assertEqual(0, code, reduced_writer)
            self.assertEqual("writer_ready", reduced_writer["state"])
            revision = reduced_writer["revision"]

            final_overlay = root / "final-overlay.json"
            final_overlay.write_bytes(canonical_bytes({"patch_operations": [{
                "op": "add", "path": "/delivery_scope/package", "value": "ceo_brief",
            }]}))
            code, final_request = _call([
                "approval-request", *common, "--gate", "final",
                "--overlay", str(final_overlay), "--expected-revision", str(revision),
            ])
            self.assertEqual(2, code, final_request)
            revision = final_request["revision"]
            final_input = f"ceo-1\nceo\n{final_request['data']['nonce']}\nAPPROVE\n"
            code, final_approved = _call([
                "approve-interactive", *common,
                "--request-id", final_request["data"]["approval_request_id"],
                "--expected-revision", str(revision),
            ], final_input)
            self.assertEqual(0, code, final_approved)
            self.assertEqual("delivery_approved", final_approved["state"])
            revision = final_approved["revision"]

            code, finalized = _call([
                "finalize", *common, "--expected-revision", str(revision),
            ])
            self.assertEqual(0, code, finalized)
            self.assertEqual("finalized", finalized["state"])
            revision = finalized["revision"]
            files = _snapshot_files(store, revision)
            self.assertIn("final/result.json", files)
            self.assertIn("final/ceo-brief.md", files)
            self.assertIn("final/audit-manifest.json", files)

            code, validated = _call(["validate", *common, "--revision", str(revision)])
            self.assertEqual(0, code, validated)
            self.assertIn("component_run_recomputation", validated["data"]["checks"])
            self.assertIn("grade_recomputation", validated["data"]["checks"])
            self.assertIn("final_package", validated["data"]["checks"])
            code, rendered = _call(["render", *common, "--revision", str(revision)])
            self.assertEqual(0, code, rendered)
            self.assertIn("final/ceo-brief.md", rendered["data"]["files"])


if __name__ == "__main__":
    unittest.main()
