from __future__ import annotations

import tempfile
import threading
import time
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from trusted_ceo_agent.application.models import CreateRunRequest
from trusted_ceo_agent.application.run_application import TrustedCeoApplication
from trusted_ceo_agent.service.analysis_coordinator import AnalysisCoordinator
from trusted_ceo_agent.service.app import create_app
from trusted_ceo_agent.service.contracts import MutationBase, RunSnapshot
from trusted_ceo_agent.service.openai_gateway import AIServiceError
from trusted_ceo_agent.service.orchestrator import AnalysisOrchestrator
from trusted_ceo_agent.service.questions import QuestionRequest, QuestionSnapshot
from trusted_ceo_agent.service.run_store import RunStore
from trusted_ceo_agent.service.service_lease import ServiceRootLease
from trusted_ceo_agent.service.settings import ServiceSettings
from trusted_ceo_agent.service.testing.fake_openai import (
    KeylessFakeReasoningGateway,
)
from tests.support import mission_body


ROOT = Path(__file__).resolve().parents[3]
TOKEN = "internal_token_for_async_analysis_test_123456"
AUTH = {"X-Trusted-Ceo-Internal-Token": TOKEN}
FINGERPRINT = "e" * 64


class StubQuestionService:
    def __init__(self) -> None:
        self.closed = False

    def start(self, run_id: str, request: QuestionRequest) -> QuestionSnapshot:
        raise AssertionError("question work is outside this test")

    def get(self, run_id: str, request_id: str) -> QuestionSnapshot:
        raise AssertionError("question work is outside this test")

    def close(self) -> None:
        self.closed = True


class BlockingFakeOrchestrator(AnalysisOrchestrator):
    """The real orchestrator with a short, controllable provider delay."""

    def __init__(
        self,
        application: TrustedCeoApplication,
        run_store: RunStore,
        gateway: KeylessFakeReasoningGateway,
        *,
        report_root: Path,
    ) -> None:
        super().__init__(
            application,
            run_store,
            gateway,
            report_root=report_root,
        )
        self.started = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()
        self.failure: AIServiceError | None = None
        self.call_count = 0

    def continue_run(
        self,
        run_id: str,
        request: MutationBase,
    ) -> RunSnapshot:
        self.call_count += 1
        self.started.set()
        try:
            if not self.release.wait(2.0):
                raise AssertionError("blocking fake orchestrator was not released")
            if self.failure is not None:
                raise self.failure
            return super().continue_run(run_id, request)
        finally:
            self.finished.set()

    def reset(self, *, failure: AIServiceError | None = None) -> None:
        self.started.clear()
        self.release.clear()
        self.finished.clear()
        self.failure = failure


