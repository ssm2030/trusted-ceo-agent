import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent import cli
from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.trust.artifact_store import ArtifactStore


ROOT = Path(__file__).resolve().parents[2]


def call(arguments: list[str]) -> tuple[int, dict]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = cli.main(arguments)
    return code, json.loads(output.getvalue())


def create_run(
    artifact_root: Path,
    *,
    run_id: str,
    state: str,
    job: dict | None = None,
    extra_files: dict[str, bytes] | None = None,
) -> None:
    store = ArtifactStore(artifact_root)
    store.create_run(run_id)
    files = {
        "workflow/state.json": canonical_bytes({
            "run_id": run_id,
            "revision": 1,
            "state": state,
            "resume_state": None,
            "blocker": None,
            "approvals": [],
        }),
    }
    if job is not None:
        files[f"tasks/{job['job_id']}/job.json"] = canonical_bytes(job)
    files.update(extra_files or {})
    store.publish(0, files)


def snapshot(artifact_root: Path, run_id: str, revision: int) -> Path:
    return artifact_root / run_id / "snapshots" / f"r{revision:04d}"


class CliReasoningRetryPolicyTests(unittest.TestCase):
    def test_schema_mapper_uses_canonical_fallback_after_two_persisted_failures(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            artifacts = root / "artifacts"
            run_id = "run_schema_retry"
            job = {"job_id": "job_schema", "stage": "schema_mapping"}
            proposal = {"mappings": []}
            create_run(
                artifacts,
                run_id=run_id,
                state="schema_mapping_job_ready",
                job=job,
                extra_files={
                    "intake/canonical-mapping-proposal.json": canonical_bytes(proposal),
                },
            )
            invalid = root / "invalid.json"
            invalid.write_text("{", encoding="utf-8")
            common = ["--artifact-root", str(artifacts), "--run-id", run_id]

            code, first = call([
                "ingest-result", *common, "--job-id", job["job_id"],
                "--draft", str(invalid), "--expected-revision", "1",
            ])
            self.assertEqual(3, code)
            self.assertFalse(first["ok"])
            self.assertEqual("retry", first["data"]["attempt_action"])
            self.assertEqual(1, len(first["data"]["validation_errors"]))
            first_snapshot = snapshot(artifacts, run_id, 2)
            self.assertEqual(
                b"{",
                (first_snapshot / "tasks" / job["job_id"] / "attempts" / "attempt-1.draft").read_bytes(),
            )
            first_record = json.loads(
                (first_snapshot / "tasks" / job["job_id"] / "attempts" / "attempt-1.json").read_text("utf-8")
            )
            self.assertFalse(first_record["valid"])
            self.assertEqual("invalid_json", first_record["failure_kind"])
            self.assertEqual(1, len(first_record["validation_errors"]))

            code, second = call([
                "ingest-result", *common, "--job-id", job["job_id"],
                "--draft", str(invalid), "--expected-revision", "2",
            ])
            self.assertEqual(0, code)
            self.assertTrue(second["ok"])
            self.assertEqual("deterministic_mapping", second["data"]["attempt_action"])
            fallback_snapshot = snapshot(artifacts, run_id, 3)
            self.assertEqual(
                canonical_bytes(proposal),
                (fallback_snapshot / "tasks" / job["job_id"] / "draft.json").read_bytes(),
            )
            validation = json.loads(
                (fallback_snapshot / "tasks" / job["job_id"] / "validation.json").read_text("utf-8")
            )
            self.assertTrue(validation["valid"])
            self.assertEqual("deterministic_fallback", validation["source"])

            code, reduced = call([
                "reduce-stage", *common, "--stage", "schema_mapping",
                "--expected-revision", "3",
            ])
            self.assertEqual(0, code)
            self.assertEqual("mapping_proposal_ready", reduced["state"])
            self.assertEqual(
                canonical_bytes(proposal),
                (snapshot(artifacts, run_id, 4) / "reasoning" / "schema-mapping-proposal.json").read_bytes(),
            )

    def test_writer_uses_empty_override_fallback_without_changing_structured_output(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            artifacts = root / "artifacts"
            run_id = "run_writer_retry"
            job = {
                "job_id": "job_writer",
                "stage": "writer",
                "structured_output_ref": "final/structured-output.json",
                "allowed_claim_ids": ["issue_1"],
            }
            create_run(
                artifacts,
                run_id=run_id,
                state="finalization_jobs_ready",
                job=job,
            )
            invalid = root / "invalid.json"
            invalid.write_text("[]", encoding="utf-8")
            common = ["--artifact-root", str(artifacts), "--run-id", run_id]

            self.assertEqual(3, call([
                "ingest-result", *common, "--job-id", job["job_id"],
                "--draft", str(invalid), "--expected-revision", "1",
            ])[0])
            code, fallback = call([
                "ingest-result", *common, "--job-id", job["job_id"],
                "--draft", str(invalid), "--expected-revision", "2",
            ])
            self.assertEqual(0, code)
            self.assertEqual("fallback", fallback["data"]["attempt_action"])
            writer = json.loads(
                (snapshot(artifacts, run_id, 3) / "tasks" / job["job_id"] / "writer.json").read_text("utf-8")
            )
            self.assertEqual("deterministic_template_fallback", writer["materialized_by"])
            self.assertEqual([], writer["payload"]["claim_templates"])
            self.assertEqual([], writer["payload"]["expert_packet_templates"])
            self.assertEqual([], writer["payload"]["ceo_brief_section_order"])

            code, reduced = call([
                "reduce-stage", *common, "--stage", "writer", "--expected-revision", "3",
            ])
            self.assertEqual(0, code)
            self.assertEqual("writer_ready", reduced["state"])
            self.assertEqual("deterministic_fallback", reduced["data"]["reduction_source"])
            result = json.loads(
                (snapshot(artifacts, run_id, 4) / "reasoning" / "writer-result.json").read_text("utf-8")
            )
            self.assertEqual("deterministic_template_fallback", result["materialized_by"])

    def test_schema_reducer_rejects_a_draft_without_accepted_validation(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            artifacts = root / "artifacts"
            run_id = "run_unvalidated_schema"
            job = {"job_id": "job_schema", "stage": "schema_mapping"}
            proposal = {"mappings": []}
            create_run(
                artifacts,
                run_id=run_id,
                state="schema_mapping_job_ready",
                job=job,
                extra_files={
                    "intake/canonical-mapping-proposal.json": canonical_bytes(proposal),
                    f"tasks/{job['job_id']}/draft.json": canonical_bytes(proposal),
                    f"tasks/{job['job_id']}/validation.json": canonical_bytes({
                        "job_id": job["job_id"],
                        "stage": "schema_mapping",
                        "attempt": 1,
                        "valid": False,
                        "action": "retry",
                    }),
                },
            )
            code, result = call([
                "reduce-stage", "--artifact-root", str(artifacts), "--run-id", run_id,
                "--stage", "schema_mapping", "--expected-revision", "1",
            ])
            self.assertEqual(3, code)
            self.assertIn("validated", result["message"])
            pointer = json.loads((artifacts / run_id / "state.json").read_text("utf-8"))
            self.assertEqual(1, pointer["revision"])

    def test_required_reasoning_stages_block_after_second_invalid_attempt(self) -> None:
        cases = (
            ("lens", "lens_jobs_ready"),
            ("integrated", "lens_ready"),
            ("deep_dive", "deep_dive_jobs_ready"),
        )
        for stage, initial_state in cases:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory(dir=ROOT) as directory:
                root = Path(directory)
                artifacts = root / "artifacts"
                run_id = f"run_{stage}_retry"
                job = {"job_id": f"job_{stage}", "stage": stage}
                create_run(artifacts, run_id=run_id, state=initial_state, job=job)
                invalid = root / "invalid.json"
                invalid.write_text("{", encoding="utf-8")
                common = ["--artifact-root", str(artifacts), "--run-id", run_id]

                self.assertEqual(3, call([
                    "ingest-result", *common, "--job-id", job["job_id"],
                    "--draft", str(invalid), "--expected-revision", "1",
                ])[0])
                code, failed = call([
                    "ingest-result", *common, "--job-id", job["job_id"],
                    "--draft", str(invalid), "--expected-revision", "2",
                ])
                self.assertEqual(3, code)
                self.assertFalse(failed["ok"])
                self.assertEqual("blocked", failed["state"])
                self.assertEqual("blocked", json.loads(
                    (snapshot(artifacts, run_id, 3) / "workflow" / "state.json").read_text("utf-8")
                )["state"])
                self.assertFalse(any(
                    path.name in {"card.json", "integrated.json", "deep-dive.json"}
                    for path in (snapshot(artifacts, run_id, 3) / "tasks" / job["job_id"]).rglob("*.json")
                ))

    def test_prepare_jobs_checks_non_lens_state_before_pack_compilation(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            artifacts = root / "artifacts"
            run_id = "run_wrong_state"
            create_run(artifacts, run_id=run_id, state="context_ready")
            code, result = call([
                "prepare-jobs", "--artifact-root", str(artifacts), "--run-id", run_id,
                "--stage", "writer", "--expected-revision", "1",
            ])
            self.assertEqual(3, code)
            self.assertIn("not allowed from context_ready", result["message"])
            pointer = json.loads((artifacts / run_id / "state.json").read_text("utf-8"))
            self.assertEqual(1, pointer["revision"])


if __name__ == "__main__":
    unittest.main()
