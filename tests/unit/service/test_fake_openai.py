from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.service.testing.fake_openai import (
    KeylessFakeReasoningGateway,
)


ROOT = Path(__file__).resolve().parents[3]
QUESTION_FIXTURE = (
    ROOT
    / "contracts"
    / "web-report"
    / "v1"
    / "fixtures"
    / "questions"
    / "valid-result-question-job.json"
)


class KeylessFakeOpenAITests(unittest.TestCase):
    def test_question_draft_is_dynamic_bound_and_schema_valid(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            gateway = KeylessFakeReasoningGateway(Path(directory))
            job = json.loads(QUESTION_FIXTURE.read_text("utf-8"))

            draft = gateway.execute_question(job)

            SchemaStore().validate(
                "result-answer-draft.schema.json",
                draft,
            )
            self.assertEqual(job["job_id"], draft["job_id"])
            self.assertEqual(job["run_id"], draft["run_id"])
            self.assertEqual(job["revision"], draft["revision"])
            block = draft["answer_blocks"][0]
            self.assertIn(
                block["value_refs"][0],
                job["allowed_value_refs"],
            )
            self.assertIn(
                block["evidence_link_ids"][0],
                job["allowed_evidence_link_ids"],
            )

    def test_question_without_allowlisted_claim_uses_schema_valid_fallback(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            gateway = KeylessFakeReasoningGateway(Path(directory))
            job = json.loads(QUESTION_FIXTURE.read_text("utf-8"))
            job["allowed_claim_refs"] = []

            draft = gateway.execute_question(job)

            SchemaStore().validate(
                "result-answer-draft.schema.json",
                draft,
            )
            block = draft["answer_blocks"][0]
            self.assertEqual("not_supported", block["support_status"])
            self.assertEqual(
                "현재 실행본의 근거로는 확인할 수 없습니다",
                block["text_template"],
            )
    def test_production_main_does_not_import_the_test_fake(self) -> None:
        source = (
            ROOT
            / "plugin"
            / "trusted-ceo-agent"
            / "trusted_ceo_agent"
            / "service"
            / "main.py"
        ).read_text("utf-8")
        self.assertNotIn("service.testing", source)
        self.assertNotIn("KeylessFakeReasoningGateway", source)

    def test_e2e_main_uses_the_safe_workspace_report_directory(self) -> None:
        source = (
            ROOT
            / "plugin"
            / "trusted-ceo-agent"
            / "trusted_ceo_agent"
            / "service"
            / "testing_main.py"
        ).read_text("utf-8")
        self.assertIn("KeylessFakeReasoningGateway", source)
        self.assertNotIn("report_root=settings.service_root", source)


if __name__ == "__main__":
    unittest.main()