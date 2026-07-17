import unittest

from trusted_ceo_agent.reasoning.attempts import next_attempt_action


class AttemptPolicyTests(unittest.TestCase):
    def test_attempt_policy_distinguishes_required_optional_writer_and_data(self) -> None:
        self.assertEqual("retry", next_attempt_action("lens", 1, required=True, failure_kind="contract"))
        self.assertEqual("blocked", next_attempt_action("lens", 2, required=True, failure_kind="contract"))
        self.assertEqual("coverage_gap", next_attempt_action("lens", 2, required=False, failure_kind="contract"))
        self.assertEqual("fallback", next_attempt_action("writer", 2, required=True, failure_kind="contract"))
        self.assertEqual("not_assessable", next_attempt_action("lens", 1, required=True, failure_kind="data_insufficient"))


if __name__ == "__main__":
    unittest.main()
