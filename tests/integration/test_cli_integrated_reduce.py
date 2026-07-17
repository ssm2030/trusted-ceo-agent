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


class CliIntegratedReduceTests(unittest.TestCase):
    def test_validated_integrated_draft_is_materialized_after_join(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            mission = root / "mission.json"
            source = root / "data.json"
            artifacts = root / "artifacts"
            mission.write_text(json.dumps(confirmed_mission()), "utf-8")
            source.write_text('[{"domain":"b2b_services"}]', "utf-8")
            code, started = call(["start", "--artifact-root", str(artifacts), "--mission-contract", str(mission), "--input", str(source)])
            self.assertEqual(0, code)
            common = ["--artifact-root", str(artifacts), "--run-id", started["run_id"]]
            scan_code, scanned = call(["scan", *common, "--expected-revision", "1"])
            self.assertEqual(0, scan_code, scanned)
            prepared = call(["prepare-jobs", *common, "--stage", "lens", "--expected-revision", "2"])[1]
            lens_draft = root / "lens.json"
            lens_draft.write_text(json.dumps({
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
                "data_requests": [{"local_key": "request_1", "statement_template": "원천 자료가 필요합니다."}],
                "human_questions": [],
                "expert_trigger_candidates": [],
                "limitations": [{"local_key": "limit_1", "statement_template": "현재 자료로 판단할 수 없습니다."}],
            }, ensure_ascii=False), "utf-8")
            revision = 3
            for job_id in prepared["data"]["job_ids"]:
                ingest_code, ingested = call(["ingest-result", *common, "--job-id", job_id, "--draft", str(lens_draft), "--expected-revision", str(revision)])
                self.assertEqual(0, ingest_code, ingested)
                revision += 1
            self.assertEqual(0, call(["reduce-stage", *common, "--stage", "lens", "--expected-revision", str(revision)])[0])
            revision += 1
            code, integrated_jobs = call(["prepare-jobs", *common, "--stage", "integrated", "--expected-revision", str(revision)])
            self.assertEqual(0, code)
            revision += 1
            job_id = integrated_jobs["data"]["job_ids"][0]
            snapshot = artifacts / started["run_id"] / "snapshots" / f"r{revision:04d}"
            job = json.loads((snapshot / "tasks" / job_id / "job.json").read_text("utf-8"))
            joined = json.loads((snapshot / "reasoning" / "join-result.json").read_text("utf-8"))
            integrated_draft = root / "integrated.json"
            integrated_draft.write_text(json.dumps({
                "join_manifest_ref": job["join_manifest_ref"],
                "card_refs": joined["card_refs"],
                "issue_clusters": [], "integrated_issues": [],
                "causal_relation_hypotheses": [], "cross_issue_conflicts": [],
                "blind_spots": [], "response_type_candidates": [],
                "expert_review_candidates": [],
            }), "utf-8")
            self.assertEqual(0, call(["ingest-result", *common, "--job-id", job_id, "--draft", str(integrated_draft), "--expected-revision", str(revision)])[0])
            revision += 1
            code, reduced = call(["reduce-stage", *common, "--stage", "integrated", "--expected-revision", str(revision)])
            self.assertEqual(0, code)
            self.assertEqual("integrated_draft", reduced["state"])
            final_snapshot = artifacts / started["run_id"] / "snapshots" / f"r{revision + 1:04d}"
            self.assertTrue((final_snapshot / "reasoning" / "integrated-assessment.json").is_file())


if __name__ == "__main__":
    unittest.main()
