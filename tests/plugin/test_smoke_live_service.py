from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "plugin" / "trusted-ceo-agent" / "scripts" / "smoke_live_service.py"
FIXTURE_ROOT = ROOT / "web" / "tests" / "fixtures"
REPORT_FIXTURE = ROOT / "contracts" / "web-report" / "v1" / "fixtures" / "valid-trusted.json"
RUN_ID = "run_20260717T000000Z_aaaaaaaaaaaaaaaa"


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("smoke_live_service", PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("smoke module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeSmokeClient:
    def __init__(self, *, ai_ready: bool = True) -> None:
        self.ai_ready = ai_ready
        self.deleted = False
        self.question_polls = 0

    def health(self):
        return {"status": "ok", "ai_ready": self.ai_ready, "model": "gpt-5.6"}

    def create_run(self):
        return self._snapshot(1, "context_confirmation_required", "human_response")

    def upload_file(self, run_id, revision, fixture):
        self._bound(run_id)
        self.assert_fixture(fixture)
        return self._snapshot(1, "context_confirmation_required", "human_response")

    def submit_hitl(self, run_id, snapshot):
        self._bound(run_id)
        return self._snapshot(2, "context_ready", "provider_work")

    def continue_run(self, run_id, revision):
        self._bound(run_id)
        if revision == 2:
            return self._snapshot(3, "finalized", "terminal")
        raise AssertionError("unexpected continuation")

    def retry_run(self, run_id, revision):
        raise AssertionError("retry was not expected")

    def resume_run(self, run_id, revision):
        raise AssertionError("resume was not expected")

    def get_report(self, run_id):
        self._bound(run_id)
        return json.loads(REPORT_FIXTURE.read_text("utf-8"))

    def start_question(self, run_id, revision):
        self._bound(run_id)
        self.question_polls = 0
        return self._question_snapshot("queued", revision)

    def get_question(self, run_id, request_id):
        self._bound(run_id)
        self.question_polls += 1
        return self._question_snapshot("completed", 3, answer={
            "answer_version": "1.0.0",
            "job_id": "questionjob_0123456789abcdef01234567",
            "run_id": RUN_ID,
            "revision": 3,
            "scope": {
                "scope_kind": "run",
                "scope_instance_id": "run",
                "start_refs": ["run"],
                "issue_id": None,
            },
            "validation": {
                "schema_valid": True,
                "references_valid": True,
                "values_valid": True,
                "semantic_entailment_verified": False,
                "label_ko": "스키마·참조 검증 통과",
            },
            "answer_blocks": [{
                "block_id": "block_1",
                "support_status": "not_supported",
                "text": "현재 실행본의 근거로는 확인할 수 없습니다",
                "resolved_values": [],
                "claim_refs": [],
                "evidence_link_ids": [],
                "source_refs": [],
            }],
        })

    def metrics(self):
        return {"input_token_count": 0, "output_token_count": 0}

    def delete_run(self, run_id, revision):
        self._bound(run_id)
        self.deleted = True

    @staticmethod
    def assert_fixture(fixture):
        if fixture.name != "company-diagnostic.json":
            raise AssertionError("unexpected fixture")

    @staticmethod
    def _bound(run_id):
        if run_id != RUN_ID:
            raise AssertionError("run binding changed")

    @staticmethod
    def _snapshot(revision, workflow_status, pending_action):
        allowed_actions = (
            ["approve"]
            if pending_action == "human_response"
            else ["continue"]
            if pending_action == "provider_work"
            else []
        )
        return {
            "provider_kind": "service",
            "display_badge": "실시간 AI 분석",
            "run_id": RUN_ID,
            "revision": revision,
            "workflow_status": workflow_status,
            "ui_phase": 7 if workflow_status == "finalized" else 1,
            "pending_action": pending_action,
            "allowed_actions": allowed_actions,
            "latest_event": workflow_status,
            "progress": 100 if workflow_status == "finalized" else 10,
            "result_ref": "result_smoke" if workflow_status == "finalized" else None,
            "hitl_card": ({
                "hitl_kind": "context_data",
                "request_id": "hitl_1",
                "base_revision": revision,
                "title": "합성 자료 확인",
                "summary": "승인된 합성 자료입니다.",
                "target_refs": [],
                "allowed_decisions": ["approve"],
                "editable_fields": [],
                "sections": [],
            } if pending_action == "human_response" else None),
            "error": None,
        }

    @staticmethod
    def _question_snapshot(state, revision, answer=None):
        return {
            "request_id": "questionrequest_0123456789abcdef01234567",
            "run_id": RUN_ID,
            "revision": revision,
            "generation": 1,
            "state": state,
            "scope_kind": "run",
            "scope_instance_id": "run",
            "answer": answer,
            "scope_suggestions": [],
            "error_code": None,
            "retryable": False,
        }


class AsyncFakeSmokeClient(FakeSmokeClient):
    def __init__(self) -> None:
        super().__init__()
        self.continue_calls = 0
        self.run_polls = 0

    def continue_run(self, run_id, revision):
        self._bound(run_id)
        self.continue_calls += 1
        if self.continue_calls > 1 or revision != 2:
            raise AssertionError("async provider work was submitted more than once")
        active = self._snapshot(2, "context_ready", "provider_work")
        active["allowed_actions"] = []
        return active

    def get_run(self, run_id):
        self._bound(run_id)
        self.run_polls += 1
        return self._snapshot(3, "finalized", "terminal")


class LiveServiceSmokeTests(unittest.TestCase):
    def test_script_entrypoint_does_not_shadow_the_package(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(PATH), "--help"],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("--artifact-root", completed.stdout)
    def test_fake_service_contract_and_redacted_summary(self) -> None:
        smoke = load_smoke_module()
        client = FakeSmokeClient()

        summary = smoke.execute_smoke(
            FIXTURE_ROOT,
            client,
            monotonic_values=iter((10.0, 12.5)),
            pause=lambda _seconds: None,
        )
        output = io.StringIO()
        smoke.write_summary(summary, output)

        self.assertTrue(client.deleted)
        self.assertEqual(1, client.question_polls)
        self.assertEqual(
            [
                "contract_valid=true",
                "stage_count=2",
                "elapsed_seconds=2.500",
                "input_token_count=0",
                "output_token_count=0",
                "final_validation=passed",
            ],
            output.getvalue().splitlines(),
        )
        self.assertNotIn(RUN_ID, output.getvalue())
        self.assertNotIn("company-diagnostic", output.getvalue())

    def test_async_provider_work_is_polled_without_duplicate_mutation(self) -> None:
        smoke = load_smoke_module()
        client = AsyncFakeSmokeClient()

        summary = smoke.execute_smoke(
            FIXTURE_ROOT,
            client,
            monotonic_values=iter((10.0, 12.5)),
            pause=lambda _seconds: None,
        )

        self.assertEqual(1, client.continue_calls)
        self.assertEqual(1, client.run_polls)
        self.assertEqual(2, summary["stage_count"])

    def test_http_metrics_are_relative_to_the_initial_health_check(self) -> None:
        smoke = load_smoke_module()
        client = smoke.HttpSmokeClient(
            "http://127.0.0.1:8765",
            "internal_token_for_local_test_1234567890",
        )
        client._input_tokens = 10
        client._output_tokens = 4
        client._request = lambda *_args, **_kwargs: {
            "status": "ok",
            "ai_ready": True,
            "model": "gpt-5.6",
        }

        client.health()
        client._input_tokens = 17
        client._output_tokens = 9

        self.assertEqual({
            "input_token_count": 7,
            "output_token_count": 5,
        }, client.metrics())
    def test_http_question_start_requires_accepted_status(self) -> None:
        smoke = load_smoke_module()
        client = smoke.HttpSmokeClient(
            "http://127.0.0.1:8765",
            "internal_token_for_local_test_1234567890",
        )
        captured = {}

        def capture(_method, _path, **kwargs):
            captured.update(kwargs)
            return FakeSmokeClient._question_snapshot("queued", 3)

        client._request = capture
        client.start_question(RUN_ID, 3)

        self.assertEqual(202, captured["expected_status"])
    def test_http_report_unwraps_the_backend_envelope(self) -> None:
        smoke = load_smoke_module()
        client = smoke.HttpSmokeClient(
            "http://127.0.0.1:8765",
            "internal_token_for_local_test_1234567890",
        )
        bundle = {"run": {"run_id": RUN_ID, "revision": 3}}
        client._request = lambda *_args, **_kwargs: {
            "bundle": bundle,
            "eligibility": {"trusted": True},
        }

        self.assertIs(bundle, client.get_report(RUN_ID))

    def test_http_run_status_uses_the_bound_authenticated_get_path(self) -> None:
        smoke = load_smoke_module()
        client = smoke.HttpSmokeClient(
            "http://127.0.0.1:8765",
            "internal_token_for_local_test_1234567890",
        )
        captured = {}

        def capture(method, path, **_kwargs):
            captured["method"] = method
            captured["path"] = path
            return FakeSmokeClient._snapshot(3, "finalized", "terminal")

        client._request = capture

        self.assertTrue(hasattr(client, "get_run"), "run status adapter is required")
        snapshot = client.get_run(RUN_ID)

        self.assertEqual("GET", captured["method"])
        self.assertEqual(f"/v1/runs/{RUN_ID}", captured["path"])
        self.assertEqual(3, snapshot["revision"])
    def test_http_hitl_payload_matches_the_strict_service_contract(self) -> None:
        smoke = load_smoke_module()
        client = smoke.HttpSmokeClient(
            "http://127.0.0.1:8765",
            "internal_token_for_local_test_1234567890",
        )
        captured = {}

        def capture(method, path, **kwargs):
            captured["method"] = method
            captured["path"] = path
            captured["body"] = json.loads(kwargs["body"].decode("utf-8"))
            return FakeSmokeClient._snapshot(2, "context_ready", "provider_work")

        client._request = capture
        snapshot = FakeSmokeClient._snapshot(
            1,
            "context_confirmation_required",
            "human_response",
        )

        client.submit_hitl(RUN_ID, snapshot)

        self.assertEqual("POST", captured["method"])
        self.assertEqual({
            "decision",
            "edits",
            "expected_revision",
            "idempotency_key",
            "rationale",
        }, set(captured["body"]))
    def test_missing_ai_readiness_fails_with_key_required_code(self) -> None:
        smoke = load_smoke_module()

        with self.assertRaisesRegex(smoke.SmokeFailure, "AI_API_KEY_REQUIRED"):
            smoke.execute_smoke(
                FIXTURE_ROOT,
                FakeSmokeClient(ai_ready=False),
                monotonic_values=iter((10.0, 10.1)),
                pause=lambda _seconds: None,
            )


if __name__ == "__main__":
    unittest.main()
