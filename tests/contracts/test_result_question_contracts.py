from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "contracts" / "web-report" / "v1"


def load_schema(name: str) -> dict[str, Any]:
    value = json.loads((CONTRACT_ROOT / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{name} must contain a JSON object")
    return value


def current_question_job() -> dict[str, Any]:
    return {
        "job_version": "1.0.0",
        "job_id": "job_01",
        "run_id": "run_20260717T010203Z_0123456789abcdef",
        "revision": 2,
        "question": "이 문제를 뒷받침하는 근거는 무엇인가요?",
        "response_locale": "ko-KR",
        "scope": {
            "scope_kind": "issue",
            "scope_instance_id": "issue_01",
            "start_refs": ["issue_01"],
            "issue_id": "issue_01",
        },
        "allowed_issue_refs": ["issue_01"],
        "allowed_claim_refs": ["claim_01"],
        "allowed_fact_refs": ["fact_01"],
        "allowed_signal_refs": [],
        "allowed_evidence_link_ids": ["evidence_01"],
        "allowed_source_refs": ["source_01"],
        "allowed_value_refs": ["value_01"],
        "forbidden_conclusions": [],
        "not_assessable_conditions": [],
        "deidentification": {
            "poc_only": False,
            "direct_identifiers_removed": True,
            "notice_ko": "질문 작업에는 비식별화된 근거만 포함됩니다.",
        },
        "context_caps": {
            "max_context_bytes": 1_048_576,
            "max_answer_blocks": 12,
            "max_block_characters": 800,
        },
        "excluded_summary": {
            "excluded": False,
            "reason_codes": [],
            "available_scope_instance_ids": [],
        },
        "output_schema_version": "1.0.0",
    }


def answer_draft_block(
    *,
    support_status: str,
    text_template: str,
    claim_refs: list[str],
    evidence_link_ids: list[str],
    source_refs: list[str],
) -> dict[str, Any]:
    return {
        "block_id": "block_01",
        "support_status": support_status,
        "text_template": text_template,
        "value_refs": [],
        "claim_refs": claim_refs,
        "evidence_link_ids": evidence_link_ids,
        "source_refs": source_refs,
    }


def answer_draft(block: dict[str, Any]) -> dict[str, Any]:
    return {
        "draft_version": "1.0.0",
        "job_id": "job_01",
        "run_id": "run_20260717T010203Z_0123456789abcdef",
        "revision": 2,
        "answer_blocks": [block],
    }


class ResultQuestionContractTests(unittest.TestCase):
    def test_question_job_rejects_missing_execution_context(self) -> None:
        schema = load_schema("result-question-job.schema.json")
        job = current_question_job()

        self.assertFalse(
            Draft202012Validator(schema).is_valid(job),
            "question jobs must require their hash, bounded context, value table, "
            "privacy policy, and actual/excluded cap accounting",
        )

    def test_supported_block_requires_claim_and_evidence(self) -> None:
        schema = load_schema("result-answer-draft.schema.json")
        unsupported_supported_block = answer_draft_block(
            support_status="supported",
            text_template="근거가 있다고 주장하지만 참조가 없습니다.",
            claim_refs=[],
            evidence_link_ids=[],
            source_refs=[],
        )

        self.assertFalse(
            Draft202012Validator(schema).is_valid(
                answer_draft(unsupported_supported_block)
            ),
            "supported blocks must include at least one claim and evidence link",
        )

    def test_not_supported_block_has_fixed_text_and_no_references(self) -> None:
        schema = load_schema("result-answer-draft.schema.json")
        unsafe_not_supported_block = answer_draft_block(
            support_status="not_supported",
            text_template="모델이 임의로 만든 판단불가 문구",
            claim_refs=["claim_01"],
            evidence_link_ids=["evidence_01"],
            source_refs=["source_01"],
        )

        self.assertFalse(
            Draft202012Validator(schema).is_valid(
                answer_draft(unsafe_not_supported_block)
            ),
            "not_supported blocks must use the fixed Korean text and empty refs",
        )

    def test_canonical_answer_requires_closed_validation_object(self) -> None:
        schema = load_schema("result-answer.schema.json")
        required = set(schema["required"])
        properties = schema["properties"]

        self.assertIn("validation", required)
        validation_property = properties["validation"]
        validation_ref = validation_property.get("$ref")
        validation = (
            schema["$defs"][validation_ref.rsplit("/", 1)[-1]]
            if validation_ref
            else validation_property
        )
        self.assertIs(False, validation["additionalProperties"])
        self.assertEqual(
            {
                "schema_valid",
                "references_valid",
                "values_valid",
                "semantic_entailment_verified",
                "label_ko",
            },
            set(validation["required"]),
        )


if __name__ == "__main__":
    unittest.main()
