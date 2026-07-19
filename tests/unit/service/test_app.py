from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from trusted_ceo_agent.application.run_application import TrustedCeoApplication
from trusted_ceo_agent.service.app import create_app
from trusted_ceo_agent.service.main import MissingApiKeyGateway
from trusted_ceo_agent.service.orchestrator import AnalysisOrchestrator
from trusted_ceo_agent.service.run_store import RunStore
from trusted_ceo_agent.service.settings import ServiceSettings
from trusted_ceo_agent.service.testing.fake_openai import KeylessFakeReasoningGateway
from tests.support import confirmed_mission, mission_body


ROOT = Path(__file__).resolve().parents[3]
TOKEN = "internal_token_for_local_test_1234567890"
AUTH = {"X-Trusted-Ceo-Internal-Token": TOKEN}
FINGERPRINT = "d" * 64


class ServiceAppTests(unittest.TestCase):
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
            client = TestClient(create_app(settings, application, orchestrator))

            self.assertEqual(401, client.get("/health").status_code)
            health = client.get("/health", headers=AUTH)
            self.assertEqual(200, health.status_code)
            self.assertEqual(
                {"status": "ok", "ai_ready": False, "model": "gpt-5.6"},
                health.json(),
            )
            self.assertEqual("no-store", health.headers["cache-control"])
            self.assertEqual("nosniff", health.headers["x-content-type-options"])
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
            client = TestClient(create_app(settings, application, orchestrator))
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
            self.assertEqual("terminal", stopped.json()["pending_action"])
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

            deleted = client.request(
                "DELETE",
                f"/v1/runs/{run_id}",
                headers=AUTH,
                json={
                    "expected_revision": 3,
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
                    "expected_revision": 3,
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
            client = TestClient(create_app(settings, application, orchestrator))
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

            for revision, key in (
                (2, "continue_missing_key_0001"),
                (3, "continue_missing_key_0002"),
            ):
                with self.subTest(revision=revision):
                    advanced = client.post(
                        f"/v1/runs/{run_id}/actions/continue",
                        headers=AUTH,
                        json={"expected_revision": revision, "idempotency_key": key},
                    )
                    self.assertEqual(200, advanced.status_code, advanced.text)
            unavailable = client.post(
                f"/v1/runs/{run_id}/actions/continue",
                headers=AUTH,
                json={
                    "expected_revision": 4,
                    "idempotency_key": "continue_missing_key_0003",
                },
            )
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
                    "expected_revision": 4,
                    "idempotency_key": "retry_missing_key_0001",
                },
            )
            self.assertEqual(200, retried.status_code, retried.text)
            self.assertEqual("provider_work", retried.json()["pending_action"])


if __name__ == "__main__":
    unittest.main()
