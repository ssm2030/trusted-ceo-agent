from __future__ import annotations

import unittest

from trusted_ceo_agent.evaluation.runner import run_paired_evaluation

from tests.unit.evaluation._fixtures import evaluation_cases, execution


class AccountingProfileEquivalenceTests(unittest.TestCase):
    def test_profile_input_order_does_not_change_paired_artifacts(self):
        profiles = ("sequential", "parallel_2", "parallel_3", "parallel_4")
        first = run_paired_evaluation(
            evaluation_cases()[:1],
            repetitions=2,
            execute=execution,
            profiles=profiles,
        )
        second = run_paired_evaluation(
            list(reversed(evaluation_cases()[:1])),
            repetitions=2,
            execute=execution,
            profiles=tuple(reversed(profiles)),
        )
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()

