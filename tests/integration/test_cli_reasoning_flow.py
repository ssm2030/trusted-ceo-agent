import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent import cli
from tests.support import confirmed_mission


ROOT = Path(__file__).resolve().parents[2]


def call(arguments: list[str]) -> tuple[int, dict]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = cli.main(arguments)
    return code, json.loads(output.getvalue())


class CliReasoningFlowTests(unittest.TestCase):
    def test_lens_job_is_compiled_normalized_and_joined(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            mission = root / "mission.json"
            source = root / "data.json"
            mission.write_text(json.dumps(confirmed_mission()), "utf-8")
            source.write_text('[{"domain":"b2b_services"}]', "utf-8")
            artifacts = root / "artifacts"
            code, started = call(["start", "--artifact-root", str(artifacts), "--mission-contract", str(mission), "--input", str(source)])
            self.assertEqual(0, code, started)
            common = ["--artifact-root", str(artifacts), "--run-id", started["run_id"]]

            code, scanned = call(["scan", *common, "--expected-revision", "1"])
            self.assertEqual(0, code, scanned)
            code, prepared = call(["prepare-jobs", *common, "--stage", "lens", "--expected-revision", "2"])
            self.assertEqual(0, code)
            self.assertEqual(1, len(prepared["data"]["job_ids"]))

            draft = root / "draft.json"
            draft.write_text(json.dumps({
                "assessment_status": "not_assessable",
                "status_reason_codes": ["no_canonical_metric"],
                "observations": [],
                "business_meanings": [],
                "problem_candidates": [],
                "cause_hypotheses": [],
                "counter_hypotheses": [],
                "challenge_reviews": [],
                "verification_tests": [],
                "signal_dispositions": [],
                "uncertainties": [],
                "data_requests": [{"local_key": "request_1", "statement_template": "필수 원천 자료가 필요합니다."}],
                "human_questions": [],
                "expert_trigger_candidates": [],
                "limitations": [{"local_key": "limit_1", "statement_template": "현재 자료로 원인을 평가할 수 없습니다."}],
            }, ensure_ascii=False), "utf-8")
            revision = 3
            for job_id in prepared["data"]["job_ids"]:
                code, ingested = call([
                    "ingest-result", *common, "--job-id", job_id, "--draft", str(draft),
                    "--expected-revision", str(revision),
                ])
                self.assertEqual(0, code, ingested)
                self.assertIn("card_id", ingested["data"])
                revision += 1
            code, reduced = call([
                "reduce-stage", *common, "--stage", "lens", "--expected-revision", str(revision),
            ])
            self.assertEqual(0, code)
            self.assertEqual("lens_ready", reduced["state"])
            self.assertIn("join_result_id", reduced["data"])


if __name__ == "__main__":
    unittest.main()
