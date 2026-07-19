import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from trusted_ceo_agent.errors import ContractError, RevisionConflict
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from trusted_ceo_agent.workflow.approvals import ApprovalService, current_approvals
from trusted_ceo_agent.workflow.revisions import RevisionManager


class TtyBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


class ApprovalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        store = ArtifactStore(Path(self.temp.name))
        store.create_run("run_20260717T000000Z_0123456789abcdef")
        self.manager = RevisionManager(store)
        self.now = datetime(2026, 7, 17, tzinfo=timezone.utc)
        self.service = ApprovalService(self.manager, clock=lambda: self.now, nonce_factory=lambda: "nonce-secret")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def assertApprovalSchema(self, value: dict) -> None:
        schema_path = Path(__file__).parents[3] / "plugin" / "trusted-ceo-agent" / "schemas" / "approval.schema.json"
        schema = json.loads(schema_path.read_text("utf-8"))
        Draft202012Validator(schema).validate(value)

    def test_request_stores_only_nonce_hash_and_interactive_approval_consumes_it(self) -> None:
        request, nonce, revision = self.service.request(
            expected_revision=0,
            gate="diagnostic",
            base_artifact_ref="artifact_001",
            base_artifact_hash="a" * 64,
            patch_operations=[],
            invalidated_approval_ids=[],
            result_preview_hash="b" * 64,
        )
        self.assertEqual("nonce-secret", nonce)
        self.assertNotIn(nonce, json.dumps(request))
        stdin = TtyBuffer("ceo-1\nceo\nnonce-secret\nAPPROVE\n")
        stdout = TtyBuffer()
        approval, approved_revision = self.service.approve_interactive(
            request["approval_request_id"], expected_revision=revision, input_stream=stdin, output_stream=stdout
        )
        self.assertEqual("interactive_tty", approval["input_method"])
        self.assertEqual(revision + 1, approved_revision)
        self.assertIn("BASE HASH", stdout.getvalue())
        with self.assertRaises(RevisionConflict):
            self.service.approve_interactive(
                request["approval_request_id"], expected_revision=revision,
                input_stream=TtyBuffer("ceo-1\nceo\nnonce-secret\nAPPROVE\n"), output_stream=TtyBuffer(),
            )

    def test_wrong_role_and_non_tty_are_rejected_without_consuming_nonce(self) -> None:
        request, _, revision = self.service.request(
            expected_revision=0, gate="final", base_artifact_ref="artifact_001", base_artifact_hash="a" * 64,
            patch_operations=[], invalidated_approval_ids=[], result_preview_hash="b" * 64,
        )
        with self.assertRaises(ContractError):
            self.service.approve_interactive(request["approval_request_id"], expected_revision=revision, input_stream=io.StringIO(), output_stream=io.StringIO())
        with self.assertRaises(ContractError):
            self.service.approve_interactive(
                request["approval_request_id"], expected_revision=revision,
                input_stream=TtyBuffer("data-1\ndata_owner\nnonce-secret\nAPPROVE\n"), output_stream=TtyBuffer(),
            )

    def test_web_approval_records_browser_provenance_without_tty(self) -> None:
        request, nonce, revision = self.service.request(
            expected_revision=0,
            gate="final",
            base_artifact_ref="artifact_001@r0000",
            base_artifact_hash="a" * 64,
            patch_operations=[],
            invalidated_approval_ids=[],
            result_preview_hash="b" * 64,
        )

        approval, approved_revision = self.service.approve_web(
            request["approval_request_id"],
            expected_revision=revision,
            actor_id="ceo-web-1",
            actor_role="ceo",
            nonce=nonce,
            rationale="브라우저에서 근거를 검토하고 승인했습니다.",
            browser_session_fingerprint="c" * 64,
            response_hash="d" * 64,
        )

        self.assertEqual(revision + 1, approved_revision)
        self.assertEqual("web_hitl", approval["input_method"])
        self.assertEqual("c" * 64, approval["browser_session_fingerprint"])
        self.assertEqual("d" * 64, approval["response_hash"])
        self.assertNotIn("tty_session_fingerprint", approval)
        self.assertApprovalSchema(approval)
        with self.assertRaises(RevisionConflict):
            self.service.approve_web(
                request["approval_request_id"],
                expected_revision=revision,
                actor_id="ceo-web-1",
                actor_role="ceo",
                nonce=nonce,
                rationale="재사용 시도",
                browser_session_fingerprint="c" * 64,
                response_hash="d" * 64,
            )

    def test_web_approval_rejects_wrong_role_and_expired_request(self) -> None:
        request, nonce, revision = self.service.request(
            expected_revision=0,
            gate="final",
            base_artifact_ref="artifact_001",
            base_artifact_hash="a" * 64,
            patch_operations=[],
            invalidated_approval_ids=[],
            result_preview_hash="b" * 64,
        )
        with self.assertRaisesRegex(ContractError, "role"):
            self.service.approve_web(
                request["approval_request_id"],
                expected_revision=revision,
                actor_id="data-web-1",
                actor_role="data_owner",
                nonce=nonce,
                rationale="잘못된 역할",
                browser_session_fingerprint="c" * 64,
                response_hash="d" * 64,
            )

        self.now += timedelta(minutes=11)
        with self.assertRaisesRegex(ContractError, "expired"):
            self.service.approve_web(
                request["approval_request_id"],
                expected_revision=revision,
                actor_id="ceo-web-1",
                actor_role="ceo",
                nonce=nonce,
                rationale="만료된 승인",
                browser_session_fingerprint="c" * 64,
                response_hash="d" * 64,
            )

    def test_web_approval_rejects_invalid_browser_provenance(self) -> None:
        request, nonce, revision = self.service.request(
            expected_revision=0,
            gate="final",
            base_artifact_ref="artifact_001",
            base_artifact_hash="a" * 64,
            patch_operations=[],
            invalidated_approval_ids=[],
            result_preview_hash="b" * 64,
        )
        for fingerprint, response_hash in (("short", "d" * 64), ("c" * 64, "invalid")):
            with self.subTest(fingerprint=fingerprint, response_hash=response_hash):
                with self.assertRaisesRegex(ContractError, "provenance"):
                    self.service.approve_web(
                        request["approval_request_id"],
                        expected_revision=revision,
                        actor_id="ceo-web-1",
                        actor_role="ceo",
                        nonce=nonce,
                        rationale="브라우저 승인",
                        browser_session_fingerprint=fingerprint,
                        response_hash=response_hash,
                    )

    def test_web_request_changes_is_recorded_but_never_authorizes(self) -> None:
        request, nonce, revision = self.service.request(
            expected_revision=0,
            gate="diagnostic",
            base_artifact_ref="artifact_001@r0000",
            base_artifact_hash="a" * 64,
            patch_operations=[],
            invalidated_approval_ids=[],
            result_preview_hash="b" * 64,
        )

        record, decided_revision = self.service.decide_web(
            request["approval_request_id"],
            decision="request_changes",
            expected_revision=revision,
            actor_id="ceo-web-1",
            actor_role="ceo",
            nonce=nonce,
            rationale="고객 모집단을 먼저 재검증하세요.",
            browser_session_fingerprint="c" * 64,
            response_hash="d" * 64,
        )

        self.assertEqual("request_changes", record["decision"])
        self.assertEqual("web_hitl", record["input_method"])
        self.assertEqual((), current_approvals(self.manager.files(decided_revision)))
        self.assertApprovalSchema(record)

    def test_request_changes_consumes_nonce_but_never_creates_authorization(self) -> None:
        request, _, revision = self.service.request(
            expected_revision=0,
            gate="diagnostic",
            base_artifact_ref="artifact_001@r0000",
            base_artifact_hash="a" * 64,
            patch_operations=[
                {"op": "add", "path": "/deep_dive_scope/component_ids", "value": ["component_margin"]},
                {"op": "add", "path": "/deep_dive_scope/issue_ids", "value": ["issue_01"]},
            ],
            invalidated_approval_ids=[],
            result_preview_hash="b" * 64,
        )

        record, decided_revision = self.service.decide_interactive(
            request["approval_request_id"],
            decision="request_changes",
            expected_revision=revision,
            input_stream=TtyBuffer(
                "ceo-1\nceo\nnonce-secret\nReconcile the customer population first.\nREQUEST_CHANGES\n"
            ),
            output_stream=TtyBuffer(),
        )

        self.assertEqual("request_changes", record["decision"])
        self.assertEqual("Reconcile the customer population first.", record["rationale"])
        self.assertEqual([], record["authorized_component_ids"])
        self.assertEqual([], record["target_refs"])
        self.assertEqual("artifact_001@r0000", record["result_artifact_ref"])
        self.assertApprovalSchema(record)
        self.assertEqual((), current_approvals(self.manager.files(decided_revision)))
        stored_request = json.loads(self.manager.read(
            f"approvals/requests/{request['approval_request_id']}.json",
            revision=decided_revision,
        ))
        self.assertEqual("used", stored_request["status"])
        self.assertEqual(record["approval_id"], stored_request["approval_id"])
        with self.assertRaisesRegex(ContractError, "already consumed"):
            self.service.decide_interactive(
                request["approval_request_id"],
                decision="request_changes",
                expected_revision=decided_revision,
                input_stream=TtyBuffer(
                    "ceo-1\nceo\nnonce-secret\nTry reuse.\nREQUEST_CHANGES\n"
                ),
                output_stream=TtyBuffer(),
            )

    def test_reject_is_separate_from_request_changes_and_requires_exact_tty_phrase(self) -> None:
        request, _, revision = self.service.request(
            expected_revision=0,
            gate="final",
            base_artifact_ref="artifact_001",
            base_artifact_hash="a" * 64,
            patch_operations=[],
            invalidated_approval_ids=[],
            result_preview_hash="b" * 64,
        )
        with self.assertRaisesRegex(ContractError, "exact REJECT"):
            self.service.decide_interactive(
                request["approval_request_id"],
                decision="reject",
                expected_revision=revision,
                input_stream=TtyBuffer("ceo-1\nceo\nnonce-secret\nEvidence conflict.\nREQUEST_CHANGES\n"),
                output_stream=TtyBuffer(),
            )
        record, decided_revision = self.service.decide_interactive(
            request["approval_request_id"],
            decision="reject",
            expected_revision=revision,
            input_stream=TtyBuffer("ceo-1\nceo\nnonce-secret\nEvidence conflict.\nREJECT\n"),
            output_stream=TtyBuffer(),
        )
        self.assertEqual("reject", record["decision"])
        self.assertEqual("Evidence conflict.", record["rationale"])
        self.assertEqual((), current_approvals(self.manager.files(decided_revision), gate="final"))
        with self.assertRaisesRegex(ContractError, "unsupported interactive decision"):
            self.service.decide_interactive(
                request["approval_request_id"],
                decision="approve",
                expected_revision=decided_revision,
                input_stream=TtyBuffer(),
                output_stream=TtyBuffer(),
            )

    def test_nonapproval_decision_rejects_pipe_and_wrong_role_without_consuming_nonce(self) -> None:
        request, _, revision = self.service.request(
            expected_revision=0,
            gate="final",
            base_artifact_ref="artifact_001",
            base_artifact_hash="a" * 64,
            patch_operations=[],
            invalidated_approval_ids=[],
            result_preview_hash="b" * 64,
        )
        with self.assertRaisesRegex(ContractError, "TTY"):
            self.service.decide_interactive(
                request["approval_request_id"],
                decision="request_changes",
                expected_revision=revision,
                input_stream=io.StringIO(
                    "ceo-1\nceo\nnonce-secret\nExplain.\nREQUEST_CHANGES\n"
                ),
                output_stream=io.StringIO(),
            )
        with self.assertRaisesRegex(ContractError, "role"):
            self.service.decide_interactive(
                request["approval_request_id"],
                decision="request_changes",
                expected_revision=revision,
                input_stream=TtyBuffer(
                    "data-1\ndata_owner\nnonce-secret\nExplain.\nREQUEST_CHANGES\n"
                ),
                output_stream=TtyBuffer(),
            )
        record, _ = self.service.decide_interactive(
            request["approval_request_id"],
            decision="request_changes",
            expected_revision=revision,
            input_stream=TtyBuffer(
                "ceo-1\nceo\nnonce-secret\nExplain.\nREQUEST_CHANGES\n"
            ),
            output_stream=TtyBuffer(),
        )
        self.assertEqual("request_changes", record["decision"])

    def test_nonapproval_decision_preserves_existing_authorization_and_protected_updates(self) -> None:
        first_request, _, first_request_revision = self.service.request(
            expected_revision=0,
            gate="diagnostic",
            base_artifact_ref="artifact_001",
            base_artifact_hash="a" * 64,
            patch_operations=[],
            invalidated_approval_ids=[],
            result_preview_hash="b" * 64,
        )
        first_approval, first_approval_revision = self.service.approve_interactive(
            first_request["approval_request_id"],
            expected_revision=first_request_revision,
            input_stream=TtyBuffer("ceo-1\nceo\nnonce-secret\nAPPROVE\n"),
            output_stream=TtyBuffer(),
        )
        replacement_request, _, replacement_revision = self.service.request(
            expected_revision=first_approval_revision,
            gate="final",
            base_artifact_ref="artifact_001",
            base_artifact_hash="c" * 64,
            patch_operations=[],
            invalidated_approval_ids=["diagnostic"],
            result_preview_hash="d" * 64,
        )
        protected_path = f"approvals/records/{first_approval['approval_id']}.json"
        with self.assertRaisesRegex(ContractError, "security records"):
            self.service.decide_interactive(
                replacement_request["approval_request_id"],
                decision="reject",
                expected_revision=replacement_revision,
                input_stream=TtyBuffer("ceo-1\nceo\nnonce-secret\nDo not replace it.\nREJECT\n"),
                output_stream=TtyBuffer(),
                additional_updates={protected_path: b"{}"},
            )
        _, decided_revision = self.service.decide_interactive(
            replacement_request["approval_request_id"],
            decision="reject",
            expected_revision=replacement_revision,
            input_stream=TtyBuffer("ceo-1\nceo\nnonce-secret\nDo not replace it.\nREJECT\n"),
            output_stream=TtyBuffer(),
        )
        current = current_approvals(self.manager.files(decided_revision), gate="diagnostic")
        self.assertEqual([first_approval["approval_id"]], [item["approval_id"] for item in current])
        self.assertEqual(
            "current",
            json.loads(self.manager.read(protected_path, revision=decided_revision))["status"],
        )

    def test_nonapproval_decision_rejects_request_after_intervening_revision(self) -> None:
        request, _, request_revision = self.service.request(
            expected_revision=0,
            gate="final",
            base_artifact_ref="artifact_001",
            base_artifact_hash="a" * 64,
            patch_operations=[],
            invalidated_approval_ids=[],
            result_preview_hash="b" * 64,
        )
        intervening_revision = self.manager.commit(
            request_revision,
            {"workflow/unrelated.json": b"{}"},
        )
        with self.assertRaisesRegex(RevisionConflict, "stale"):
            self.service.decide_interactive(
                request["approval_request_id"],
                decision="reject",
                expected_revision=intervening_revision,
                input_stream=TtyBuffer("ceo-1\nceo\nnonce-secret\nStale.\nREJECT\n"),
                output_stream=TtyBuffer(),
            )

    def test_workflow_state_and_overlay_updates_share_the_approval_cas(self) -> None:
        request, _, revision = self.service.request(
            expected_revision=0, gate="diagnostic", base_artifact_ref="artifact_001", base_artifact_hash="a" * 64,
            patch_operations=[], invalidated_approval_ids=[], result_preview_hash="b" * 64,
            additional_updates={"workflow/state.json": b'{"status":"diagnostic_approval_required"}'},
        )
        self.assertEqual(
            b'{"status":"diagnostic_approval_required"}',
            self.manager.read("workflow/state.json", revision=revision),
        )
        _, approved_revision = self.service.approve_interactive(
            request["approval_request_id"], expected_revision=revision,
            input_stream=TtyBuffer("ceo-1\nceo\nnonce-secret\nAPPROVE\n"), output_stream=TtyBuffer(),
            additional_updates={"workflow/overlay.json": b"{}", "workflow/state.json": b'{"status":"deep_dive_authorized"}'},
        )
        self.assertEqual(b"{}", self.manager.read("workflow/overlay.json", revision=approved_revision))
        self.assertEqual(b'{"status":"deep_dive_authorized"}', self.manager.read("workflow/state.json", revision=approved_revision))

    def test_result_ref_replaces_base_revision_and_diagnostic_scope_is_recorded(self) -> None:
        request, _, revision = self.service.request(
            expected_revision=0,
            gate="diagnostic",
            base_artifact_ref="artifact_001@r0000",
            base_artifact_hash="a" * 64,
            patch_operations=[
                {
                    "op": "add",
                    "path": "/deep_dive_scope/component_ids",
                    "value": ["component_margin", "component_cash", "component_margin"],
                },
                {
                    "op": "add",
                    "path": "/deep_dive_scope/issue_ids",
                    "value": ["issue_02", "issue_01", "issue_02"],
                },
            ],
            invalidated_approval_ids=[],
            result_preview_hash="b" * 64,
        )

        approval, approved_revision = self.service.approve_interactive(
            request["approval_request_id"],
            expected_revision=revision,
            input_stream=TtyBuffer("ceo-1\nceo\nnonce-secret\nAPPROVE\n"),
            output_stream=TtyBuffer(),
        )

        self.assertEqual(2, approved_revision)
        self.assertEqual("artifact_001@r0002", approval["result_artifact_ref"])
        self.assertEqual(["component_cash", "component_margin"], approval["authorized_component_ids"])
        self.assertEqual(["issue_01", "issue_02"], approval["target_refs"])
        self.assertEqual("current", approval["status"])
        self.assertApprovalSchema(approval)

    def test_gate_invalidation_resolves_current_record_id_and_preserves_invalidated_record(self) -> None:
        first_request, _, first_request_revision = self.service.request(
            expected_revision=0,
            gate="diagnostic",
            base_artifact_ref="artifact_001@r0000",
            base_artifact_hash="a" * 64,
            patch_operations=[],
            invalidated_approval_ids=[],
            result_preview_hash="b" * 64,
        )
        first_approval, first_approval_revision = self.service.approve_interactive(
            first_request["approval_request_id"],
            expected_revision=first_request_revision,
            input_stream=TtyBuffer("ceo-1\nceo\nnonce-secret\nAPPROVE\n"),
            output_stream=TtyBuffer(),
        )

        replacement_request, _, replacement_request_revision = self.service.request(
            expected_revision=first_approval_revision,
            gate="final",
            base_artifact_ref="artifact_001@r0002",
            base_artifact_hash="c" * 64,
            patch_operations=[],
            invalidated_approval_ids=["diagnostic"],
            result_preview_hash="d" * 64,
        )
        self.assertEqual(
            [first_approval["approval_id"]],
            replacement_request["invalidated_approval_ids"],
        )

        _, result_revision = self.service.approve_interactive(
            replacement_request["approval_request_id"],
            expected_revision=replacement_request_revision,
            input_stream=TtyBuffer("ceo-1\nceo\nnonce-secret\nAPPROVE\n"),
            output_stream=TtyBuffer(),
        )
        stored = json.loads(self.manager.read(
            f"approvals/records/{first_approval['approval_id']}.json",
            revision=result_revision,
        ))
        self.assertEqual("invalidated", stored["status"])
        self.assertEqual(result_revision, stored["invalidated_by_revision"])
        self.assertEqual(first_approval["approval_id"], stored["approval_id"])
        self.assertTrue(stored["approval_hash"])
        self.assertApprovalSchema(stored)

        with self.assertRaises(ContractError):
            self.service.request(
                expected_revision=result_revision,
                gate="final",
                base_artifact_ref="artifact_001@r0004",
                base_artifact_hash="e" * 64,
                patch_operations=[],
                invalidated_approval_ids=[first_approval["approval_id"]],
                result_preview_hash="f" * 64,
            )

    def test_invalidation_rejects_unknown_approval_ids(self) -> None:
        with self.assertRaises(ContractError):
            self.service.request(
                expected_revision=0,
                gate="final",
                base_artifact_ref="artifact_001@r0000",
                base_artifact_hash="a" * 64,
                patch_operations=[],
                invalidated_approval_ids=["approval_missing"],
                result_preview_hash="b" * 64,
            )


if __name__ == "__main__":
    unittest.main()
