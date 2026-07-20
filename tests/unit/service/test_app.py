from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from trusted_ceo_agent.application.run_application import TrustedCeoApplication
from trusted_ceo_agent.service.app import _draft_mission, create_app
from trusted_ceo_agent.service.main import MissingApiKeyGateway, build_app
from trusted_ceo_agent.service.openai_gateway import AIServiceError
from trusted_ceo_agent.service.orchestrator import AnalysisOrchestrator
from trusted_ceo_agent.service.questions import (
    QuestionRequest,
    QuestionSnapshot,
)
from trusted_ceo_agent.service.run_store import RunStore
from trusted_ceo_agent.service.settings import ServiceSettings
from trusted_ceo_agent.service.testing.fake_openai import KeylessFakeReasoningGateway
from tests.support import confirmed_mission, mission_body


ROOT = Path(__file__).resolve().parents[3]
TOKEN = "internal_token_for_local_test_1234567890"
AUTH = {"X-Trusted-Ceo-Internal-Token": TOKEN}
FINGERPRINT = "d" * 64


class StubQuestionService:
    def __init__(self) -> None:
        self.snapshots: dict[str, QuestionSnapshot] = {}
        self.closed = False

    def start(self, run_id: str, request: QuestionRequest) -> QuestionSnapshot:
        snapshot = QuestionSnapshot(
            request_id="questionrequest_" + "a" * 24,
            run_id=run_id,
            revision=request.expected_revision,
            state="queued",
            scope_kind=request.scope_kind,
            scope_instance_id=request.scope_instance_id,
        )
        self.snapshots[snapshot.request_id] = snapshot
        return snapshot

    def get(self, run_id: str, request_id: str) -> QuestionSnapshot:
        snapshot = self.snapshots.get(request_id)
        if snapshot is None or snapshot.run_id != run_id:
            raise FileNotFoundError(request_id)
        return snapshot

    def close(self) -> None:
        self.closed = True


