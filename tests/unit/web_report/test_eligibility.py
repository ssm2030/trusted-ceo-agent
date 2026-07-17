from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trusted_ceo_agent.web_report.canonical import jcs_bytes, jcs_sha256
from trusted_ceo_agent.web_report.eligibility import (
    decide_unregistered_import,
    decide_viewer_eligibility,
)
from trusted_ceo_agent.web_report.exporter import (
    ExportedWebReport,
    export_web_report,
)
from tests.unit.web_report.test_exporter import ROOT, RUN_ID, _fixture


class WebReportEligibilityTests(unittest.TestCase):
    def _exported(self, root: Path):
        store, validation = _fixture(root)
        with patch(
            "trusted_ceo_agent.web_report.exporter.validate_revision",
            return_value=validation,
        ):
            exported = export_web_report(store, run_id=RUN_ID, revision=2)
        return store, exported

    def test_registered_tty_bundle_is_trusted(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            store, exported = self._exported(Path(directory))
            with patch(
                "trusted_ceo_agent.web_report.eligibility.export_web_report",
                return_value=exported,
            ):
                decision = decide_viewer_eligibility(
                    store,
                    expected_run_id=RUN_ID,
                    expected_revision=2,
                    bundle_payload=exported.payload,
                )

            self.assertTrue(decision["eligible"])
            self.assertEqual("trusted_final", decision["viewer_mode"])
            self.assertEqual("승인·검증된 실행본", decision["badge_label_ko"])

    def test_fixture_bundle_is_never_promoted_to_trusted(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            store, exported = self._exported(Path(directory))
            poc = copy.deepcopy(exported.bundle)
            receipt = poc["viewer_eligibility_receipt"]
            receipt["claimed_viewer_mode"] = "poc_fixture"
            receipt["final_approval_summary"]["input_method"] = "test_fixture"
            receipt["final_approval_summary"]["fixture_only"] = True
            poc["final_result"]["approvals"][0]["input_method"] = "test_fixture"
            poc["final_result"]["approvals"][0]["fixture_only"] = True
            poc["trust_view"]["approval_summary"][0]["input_method"] = "test_fixture"
            poc["trust_view"]["approval_summary"][0]["fixture_only"] = True
            poc["trust_view"]["limitations"] = ["fixture_only"]
            poc["trust_view"]["deidentification"].update(
                {
                    "poc_only": True,
                    "direct_identifiers_removed": True,
                    "notice_ko": "POC 시연 자료이며 실제 승인 실행본이 아닙니다.",
                }
            )
            poc["bundle_hash"] = jcs_sha256(
                poc,
                omit_root_field="bundle_hash",
            )
            payload = jcs_bytes(poc)
            recomputed = ExportedWebReport(
                bundle=poc,
                payload=payload,
                checks=exported.checks,
            )
            with patch(
                "trusted_ceo_agent.web_report.eligibility.export_web_report",
                return_value=recomputed,
            ):
                decision = decide_viewer_eligibility(
                    store,
                    expected_run_id=RUN_ID,
                    expected_revision=2,
                    bundle_payload=payload,
                )

            self.assertEqual("poc_fixture", decision["viewer_mode"])
            self.assertEqual(
                "검증된 POC 시연 실행본",
                decision["badge_label_ko"],
            )

    def test_schema_valid_rehashed_tamper_is_rejected_by_reexport(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            store, exported = self._exported(Path(directory))
            tampered = copy.deepcopy(exported.bundle)
            tampered["final_result"]["mission_summary"][
                "objective"
            ] = "변조된 제목"
            tampered["bundle_hash"] = jcs_sha256(
                tampered,
                omit_root_field="bundle_hash",
            )
            with patch(
                "trusted_ceo_agent.web_report.eligibility.export_web_report",
                return_value=exported,
            ):
                decision = decide_viewer_eligibility(
                    store,
                    expected_run_id=RUN_ID,
                    expected_revision=2,
                    bundle_payload=jcs_bytes(tampered),
                )

            self.assertFalse(decision["eligible"])
            self.assertEqual("BYTE_MISMATCH", decision["failure_code"])

    def test_independent_json_is_always_unverified(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            _, exported = self._exported(Path(directory))

            decision = decide_unregistered_import(exported.payload)

            self.assertTrue(decision["eligible"])
            self.assertEqual("unverified_import", decision["viewer_mode"])
            self.assertEqual("출처 미확인 묶음", decision["badge_label_ko"])
            self.assertEqual([], decision["completed_checks"])


if __name__ == "__main__":
    unittest.main()
