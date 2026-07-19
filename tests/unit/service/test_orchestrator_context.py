from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from trusted_ceo_agent.application.models import CreateRunRequest
from trusted_ceo_agent.application.run_application import TrustedCeoApplication
from trusted_ceo_agent.canonical import strict_loads
from trusted_ceo_agent.service.contracts import HitlDecisionRequest, MutationBase
from trusted_ceo_agent.service.orchestrator import AnalysisOrchestrator
from trusted_ceo_agent.service.run_store import RunStore
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from tests.support import confirmed_mission, mission_body


ROOT = Path(__file__).resolve().parents[3]
FINGERPRINT = "b" * 64


class FakeGateway:
    def __init__(self) -> None:
        self.result: dict[str, Any] | None = None
        self.calls: list[dict[str, Any]] = []

    def execute(self, job: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(dict(job))
        if self.result is None:
            raise AssertionError("fake gateway result was not configured")
        return self.result


def _files(application: TrustedCeoApplication, run_id: str, revision: int) -> dict[str, bytes]:
    store = ArtifactStore(application.artifact_root)
    store.open_run(run_id)
    snapshot = store.verify_revision(revision)
    manifest = json.loads((snapshot / "snapshot-manifest.json").read_text("utf-8"))
    return {
        item["path"]: (snapshot / item["path"]).read_bytes()
        for item in manifest["files"]
    }


class OrchestratorContextTests(unittest.TestCase):
    def _runtime(
        self,
        root: Path,
    ) -> tuple[TrustedCeoApplication, RunStore, FakeGateway, AnalysisOrchestrator]:
        run_store = RunStore(root / "runtime")
        application = TrustedCeoApplication(run_store.runs_root)
        gateway = FakeGateway()
        orchestrator = AnalysisOrchestrator(application, run_store, gateway)
        return application, run_store, gateway, orchestrator

    def test_context_card_keeps_nonce_private_and_web_approval_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            source = root / "monthly.json"
            source.write_text('[{"period":"2026-01","gross_margin":"0.40"}]', "utf-8")
            application, run_store, _, orchestrator = self._runtime(root)
            run_id = "run_context_service_01234567"
            application.create_run(CreateRunRequest(
                mission=mission_body(),
                inputs=(source,),
                run_owner_actor_id="local-browser-user",
                run_id=run_id,
            ))

            initial = orchestrator.snapshot(run_id)
            self.assertEqual("context_confirmation_required", initial.workflow_status)
            pending = orchestrator.continue_run(
                run_id,
                MutationBase(
                    expected_revision=1,
                    idempotency_key="continue_context_0001",
                ),
            )

            self.assertEqual(2, pending.revision)
            self.assertEqual("human_response", pending.pending_action)
            self.assertEqual("실시간 AI 분석", pending.display_badge)
            self.assertEqual("context_data", pending.hitl_card.hitl_kind)
            self.assertEqual(
                ["approve", "approve_with_edits", "stop"],
                pending.hitl_card.allowed_decisions,
            )
            self.assertEqual(
                {"mission", "source_summary", "risk"},
                {section.kind for section in pending.hitl_card.sections},
            )
            public_body = pending.model_dump_json()
            manifest = run_store.read_manifest(run_id)
            self.assertIsNotNone(manifest.pending_approval_nonce)
            self.assertNotIn(manifest.pending_approval_nonce or "", public_body)
            self.assertNotIn(str(root), public_body)

            decision = HitlDecisionRequest(
                expected_revision=2,
                idempotency_key="approve_context_0001",
                decision="approve",
            )
            approved = orchestrator.submit_hitl(
                run_id,
                decision,
                browser_session_fingerprint=FINGERPRINT,
            )
            replay = orchestrator.submit_hitl(
                run_id,
                decision,
                browser_session_fingerprint=FINGERPRINT,
            )

            self.assertEqual("context_ready", approved.workflow_status)
            self.assertEqual(3, approved.revision)
            self.assertEqual(approved, replay)
            self.assertIsNone(run_store.read_manifest(run_id).pending_approval_nonce)
            files = _files(application, run_id, 3)
            record = strict_loads(next(
                payload
                for path, payload in files.items()
                if path.startswith("approvals/records/")
            ))
            self.assertEqual("web_hitl", record["input_method"])
            self.assertEqual(FINGERPRINT, record["browser_session_fingerprint"])
            self.assertRegex(record["response_hash"], r"^[0-9a-f]{64}$")

    def test_schema_mapping_and_data_approval_reach_verified_evidence(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            source = root / "monthly.json"
            source.write_text(json.dumps([
                {"period": "2026-01", "gross_margin": "0.42"},
                {"period": "2026-02", "gross_margin": "0.39"},
                {"period": "2026-03", "gross_margin": "0.36"},
            ]), "utf-8")
            application, run_store, gateway, orchestrator = self._runtime(root)
            run_id = "run_20260719T000000Z_0123456789abcdef"
            application.create_run(CreateRunRequest(
                mission=confirmed_mission(),
                inputs=(source,),
                run_owner_actor_id="local-browser-user",
                run_id=run_id,
            ))

            scanned = orchestrator.continue_run(
                run_id,
                MutationBase(expected_revision=1, idempotency_key="continue_mapping_0001"),
            )
            self.assertEqual("schema_mapping_job_ready", scanned.workflow_status)
            prepared = orchestrator.continue_run(
                run_id,
                MutationBase(expected_revision=2, idempotency_key="continue_mapping_0002"),
            )
            self.assertEqual(3, prepared.revision)
            proposal = strict_loads(
                _files(application, run_id, prepared.revision)[
                    "intake/canonical-mapping-proposal.json"
                ]
            )
            gateway.result = proposal
            ingested = orchestrator.continue_run(
                run_id,
                MutationBase(expected_revision=3, idempotency_key="continue_mapping_0003"),
            )
            self.assertEqual(4, ingested.revision)
            reduced = orchestrator.continue_run(
                run_id,
                MutationBase(expected_revision=4, idempotency_key="continue_mapping_0004"),
            )
            self.assertEqual("mapping_proposal_ready", reduced.workflow_status)
            pending = orchestrator.continue_run(
                run_id,
                MutationBase(expected_revision=5, idempotency_key="continue_mapping_0005"),
            )

            self.assertEqual("data_confirmation_required", pending.workflow_status)
            self.assertEqual("human_response", pending.pending_action)
            self.assertEqual(
                {"mapping", "risk", "facts", "source_summary"},
                {section.kind for section in pending.hitl_card.sections},
            )
            self.assertEqual(
                ["approve", "approve_with_edits", "reanalyze", "stop"],
                pending.hitl_card.allowed_decisions,
            )
            self.assertNotIn(
                run_store.read_manifest(run_id).pending_approval_nonce or "",
                pending.model_dump_json(),
            )

            approved = orchestrator.submit_hitl(
                run_id,
                HitlDecisionRequest(
                    expected_revision=6,
                    idempotency_key="approve_mapping_0001",
                    decision="approve",
                ),
                browser_session_fingerprint=FINGERPRINT,
            )

            self.assertEqual("evidence_ready", approved.workflow_status)
            self.assertEqual(7, approved.revision)
            self.assertEqual(1, len(gateway.calls))
            files = _files(application, run_id, 7)
            facts = strict_loads(files["evidence/fact-register.json"])
            self.assertIn("gross_margin_change_pp", {fact["fact_code"] for fact in facts})

    def test_forbidden_edit_changes_neither_engine_nor_manifest(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            application, run_store, _, orchestrator = self._runtime(root)
            run_id = "run_forbidden_edit_01234567"
            application.create_run(CreateRunRequest(
                mission=mission_body(),
                run_owner_actor_id="local-browser-user",
                run_id=run_id,
            ))
            orchestrator.continue_run(
                run_id,
                MutationBase(expected_revision=1, idempotency_key="continue_forbidden_01"),
            )
            state_path = run_store.run_root(run_id) / "state.json"
            manifest_path = run_store.run_root(run_id) / "service-manifest.json"
            state_before = state_path.read_bytes()
            manifest_before = manifest_path.read_bytes()

            with self.assertRaises(ValueError):
                orchestrator.submit_hitl(
                    run_id,
                    HitlDecisionRequest(
                        expected_revision=2,
                        idempotency_key="approve_forbidden_01",
                        decision="approve_with_edits",
                        edits={"filesystem_path": str(root / "secret.txt")},
                    ),
                    browser_session_fingerprint=FINGERPRINT,
                )

            self.assertEqual(state_before, state_path.read_bytes())
            self.assertEqual(manifest_before, manifest_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
