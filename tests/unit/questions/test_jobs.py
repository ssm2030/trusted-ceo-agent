from __future__ import annotations

import tempfile
import unittest
import unicodedata
from pathlib import Path

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.questions.index import QuestionIndex
from trusted_ceo_agent.questions.jobs import build_result_question_job
from tests.unit.questions.support import ROOT, finalized_files


class ResultQuestionJobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        _, files = finalized_files(Path(cls.temporary.name))
        cls.index = QuestionIndex.from_snapshot(files)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def _build(self, question: str) -> dict:
        return build_result_question_job(
            index=self.index,
            question=question,
            scope_kind="issue",
            scope_instance_id="issue_main",
            privacy_classification="poc_deidentified",
        )

    def test_job_is_deterministic_and_bound_to_run_revision(self) -> None:
        left = self._build("이 문제의 근거는 무엇입니까?")
        right = self._build("이 문제의 근거는 무엇입니까?")

        self.assertEqual(canonical_bytes(left), canonical_bytes(right))
        self.assertEqual(self.index.run_id, left["run_id"])
        self.assertEqual(self.index.revision, left["revision"])
        self.assertEqual(sorted(left["allowed_fact_refs"]), left["allowed_fact_refs"])

    def test_question_is_nfc_normalized_and_bounded(self) -> None:
        decomposed = unicodedata.normalize("NFD", "근거는 무엇입니까?")
        self.assertEqual(
            self._build("근거는 무엇입니까?")["job_id"],
            self._build(decomposed)["job_id"],
        )
        with self.assertRaisesRegex(ContractError, "2000"):
            self._build("가" * 2001)

    def test_question_text_cannot_expand_the_allowlist(self) -> None:
        job = self._build("fact_ffffffffffffffffffffffff의 값은?")
        self.assertNotIn(
            "fact_ffffffffffffffffffffffff",
            job["allowed_fact_refs"],
        )


if __name__ == "__main__":
    unittest.main()
