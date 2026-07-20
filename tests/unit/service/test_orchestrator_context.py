from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from trusted_ceo_agent.application.models import CreateRunRequest, MutationRequest
from trusted_ceo_agent.application.run_application import TrustedCeoApplication
from trusted_ceo_agent.canonical import strict_loads
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.service.contracts import HitlDecisionRequest, MutationBase
from trusted_ceo_agent.service.file_policy import IncomingUpload
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

    def execute(
        self,
        job: dict[str, Any],
        *,
        validator=None,
    ) -> dict[str, Any]:
        self.calls.append(dict(job))
        if self.result is None:
            raise AssertionError("fake gateway result was not configured")
        if validator is not None:
            validator(self.result)
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

    def test_repeated_upload_batches_return_sanitized_canonical_summaries(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            _, _, _, orchestrator = self._runtime(root)
            run_id = 'run_upload_summary_0123456789'
            created = orchestrator.create_run(CreateRunRequest(
                mission=confirmed_mission(),
                run_id=run_id,
            ))

            first = orchestrator.attach_files(
                run_id,
                MutationBase(
                    expected_revision=created.revision,
                    idempotency_key='upload_summary_0001',
                ),
                (IncomingUpload.from_bytes(
                    'a.md',
                    'text/markdown',
                    b'# Plan\nRevenue assumptions\n',
                    logical_path='folder-a/a.md',
                ),),
            )
            second = orchestrator.attach_files(
                run_id,
                MutationBase(
                    expected_revision=first.revision,
                    idempotency_key='upload_summary_0002',
                ),
                (IncomingUpload.from_bytes(
                    'b.csv',
                    'text/csv',
                    b'name,value\nb,2\n',
                    logical_path='folder-b/b.csv',
                ),),
            )

            self.assertEqual(
                ['folder-a/a.md', 'folder-b/b.csv'],
                [item.logical_path for item in second.uploaded_files],
            )
            self.assertEqual(['a.md', 'b.csv'], [item.display_name for item in second.uploaded_files])
            self.assertEqual(
                ['folder-a', 'folder-b'],
                [item.collection_label for item in second.uploaded_files],
            )
            self.assertIn('attach_data', second.allowed_actions)
            public_body = second.model_dump_json()
            for forbidden in ('private_path', 'snapshot_ref', 'original_path_token', 'sha256'):
                self.assertNotIn(forbidden, public_body)
            self.assertNotIn(str(root), public_body)

    def test_upload_limit_counts_alias_logical_paths_not_unique_blobs(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            _, _, _, orchestrator = self._runtime(root)
            run_id = 'run_upload_path_limit_01234567'
            created = orchestrator.create_run(CreateRunRequest(
                mission=confirmed_mission(),
                run_id=run_id,
            ))
            uploads = tuple(
                IncomingUpload.from_bytes(
                    f'f{index:02d}.md',
                    'text/markdown',
                    b'# Shared\n',
                    logical_path=f'folder/f{index:02d}.md',
                )
                for index in range(64)
            )
            full = orchestrator.attach_files(
                run_id,
                MutationBase(
                    expected_revision=created.revision,
                    idempotency_key='upload_path_limit_0001',
                ),
                uploads,
            )

            self.assertEqual(64, len(full.uploaded_files))
            with self.assertRaisesRegex(ContractError, 'count|limit'):
                orchestrator.attach_files(
                    run_id,
                    MutationBase(
                        expected_revision=full.revision,
                        idempotency_key='upload_path_limit_0002',
                    ),
                    (IncomingUpload.from_bytes(
                        'overflow.md',
                        'text/markdown',
                        b'# Shared\n',
                        logical_path='folder/overflow.md',
                    ),),
                )
            self.assertEqual(full.revision, orchestrator.snapshot(run_id).revision)

    def test_markdown_scan_registers_document_evidence_without_fabricating_facts(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            application, _, _, orchestrator = self._runtime(root)
            run_id = 'run_20260721T010000Z_0123456789abcdef'
            created = orchestrator.create_run(CreateRunRequest(
                mission=confirmed_mission(),
                run_id=run_id,
            ))
            attached = orchestrator.attach_files(
                run_id,
                MutationBase(
                    expected_revision=created.revision,
                    idempotency_key='upload_markdown_scan_0001',
                ),
                (IncomingUpload.from_bytes(
                    'plan.md',
                    'text/markdown',
                    b'# Plan\nRevenue assumptions\n',
                    logical_path='strategy/plan.md',
                ),),
            )

            scanned = orchestrator.continue_run(
                run_id,
                MutationBase(
                    expected_revision=attached.revision,
                    idempotency_key='continue_markdown_scan_0001',
                ),
            )
            files = _files(application, run_id, scanned.revision)
            core = strict_loads(files['evidence/core.json'])

            self.assertGreater(len(core['document_evidence_register']), 0)
            self.assertEqual([], [
                item for item in core['data_quality_register']
                if item.get('reason_code') == 'source_parse_failed'
            ])
            self.assertEqual([], core['fact_register'])
            self.assertEqual([], core['capability_map']['capabilities'])

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
            self.assertIn(
                "intake/canonical-mapping-proposal.json",
                _files(application, run_id, prepared.revision),
            )
            ingested = orchestrator.continue_run(
                run_id,
                MutationBase(expected_revision=3, idempotency_key="continue_mapping_0003"),
            )
            self.assertEqual(4, ingested.revision)
            ingested_files = _files(application, run_id, ingested.revision)
            validation = strict_loads(next(
                payload
                for path, payload in ingested_files.items()
                if path.startswith("tasks/") and path.endswith("/validation.json")
            ))
            self.assertEqual("deterministic_canonical", validation["source"])
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
            self.assertEqual(0, len(gateway.calls))
            files = _files(application, run_id, 7)
            facts = strict_loads(files["evidence/fact-register.json"])
            self.assertIn("gross_margin_change_pp", {fact["fact_code"] for fact in facts})

            lens_prepared = orchestrator.continue_run(
                run_id,
                MutationBase(
                    expected_revision=approved.revision,
                    idempotency_key="continue_lens_guard_0001",
                ),
            )
            self.assertEqual("lens_jobs_ready", lens_prepared.workflow_status)
            lens_files = _files(application, run_id, lens_prepared.revision)
            lens_job = strict_loads(next(
                payload
                for path, payload in lens_files.items()
                if path.startswith("tasks/")
                and path.endswith("/job.json")
                and strict_loads(payload).get("stage") == "lens"
            ))
            store = ArtifactStore(application.artifact_root)
            store.open_run(run_id)
            with self.assertRaisesRegex(
                ContractError,
                "deterministic_canonical source is only allowed for schema_mapping",
            ):
                application.mutate(MutationRequest(
                    artifact_root=application.artifact_root,
                    run_id=run_id,
                    expected_revision=lens_prepared.revision,
                    command="ingest-result",
                    parameters={
                        "job_id": lens_job["job_id"],
                        "draft_document": {},
                        "draft_source": "deterministic_canonical",
                    },
                ))
            self.assertEqual(lens_prepared.revision, store.state()["revision"])

    def test_separate_markdown_and_csv_batches_reach_lens_with_exact_document_context(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            application, _, gateway, orchestrator = self._runtime(root)
            run_id = 'run_20260721T020000Z_0123456789abcdef'
            markdown = '# Strategy\nRevenue assumptions are provisional.\n'
            created = orchestrator.create_run(CreateRunRequest(
                mission=confirmed_mission(),
                run_id=run_id,
            ))
            markdown_attached = orchestrator.attach_files(
                run_id,
                MutationBase(
                    expected_revision=created.revision,
                    idempotency_key='upload_mixed_markdown_0001',
                ),
                (IncomingUpload.from_bytes(
                    'plan.md',
                    'text/markdown',
                    markdown.encode('utf-8'),
                    logical_path='strategy/plan.md',
                ),),
            )
            data_attached = orchestrator.attach_files(
                run_id,
                MutationBase(
                    expected_revision=markdown_attached.revision,
                    idempotency_key='upload_mixed_csv_0001',
                ),
                (IncomingUpload.from_bytes(
                    'data.csv',
                    'text/csv',
                    (
                        b'period,gross_margin\n'
                        b'2026-01,0.42\n'
                        b'2026-02,0.39\n'
                        b'2026-03,0.36\n'
                    ),
                    logical_path='folder-b/sub/data.csv',
                ),),
            )
            self.assertEqual(
                ['folder-b/sub/data.csv', 'strategy/plan.md'],
                [item.logical_path for item in data_attached.uploaded_files],
            )

            def advance(idempotency_key: str):
                snapshot = orchestrator.snapshot(run_id)
                return orchestrator.continue_run(
                    run_id,
                    MutationBase(
                        expected_revision=snapshot.revision,
                        idempotency_key=idempotency_key,
                    ),
                )

            self.assertEqual(
                'schema_mapping_job_ready',
                advance('continue_mixed_scan_0001').workflow_status,
            )
            advance('continue_mixed_prepare_0001')
            advance('continue_mixed_ingest_0001')
            self.assertEqual(
                'mapping_proposal_ready',
                advance('continue_mixed_reduce_0001').workflow_status,
            )
            pending = advance('continue_mixed_data_gate_0001')
            self.assertEqual('data_confirmation_required', pending.workflow_status)
            approved = orchestrator.submit_hitl(
                run_id,
                HitlDecisionRequest(
                    expected_revision=pending.revision,
                    idempotency_key='approve_mixed_data_0001',
                    decision='approve',
                ),
                browser_session_fingerprint=FINGERPRINT,
            )
            self.assertEqual('evidence_ready', approved.workflow_status)
            lens_prepared = advance('continue_mixed_lens_0001')
            self.assertEqual('lens_jobs_ready', lens_prepared.workflow_status)
            self.assertEqual([], gateway.calls)

            files = _files(application, run_id, lens_prepared.revision)
            lens_jobs = [
                strict_loads(payload)
                for path, payload in files.items()
                if path.startswith('tasks/')
                and path.endswith('/job.json')
                and strict_loads(payload).get('stage') == 'lens'
            ]
            document_jobs = [
                job for job in lens_jobs
                if job.get('document_evidence_context')
            ]
            self.assertTrue(document_jobs)
            self.assertTrue(
                any(
                    markdown == ''.join(
                        item['content']
                        for item in sorted(
                            job['document_evidence_context'],
                            key=lambda item: item['chunk_index'],
                        )
                    )
                    for job in document_jobs
                ),
            )
            for job in document_jobs:
                self.assertEqual(
                    job['allowed_document_evidence_ids'],
                    [
                        item['document_evidence_id']
                        for item in job['document_evidence_context']
                    ],
                )

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

    def test_expired_web_approval_is_reissued_with_a_new_private_nonce(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            application, run_store, gateway, orchestrator = self._runtime(root)
            run_id = "run_expired_hitl_01234567"
            application.create_run(CreateRunRequest(
                mission=mission_body(),
                run_owner_actor_id="local-browser-user",
                run_id=run_id,
            ))
            first = orchestrator.continue_run(
                run_id,
                MutationBase(expected_revision=1, idempotency_key="continue_expired_0001"),
            )
            old_manifest = run_store.read_manifest(run_id)

            future = datetime.now(timezone.utc) + timedelta(hours=1)
            restarted = AnalysisOrchestrator(
                application,
                run_store,
                gateway,
                clock=lambda: future,
            )
            renewed = restarted.continue_run(
                run_id,
                MutationBase(expected_revision=2, idempotency_key="continue_expired_0002"),
            )
            new_manifest = run_store.read_manifest(run_id)

            self.assertEqual(3, renewed.revision)
            self.assertEqual("human_response", renewed.pending_action)
            self.assertNotEqual(first.hitl_card.request_id, renewed.hitl_card.request_id)
            self.assertNotEqual(
                old_manifest.pending_approval_nonce,
                new_manifest.pending_approval_nonce,
            )
            self.assertNotIn(
                new_manifest.pending_approval_nonce or "",
                renewed.model_dump_json(),
            )


if __name__ == "__main__":
    unittest.main()
