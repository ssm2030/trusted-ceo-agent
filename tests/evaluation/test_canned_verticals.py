import json
import unittest
from pathlib import Path

from trusted_ceo_agent.poc import run_scenario


ROOT = Path(__file__).resolve().parents[2]


class CannedScenarioTests(unittest.TestCase):
    def test_scenarios_match_semantic_oracles(self) -> None:
        oracle_root = ROOT / "tests" / "evaluation" / "oracles"
        fixture_root = ROOT / "tests" / "fixtures" / "evaluation"
        for oracle_path in sorted(oracle_root.glob("*.json")):
            with self.subTest(scenario=oracle_path.stem):
                oracle = json.loads(oracle_path.read_text("utf-8"))
                actual = run_scenario(fixture_root / oracle_path.stem)
                self.assertTrue(set(oracle["expected_fact_codes"]).issubset(actual["fact_codes"]))
                self.assertTrue(set(oracle["expected_signal_codes"]).issubset(actual["signal_codes"]))
                self.assertEqual(oracle["expected_issue_keys"], actual["issue_keys"])
                self.assertEqual(oracle["expected_primary_grades"], actual["primary_grades"])
                self.assertTrue(set(oracle["forbidden_claim_codes"]).isdisjoint(actual["claim_codes"]))
                self.assertTrue(
                    set(oracle["forbidden_professional_conclusions"]).isdisjoint(
                        actual["professional_conclusions"]
                    )
                )


if __name__ == "__main__":
    unittest.main()