class ServiceAppTests(unittest.TestCase):
    def test_default_browser_mission_has_an_executable_decision_unit(self) -> None:
        self.assertEqual([{
            "decision_unit_ref": "unit_enterprise",
            "unit_type": "enterprise",
            "scope_key": "enterprise",
            "owner_role": "ceo",
            "deadline": None,
        }], _draft_mission()["decision_units"])

    def test_internal_token_keyless_health_and_context_hitl_contract(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            settings = ServiceSettings(
                host="127.0.0.1",
                port=8765,
                service_root=root / "runtime",
                internal_token=TOKEN,
                openai_api_key=None,
                model="gpt-5.6",
            )
            store = RunStore(settings.service_root)
            application = TrustedCeoApplication(store.runs_root)
            orchestrator = AnalysisOrchestrator(
                application,
                store,
                KeylessFakeReasoningGateway(application.artifact_root),
                report_root=root / "reports",
            )
            client = TestClient(
                create_app(
                    settings,
                    application,
                    orchestrator,
                    StubQuestionService(),
                )
            )

            self.assertEqual(401, client.get("/health").status_code)
            health = client.get("/health", headers=AUTH)
            self.assertEqual(200, health.status_code)
            self.assertEqual(
                {"status": "ok", "ai_ready": False, "model": "gpt-5.6"},
                health.json(),
            )
            self.assertEqual("no-store", health.headers["cache-control"])
            self.assertEqual("nosniff", health.headers["x-content-type-options"])
            self.assertEqual("0", health.headers["x-trusted-ceo-input-tokens"])
            self.assertEqual("0", health.headers["x-trusted-ceo-output-tokens"])
            self.assertEqual(404, client.get("/docs", headers=AUTH).status_code)
            self.assertNotIn("access-control-allow-origin", health.headers)

            created = client.post(
                "/v1/runs",
                headers=AUTH,
                json={
                    "expected_revision": 0,
                    "idempotency_key": "create_browser_run_0001",
                },
            )
            self.assertEqual(200, created.status_code, created.text)
            snapshot = created.json()
            run_id = snapshot["run_id"]
            self.assertEqual("service", snapshot["provider_kind"])
            self.assertEqual("context_confirmation_required", snapshot["workflow_status"])
            self.assertNotIn(str(root), created.text)

            status = client.get(f"/v1/runs/{run_id}", headers=AUTH)
            self.assertEqual(snapshot, status.json())
            pending = client.post(
                f"/v1/runs/{run_id}/actions/continue",
                headers=AUTH,
                json={
                    "expected_revision": 1,
                    "idempotency_key": "continue_browser_run_0001",
                },
            )
            self.assertEqual(200, pending.status_code, pending.text)
            self.assertEqual("human_response", pending.json()["pending_action"])
            self.assertNotIn("nonce", pending.text.casefold())

            approved = client.post(
                f"/v1/runs/{run_id}/human-responses",
                headers={
                    **AUTH,
                    "X-Trusted-Ceo-Browser-Fingerprint": FINGERPRINT,
                },
                json={
                    "expected_revision": 2,
                    "idempotency_key": "approve_browser_run_0001",
                    "decision": "approve",
                    "edits": {},
                    "rationale": None,
                },
            )
            self.assertEqual(200, approved.status_code, approved.text)
            self.assertEqual("context_ready", approved.json()["workflow_status"])

            stale = client.post(
                f"/v1/runs/{run_id}/actions/continue",
                headers=AUTH,
                json={
                    "expected_revision": 1,
                    "idempotency_key": "continue_browser_stale_1",
                },
            )
            self.assertEqual(409, stale.status_code)
            self.assertEqual("STALE_REVISION", stale.json()["code"])
            self.assertNotIn(str(root), stale.text)
            self.assertEqual(
                404,
                client.get("/v1/runs/run_missing_01234567", headers=AUTH).status_code,
            )

    def test_app_lifespan_closes_question_service(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            settings = ServiceSettings(
                host="127.0.0.1",
                port=8765,
                service_root=root / "runtime",
                internal_token=TOKEN,
                openai_api_key=None,
                model="gpt-5.6",
            )
            store = RunStore(settings.service_root)
            application = TrustedCeoApplication(store.runs_root)
            orchestrator = AnalysisOrchestrator(
                application,
                store,
                KeylessFakeReasoningGateway(application.artifact_root),
                report_root=root / "reports",
            )
            questions = StubQuestionService()

            with TestClient(
                create_app(settings, application, orchestrator, questions)
            ) as client:
                self.assertEqual(200, client.get("/health", headers=AUTH).status_code)
                self.assertFalse(questions.closed)

            self.assertTrue(questions.closed)

    def test_question_endpoints_return_public_python_snapshots(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            settings = ServiceSettings(
                host="127.0.0.1",
                port=8765,
                service_root=root / "runtime",
                internal_token=TOKEN,
                openai_api_key=None,
                model="gpt-5.6",
            )
            store = RunStore(settings.service_root)
            application = TrustedCeoApplication(store.runs_root)
            orchestrator = AnalysisOrchestrator(
                application,
                store,
                KeylessFakeReasoningGateway(application.artifact_root),
                report_root=root / "reports",
            )
            questions = StubQuestionService()
            client = TestClient(
                create_app(settings, application, orchestrator, questions)
            )
            run_id = "run_http_questions_12345678"
            submitted = client.post(
                f"/v1/runs/{run_id}/questions",
                headers=AUTH,
                json={
                    "expected_revision": 2,
                    "idempotency_key": "question_http_request_0001",
                    "question": "Which verified value answers this question?",
                    "scope_kind": "issue",
                    "scope_instance_id": "issue_main",
                    "privacy_classification": "poc_deidentified",
                },
            )

            self.assertEqual(202, submitted.status_code, submitted.text)
            snapshot = submitted.json()
            self.assertEqual("queued", snapshot["state"])
            self.assertEqual(run_id, snapshot["run_id"])
            self.assertNotIn("idempotency_key", snapshot)
            self.assertNotIn("question", snapshot)

            loaded = client.get(
                f"/v1/runs/{run_id}/questions/{snapshot['request_id']}",
                headers=AUTH,
            )
            self.assertEqual(200, loaded.status_code, loaded.text)
            self.assertEqual(snapshot, loaded.json())
            self.assertEqual(
                404,
                client.get(
                    f"/v1/runs/{run_id}/questions/questionrequest_{'f' * 24}",
                    headers=AUTH,
                ).status_code,
            )

    def test_keyless_build_exposes_questions_and_fails_closed_at_gateway(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            environment = {
                "TRUSTED_CEO_INTERNAL_TOKEN": TOKEN,
                "TRUSTED_CEO_SERVICE_ROOT": directory,
            }
            with patch.dict(os.environ, environment, clear=True):
                settings, app = build_app()

            self.assertFalse(settings.ai_ready)
            response = TestClient(app).post(
                "/v1/runs/run_keyless_questions_12345678/questions",
                headers=AUTH,
                json={},
            )
            self.assertEqual(422, response.status_code, response.text)

            with self.assertRaises(AIServiceError) as caught:
                MissingApiKeyGateway().execute_question({})
            self.assertEqual("AI_AUTH_FAILURE", caught.exception.code)
            self.assertFalse(caught.exception.retryable)

    def test_upload_route_preserves_logical_path_order_and_rejects_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            settings = ServiceSettings(
                host='127.0.0.1',
                port=8765,
                service_root=root / 'runtime',
                internal_token=TOKEN,
                openai_api_key=None,
                model='gpt-5.6',
            )
            store = RunStore(settings.service_root)
            application = TrustedCeoApplication(store.runs_root)
            orchestrator = AnalysisOrchestrator(
                application,
                store,
                KeylessFakeReasoningGateway(application.artifact_root),
                report_root=root / 'reports',
            )
            client = TestClient(create_app(
                settings,
                application,
                orchestrator,
                StubQuestionService(),
            ))
            created = client.post(
                '/v1/runs',
                headers=AUTH,
                json={
                    'expected_revision': 0,
                    'idempotency_key': 'create_logical_paths_0001',
                },
            ).json()
            run_id = created['run_id']
            files = [
                ('files', ('plan.md', b'# Plan\n', 'text/markdown')),
                ('files', ('data.csv', b'name,value\na,1\n', 'text/csv')),
            ]
            with patch.object(
                orchestrator,
                'attach_files',
                return_value=orchestrator.snapshot(run_id),
            ) as attach:
                response = client.post(
                    f'/v1/runs/{run_id}/files',
                    headers=AUTH,
                    data={
                        'expected_revision': '1',
                        'idempotency_key': 'upload_logical_paths_0001',
                        'logical_paths': ['strategy/plan.md', 'folder-b/data.csv'],
                    },
                    files=files,
                )

            self.assertEqual(200, response.status_code, response.text)
            uploads = attach.call_args.args[2]
            self.assertEqual(
                ['strategy/plan.md', 'folder-b/data.csv'],
                [item.logical_path for item in uploads],
            )

            mismatch = client.post(
                f'/v1/runs/{run_id}/files',
                headers=AUTH,
                data={
                    'expected_revision': '1',
                    'idempotency_key': 'upload_logical_paths_0002',
                    'logical_paths': ['strategy/plan.md'],
                },
                files=files,
            )
            self.assertEqual(422, mismatch.status_code, mismatch.text)
            self.assertEqual('INPUT_POLICY_FAILURE', mismatch.json()['code'])

    def test_idempotent_create_upload_controls_and_delete_are_http_safe(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            settings = ServiceSettings(
                host="127.0.0.1",
                port=8765,
                service_root=root / "runtime",
                internal_token=TOKEN,
                openai_api_key=None,
                model="gpt-5.6",
            )
            store = RunStore(settings.service_root)
            application = TrustedCeoApplication(store.runs_root)
            orchestrator = AnalysisOrchestrator(
                application,
                store,
                KeylessFakeReasoningGateway(application.artifact_root),
                report_root=root / "reports",
            )
            client = TestClient(
                create_app(
                    settings,
                    application,
                    orchestrator,
                    StubQuestionService(),
                )
            )
            create_body = {
                "expected_revision": 0,
                "idempotency_key": "create_upload_control_0001",
            }

            created = client.post("/v1/runs", headers=AUTH, json=create_body)
            self.assertEqual(200, created.status_code, created.text)
            self.assertEqual(
                created.json(),
                client.post("/v1/runs", headers=AUTH, json=create_body).json(),
            )
            conflict = client.post(
                "/v1/runs",
                headers=AUTH,
                json={**create_body, "mission": mission_body()},
            )
            self.assertEqual(409, conflict.status_code, conflict.text)
            self.assertEqual("IDEMPOTENCY_CONFLICT", conflict.json()["code"])

            run_id = created.json()["run_id"]
            upload_data = {
                "expected_revision": "1",
                "idempotency_key": "upload_browser_data_0001",
            }
            upload_files = {
                "files": (
                    "monthly.json",
                    b'[{"period":"2026-01","gross_margin":"0.42"}]',
                    "application/json",
                ),
            }
            uploaded = client.post(
                f"/v1/runs/{run_id}/files",
                headers=AUTH,
                data=upload_data,
                files=upload_files,
            )
            self.assertEqual(200, uploaded.status_code, uploaded.text)
            self.assertEqual(2, uploaded.json()["revision"])
            replay = client.post(
                f"/v1/runs/{run_id}/files",
                headers=AUTH,
                data=upload_data,
                files=upload_files,
            )
            self.assertEqual(uploaded.json(), replay.json())

            stopped = client.post(
                f"/v1/runs/{run_id}/actions/stop",
                headers=AUTH,
                json={
                    "expected_revision": 2,
                    "idempotency_key": "stop_browser_run_0001",
                },
            )
            self.assertEqual(200, stopped.status_code, stopped.text)
            self.assertEqual("stopped_by_human", stopped.json()["workflow_status"])
            self.assertEqual("resume", stopped.json()["pending_action"])
            self.assertEqual(["resume"], stopped.json()["allowed_actions"])
            self.assertEqual(
                stopped.json(),
                client.post(
                    f"/v1/runs/{run_id}/actions/stop",
                    headers=AUTH,
                    json={
                        "expected_revision": 2,
                        "idempotency_key": "stop_browser_run_0001",
                    },
                ).json(),
            )

            resumed = client.post(
                f"/v1/runs/{run_id}/actions/resume",
                headers=AUTH,
                json={
                    "expected_revision": 2,
                    "idempotency_key": "resume_browser_run_0001",
                },
            )
            self.assertEqual(200, resumed.status_code, resumed.text)
            self.assertEqual("provider_work", resumed.json()["pending_action"])

            deleted = client.request(
                "DELETE",
                f"/v1/runs/{run_id}",
                headers=AUTH,
                json={
                    "expected_revision": 2,
                    "idempotency_key": "delete_browser_run_0001",
                    "confirmed": True,
                },
            )
            self.assertEqual(204, deleted.status_code, deleted.text)
            replay_delete = client.request(
                "DELETE",
                f"/v1/runs/{run_id}",
                headers=AUTH,
                json={
                    "expected_revision": 2,
                    "idempotency_key": "delete_browser_run_0001",
                    "confirmed": True,
                },
            )
            self.assertEqual(204, replay_delete.status_code, replay_delete.text)
            self.assertEqual(404, client.get(f"/v1/runs/{run_id}", headers=AUTH).status_code)

            second = client.post(
                "/v1/runs",
                headers=AUTH,
                json={
                    "expected_revision": 0,
                    "idempotency_key": "create_cancel_run_0001",
                },
            ).json()
            cancelled = client.post(
                f"/v1/runs/{second['run_id']}/actions/cancel",
                headers=AUTH,
                json={
                    "expected_revision": 1,
                    "idempotency_key": "cancel_browser_run_0001",
                },
            )
            self.assertEqual(200, cancelled.status_code, cancelled.text)
            self.assertEqual("cancelled", cancelled.json()["workflow_status"])

    def test_missing_api_key_becomes_a_safe_retryable_snapshot(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            settings = ServiceSettings(
                host="127.0.0.1",
                port=8765,
                service_root=root / "runtime",
                internal_token=TOKEN,
                openai_api_key=None,
                model="gpt-5.6",
            )
            store = RunStore(settings.service_root)
            application = TrustedCeoApplication(store.runs_root)
            orchestrator = AnalysisOrchestrator(
                application,
                store,
                MissingApiKeyGateway(),
                report_root=root / "reports",
            )
            client = TestClient(
                create_app(
                    settings,
                    application,
                    orchestrator,
                    StubQuestionService(),
                )
            )
            created = client.post(
                "/v1/runs",
                headers=AUTH,
                json={
                    "expected_revision": 0,
                    "idempotency_key": "create_missing_key_0001",
                    "mission": confirmed_mission(),
                },
            ).json()
            run_id = created["run_id"]
            uploaded = client.post(
                f"/v1/runs/{run_id}/files",
                headers=AUTH,
                data={
                    "expected_revision": "1",
                    "idempotency_key": "upload_missing_key_0001",
                },
                files={
                    "files": (
                        "monthly.json",
                        b'[{"period":"2026-01","gross_margin":"0.42"}]',
                        "application/json",
                    ),
                },
            )
            self.assertEqual(200, uploaded.status_code, uploaded.text)

            snapshot = uploaded.json()
            unavailable = None
            approval_count = 0
            for sequence in range(12):
                if snapshot["pending_action"] == "human_response":
                    approval_count += 1
                    advanced = client.post(
                        f"/v1/runs/{run_id}/human-responses",
                        headers={
                            **AUTH,
                            "X-Trusted-Ceo-Browser-Fingerprint": FINGERPRINT,
                        },
                        json={
                            "expected_revision": snapshot["revision"],
                            "idempotency_key": (
                                f"approve_missing_key_{sequence:04d}"
                            ),
                            "decision": "approve",
                            "edits": {},
                            "rationale": None,
                        },
                    )
                else:
                    self.assertEqual("provider_work", snapshot["pending_action"])
                    advanced = client.post(
                        f"/v1/runs/{run_id}/actions/continue",
                        headers=AUTH,
                        json={
                            "expected_revision": snapshot["revision"],
                            "idempotency_key": (
                                f"continue_missing_key_{sequence:04d}"
                            ),
                        },
                    )
                if advanced.status_code == 503:
                    unavailable = advanced
                    break
                self.assertEqual(200, advanced.status_code, advanced.text)
                snapshot = advanced.json()
            self.assertEqual(1, approval_count)
            self.assertIsNotNone(unavailable)
            self.assertEqual(503, unavailable.status_code, unavailable.text)
            self.assertEqual("AI_AUTH_FAILURE", unavailable.json()["code"])
            self.assertNotIn(str(root), unavailable.text)

            failed = client.get(f"/v1/runs/{run_id}", headers=AUTH)
            self.assertEqual("retry", failed.json()["pending_action"])
            self.assertEqual("AI_AUTH_FAILURE", failed.json()["error"]["code"])
            retried = client.post(
                f"/v1/runs/{run_id}/actions/retry",
                headers=AUTH,
                json={
                    "expected_revision": failed.json()["revision"],
                    "idempotency_key": "retry_missing_key_0001",
                },
            )
            self.assertEqual(200, retried.status_code, retried.text)
            self.assertEqual("provider_work", retried.json()["pending_action"])


if __name__ == "__main__":
    unittest.main()
