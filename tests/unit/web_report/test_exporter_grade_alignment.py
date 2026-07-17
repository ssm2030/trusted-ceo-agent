from __future__ import annotations

import unittest

from trusted_ceo_agent.canonical import canonical_bytes
from trusted_ceo_agent.errors import IntegrityError
from trusted_ceo_agent.web_report.exporter import _assert_grade_alignment


class ExporterGradeAlignmentTests(unittest.TestCase):
    def test_rejects_final_issue_that_disagrees_with_published_grade(self) -> None:
        result = {
            "issues": [
                {
                    "issue_id": "issue_margin",
                    "primary_grade": "Monitor",
                }
            ]
        }
        files = {
            "grading/records/issue_margin.json": canonical_bytes(
                {
                    "issue_id": "issue_margin",
                    "publication_status": "published",
                    "primary_grade": "Decision Required",
                }
            )
        }

        with self.assertRaisesRegex(IntegrityError, "Grade Record mismatch"):
            _assert_grade_alignment(result, files)


if __name__ == "__main__":
    unittest.main()
