from __future__ import annotations

import json
import unittest
from pathlib import Path

from trusted_ceo_agent.web_report.contracts import (
    MAX_BUNDLE_BYTES,
    WebReportContractError,
    load_bundle_bytes,
    validate_bundle_document,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "contracts" / "web-report" / "v1" / "fixtures"


class WebReportContractSemanticTests(unittest.TestCase):
    def test_three_viewer_modes_are_valid(self) -> None:
        expected_modes = {
            "valid-trusted.json": "trusted_final",
            "valid-poc.json": "poc_fixture",
            "valid-unverified-import.json": "unverified_import",
        }
        for name, expected_mode in expected_modes.items():
            with self.subTest(fixture=name):
                document = load_bundle_bytes((FIXTURES / name).read_bytes())
                self.assertEqual(
                    expected_mode,
                    document["viewer_eligibility_receipt"]["claimed_viewer_mode"],
                )
                validate_bundle_document(document)

    def test_wrong_hash_and_dangling_reference_are_rejected_separately(self) -> None:
        with self.assertRaisesRegex(WebReportContractError, "bundle hash"):
            load_bundle_bytes((FIXTURES / "invalid-hash.json").read_bytes())
        with self.assertRaisesRegex(
            WebReportContractError,
            "unknown Evidence Link",
        ):
            load_bundle_bytes((FIXTURES / "invalid-reference.json").read_bytes())

    def test_size_is_rejected_before_json_parse(self) -> None:
        with self.assertRaisesRegex(WebReportContractError, "52_428_800"):
            load_bundle_bytes(b" " * (MAX_BUNDLE_BYTES + 1))

    def test_oversize_descriptor_synthesizes_exact_boundary_failure(self) -> None:
        descriptor = json.loads(
            (FIXTURES / "oversize.json").read_text(encoding="utf-8")
        )
        self.assertEqual("generated_oversize", descriptor["fixture_kind"])
        self.assertEqual(MAX_BUNDLE_BYTES + 1, descriptor["target_bytes"])
        with self.assertRaisesRegex(WebReportContractError, "52_428_800"):
            load_bundle_bytes(b" " * descriptor["target_bytes"])


if __name__ == "__main__":
    unittest.main()
