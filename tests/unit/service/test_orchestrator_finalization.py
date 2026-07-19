from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent.application.models import CreateRunRequest
from trusted_ceo_agent.application.run_application import TrustedCeoApplication
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.service.contracts import HitlDecisionRequest, MutationBase
from trusted_ceo_agent.service.orchestrator import AnalysisOrchestrator
from trusted_ceo_agent.service.run_store import RunStore
from trusted_ceo_agent.service.testing.fake_openai import KeylessFakeReasoningGateway
from tests.support import confirmed_mission


ROOT = Path(__file__).resolve().parents[3]
FINGERPRINT = "c" * 64


def _executive_mission() -> dict:
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


class OrchestratorFinalizationTests(unittest.TestCase):
    def test_keyless_fake_ai_reaches_two_hitl_gates_and_verified_report(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            source = root / "monthly.json"
            source.write_text(json.dumps([
                {"period": "2026-01", "gross_margin": "0.42"},
                {"period": "2026-02", "gross_margin": "0.39"},
                {"period": "2026-03", "gross_margin": "0.36"},
            ]), "utf-8")
            run_store = RunStore(root / "runtime")
            application = TrustedCeoApplication(run_store.runs_root)
            gateway = KeylessFakeReasoningGateway(application.artifact_root)
            orchestrator = AnalysisOrchestrator(
                application,
                run_store,
                gateway,
                report_root=root / "reports",
            )
            run_id = "run_20260719T010000Z_0123456789abcdef"
            application.create_run(CreateRunRequest(
                mission=_executive_mission(),
                inputs=(source,),
                run_owner_actor_id="local-browser-user",
                run_id=run_id,
            ))
            sequence = 0

            def advance():
                nonlocal sequence
                sequence += 1
                current = orchestrator.snapshot(run_id)
                return orchestrator.continue_run(
                    run_id,
                    MutationBase(
                        expected_revision=current.revision,
                        idempotency_key=f"advance_final_{sequence:04d}",
                    ),
                )

            self.assertEqual("schema_mapping_job_ready", advance().workflow_status)
            self.assertEqual("schema_mapping_job_ready", advance().workflow_status)
            self.assertEqual("schema_mapping_job_ready", advance().workflow_status)
            self.assertEqual("mapping_proposal_ready", advance().workflow_status)
            data_card = advance()
            self.assertEqual("data_confirmation_required", data_card.workflow_status)
            after_data = orchestrator.submit_hitl(
                run_id,
                HitlDecisionRequest(
                    expected_revision=data_card.revision,
                    idempotency_key="approve_final_data_0001",
                    decision="approve",
                ),
                browser_session_fingerprint=FINGERPRINT,
            )
            self.assertEqual("evidence_ready", after_data.workflow_status)

            self.assertEqual("lens_jobs_ready", advance().workflow_status)
            self.assertEqual("lens_jobs_ready", advance().workflow_status)
            self.assertEqual("lens_ready", advance().workflow_status)
            self.assertEqual("lens_ready", advance().workflow_status)
            self.assertEqual("lens_ready", advance().workflow_status)
            self.assertEqual("integrated_draft", advance().workflow_status)
            diagnostic = advance()
            self.assertEqual("diagnostic_approval_required", diagnostic.workflow_status)
            self.assertEqual("diagnostic_final", diagnostic.hitl_card.hitl_kind)
            self.assertEqual("human_response", diagnostic.pending_action)
            diagnostic_request_id = diagnostic.hitl_card.request_id

            after_diagnostic = orchestrator.submit_hitl(
                run_id,
                HitlDecisionRequest(
                    expected_revision=diagnostic.revision,
                    idempotency_key="approve_diagnostic_0001",
                    decision="approve_with_edits",
                    edits={
                        "deep_dive_scope": {
                            "component_ids": [],
                            "issue_ids": [],
                        },
                    },
                ),
                browser_session_fingerprint=FINGERPRINT,
            )
            self.assertEqual("finalization_jobs_ready", after_diagnostic.workflow_status)
            self.assertEqual("finalization_jobs_ready", advance().workflow_status)
            self.assertEqual("finalization_jobs_ready", advance().workflow_status)
            self.assertEqual("finalization_jobs_ready", advance().workflow_status)
            self.assertEqual("writer_ready", advance().workflow_status)
            final_card = advance()
            self.assertEqual("final_approval_required", final_card.workflow_status)
            self.assertEqual("diagnostic_final", final_card.hitl_card.hitl_kind)
            self.assertNotEqual(diagnostic_request_id, final_card.hitl_card.request_id)

            delivery = orchestrator.submit_hitl(
                run_id,
                HitlDecisionRequest(
                    expected_revision=final_card.revision,
                    idempotency_key="approve_delivery_0001",
                    decision="approve_with_edits",
                    edits={"delivery_scope": {"package": "ceo_brief"}},
                ),
                browser_session_fingerprint=FINGERPRINT,
            )
            self.assertEqual("delivery_approved", delivery.workflow_status)
            finalized = advance()

            self.assertEqual("finalized", finalized.workflow_status)
            self.assertEqual("terminal", finalized.pending_action)
            self.assertIsNotNone(finalized.result_ref)
            manifest = run_store.read_manifest(run_id)
            self.assertEqual("finalized", manifest.status)
            self.assertRegex(manifest.bundle_hash or "", r"^[0-9a-f]{64}$")
            report = orchestrator.report(run_id)
            self.assertEqual(run_id, report["bundle"]["run"]["run_id"])
            self.assertEqual(finalized.revision, report["bundle"]["run"]["revision"])
            self.assertEqual(manifest.bundle_hash, report["bundle"]["bundle_hash"])
            self.assertGreaterEqual(len(gateway.calls), 5)
            self.assertEqual(
                {"schema_mapping", "lens", "integrated", "writer"},
                {call["stage"] for call in gateway.calls},
            )


if __name__ == "__main__":
    unittest.main()
