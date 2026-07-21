import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent import cli
from trusted_ceo_agent.cli_commands import dispatch
from trusted_ceo_agent.cli_context import store_for
from trusted_ceo_agent.cli_parser import build_parser as parser_builder
from tests.support import confirmed_mission


ROOT = Path(__file__).resolve().parents[2]


class CliCommandTests(unittest.TestCase):
    def test_cli_facade_uses_split_parser_context_and_dispatch_modules(self) -> None:
        self.assertIs(cli.build_parser, parser_builder)
        self.assertTrue(callable(store_for))
        self.assertTrue(callable(dispatch))

    def test_parser_exposes_the_approved_commands(self) -> None:
        parser = cli.build_parser()
        subparsers = next(action for action in parser._actions if action.dest == "command")
        self.assertEqual(
            {
                "preflight", "start", "scan", "prepare-jobs", "ingest-result",
                "reduce-stage", "approval-request", "approve-interactive", "decide-interactive",
                "run-components", "prepare-accounting-input",
                "prepare-finalization", "finalize", "status",
                "validate", "render", "export-web-report", "validate-web-report",
                "prepare-result-question", "validate-result-answer", "resume", "stop", "cancel",
                "pending-action", "preview-human-response", "submit-human-response",
            },
            set(subparsers.choices),
        )

    def test_start_prints_one_json_response_and_status_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = Path(directory)
            mission = workspace / "mission.json"
            source = workspace / "data.json"
            mission.write_text('{"confirmed":true,"objective":"diagnose"}', encoding="utf-8")
            source.write_text('{"revenue":"10"}', encoding="utf-8")
            artifact_root = workspace / "artifacts"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main([
                    "start", "--artifact-root", str(artifact_root),
                    "--mission-contract", str(mission), "--input", str(source),
                ])
            self.assertEqual(0, code)
            lines = stdout.getvalue().splitlines()
            self.assertEqual(1, len(lines))
            response = json.loads(lines[0])
            self.assertEqual("context_confirmation_required", response["state"])

            before = (artifact_root / response["run_id"] / "state.json").read_bytes()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main([
                    "status", "--artifact-root", str(artifact_root),
                    "--run-id", response["run_id"],
                ])
            self.assertEqual(0, code)
            self.assertEqual(before, (artifact_root / response["run_id"] / "state.json").read_bytes())

    def test_valid_nested_confirmation_is_required_and_hash_checked(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = Path(directory)
            mission = workspace / "mission.json"
            source = workspace / "data.json"
            source.write_text('{"revenue":"10"}', encoding="utf-8")

            valid = confirmed_mission()
            mission.write_text(json.dumps(valid), encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main([
                    "start", "--artifact-root", str(workspace / "valid-artifacts"),
                    "--mission-contract", str(mission), "--input", str(source),
                ])
            self.assertEqual(0, code)
            self.assertEqual("context_ready", json.loads(stdout.getvalue())["state"])

            valid["business_question"] = "Tampered after confirmation"
            mission.write_text(json.dumps(valid), encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main([
                    "start", "--artifact-root", str(workspace / "tampered-artifacts"),
                    "--mission-contract", str(mission), "--input", str(source),
                ])
            self.assertEqual(3, code)
            self.assertFalse(json.loads(stdout.getvalue())["ok"])

    def test_mutation_requires_expected_revision(self) -> None:
        parser = cli.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["scan", "--artifact-root", "x", "--run-id", "run_x"])


    def test_prepare_accounting_input_is_read_only_and_requires_its_contract(self) -> None:
        parser = cli.build_parser()
        arguments = [
            "prepare-accounting-input",
            "--artifact-root", "artifacts",
            "--run-id", "run_x",
            "--revision", "3",
            "--source-id", "source_" + "a" * 24,
            "--scope-ref", "scope_x",
            "--output", "accounting.json",
        ]

        parsed = parser.parse_args(arguments)
        self.assertEqual("prepare-accounting-input", parsed.command)
        self.assertFalse(hasattr(parsed, "expected_revision"))
        with self.assertRaises(SystemExit):
            parser.parse_args(arguments + ["--expected-revision", "3"])
        for option in ("--revision", "--source-id", "--scope-ref", "--output"):
            with self.subTest(option=option):
                index = arguments.index(option)
                with self.assertRaises(SystemExit):
                    parser.parse_args(arguments[:index] + arguments[index + 2 :])

if __name__ == "__main__":
    unittest.main()
