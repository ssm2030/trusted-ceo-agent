from __future__ import annotations

import hashlib
import io
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError, RevisionConflict
from trusted_ceo_agent.trust.artifact_store import ArtifactStore
from trusted_ceo_agent.workflow.approvals import ApprovalService, current_approvals
from trusted_ceo_agent.workflow.human_actions import (
    compile_human_action_card,
    compile_data_request_card,
    pending_action_for_state,
)
from trusted_ceo_agent.workflow.responses import HumanResponseService
from trusted_ceo_agent.workflow.revisions import RevisionManager


RUN_ID = "run_20260717T000000Z_0123456789abcdef"
NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)
TRUSTED_PRINCIPAL = {"subject": "local-owner", "roles": ["run_owner"]}


def human_response_policy(
    *,
    restricted_source_allowlist: list[str] | None = None,
) -> dict:
    body = {
        "schema_version": "1.0.0",
        "policy_id": "human-response-local-owner",
        "policy_version": "1.0.0",
        "transport_principal": "local-owner",
        "authorized_actors": [{
            "actor_id": "ceo-1",
            "roles": ["run_owner"],
            "allowed_gates": ["context", "data", "scope_narrowing", "diagnostic", "final"],
        }],
        "restricted_source_allowlist": sorted(restricted_source_allowlist or []),
        "privacy_policy": {
            "direct_identifier_reasoning": "forbidden",
            "minimum_group_size": 5,
        },
    }
    body["policy_hash"] = hashlib.sha256(canonical_bytes(body)).hexdigest()
    return body


class TtyBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


class HumanResponseServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.store = ArtifactStore(Path(self.temp.name))
        self.store.create_run(RUN_ID)
        self.manager = RevisionManager(self.store)
        self.pending_card = pending_action_for_state(
            run_id=RUN_ID,
            revision=1,
            workflow_state="context_confirmation_required",
            evidence_refs=[],
            expires_at="2026-07-17T00:10:00Z",
        )
        self.manager.commit(0, {
            "workflow/state.json": canonical_bytes({
            "run_id": RUN_ID,
            "revision": 1,
            "state": "context_confirmation_required",
            "resume_state": None,
            "blocker": None,
            "approvals": [],
            }),
            "workflow/pending-action.json": canonical_bytes(self.pending_card),
            "workflow/human-response-policy.json": canonical_bytes(human_response_policy()),
        })
        self.service = HumanResponseService(
            self.manager,
            clock=lambda: NOW,
            trusted_principal=TRUSTED_PRINCIPAL,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def card(self, *, expires_at: str | None = "2026-07-17T00:10:00Z") -> dict:
        if expires_at == "2026-07-17T00:10:00Z":
            return dict(self.pending_card)
        return pending_action_for_state(
            run_id=RUN_ID,
            revision=1,
            workflow_state="context_confirmation_required",
            evidence_refs=[],
            expires_at=expires_at,
        )

    def test_explanation_is_read_only_and_creates_no_response_artifact(self) -> None:
        response = {
            "response_type": "request_explanation",
            "payload": {"question": "Why is confirmation required?"},
            "actor_id": "ceo-1",
        }
        receipt, revision = self.service.submit(
            expected_revision=1,
            action=self.card(),
            response=response,
            idempotency_key="explain-1",
        )
        self.assertEqual(1, revision)
        self.assertEqual(1, receipt["result_revision"])
        self.assertEqual(1, self.manager.current_revision())
        self.assertFalse(any("human-responses" in path for path in self.manager.files()))

        later = HumanResponseService(
            self.manager,
            clock=lambda: datetime(2026, 7, 17, 0, 1, tzinfo=timezone.utc),
            trusted_principal=TRUSTED_PRINCIPAL,
        )
        repeated, repeated_revision = later.submit(
            expected_revision=1,
            action=self.card(),
            response=response,
            idempotency_key="explain-1",
        )
        self.assertEqual(receipt, repeated)
        self.assertEqual(1, repeated_revision)
        changed = {
            "response_type": "request_explanation",
            "payload": {"question": "A different question"},
            "actor_id": "ceo-1",
        }
        with self.assertRaisesRegex(ContractError, "idempotency"):
            later.submit(
                expected_revision=1,
                action=self.card(),
                response=changed,
                idempotency_key="explain-1",
            )

    def test_mutation_is_exactly_one_revision_and_idempotent(self) -> None:
        before = self.manager.files(1)
        card = self.card()
        response = {
            "response_type": "request_changes",
            "payload": {
                "text": "사업 질문을 명확히 해 주세요.",
                "patch_operations": [{
                    "op": "add",
                    "path": "/mission_contract/business_question",
                    "value": "검증된 수익성 저하 원인을 찾는다",
                }],
                "runtime_context": {},
            },
            "actor_id": "ceo-1",
        }
        receipt, revision = self.service.submit(
            expected_revision=1,
            action=card,
            response=response,
            idempotency_key="request-change-1",
        )
        self.assertEqual(2, revision)
        self.assertEqual(before, self.manager.files(1))
        self.assertEqual(["/mission_contract/business_question"], receipt["affected_paths"])
        self.assertFalse(receipt["terminal_approval_required"])
        files = self.manager.files(2)
        self.assertIn(f"workflow/actions/{card['action_id']}.json", files)
        self.assertIn(f"workflow/human-responses/{receipt['response_id']}.json", files)
        self.assertFalse(any(path.startswith("approvals/records/") for path in files))
        self.assertNotIn(b"request-change-1", b"".join(files.values()))

        repeated, repeated_revision = self.service.submit(
            expected_revision=1,
            action=card,
            response=response,
            idempotency_key="request-change-1",
        )
        self.assertEqual(receipt, repeated)
        self.assertEqual(2, repeated_revision)
        self.assertEqual(2, self.manager.current_revision())

        changed = dict(response)
        changed["payload"] = {"text": "다른 요청", "patch_operations": []}
        with self.assertRaisesRegex(ContractError, "idempotency"):
            self.service.submit(
                expected_revision=1,
                action=card,
                response=changed,
                idempotency_key="request-change-1",
            )

    def test_stale_expired_and_atomic_failure_publish_nothing(self) -> None:
        card = self.card()
        expired_service = HumanResponseService(
            self.manager,
            clock=lambda: datetime(2026, 7, 17, 0, 11, tzinfo=timezone.utc),
            trusted_principal=TRUSTED_PRINCIPAL,
        )
        with self.assertRaisesRegex(ContractError, "expired"):
            expired_service.submit(
                expected_revision=1,
                action=card,
                response={"response_type": "confirm", "payload": {}, "actor_id": "ceo-1"},
                idempotency_key="expired-1",
            )
        self.assertEqual(1, self.manager.current_revision())

        fresh = self.card()
        with self.assertRaises(RevisionConflict):
            self.service.submit(
                expected_revision=0,
                action=fresh,
                response={"response_type": "confirm", "payload": {}, "actor_id": "ceo-1"},
                idempotency_key="stale-1",
            )
        self.assertEqual(1, self.manager.current_revision())

        forged = pending_action_for_state(
            run_id=RUN_ID,
            revision=1,
            workflow_state="context_confirmation_required",
            evidence_refs=["evidence_0123456789abcdef01234567"],
            expires_at="2026-07-17T00:10:00Z",
        )
        with self.assertRaisesRegex(RevisionConflict, "active card"):
            self.service.submit(
                expected_revision=1,
                action=forged,
                response={"response_type": "confirm", "payload": {}, "actor_id": "ceo-1"},
                idempotency_key="forged-1",
            )

        def reject_response(files: dict[str, bytes]) -> None:
            if any(path.startswith("workflow/human-responses/") for path in files):
                raise ContractError("forced validator failure")

        guarded = HumanResponseService(
            RevisionManager(self.store, validator=reject_response),
            clock=lambda: NOW,
            trusted_principal=TRUSTED_PRINCIPAL,
        )
        with self.assertRaisesRegex(ContractError, "forced validator"):
            guarded.submit(
                expected_revision=1,
                action=fresh,
                response={"response_type": "confirm", "payload": {}, "actor_id": "ceo-1"},
                idempotency_key="atomic-1",
            )
        self.assertEqual(1, self.manager.current_revision())

    def test_semantic_change_invalidates_existing_downstream_approval(self) -> None:
        approval_service = ApprovalService(
            self.manager,
            clock=lambda: NOW,
            nonce_factory=lambda: "nonce-secret",
        )
        request, _, request_revision = approval_service.request(
            expected_revision=1,
            gate="diagnostic",
            base_artifact_ref=f"{RUN_ID}@r0001",
            base_artifact_hash="a" * 64,
            patch_operations=[],
            invalidated_approval_ids=[],
            result_preview_hash="b" * 64,
        )
        approval, approval_revision = approval_service.approve_interactive(
            request["approval_request_id"],
            expected_revision=request_revision,
            input_stream=TtyBuffer("ceo-1\nceo\nnonce-secret\nAPPROVE\n"),
            output_stream=TtyBuffer(),
        )
        card = pending_action_for_state(
            run_id=RUN_ID,
            revision=approval_revision + 1,
            workflow_state="context_confirmation_required",
            evidence_refs=[],
            expires_at="2026-07-17T00:10:00Z",
        )
        next_revision = self.manager.commit(approval_revision, {
            "workflow/state.json": canonical_bytes({
                "run_id": RUN_ID,
                "revision": approval_revision + 1,
                "state": "context_confirmation_required",
                "resume_state": None,
                "blocker": None,
                "approvals": [],
            }),
            "workflow/pending-action.json": canonical_bytes(card),
        })
        receipt, result_revision = HumanResponseService(
            self.manager,
            clock=lambda: NOW,
            trusted_principal=TRUSTED_PRINCIPAL,
        ).submit(
            expected_revision=next_revision,
            action=card,
            response={
                "response_type": "request_changes",
                "payload": {
                    "text": "질문을 바꿉니다.",
                    "patch_operations": [{
                        "op": "add",
                        "path": "/mission_contract/business_question",
                        "value": "변경된 질문",
                    }],
                },
                "actor_id": "ceo-1",
            },
            idempotency_key="invalidate-1",
        )
        self.assertEqual([approval["approval_id"]], receipt["invalidated_approval_refs"])
        self.assertEqual((), current_approvals(self.manager.files(result_revision), gate="diagnostic"))

    def test_naive_clock_and_unknown_provided_source_fail_closed(self) -> None:
        with self.assertRaisesRegex(ContractError, "timezone"):
            HumanResponseService(
                self.manager,
                clock=lambda: datetime(2026, 7, 17),
                trusted_principal=TRUSTED_PRINCIPAL,
            ).submit(
                expected_revision=1,
                action=self.card(),
                response={"response_type": "confirm", "payload": {}, "actor_id": "ceo-1"},
                idempotency_key="naive-clock-1",
            )

        data_card = compile_data_request_card(
            run_id=RUN_ID,
            base_revision=2,
            missing_source_roles=["contract_register"],
            missing_capabilities=["revenue_contract_terms"],
            affected_issue_family_refs=["RV-03"],
            affected_domains=["accounting"],
            evidence_refs=[],
            expires_at=None,
        )
        revision = self.manager.commit(1, {
            "workflow/state.json": canonical_bytes({
                "run_id": RUN_ID,
                "revision": 2,
                "state": "data_confirmation_required",
                "resume_state": None,
                "blocker": None,
                "approvals": [],
            }),
            "workflow/pending-action.json": canonical_bytes(data_card),
            "sources/registry.json": canonical_bytes([]),
        })
        with self.assertRaisesRegex(ContractError, "Source"):
            HumanResponseService(
                self.manager,
                clock=lambda: NOW,
                trusted_principal=TRUSTED_PRINCIPAL,
            ).submit(
                expected_revision=revision,
                action=data_card,
                response={
                    "response_type": "provide_data",
                    "payload": {"source_refs": ["source_missing"]},
                    "actor_id": "ceo-1",
                },
                idempotency_key="missing-source-1",
            )
        self.assertEqual(revision, self.manager.current_revision())

    def test_resolved_action_does_not_regenerate_without_workflow_change(self) -> None:
        receipt, revision = self.service.submit(
            expected_revision=1,
            action=self.card(),
            response={"response_type": "confirm", "payload": {}, "actor_id": "ceo-1"},
            idempotency_key="confirm-once",
        )
        self.assertEqual(2, revision)
        self.assertTrue(receipt["terminal_approval_required"])
        files = self.manager.files(revision)
        self.assertNotIn("workflow/pending-action.json", files)
        self.assertIn("workflow/human-action-resolution.json", files)
        regenerated = pending_action_for_state(
            run_id=RUN_ID,
            revision=revision,
            workflow_state="context_confirmation_required",
            evidence_refs=[],
            expires_at=None,
        )
        with self.assertRaisesRegex(ContractError, "no Human Action Card is active"):
            HumanResponseService(
                self.manager,
                clock=lambda: NOW,
                trusted_principal=TRUSTED_PRINCIPAL,
            ).submit(
                expected_revision=revision,
                action=regenerated,
                response={"response_type": "confirm", "payload": {}, "actor_id": "ceo-1"},
                idempotency_key="confirm-twice",
            )
        self.assertEqual(revision, self.manager.current_revision())

    def test_choice_ids_must_be_bound_to_card_options(self) -> None:
        card = compile_human_action_card(
            run_id=RUN_ID,
            base_revision=2,
            workflow_state="context_confirmation_required",
            gate="context",
            action_type="test-choice",
            title="Choose",
            question="Choose safely",
            why_asked="Test binding",
            current_interpretation="Only declared options are valid",
            evidence_refs=[],
            required=True,
            allowed_response_types=["choose_one", "choose_many"],
            options=[
                {
                    "option_id": "safe-one",
                    "label": "Safe one",
                    "response_type": "choose_one",
                    "description": "Declared single choice",
                },
                {
                    "option_id": "safe-many",
                    "label": "Safe many",
                    "response_type": "choose_many",
                    "description": "Declared multiple choice",
                },
            ],
            recommended_option_id=None,
            recommendation_reason=None,
            unanswered_effect="No choice is recorded",
            next_step_by_option={"safe-one": "Continue", "safe-many": "Continue"},
            expires_at=None,
        )
        revision = self.manager.commit(1, {
            "workflow/state.json": canonical_bytes({
                "run_id": RUN_ID,
                "revision": 2,
                "state": "context_confirmation_required",
                "resume_state": None,
                "blocker": None,
                "approvals": [],
            }),
            "workflow/pending-action.json": canonical_bytes(card),
        })
        service = HumanResponseService(
            self.manager,
            clock=lambda: NOW,
            trusted_principal=TRUSTED_PRINCIPAL,
        )
        with self.assertRaisesRegex(ContractError, "option"):
            service.submit(
                expected_revision=revision,
                action=card,
                response={
                    "response_type": "choose_one",
                    "payload": {"option_id": "forged"},
                    "actor_id": "ceo-1",
                },
                idempotency_key="forged-one",
            )
        with self.assertRaisesRegex(ContractError, "option"):
            service.submit(
                expected_revision=revision,
                action=card,
                response={
                    "response_type": "choose_many",
                    "payload": {"option_ids": ["safe-many", "forged"]},
                    "actor_id": "ceo-1",
                },
                idempotency_key="forged-many",
            )
        self.assertEqual(revision, self.manager.current_revision())

    def test_policy_denies_principal_mismatch_and_prohibited_source(self) -> None:
        mismatched = HumanResponseService(
            self.manager,
            clock=lambda: NOW,
            trusted_principal={"subject": "another-user", "roles": ["run_owner"]},
        )
        with self.assertRaisesRegex(ContractError, "principal"):
            mismatched.submit(
                expected_revision=1,
                action=self.card(),
                response={"response_type": "confirm", "payload": {}, "actor_id": "ceo-1"},
                idempotency_key="wrong-principal",
            )
        self.assertEqual(1, self.manager.current_revision())

        source_id = "source_" + ("a" * 24)
        data_card = compile_data_request_card(
            run_id=RUN_ID,
            base_revision=2,
            missing_source_roles=["contract_register"],
            missing_capabilities=["revenue_contract_terms"],
            affected_issue_family_refs=["RV-03"],
            affected_domains=["accounting"],
            evidence_refs=[],
            expires_at=None,
        )
        revision = self.manager.commit(1, {
            "workflow/state.json": canonical_bytes({
                "run_id": RUN_ID,
                "revision": 2,
                "state": "data_confirmation_required",
                "resume_state": None,
                "blocker": None,
                "approvals": [],
            }),
            "workflow/pending-action.json": canonical_bytes(data_card),
            "sources/registry.json": canonical_bytes([{
                "source_id": source_id,
                "access_policy": "prohibited",
            }]),
        })
        with self.assertRaisesRegex(ContractError, "prohibited"):
            HumanResponseService(
                self.manager,
                clock=lambda: NOW,
                trusted_principal=TRUSTED_PRINCIPAL,
            ).submit(
                expected_revision=revision,
                action=data_card,
                response={
                    "response_type": "provide_data",
                    "payload": {"source_refs": [source_id]},
                    "actor_id": "ceo-1",
                },
                idempotency_key="prohibited-source",
            )
        self.assertEqual(revision, self.manager.current_revision())


if __name__ == "__main__":
    unittest.main()
