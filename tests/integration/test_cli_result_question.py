from __future__ import annotations

import contextlib
import json
import tempfile
import unittest
from pathlib import Path

from tests.integration.test_cli_finalization_flow import call
from tests.unit.web_report.test_converter import (
    ROOT,
    RUN_ID,
    _build_finalized_run,
)


class CliResultQuestionTests(unittest.TestCase):
    def test_prepare_and_validate_are_read_only_and_hide_the_draft(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            store, _ = _build_finalized_run(root)
            artifacts = root / "artifacts"
            question_file = root / "question.txt"
            question_file.write_text(
                "관찰된 값과 그 근거를 알려 주세요.",
                encoding="utf-8",
            )
            state_before = (store.run_dir / "state.json").read_bytes()
            snapshot = store.verify_revision(2)
            manifest_before = (snapshot / "snapshot-manifest.json").read_bytes()
            common = [
                "--artifact-root",
                str(artifacts),
                "--run-id",
                RUN_ID,
                "--revision",
                "2",
            ]

            code, prepared = call(
                [
                    "prepare-result-question",
                    *common,
                    "--question-file",
                    str(question_file),
                    "--scope-kind",
                    "issue",
                    "--scope-instance-id",
                    "issue_main",
                    "--privacy-classification",
                    "poc_deidentified",
                ]
            )
            self.assertEqual(0, code, prepared)
            job = prepared["data"]["job"]
            self.assertEqual("finalized", prepared["state"])

            relative_dir = root / "questions"
            relative_dir.mkdir()
            relative_question = relative_dir / "question.txt"
            relative_question.write_text(
                "관찰된 값과 그 근거를 알려 주세요.",
                encoding="utf-8",
            )
            with contextlib.chdir(root):
                relative_code, relative_prepared = call([
                    "prepare-result-question",
                    *common,
                    "--question-file", "questions/question.txt",
                    "--scope-kind", "issue",
                    "--scope-instance-id", "issue_main",
                    "--privacy-classification", "poc_deidentified",
                ])
            self.assertEqual(0, relative_code, relative_prepared)
            self.assertEqual(job, relative_prepared["data"]["job"])

            job_file = root / "question-job.json"
            job_file.write_text(
                json.dumps(job, ensure_ascii=False),
                encoding="utf-8",
            )
            value_ref = job["allowed_value_refs"][0]
            draft_file = root / "answer-draft.json"
            draft_file.write_text(
                json.dumps(
                    {
                        "draft_version": "1.0.0",
                        "job_id": job["job_id"],
                        "run_id": job["run_id"],
                        "revision": job["revision"],
                        "answer_blocks": [
                            {
                                "block_id": "block_1",
                                "support_status": "supported",
                                "text_template": (
                                    "관찰된 값은 "
                                    f"{{{{value:{value_ref}}}}}입니다."
                                ),
                                "value_refs": [value_ref],
                                "claim_refs": [job["allowed_claim_refs"][0]],
                                "evidence_link_ids": [
                                    job["allowed_evidence_link_ids"][0]
                                ],
                                "source_refs": [
                                    job["allowed_source_refs"][0]
                                ],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            code, validated = call(
                [
                    "validate-result-answer",
                    *common,
                    "--job",
                    str(job_file),
                    "--draft",
                    str(draft_file),
                ]
            )
            self.assertEqual(0, code, validated)
            answer = validated["data"]["answer"]
            self.assertNotIn("text_template", json.dumps(answer, ensure_ascii=False))
            self.assertEqual("finalized", validated["state"])
            self.assertEqual(
                state_before,
                (store.run_dir / "state.json").read_bytes(),
            )
            self.assertEqual(
                manifest_before,
                (snapshot / "snapshot-manifest.json").read_bytes(),
            )

            job_file.write_text("[]", encoding="utf-8")
            code, rejected = call([
                "validate-result-answer",
                *common,
                "--job", str(job_file),
                "--draft", str(draft_file),
            ])
            self.assertEqual(3, code)
            self.assertEqual(
                "result question Job and answer draft must be objects",
                rejected["message"],
            )


if __name__ == "__main__":
    unittest.main()
