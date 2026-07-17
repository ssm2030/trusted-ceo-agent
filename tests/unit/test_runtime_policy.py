import unittest

from trusted_ceo_agent.runtime_policy import PARALLEL_LIMITS, TIME_BUDGET_SECONDS, validate_policy


class RuntimePolicyTests(unittest.TestCase):
    def test_join_and_post_join_reasoning_are_single_worker(self) -> None:
        self.assertEqual(3, PARALLEL_LIMITS["lens_jobs"])
        self.assertEqual(1, PARALLEL_LIMITS["integrated_reasoning"])
        self.assertEqual(1, PARALLEL_LIMITS["deep_integrator"])
        self.assertEqual(1, PARALLEL_LIMITS["output_writer"])

    def test_full_and_live_demo_limits_are_explicit(self) -> None:
        self.assertEqual(225, TIME_BUDGET_SECONDS["full_target"])
        self.assertEqual(300, TIME_BUDGET_SECONDS["full_hard_limit"])
        self.assertEqual(50, TIME_BUDGET_SECONDS["live_demo_target"])
        self.assertEqual(75, TIME_BUDGET_SECONDS["live_demo_hard_limit"])
        validate_policy()


if __name__ == "__main__":
    unittest.main()