class AnalysisCoordinatorHttpTests(unittest.TestCase):
    def _runtime(
        self,
        root: Path,
        *,
        run_id: str,
    ) -> tuple[
        ServiceSettings,
        RunStore,
        AnalysisOrchestrator,
        BlockingFakeOrchestrator,
        int,
    ]:
        settings = ServiceSettings(
            host="127.0.0.1",
            port=8765,
            service_root=root / "runtime",
            internal_token=TOKEN,
            openai_api_key="keyless-test-ready",
            model="gpt-5.6",
        )
        store = RunStore(settings.service_root)
        application = TrustedCeoApplication(store.runs_root)
        gateway = KeylessFakeReasoningGateway(application.artifact_root)
        orchestrator = BlockingFakeOrchestrator(
            application,
            store,
            gateway,
            report_root=root / "reports",
        )
        created = orchestrator.create_run(CreateRunRequest(
            mission=mission_body(),
            run_owner_actor_id="local-browser-user",
            run_id=run_id,
        ))
        self.assertEqual("context_confirmation_required", created.workflow_status)
        self.assertEqual(0, orchestrator.call_count)
        return settings, store, orchestrator, orchestrator, created.revision

    def _wait_for_snapshot(
        self,
        client: TestClient,
        run_id: str,
        predicate: Callable[[dict[str, Any]], bool],
    ) -> dict[str, Any]:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            response = client.get(f"/v1/runs/{run_id}", headers=AUTH)
            self.assertEqual(200, response.status_code, response.text)
            snapshot = response.json()
            if predicate(snapshot):
                return snapshot
            time.sleep(0.01)
        self.fail("analysis worker did not publish its terminal checkpoint")

    def test_continue_returns_immediately_and_gates_other_mutations(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            run_id = "run_20260722T010000Z_1111111111111111"
            settings, store, orchestrator, gateway, revision = self._runtime(
                root,
                run_id=run_id,
            )
            questions = StubQuestionService()
            app = create_app(settings, orchestrator.application, orchestrator, questions)
            body = {
                "expected_revision": revision,
                "idempotency_key": "continue_async_work_0001",
            }

            fallback_release = threading.Timer(1.5, gateway.release.set)
            fallback_release.start()
            try:
                with TestClient(app) as client:
                    started_at = time.monotonic()
                    started = client.post(
                        f"/v1/runs/{run_id}/actions/continue",
                        headers=AUTH,
                        json=body,
                    )
                    elapsed = time.monotonic() - started_at

                    self.assertEqual(200, started.status_code, started.text)
                    self.assertLess(elapsed, 0.8)
                    active = started.json()
                    self.assertEqual("provider_work", active["pending_action"])
                    self.assertEqual([], active["allowed_actions"])
                    self.assertTrue(gateway.started.wait(0.5))
                    pending_receipt = store.read_idempotency_receipt(
                        run_id,
                        idempotency_key=body["idempotency_key"],
                        request_body=body,
                    )
                    self.assertIsNotNone(pending_receipt)
                    self.assertEqual(202, pending_receipt.status_code)
                    self.assertEqual(active, pending_receipt.response)

                    health_started = time.monotonic()
                    health = client.get("/health", headers=AUTH)
                    self.assertEqual(200, health.status_code, health.text)
                    self.assertLess(time.monotonic() - health_started, 0.8)
                    status = client.get(f"/v1/runs/{run_id}", headers=AUTH)
                    self.assertEqual(active, status.json())

                    duplicate = client.post(
                        f"/v1/runs/{run_id}/actions/continue",
                        headers=AUTH,
                        json=body,
                    )
                    self.assertEqual(200, duplicate.status_code, duplicate.text)
                    self.assertEqual(active, duplicate.json())
                    self.assertEqual(1, gateway.call_count)

                    conflicts = [
                        client.post(
                            f"/v1/runs/{run_id}/actions/continue",
                            headers=AUTH,
                            json={
                                **body,
                                "idempotency_key": "continue_async_work_0002",
                            },
                        ),
                        client.post(
                            f"/v1/runs/{run_id}/actions/retry",
                            headers=AUTH,
                            json={
                                **body,
                                "idempotency_key": "retry_async_work_0001",
                            },
                        ),
                        client.post(
                            f"/v1/runs/{run_id}/actions/resume",
                            headers=AUTH,
                            json={
                                **body,
                                "idempotency_key": "resume_async_work_0001",
                            },
                        ),
                        client.post(
                            f"/v1/runs/{run_id}/actions/stop",
                            headers=AUTH,
                            json={
                                **body,
                                "idempotency_key": "stop_async_work_0001",
                            },
                        ),
                        client.post(
                            f"/v1/runs/{run_id}/actions/cancel",
                            headers=AUTH,
                            json={
                                **body,
                                "idempotency_key": "cancel_async_work_0001",
                            },
                        ),
                        client.post(
                            f"/v1/runs/{run_id}/files",
                            headers=AUTH,
                            data={
                                "expected_revision": str(revision),
                                "idempotency_key": "upload_async_work_0001",
                            },
                            files={
                                "files": (
                                    "blocked.json",
                                    b"[]",
                                    "application/json",
                                ),
                            },
                        ),
                        client.post(
                            f"/v1/runs/{run_id}/human-responses",
                            headers={
                                **AUTH,
                                "X-Trusted-Ceo-Browser-Fingerprint": FINGERPRINT,
                            },
                            json={
                                **body,
                                "idempotency_key": "human_async_work_0001",
                                "decision": "approve",
                                "edits": {},
                                "rationale": None,
                            },
                        ),
                        client.request(
                            "DELETE",
                            f"/v1/runs/{run_id}",
                            headers=AUTH,
                            json={
                                **body,
                                "idempotency_key": "delete_async_work_0001",
                                "confirmed": True,
                            },
                        ),
                        client.post(
                            "/v1/runs",
                            headers=AUTH,
                            json={
                                "expected_revision": 0,
                                "idempotency_key": "create_async_work_0001",
                            },
                        ),
                        client.post(
                            f"/v1/runs/{run_id}/questions",
                            headers=AUTH,
                            json={
                                "expected_revision": revision,
                                "idempotency_key": "question_async_work_0001",
                                "question": "What changed?",
                                "scope_kind": "issue",
                                "scope_instance_id": "issue_main",
                                "privacy_classification": "poc_deidentified",
                            },
                        ),
                    ]
                    for conflict in conflicts:
                        self.assertEqual(409, conflict.status_code, conflict.text)
                        self.assertEqual("IDEMPOTENCY_CONFLICT", conflict.json()["code"])

                    gateway.release.set()
                    completed = self._wait_for_snapshot(
                        client,
                        run_id,
                        lambda value: value["revision"] > revision,
                    )
                    self.assertEqual("context_confirmation_required", completed["workflow_status"])
                    self.assertEqual("human_response", completed["pending_action"])
                    self.assertEqual(["submit_hitl"], completed["allowed_actions"])
                    self.assertEqual("awaiting_human", store.read_manifest(run_id).status)
                    receipt = store.read_idempotency_receipt(
                        run_id,
                        idempotency_key=body["idempotency_key"],
                        request_body=body,
                    )
                    self.assertIsNotNone(receipt)
                    self.assertEqual(completed, receipt.response)

                    replay = client.post(
                        f"/v1/runs/{run_id}/actions/continue",
                        headers=AUTH,
                        json=body,
                    )
                    self.assertEqual(completed, replay.json())
                    self.assertEqual(1, gateway.call_count)
            finally:
                gateway.release.set()
                fallback_release.cancel()

            self.assertTrue(questions.closed)

    def test_failure_manifest_is_pollable_and_retry_runs_one_provider_step(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            run_id = "run_20260722T020000Z_2222222222222222"
            settings, store, orchestrator, gateway, revision = self._runtime(
                root,
                run_id=run_id,
            )
            gateway.failure = AIServiceError(
                "AI_TRANSIENT_FAILURE",
                "short fake provider failure",
                retryable=True,
            )
            app = create_app(
                settings,
                orchestrator.application,
                orchestrator,
                StubQuestionService(),
            )
            continue_body = {
                "expected_revision": revision,
                "idempotency_key": "continue_async_failure_0001",
            }

            fallback_release = threading.Timer(1.0, gateway.release.set)
            fallback_release.start()
            with TestClient(app) as client:
                started = client.post(
                    f"/v1/runs/{run_id}/actions/continue",
                    headers=AUTH,
                    json=continue_body,
                )
                self.assertEqual(200, started.status_code, started.text)
                self.assertEqual([], started.json()["allowed_actions"])
                self.assertTrue(gateway.started.wait(0.5))
                gateway.release.set()

                failed = self._wait_for_snapshot(
                    client,
                    run_id,
                    lambda value: value["pending_action"] == "retry",
                )
                self.assertEqual("retryable_failure", store.read_manifest(run_id).status)
                self.assertEqual("AI_TRANSIENT_FAILURE", failed["error"]["code"])
                failed_receipt = store.read_idempotency_receipt(
                    run_id,
                    idempotency_key=continue_body["idempotency_key"],
                    request_body=continue_body,
                )
                self.assertIsNotNone(failed_receipt)
                self.assertEqual(200, failed_receipt.status_code)
                self.assertEqual(failed, failed_receipt.response)

                gateway.reset()
                retry_body = {
                    "expected_revision": failed["revision"],
                    "idempotency_key": "retry_async_failure_0001",
                }
                retried = client.post(
                    f"/v1/runs/{run_id}/actions/retry",
                    headers=AUTH,
                    json=retry_body,
                )
                self.assertEqual(200, retried.status_code, retried.text)
                self.assertEqual("provider_work", retried.json()["pending_action"])
                self.assertEqual([], retried.json()["allowed_actions"])
                self.assertTrue(gateway.started.wait(0.5))
                duplicate = client.post(
                    f"/v1/runs/{run_id}/actions/retry",
                    headers=AUTH,
                    json=retry_body,
                )
                self.assertEqual(retried.json(), duplicate.json())
                self.assertEqual(2, gateway.call_count)
                gateway.release.set()

                completed = self._wait_for_snapshot(
                    client,
                    run_id,
                    lambda value: value["revision"] > failed["revision"],
                )
                self.assertEqual("context_confirmation_required", completed["workflow_status"])
                self.assertEqual("human_response", completed["pending_action"])
                self.assertEqual("awaiting_human", store.read_manifest(run_id).status)
                receipt = store.read_idempotency_receipt(
                    run_id,
                    idempotency_key=retry_body["idempotency_key"],
                    request_body={**retry_body, "action": "retry"},
                )
                self.assertIsNotNone(receipt)
                self.assertEqual(completed, receipt.response)
            fallback_release.cancel()

    def test_resume_runs_provider_step_and_shutdown_waits_for_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            run_id = "run_20260722T030000Z_3333333333333333"
            settings, store, orchestrator, gateway, revision = self._runtime(
                root,
                run_id=run_id,
            )
            stopped = orchestrator.control_run(
                run_id,
                "stop",
                MutationBase(
                    expected_revision=revision,
                    idempotency_key="stop_before_async_resume_0001",
                ),
            )
            self.assertEqual("resume", stopped.pending_action)
            questions = StubQuestionService()
            app = create_app(settings, orchestrator.application, orchestrator, questions)
            resume_body = {
                "expected_revision": revision,
                "idempotency_key": "resume_async_work_0001",
            }

            release = threading.Timer(0.15, gateway.release.set)
            with TestClient(app) as client:
                resumed = client.post(
                    f"/v1/runs/{run_id}/actions/resume",
                    headers=AUTH,
                    json=resume_body,
                )
                self.assertEqual(200, resumed.status_code, resumed.text)
                self.assertEqual("provider_work", resumed.json()["pending_action"])
                self.assertEqual([], resumed.json()["allowed_actions"])
                self.assertTrue(gateway.started.wait(0.5))
                release.start()
                shutdown_started = time.monotonic()

            release.cancel()
            self.assertGreaterEqual(time.monotonic() - shutdown_started, 0.10)
            self.assertTrue(gateway.finished.is_set())
            self.assertTrue(questions.closed)
            manifest = store.read_manifest(run_id)
            self.assertEqual("awaiting_human", manifest.status)
            self.assertGreater(manifest.engine_revision, revision)
            receipt = store.read_idempotency_receipt(
                run_id,
                idempotency_key=resume_body["idempotency_key"],
                request_body={**resume_body, "action": "resume"},
            )
            self.assertIsNotNone(receipt)

    def test_completed_request_replays_while_another_run_is_active(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            first_run_id = "run_20260722T040000Z_4444444444444444"
            _, _, orchestrator, gateway, first_revision = self._runtime(
                root,
                run_id=first_run_id,
            )
            first_request = MutationBase(
                expected_revision=first_revision,
                idempotency_key="continue_completed_replay_0001",
            )
            gateway.release.set()
            completed = orchestrator.continue_run(first_run_id, first_request)
            gateway.reset()
            second_run_id = "run_20260722T040100Z_5555555555555555"
            second = orchestrator.create_run(CreateRunRequest(
                mission=mission_body(),
                run_owner_actor_id="local-browser-user",
                run_id=second_run_id,
            ))
            coordinator = AnalysisCoordinator(orchestrator)

            try:
                coordinator.start(
                    second_run_id,
                    "continue",
                    MutationBase(
                        expected_revision=second.revision,
                        idempotency_key="continue_other_active_0001",
                    ),
                )
                self.assertTrue(gateway.started.wait(0.5))

                replay = coordinator.start(first_run_id, "continue", first_request)

                self.assertEqual(completed, replay)
                self.assertEqual(2, gateway.call_count)
            finally:
                gateway.release.set()
                coordinator.close()

    def test_shutdown_has_a_bound_when_provider_does_not_return(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            run_id = "run_20260722T050000Z_6666666666666666"
            settings, store, orchestrator, gateway, revision = self._runtime(
                root,
                run_id=run_id,
            )
            questions = StubQuestionService()
            app = create_app(
                settings,
                orchestrator.application,
                orchestrator,
                questions,
            )

            body = {
                "expected_revision": revision,
                "idempotency_key": "continue_shutdown_bound_0001",
            }
            try:
                with TestClient(app) as client:
                    started = client.post(
                        f"/v1/runs/{run_id}/actions/continue",
                        headers=AUTH,
                        json=body,
                    )
                    self.assertEqual(200, started.status_code, started.text)
                    self.assertTrue(gateway.started.wait(0.5))
                    shutdown_started = time.monotonic()

                elapsed = time.monotonic() - shutdown_started
                self.assertLess(elapsed, 1.2)
                self.assertTrue(questions.closed)
            finally:
                gateway.release.set()
                self.assertTrue(gateway.finished.wait(1.0))
                deadline = time.monotonic() + 1.0
                while True:
                    receipt = store.read_idempotency_receipt(
                        run_id,
                        idempotency_key=body["idempotency_key"],
                        request_body=body,
                    )
                    if receipt is not None and receipt.status_code == 200:
                        break
                    if time.monotonic() >= deadline:
                        self.fail("shutdown worker did not finish its receipt")
                    time.sleep(0.01)

    def test_pending_controlled_receipt_recovers_without_repeating_work(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            run_id = "run_20260722T060000Z_7777777777777777"
            settings, store, orchestrator, gateway, revision = self._runtime(
                root,
                run_id=run_id,
            )
            manifest = store.read_manifest(run_id)
            store.save_manifest(
                manifest.model_copy(update={
                    "status": "retryable_failure",
                    "error_code": "AI_TRANSIENT_FAILURE",
                }),
                expected_revision=revision,
            )
            failed = orchestrator.snapshot(run_id)
            retry_body = {
                "expected_revision": revision,
                "idempotency_key": "retry_pending_receipt_0001",
            }
            pending = RunSnapshot.model_validate({
                **failed.model_dump(mode="python"),
                "pending_action": "provider_work",
                "allowed_actions": [],
                "hitl_card": None,
                "error": None,
            })
            store.store_idempotency_receipt(
                run_id,
                idempotency_key=retry_body["idempotency_key"],
                request_body={**retry_body, "action": "retry"},
                status_code=202,
                response=pending.model_dump(mode="json"),
            )
            transition = orchestrator.control_run(
                run_id,
                "retry",
                MutationBase(
                    expected_revision=revision,
                    idempotency_key="analysis_control_interrupted_0001",
                ),
            )
            gateway.release.set()
            completed = orchestrator.continue_run(
                run_id,
                MutationBase(
                    expected_revision=transition.revision,
                    idempotency_key="analysis_continue_interrupted_0001",
                ),
            )
            app = create_app(
                settings,
                orchestrator.application,
                orchestrator,
                StubQuestionService(),
            )
            recovered_receipt = store.read_idempotency_receipt(
                run_id,
                idempotency_key=retry_body["idempotency_key"],
                request_body={**retry_body, "action": "retry"},
            )
            self.assertIsNotNone(recovered_receipt)
            self.assertEqual(200, recovered_receipt.status_code)
            self.assertEqual(
                completed.model_dump(mode="json"),
                recovered_receipt.response,
            )

            with TestClient(app) as client:
                replay = client.post(
                    f"/v1/runs/{run_id}/actions/retry",
                    headers=AUTH,
                    json=retry_body,
                )

            self.assertEqual(200, replay.status_code, replay.text)
            self.assertEqual(completed.model_dump(mode="json"), replay.json())
            self.assertEqual(1, gateway.call_count)
            receipt = store.read_idempotency_receipt(
                run_id,
                idempotency_key=retry_body["idempotency_key"],
                request_body={**retry_body, "action": "retry"},
            )
            self.assertIsNotNone(receipt)
            self.assertEqual(200, receipt.status_code)
            self.assertEqual(completed.model_dump(mode="json"), receipt.response)

    def test_acceptance_receipt_exists_before_background_worker_starts(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            run_id = "run_20260722T070000Z_8888888888888888"
            _, store, orchestrator, _, revision = self._runtime(root, run_id=run_id)
            deferred: list[Callable[[], None]] = []
            coordinator = AnalysisCoordinator(
                orchestrator,
                worker_starter=lambda work: deferred.append(work),
            )
            request = MutationBase(
                expected_revision=revision,
                idempotency_key="continue_acceptance_receipt_0001",
            )

            accepted = coordinator.start(run_id, "continue", request)

            self.assertEqual(1, len(deferred))
            receipt = store.read_idempotency_receipt(
                run_id,
                idempotency_key=request.idempotency_key,
                request_body=request.model_dump(mode="json"),
            )
            self.assertIsNotNone(receipt)
            self.assertEqual(202, receipt.status_code)
            self.assertEqual(accepted.model_dump(mode="json"), receipt.response)

    def test_startup_recovers_only_the_run_with_pending_analysis_work(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            interrupted_run_id = "run_20260722T080000Z_9999999999999999"
            settings, store, orchestrator, _, revision = self._runtime(
                root,
                run_id=interrupted_run_id,
            )
            idle_run_id = "run_20260722T080100Z_aaaaaaaaaaaaaaaa"
            orchestrator.create_run(CreateRunRequest(
                mission=mission_body(),
                run_owner_actor_id="local-browser-user",
                run_id=idle_run_id,
            ))
            request = MutationBase(
                expected_revision=revision,
                idempotency_key="continue_interrupted_startup_0001",
            )
            current = orchestrator.snapshot(interrupted_run_id)
            pending = RunSnapshot.model_validate({
                **current.model_dump(mode="python"),
                "pending_action": "provider_work",
                "allowed_actions": [],
                "hitl_card": None,
                "error": None,
            })
            store.store_idempotency_receipt(
                interrupted_run_id,
                idempotency_key=request.idempotency_key,
                request_body=request.model_dump(mode="json"),
                status_code=202,
                response=pending.model_dump(mode="json"),
            )

            app = create_app(
                settings,
                orchestrator.application,
                orchestrator,
                StubQuestionService(),
            )
            app.state.analysis_coordinator.close()

            interrupted = store.read_manifest(interrupted_run_id)
            self.assertEqual("retryable_failure", interrupted.status)
            self.assertEqual("AI_TRANSIENT_FAILURE", interrupted.error_code)
            self.assertEqual("running", store.read_manifest(idle_run_id).status)
            receipt = store.read_idempotency_receipt(
                interrupted_run_id,
                idempotency_key=request.idempotency_key,
                request_body=request.model_dump(mode="json"),
            )
            self.assertIsNotNone(receipt)
            self.assertEqual(200, receipt.status_code)
            self.assertEqual("retry", receipt.response["pending_action"])

    def test_pending_resume_interrupted_before_control_becomes_retryable(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            run_id = "run_20260722T090000Z_bbbbbbbbbbbbbbbb"
            settings, store, orchestrator, _, revision = self._runtime(
                root,
                run_id=run_id,
            )
            stopped = orchestrator.control_run(
                run_id,
                "stop",
                MutationBase(
                    expected_revision=revision,
                    idempotency_key="stop_before_interrupted_resume_0001",
                ),
            )
            request = MutationBase(
                expected_revision=revision,
                idempotency_key="resume_interrupted_startup_0001",
            )
            pending = RunSnapshot.model_validate({
                **stopped.model_dump(mode="python"),
                "pending_action": "provider_work",
                "allowed_actions": [],
                "hitl_card": None,
                "error": None,
            })
            body = {**request.model_dump(mode="json"), "action": "resume"}
            store.store_idempotency_receipt(
                run_id,
                idempotency_key=request.idempotency_key,
                request_body=body,
                status_code=202,
                response=pending.model_dump(mode="json"),
            )

            app = create_app(
                settings,
                orchestrator.application,
                orchestrator,
                StubQuestionService(),
            )
            app.state.analysis_coordinator.close()

            manifest = store.read_manifest(run_id)
            self.assertEqual("retryable_failure", manifest.status)
            self.assertEqual("AI_TRANSIENT_FAILURE", manifest.error_code)
            receipt = store.read_idempotency_receipt(
                run_id,
                idempotency_key=request.idempotency_key,
                request_body=body,
            )
            self.assertIsNotNone(receipt)
            self.assertEqual(200, receipt.status_code)
            self.assertEqual("retry", receipt.response["pending_action"])

    def test_worker_start_failure_withdraws_the_acceptance_receipt(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            run_id = "run_20260722T100000Z_cccccccccccccccc"
            _, store, orchestrator, _, revision = self._runtime(root, run_id=run_id)

            def fail_to_start(_work: Callable[[], None]) -> None:
                raise RuntimeError("thread unavailable")

            coordinator = AnalysisCoordinator(
                orchestrator,
                worker_starter=fail_to_start,
            )
            request = MutationBase(
                expected_revision=revision,
                idempotency_key="continue_worker_start_failure_0001",
            )

            with self.assertRaisesRegex(RuntimeError, "thread unavailable"):
                coordinator.start(run_id, "continue", request)

            self.assertIsNone(store.read_idempotency_receipt(
                run_id,
                idempotency_key=request.idempotency_key,
                request_body=request.model_dump(mode="json"),
            ))

    def test_lifespan_holds_service_root_lease_until_worker_finishes(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            run_id = "run_20260722T110000Z_dddddddddddddddd"
            settings, _, orchestrator, gateway, revision = self._runtime(
                root,
                run_id=run_id,
            )
            lease = ServiceRootLease.acquire(settings.service_root)
            app = create_app(
                settings,
                orchestrator.application,
                orchestrator,
                StubQuestionService(),
                service_lease=lease,
            )
            fallback_release = threading.Timer(1.5, gateway.release.set)
            fallback_release.start()
            try:
                with TestClient(app) as client:
                    response = client.post(
                        f"/v1/runs/{run_id}/actions/continue",
                        headers=AUTH,
                        json={
                            "expected_revision": revision,
                            "idempotency_key": "continue_shutdown_lease_0001",
                        },
                    )
                    self.assertEqual(200, response.status_code, response.text)
                    self.assertTrue(gateway.started.wait(0.5))

                self.assertFalse(gateway.finished.is_set())
                try:
                    unexpected = ServiceRootLease.acquire(settings.service_root)
                except RuntimeError as error:
                    self.assertIn("already in use", str(error))
                else:
                    unexpected.close()
                    self.fail("service root lease was released before worker exit")
            finally:
                gateway.release.set()
                fallback_release.cancel()

            self.assertTrue(gateway.finished.wait(1.0))
            deadline = time.monotonic() + 1.0
            while True:
                try:
                    restarted = ServiceRootLease.acquire(settings.service_root)
                    break
                except RuntimeError:
                    if time.monotonic() >= deadline:
                        self.fail("service root lease was not released after worker exit")
                    time.sleep(0.01)
            restarted.close()


if __name__ == "__main__":
    unittest.main()
