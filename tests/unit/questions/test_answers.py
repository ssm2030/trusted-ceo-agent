from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.questions.answers import (
    NOT_SUPPORTED_TEXT,
    validate_and_render_answer,
)
from trusted_ceo_agent.questions.index import QuestionIndex
from trusted_ceo_agent.questions.jobs import build_result_question_job
from tests.unit.questions.support import ROOT, finalized_files


class ResultAnswerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        _, files = finalized_files(Path(cls.temporary.name))
        cls.index = QuestionIndex.from_snapshot(files)
        cls.job = build_result_question_job(
            index=cls.index,
            question="관찰된 값과 근거를 알려 주세요.",
            scope_kind="issue",
            scope_instance_id="issue_main",
            privacy_classification="poc_deidentified",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def _supported(self) -> dict:
        value_ref = self.job["allowed_value_refs"][0]
        return {
            "draft_version": "1.0.0",
            "job_id": self.job["job_id"],
            "run_id": self.job["run_id"],
            "revision": self.job["revision"],
            "answer_blocks": [
                {
                    "block_id": "block_1",
                    "support_status": "supported",
                    "text_template": f"관찰된 값은 {{{{value:{value_ref}}}}}입니다.",
                    "value_refs": [value_ref],
                    "claim_refs": [self.job["allowed_claim_refs"][0]],
                    "evidence_link_ids": [
                        self.job["allowed_evidence_link_ids"][0]
                    ],
                    "source_refs": [self.job["allowed_source_refs"][0]],
                }
            ],
        }

    def test_supported_block_resolves_only_allowed_values(self) -> None:
        answer = validate_and_render_answer(self.job, self._supported(), self.index)

        display = self.job["value_table"][0]["display_text"]
        self.assertEqual(
            f"관찰된 값은 {display}입니다.",
            answer["answer_blocks"][0]["text"],
        )
        self.assertTrue(answer["validation"]["values_valid"])
        self.assertFalse(answer["validation"]["semantic_entailment_verified"])

    def test_numeric_literal_and_out_of_scope_reference_are_rejected(self) -> None:
        numeric = self._supported()
        numeric["answer_blocks"][0]["text_template"] = "관찰된 값은 12.4%입니다."
        with self.assertRaises(ContractError):
            validate_and_render_answer(self.job, numeric, self.index)

        unknown = self._supported()
        unknown["answer_blocks"][0]["evidence_link_ids"] = [
            "evidence_" + "f" * 24
        ]
        with self.assertRaises(ContractError):
            validate_and_render_answer(self.job, unknown, self.index)

    def test_not_supported_is_fixed_and_draft_is_never_returned(self) -> None:
        draft = {
            "draft_version": "1.0.0",
            "job_id": self.job["job_id"],
            "run_id": self.job["run_id"],
            "revision": self.job["revision"],
            "answer_blocks": [
                {
                    "block_id": "block_1",
                    "support_status": "not_supported",
                    "text_template": NOT_SUPPORTED_TEXT,
                    "value_refs": [],
                    "claim_refs": [],
                    "evidence_link_ids": [],
                    "source_refs": [],
                }
            ],
        }
        answer = validate_and_render_answer(self.job, draft, self.index)
        self.assertEqual(NOT_SUPPORTED_TEXT, answer["answer_blocks"][0]["text"])
        self.assertNotIn("text_template", str(answer))

        tampered = copy.deepcopy(draft)
        tampered["answer_blocks"][0]["text_template"] = "아마도 그렇습니다."
        with self.assertRaises(ContractError):
            validate_and_render_answer(self.job, tampered, self.index)


if __name__ == "__main__":
    unittest.main()
