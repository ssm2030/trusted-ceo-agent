from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any, Iterator

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "contracts" / "web-report" / "v1"
GENERATION_ROOT = CONTRACT_ROOT / "web-report-contracts.schema.json"
GENERATED_TYPES = CONTRACT_ROOT / "generated" / "types.ts"

PUBLIC_SCHEMAS = {
    "web-report-bundle.schema.json": "WebReportBundleV1",
    "viewer-eligibility-decision.schema.json": "ViewerEligibilityDecisionV1",
    "presentation-manifest.schema.json": "PresentationManifestV1",
    "result-question-job.schema.json": "ResultQuestionJobV1",
    "result-answer-draft.schema.json": "ResultAnswerDraftV1",
    "result-answer.schema.json": "ResultAnswerV1",
}

REQUIRED_TYPES = (
    "WebReportBundleV1",
    "ViewerEligibilityDecisionV1",
    "PresentationManifestV1",
    "SourcePreviewV1",
    "ExpertPacketViewItemV1",
    "RevisionViewV1",
    "ResultQuestionJobV1",
    "ResultAnswerDraftV1",
    "ResultAnswerV1",
)


def walk_dicts(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def is_object_schema(value: dict[str, Any]) -> bool:
    schema_type = value.get("type")
    return schema_type == "object" or (
        isinstance(schema_type, list) and "object" in schema_type
    )


def local_document_refs(value: Any) -> Iterator[str]:
    for item in walk_dicts(value):
        ref = item.get("$ref")
        if isinstance(ref, str) and not ref.startswith("#"):
            yield ref.split("#", 1)[0]


class WebReportContractSchemaTests(unittest.TestCase):
    def load_schema(self, name: str) -> dict[str, Any]:
        value = json.loads((CONTRACT_ROOT / name).read_text(encoding="utf-8"))
        self.assertIsInstance(value, dict)
        return value

    def test_public_schemas_are_draft_2020_12_and_closed(self) -> None:
        for name, title in PUBLIC_SCHEMAS.items():
            with self.subTest(schema=name):
                schema = self.load_schema(name)
                self.assertEqual(
                    "https://json-schema.org/draft/2020-12/schema",
                    schema["$schema"],
                )
                self.assertEqual(name, schema["$id"])
                self.assertEqual(title, schema["title"])
                Draft202012Validator.check_schema(schema)
                for object_schema in filter(is_object_schema, walk_dicts(schema)):
                    self.assertIs(
                        False,
                        object_schema.get("additionalProperties"),
                        object_schema,
                    )
                    properties = set(object_schema.get("properties", {}))
                    self.assertEqual(
                        properties,
                        set(object_schema.get("required", [])),
                        object_schema,
                    )

    def test_generation_root_references_exactly_the_six_public_schemas(self) -> None:
        schema = self.load_schema(GENERATION_ROOT.name)
        Draft202012Validator.check_schema(schema)
        self.assertEqual("WebReportContractsV1", schema["title"])
        self.assertEqual(set(PUBLIC_SCHEMAS), set(local_document_refs(schema)))
        self.assertEqual(
            set(schema["properties"]),
            set(schema["required"]),
        )
        self.assertIs(False, schema["additionalProperties"])

    def test_every_non_fragment_reference_stays_in_contract_directory(self) -> None:
        known = set(PUBLIC_SCHEMAS) | {GENERATION_ROOT.name}
        for path in sorted(CONTRACT_ROOT.glob("*.schema.json")):
            schema = self.load_schema(path.name)
            for document in local_document_refs(schema):
                with self.subTest(schema=path.name, ref=document):
                    self.assertIn(document, known)
                    self.assertNotIn("/", document)
                    self.assertNotIn("\\", document)

    def test_generated_types_export_required_contract_names_without_any(self) -> None:
        text = GENERATED_TYPES.read_text(encoding="utf-8")
        for name in REQUIRED_TYPES:
            with self.subTest(type_name=name):
                self.assertRegex(
                    text,
                    rf"export (?:interface|type) {re.escape(name)}\b",
                )
        self.assertNotRegex(text, r"\bany\b")
        self.assertNotIn("[k: string]: unknown", text)


if __name__ == "__main__":
    unittest.main()
