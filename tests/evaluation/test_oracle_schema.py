import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ORACLES = ROOT / "tests" / "evaluation" / "oracles"
REQUIRED = {
    "scenario_id", "expected_fact_codes", "expected_signal_codes",
    "expected_issue_keys", "expected_primary_grades", "forbidden_claim_codes",
    "forbidden_professional_conclusions",
}


class OracleSchemaTests(unittest.TestCase):
    def test_all_four_oracles_are_strict_and_named(self) -> None:
        files = sorted(ORACLES.glob("*.json"))
        self.assertEqual(4, len(files))
        for path in files:
            value = json.loads(path.read_text("utf-8"))
            self.assertEqual(REQUIRED, set(value))
            self.assertEqual(path.stem, value["scenario_id"])


if __name__ == "__main__":
    unittest.main()

