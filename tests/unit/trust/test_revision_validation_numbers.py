from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trusted_ceo_agent.trust.revision_validation import validate_revision
from tests.unit.web_report.test_converter import ROOT, _build_finalized_run


class RevisionValidationNumberTests(unittest.TestCase):
    def test_strict_json_integer_values_are_schema_compatible(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            store, _ = _build_finalized_run(Path(directory))

            result = validate_revision(store, 2)

            self.assertIn("evidence_core", result.checks)
            self.assertIn("grade_recomputation", result.checks)
            self.assertIn("final_package", result.checks)


if __name__ == "__main__":
    unittest.main()
