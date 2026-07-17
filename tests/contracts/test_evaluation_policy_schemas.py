from __future__ import annotations

import copy
import unittest

from trusted_ceo_agent.contracts.schema_store import SchemaStore
from trusted_ceo_agent.errors import ContractError
from trusted_ceo_agent.evaluation.metrics import QUALITY_SCORE_METRICS
from trusted_ceo_agent.evaluation.non_inferiority import (
    build_concurrency_profile,
    build_non_inferiority_report,
    build_quality_policy,
)
from trusted_ceo_agent.evaluation.performance import build_performance_policy

from tests.unit.evaluation._fixtures import evaluation_cases, run_complete


class EvaluationPolicySchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = SchemaStore()
        cls.quality = build_quality_policy(
            policy_id="quality_policy_fixture",
            metric_margins={metric: "0" for metric in QUALITY_SCORE_METRICS},
        )
        cls.batch = run_complete()
        cls.report = build_non_inferiority_report(
            cls.batch["results"], cls.quality, candidate_profile_id="parallel_2"
        )
        cls.performance = build_performance_policy(
            results=cls.batch["results"],
            stage_timings=cls.batch["timings"],
            non_inferiority_reports=[cls.report],
            target_environment="target-mac-warm-local",
            approval=None,
        )

    def test_all_seven_evaluation_contracts_are_closed(self):
        samples = {
            "evaluation-case.schema.json": evaluation_cases()[0],
            "evaluation-result.schema.json": self.batch["results"][0],
            "quality-policy.schema.json": self.quality,
            "concurrency-profile.schema.json": build_concurrency_profile(
                "parallel_2", self.quality
            ),
            "performance-policy.schema.json": self.performance,
            "stage-timing.schema.json": self.batch["timings"][0],
            "non-inferiority-report.schema.json": self.report,
        }
        for schema_name, value in samples.items():
            with self.subTest(schema=schema_name):
                self.schemas.validate(schema_name, value)
                invalid = copy.deepcopy(value)
                invalid["hidden_reasoning"] = "forbidden"
                with self.assertRaises(ContractError):
                    self.schemas.validate(schema_name, invalid)


if __name__ == "__main__":
    unittest.main()
