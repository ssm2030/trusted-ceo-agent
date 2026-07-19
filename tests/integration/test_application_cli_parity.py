from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trusted_ceo_agent import cli
from trusted_ceo_agent.application.models import RunRequest
from trusted_ceo_agent.application.run_application import TrustedCeoApplication


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


if __name__ == "__main__":
    unittest.main()
