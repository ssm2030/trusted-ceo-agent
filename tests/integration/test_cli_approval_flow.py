import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent import cli


ROOT = Path(__file__).resolve().parents[2]


def call(arguments: list[str]) -> tuple[int, dict]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = cli.main(arguments)
    return code, json.loads(output.getvalue())


class CliApprovalFlowTests(unittest.TestCase):
    def test_request_hashes_nonce_and_non_tty_approval_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            mission = root / "mission.json"
            source = root / "data.json"
            overlay = root / "overlay.json"
            mission.write_text('{"confirmed":false}', "utf-8")
            source.write_text('{}', "utf-8")
            overlay.write_text(json.dumps({"patch_operations": [{
                "op": "add", "path": "/mission_contract/business_question",
                "value": "중요 경영 문제를 진단합니다."
            }]}, ensure_ascii=False), "utf-8")
            artifacts = root / "artifacts"
            code, started = call(["start", "--artifact-root", str(artifacts), "--mission-contract", str(mission), "--input", str(source)])
            self.assertEqual(0, code)
            common = ["--artifact-root", str(artifacts), "--run-id", started["run_id"]]
            code, requested = call([
                "approval-request", *common, "--gate", "context", "--overlay", str(overlay),
                "--expected-revision", "1",
            ])
            self.assertEqual(2, code)
            nonce = requested["data"]["nonce"]
            request_id = requested["data"]["approval_request_id"]
            request_file = artifacts / started["run_id"] / "snapshots" / "r0002" / "approvals" / "requests" / f"{request_id}.json"
            self.assertNotIn(nonce, request_file.read_text("utf-8"))

            code, rejected = call([
                "approve-interactive", *common, "--request-id", request_id,
                "--expected-revision", "2",
            ])
            self.assertEqual(4, code)
            self.assertIn("TTY", rejected["message"])
            pointer = json.loads((artifacts / started["run_id"] / "state.json").read_text("utf-8"))
            self.assertEqual(2, pointer["revision"])


if __name__ == "__main__":
    unittest.main()
