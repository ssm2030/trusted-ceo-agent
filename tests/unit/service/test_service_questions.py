from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Callable, Mapping
from unittest.mock import patch

from trusted_ceo_agent.application.models import ApplicationResult
from trusted_ceo_agent.application.run_application import TrustedCeoApplication
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.service.questions import (
    QuestionRequest,
    QuestionService,
)
from trusted_ceo_agent.service.run_store import RunStore, ServiceStoreError
from trusted_ceo_agent.service.testing.fake_openai import (
    KeylessFakeReasoningGateway,
)
from tests.unit.questions.support import ROOT, RUN_ID, finalized_files


class ManualExecutor:
    def __init__(self) -> None:
        self.pending: list[tuple[Future[None], Callable[..., None], tuple[Any, ...]]] = []

    def submit(
        self,
        function: Callable[..., None],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Future[None]:
        if kwargs:
            raise AssertionError("manual executor expects positional worker arguments")
        future: Future[None] = Future()
        self.pending.append((future, function, args))
        return future

    def run_next(self) -> None:
        future, function, args = self.pending.pop(0)
        if not future.set_running_or_notify_cancel():
            return
        try:
            function(*args)
        except BaseException as error:
            future.set_exception(error)
            raise
        else:
            future.set_result(None)


class RecordingApplication:
    def __init__(self, delegate: TrustedCeoApplication) -> None:
        self.delegate = delegate
        self.artifact_root = delegate.artifact_root
        self.observe: Callable[[str], None] | None = None
        self.scope_required = False

    def prepare_result_question(self, request):
        if self.observe is not None:
            self.observe("prepare")
        if self.scope_required:
            return ApplicationResult(
                command="prepare-result-question",
                ok=True,
                code=2,
                message="scope required",
                run_id=request.run_id,
                revision=request.revision,
                state="finalized",
                data={
                    "error_code": "SCOPE_REQUIRED",
                    "suggestions": [{
                        "scope_kind": "issue",
                        "scope_instance_id": "issue_main",
                    }],
                },
            )
        return self.delegate.prepare_result_question(request)

    def validate_result_answer(self, request):
        if self.observe is not None:
            self.observe("validate")
        return self.delegate.validate_result_answer(request)


class KeylessFakeQuestionGateway(KeylessFakeReasoningGateway):
    def __init__(
        self,
        artifact_root: Path,
        *,
        variant: str = "valid",
        on_execute: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(artifact_root)
        self.variant = variant
        self.on_execute = on_execute

    def execute_question(self, job: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append({
            "stage": "question",
            "job_id": str(job.get("job_id", "")),
        })
        if self.on_execute is not None:
            self.on_execute()
        value_ref = str(job["allowed_value_refs"][0])
        block: dict[str, Any] = {
            "block_id": "block_1",
            "support_status": "supported",
            "text_template": f"The verified value is {{{{value:{value_ref}}}}}.",
            "value_refs": [value_ref],
            "claim_refs": [job["allowed_claim_refs"][0]],
            "evidence_link_ids": [job["allowed_evidence_link_ids"][0]],
            "source_refs": [job["allowed_source_refs"][0]],
        }
        draft = {
            "draft_version": "1.0.0",
            "job_id": job["job_id"],
            "run_id": job["run_id"],
            "revision": job["revision"],
            "answer_blocks": [block],
        }
        if self.variant == "other_revision":
            draft["revision"] = int(job["revision"]) + 1
        elif self.variant == "out_of_scope_reference":
            block["evidence_link_ids"] = ["evidence_" + "f" * 24]
        elif self.variant == "tampered_numeric":
            block["text_template"] = "The verified value is 999."
            block["value_refs"] = []
        elif self.variant == "unsupported_claim":
            draft["answer_blocks"] = [{
                "block_id": "block_1",
                "support_status": "not_supported",
                "text_template": "The model supplied an unsupported claim.",
                "value_refs": [],
                "claim_refs": [],
                "evidence_link_ids": [],
                "source_refs": [],
            }]
        elif self.variant != "valid":
            raise AssertionError(f"unknown fake question variant: {self.variant}")
        return draft


class QuestionHarness:
    def __init__(
        self,
        root: Path,
        *,
        gateway_variant: str = "valid",
        gateway_callback: Callable[[], None] | None = None,
    ) -> None:
        fixture_root = root / "fixture"
        fixture_root.mkdir()
        source_store, _ = finalized_files(fixture_root)
        self.store = RunStore(root / "runtime")
        shutil.copytree(source_store.run_dir, self.store.run_root(RUN_ID))
        manifest = self.store.create_manifest(RUN_ID, engine_revision=2)
        self.store.save_manifest(
            manifest.model_copy(update={"status": "finalized"}),
            expected_revision=2,
        )
        delegate = TrustedCeoApplication(self.store.runs_root)
        self.application = RecordingApplication(delegate)
        self.gateway = KeylessFakeQuestionGateway(
            delegate.artifact_root,
            variant=gateway_variant,
            on_execute=gateway_callback,
        )
        self.executor = ManualExecutor()
        self.service = QuestionService(
            self.application,
            self.store,
            self.gateway,
            executor=self.executor,
        )

    @staticmethod
    def request(
        *,
        idempotency_key: str = "question_request_0001",
        expected_revision: int = 2,
        question: str = "What value is supported by the report?",
        scope_instance_id: str = "issue_main",
    ) -> QuestionRequest:
        return QuestionRequest(
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            question=question,
            scope_kind="issue",
            scope_instance_id=scope_instance_id,
            privacy_classification="poc_deidentified",
        )


class QuestionServiceTests(unittest.TestCase):
    def test_question_runs_through_validation_and_persists_only_canonical_answer(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            harness = QuestionHarness(root)
            observed_states: list[str] = []
            request_id: list[str] = []

            def observe(_event: str) -> None:
                observed_states.append(
                    harness.service.get(RUN_ID, request_id[0]).state
                )

            harness.application.observe = observe
            harness.gateway.on_execute = lambda: observe("gateway")
            request = harness.request()

            queued = harness.service.start(RUN_ID, request)
            request_id.append(queued.request_id)

            self.assertEqual("queued", queued.state)
            harness.executor.run_next()
            completed = harness.service.get(RUN_ID, queued.request_id)

            self.assertEqual(
                ["preparing", "asking", "validating"],
                observed_states,
            )
            self.assertEqual("completed", completed.state)
            self.assertIsNotNone(completed.answer)
            self.assertEqual(
                {"schema_valid": True, "references_valid": True, "values_valid": True},
                {
                    key: completed.answer["validation"][key]
                    for key in ("schema_valid", "references_valid", "values_valid")
                },
            )
            self.assertEqual(
                [{"stage": "question", "job_id": completed.answer["job_id"]}],
                harness.gateway.calls,
            )

            conversation_files = list(
                (harness.store.run_root(RUN_ID) / "conversations").rglob("*.json")
            )
            self.assertEqual(1, len(conversation_files))
            persisted = conversation_files[0].read_text("utf-8")
            self.assertNotIn(request.question, persisted)
            self.assertNotIn("text_template", persisted)
            self.assertNotIn("draft_version", persisted)
            self.assertNotIn("job_hash", persisted)
            self.assertIn('"state":"completed"', persisted)
            self.assertIn('"answer_version":"1.0.0"', persisted)
            manifest = (
                harness.store.run_root(RUN_ID) / "service-manifest.json"
            ).read_text("utf-8")
            self.assertNotIn(request.question, manifest)

    def test_client_request_is_idempotent_and_only_one_question_is_active(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            harness = QuestionHarness(Path(directory))
            request = harness.request()

            first = harness.service.start(RUN_ID, request)
            replay = harness.service.start(RUN_ID, request)

            self.assertEqual(first.request_id, replay.request_id)
            self.assertEqual("queued", replay.state)
            with self.assertRaisesRegex(
                ServiceStoreError,
                "IDEMPOTENCY_CONFLICT",
            ) as active:
                harness.service.start(
                    RUN_ID,
                    harness.request(idempotency_key="question_request_0002"),
                )
            self.assertEqual("IDEMPOTENCY_CONFLICT", active.exception.code)
            with self.assertRaisesRegex(
                ServiceStoreError,
                "IDEMPOTENCY_CONFLICT",
            ):
                harness.service.start(
                    RUN_ID,
                    harness.request(
                        question="A different body reusing the same client key.",
                    ),
                )

            harness.executor.run_next()
            completed_replay = harness.service.start(RUN_ID, request)
            self.assertEqual(first.request_id, completed_replay.request_id)
            self.assertEqual("completed", completed_replay.state)
            self.assertEqual(1, len(harness.gateway.calls))

            next_question = harness.service.start(
                RUN_ID,
                harness.request(idempotency_key="question_request_0003"),
            )
            self.assertNotEqual(first.request_id, next_question.request_id)
            self.assertEqual("queued", next_question.state)

    def test_receipt_write_failure_leaves_no_orphan_and_replays_after_restart(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            harness = QuestionHarness(Path(directory))
            request = harness.request()

            with patch.object(
                harness.store,
                "store_idempotency_receipt",
                side_effect=OSError("simulated receipt interruption"),
            ):
                with self.assertRaisesRegex(OSError, "receipt interruption"):
                    harness.service.start(RUN_ID, request)

            conversation_dir = harness.store.run_root(RUN_ID) / "conversations"
            self.assertEqual([], list(conversation_dir.glob("*.json")))

            harness.service.close()
            restarted_executor = ManualExecutor()
            restarted = QuestionService(
                harness.application,
                harness.store,
                harness.gateway,
                executor=restarted_executor,
            )
            queued = restarted.start(RUN_ID, request)
            replay = restarted.start(RUN_ID, request)

            self.assertEqual("queued", queued.state)
            self.assertEqual(queued.request_id, replay.request_id)
            self.assertEqual(1, len(restarted_executor.pending))

    def test_close_and_restart_recover_active_snapshots_and_allow_new_questions(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            harness = QuestionHarness(Path(directory))
            queued = harness.service.start(RUN_ID, harness.request())

            harness.service.close()

            cancelled = harness.service.get(RUN_ID, queued.request_id)
            self.assertEqual("cancelled", cancelled.state)
            self.assertEqual("CANCELLED", cancelled.error_code)
            self.assertFalse(cancelled.retryable)

            restarted_executor = ManualExecutor()
            restarted = QuestionService(
                harness.application,
                harness.store,
                harness.gateway,
                executor=restarted_executor,
            )
            asking = restarted.start(
                RUN_ID,
                harness.request(idempotency_key="question_request_0002"),
            )
            restarted._transition(RUN_ID, asking.request_id, "asking")

            after_crash_executor = ManualExecutor()
            after_crash = QuestionService(
                harness.application,
                harness.store,
                harness.gateway,
                executor=after_crash_executor,
            )
            recovered = after_crash.get(RUN_ID, asking.request_id)
            self.assertEqual("failed", recovered.state)
            self.assertEqual("ENGINE_FAILURE", recovered.error_code)
            self.assertTrue(recovered.retryable)

            next_question = after_crash.start(
                RUN_ID,
                harness.request(idempotency_key="question_request_0003"),
            )
            self.assertEqual("queued", next_question.state)
            self.assertEqual(1, len(after_crash_executor.pending))

    def test_non_finalized_and_stale_revision_requests_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            harness = QuestionHarness(Path(directory))
            finalized = harness.store.read_manifest(RUN_ID)
            harness.store.save_manifest(
                finalized.model_copy(update={"status": "stopped"}),
                expected_revision=2,
            )

            with self.assertRaisesRegex(ContractError, "finalized"):
                harness.service.start(RUN_ID, harness.request())
            with self.assertRaisesRegex(
                ServiceStoreError,
                "STALE_REVISION",
            ):
                harness.service.start(
                    RUN_ID,
                    harness.request(expected_revision=1),
                )
            self.assertEqual([], harness.executor.pending)

    def test_missing_scope_is_failed_and_scope_limit_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            harness = QuestionHarness(Path(directory))
            missing = harness.service.start(
                RUN_ID,
                harness.request(scope_instance_id="issue_missing"),
            )
            harness.executor.run_next()

            failed = harness.service.get(RUN_ID, missing.request_id)
            self.assertEqual("failed", failed.state)
            self.assertEqual("VALIDATION_FAILURE", failed.error_code)
            self.assertIsNone(failed.answer)

        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            harness = QuestionHarness(Path(directory))
            harness.application.scope_required = True
            pending = harness.service.start(RUN_ID, harness.request())
            harness.executor.run_next()

            blocked = harness.service.get(RUN_ID, pending.request_id)
            self.assertEqual("scope_required", blocked.state)
            self.assertEqual("SCOPE_REQUIRED", blocked.error_code)
            self.assertEqual(1, len(blocked.scope_suggestions))
            self.assertEqual("issue", blocked.scope_suggestions[0].scope_kind)
            self.assertIsNone(blocked.answer)
            self.assertEqual([], harness.gateway.calls)

    def test_untrusted_drafts_never_publish_invalid_answers(self) -> None:
        for variant in (
            "other_revision",
            "out_of_scope_reference",
            "tampered_numeric",
            "unsupported_claim",
        ):
            with self.subTest(variant=variant):
                with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                    harness = QuestionHarness(
                        Path(directory),
                        gateway_variant=variant,
                    )
                    pending = harness.service.start(RUN_ID, harness.request())
                    harness.executor.run_next()

                    failed = harness.service.get(RUN_ID, pending.request_id)
                    self.assertEqual("failed", failed.state)
                    self.assertEqual("VALIDATION_FAILURE", failed.error_code)
                    self.assertIsNone(failed.answer)
                    payload = json.loads(
                        next(
                            (
                                harness.store.run_root(RUN_ID) / "conversations"
                            ).rglob("*.json")
                        ).read_text("utf-8")
                    )
                    self.assertIsNone(payload["answer"])
                    self.assertNotIn("job", payload)
                    self.assertNotIn("draft", payload)

    def test_revision_change_during_scope_preparation_cancels_without_publishing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            harness = QuestionHarness(Path(directory))
            harness.application.scope_required = True

            def advance_engine_revision(_event: str) -> None:
                state_path = harness.store.run_root(RUN_ID) / "state.json"
                state = copy.deepcopy(json.loads(state_path.read_text("utf-8")))
                state["revision"] = 3
                state_path.write_bytes(canonical_bytes(state))

            harness.application.observe = advance_engine_revision
            pending = harness.service.start(RUN_ID, harness.request())
            harness.executor.run_next()

            cancelled = harness.service.get(RUN_ID, pending.request_id)
            self.assertEqual("cancelled", cancelled.state)
            self.assertEqual("STALE_REVISION", cancelled.error_code)
            self.assertEqual([], cancelled.scope_suggestions)
            self.assertIsNone(cancelled.answer)

    def test_revision_change_while_asking_cancels_without_publishing(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            harness = QuestionHarness(root)

            def advance_engine_revision() -> None:
                state_path = harness.store.run_root(RUN_ID) / "state.json"
                state = copy.deepcopy(json.loads(state_path.read_text("utf-8")))
                state["revision"] = 3
                state_path.write_bytes(canonical_bytes(state))

            harness.gateway.on_execute = advance_engine_revision
            pending = harness.service.start(RUN_ID, harness.request())
            harness.executor.run_next()

            cancelled = harness.service.get(RUN_ID, pending.request_id)
            self.assertEqual("cancelled", cancelled.state)
            self.assertEqual("STALE_REVISION", cancelled.error_code)
            self.assertIsNone(cancelled.answer)


if __name__ == "__main__":
    unittest.main()
