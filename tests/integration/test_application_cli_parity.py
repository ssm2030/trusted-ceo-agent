from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trusted_ceo_agent import cli
from trusted_ceo_agent.application.models import MutationRequest, RunRequest
from trusted_ceo_agent.application.run_application import TrustedCeoApplication

from tests.support import confirmed_mission, mission_body


ROOT = Path(__file__).resolve().parents[2]


def _call_cli(argv: list[str]) -> tuple[int, dict]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = cli.main(argv)
    return code, json.loads(output.getvalue())


class ApplicationCliParityTests(unittest.TestCase):
    def test_start_and_read_only_commands_match_public_application(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = Path(directory)
            mission = workspace / "mission.json"
            source = workspace / "data.json"
            mission.write_text('{"confirmed":false,"objective":"diagnose"}', encoding="utf-8")
            source.write_text('{"revenue":"10"}', encoding="utf-8")
            artifact_root = workspace / "artifacts"

            cli_code, cli_started = _call_cli([
                "start",
                "--artifact-root", str(artifact_root),
                "--mission-contract", str(mission),
                "--input", str(source),
            ])
            application = TrustedCeoApplication(artifact_root)
            app_status = application.status(RunRequest(run_id=cli_started["run_id"]))
            cli_status_code, cli_status = _call_cli([
                "status",
                "--artifact-root", str(artifact_root),
                "--run-id", cli_started["run_id"],
            ])

            self.assertEqual(0, cli_code)
            self.assertEqual(app_status.code, cli_status_code)
            self.assertEqual(app_status.state, cli_status["state"])
            self.assertEqual(app_status.data, cli_status["data"])

            app_pending = application.pending_action(RunRequest(run_id=cli_started["run_id"]))
            cli_pending_code, cli_pending = _call_cli([
                "pending-action",
                "--artifact-root", str(artifact_root),
                "--run-id", cli_started["run_id"],
            ])
            self.assertEqual(app_pending.code, cli_pending_code)
            self.assertEqual(app_pending.state, cli_pending["state"])
            self.assertEqual(app_pending.data, cli_pending["data"])

    def test_cli_start_delegates_to_public_application(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = Path(directory)
            mission = workspace / "mission.json"
            source = workspace / "data.json"
            mission.write_text('{"confirmed":false,"objective":"diagnose"}', encoding="utf-8")
            source.write_text('{"revenue":"10"}', encoding="utf-8")

            original = TrustedCeoApplication.create_run
            calls: list[dict] = []

            def recording_create(instance, request):
                calls.append({"request": request})
                return original(instance, request)

            with patch.object(
                TrustedCeoApplication,
                "create_run",
                autospec=True,
                side_effect=recording_create,
            ):
                code, payload = _call_cli([
                    "start",
                    "--artifact-root", str(workspace / "artifacts"),
                    "--mission-contract", str(mission),
                    "--input", str(source),
                ])

            self.assertEqual(0, code, payload)
            self.assertEqual(1, len(calls))
            self.assertIsNone(calls[0]["request"].run_id)

    def test_export_invalid_json_preserves_cli_error_message(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = Path(directory)
            mission = workspace / "mission.json"
            source = workspace / "data.json"
            invalid_manifest = workspace / "manifest.json"
            mission.write_text('{"confirmed":false,"objective":"diagnose"}', encoding="utf-8")
            source.write_text('{"revenue":"10"}', encoding="utf-8")
            invalid_manifest.write_text("{", encoding="utf-8")
            artifact_root = workspace / "artifacts"
            _, started = _call_cli([
                "start",
                "--artifact-root", str(artifact_root),
                "--mission-contract", str(mission),
                "--input", str(source),
            ])

            code, payload = _call_cli([
                "export-web-report",
                "--artifact-root", str(artifact_root),
                "--run-id", started["run_id"],
                "--revision", "1",
                "--input-manifest", str(invalid_manifest),
                "--output", str(workspace / "report.json"),
            ])

            self.assertEqual(3, code)
            self.assertEqual("web report input manifest is invalid JSON", payload["message"])

    def test_scan_mutation_matches_cli_and_rejects_unknown_parameters(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = Path(directory)
            mission = workspace / "mission.json"
            source = workspace / "data.json"
            mission.write_text(json.dumps(confirmed_mission()), encoding="utf-8")
            source.write_text('{"revenue":"10"}', encoding="utf-8")
            app_root = workspace / "app-artifacts"
            cli_root = workspace / "cli-artifacts"
            _, app_started = _call_cli([
                "start", "--artifact-root", str(app_root),
                "--mission-contract", str(mission), "--input", str(source),
            ])
            _, cli_started = _call_cli([
                "start", "--artifact-root", str(cli_root),
                "--mission-contract", str(mission), "--input", str(source),
            ])

            application = TrustedCeoApplication(app_root)
            app_result = application.mutate(MutationRequest(
                artifact_root=app_root,
                run_id=app_started["run_id"],
                expected_revision=1,
                command="scan",
                parameters={},
            ))
            original_mutate = TrustedCeoApplication.mutate
            mutation_calls: list[MutationRequest] = []

            def recording_mutate(instance, request):
                mutation_calls.append(request)
                return original_mutate(instance, request)

            with patch.object(
                TrustedCeoApplication,
                "mutate",
                autospec=True,
                side_effect=recording_mutate,
            ):
                cli_code, cli_result = _call_cli([
                    "scan", "--artifact-root", str(cli_root),
                    "--run-id", cli_started["run_id"], "--expected-revision", "1",
                ])

            self.assertEqual(app_result.code, cli_code)
            self.assertEqual(app_result.state, cli_result["state"])
            self.assertEqual(app_result.data, cli_result["data"])
            self.assertEqual(1, len(mutation_calls))
            self.assertEqual("scan", mutation_calls[0].command)

            pointer = (app_root / app_started["run_id"] / "state.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "parameter"):
                application.mutate(MutationRequest(
                    artifact_root=app_root,
                    run_id=app_started["run_id"],
                    expected_revision=app_result.revision or 0,
                    command="scan",
                    parameters={"unexpected": True},
                ))
            self.assertEqual(pointer, (app_root / app_started["run_id"] / "state.json").read_bytes())

    def test_web_context_approval_records_browser_provenance(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = Path(directory)
            mission = workspace / "mission.json"
            source = workspace / "data.json"
            mission.write_text(json.dumps(mission_body()), encoding="utf-8")
            source.write_text("{}", encoding="utf-8")
            artifact_root = workspace / "artifacts"
            _, started = _call_cli([
                "start", "--artifact-root", str(artifact_root),
                "--mission-contract", str(mission), "--input", str(source),
            ])
            application = TrustedCeoApplication(artifact_root)
            requested = application.mutate(MutationRequest(
                artifact_root=artifact_root,
                run_id=started["run_id"],
                expected_revision=1,
                command="approval-request",
                parameters={
                    "gate": "context",
                    "overlay_document": {"patch_operations": []},
                },
            ))

            approved = application.mutate(MutationRequest(
                artifact_root=artifact_root,
                run_id=started["run_id"],
                expected_revision=2,
                command="approve-web",
                parameters={
                    "request_id": requested.data["approval_request_id"],
                    "actor_id": "owner-web-1",
                    "actor_role": "business_owner",
                    "nonce": requested.data["nonce"],
                    "rationale": "브라우저에서 계약 내용을 확인하고 승인합니다.",
                    "browser_session_fingerprint": "c" * 64,
                    "response_hash": "d" * 64,
                },
            ))

            self.assertEqual("context_ready", approved.state)
            record_path = (
                artifact_root / started["run_id"] / "snapshots" / "r0003"
                / "approvals" / "records" / f"{approved.data['approval_id']}.json"
            )
            record = json.loads(record_path.read_text("utf-8"))
            self.assertEqual("web_hitl", record["input_method"])
            self.assertEqual("c" * 64, record["browser_session_fingerprint"])

    def test_required_mutation_values_reject_null_or_empty_without_commit(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = Path(directory)
            mission = workspace / "mission.json"
            source = workspace / "data.json"
            mission.write_text(json.dumps(confirmed_mission()), encoding="utf-8")
            source.write_text("{}", encoding="utf-8")
            artifact_root = workspace / "artifacts"
            _, started = _call_cli([
                "start", "--artifact-root", str(artifact_root),
                "--mission-contract", str(mission), "--input", str(source),
            ])
            application = TrustedCeoApplication(artifact_root)
            pointer_path = artifact_root / started["run_id"] / "state.json"
            original_pointer = pointer_path.read_bytes()
            invalid_requests = (
                ("reduce-stage", {"stage": None}, "stage"),
                (
                    "run-components",
                    {
                        "scope_ref": None,
                        "accounting_input": None,
                        "professional_input": None,
                    },
                    "scope_ref",
                ),
                (
                    "ingest-result",
                    {"job_id": "", "draft_document": {}},
                    "job_id",
                ),
                (
                    "approval-request",
                    {"gate": None, "overlay_document": {"patch_operations": []}},
                    "gate",
                ),
            )

            for command, parameters, field in invalid_requests:
                with self.subTest(command=command, field=field):
                    with self.assertRaisesRegex(ValueError, field):
                        application.mutate(MutationRequest(
                            artifact_root=artifact_root,
                            run_id=started["run_id"],
                            expected_revision=1,
                            command=command,
                            parameters=parameters,
                        ))
                    self.assertEqual(original_pointer, pointer_path.read_bytes())

    def test_web_context_rejection_stops_the_run(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = Path(directory)
            mission = workspace / "mission.json"
            source = workspace / "data.json"
            mission.write_text(json.dumps(mission_body()), encoding="utf-8")
            source.write_text("{}", encoding="utf-8")
            artifact_root = workspace / "artifacts"
            _, started = _call_cli([
                "start", "--artifact-root", str(artifact_root),
                "--mission-contract", str(mission), "--input", str(source),
            ])
            application = TrustedCeoApplication(artifact_root)
            requested = application.mutate(MutationRequest(
                artifact_root=artifact_root,
                run_id=started["run_id"],
                expected_revision=1,
                command="approval-request",
                parameters={
                    "gate": "context",
                    "overlay_document": {"patch_operations": []},
                },
            ))

            rejected = application.mutate(MutationRequest(
                artifact_root=artifact_root,
                run_id=started["run_id"],
                expected_revision=2,
                command="decide-web",
                parameters={
                    "request_id": requested.data["approval_request_id"],
                    "decision": "reject",
                    "actor_id": "owner-web-1",
                    "actor_role": "business_owner",
                    "nonce": requested.data["nonce"],
                    "rationale": "현재 조건으로는 분석을 진행하지 않습니다.",
                    "browser_session_fingerprint": "e" * 64,
                    "response_hash": "f" * 64,
                    "change_scope": None,
                },
            ))

            self.assertEqual("stopped_by_human", rejected.state)
            self.assertEqual("reject", rejected.data["decision"])


if __name__ == "__main__":
    unittest.main()
